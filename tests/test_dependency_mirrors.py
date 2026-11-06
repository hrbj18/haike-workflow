"""Check the actual npm child process, without installing dependencies."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from portable import dependency_sources as mirrors

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_build', ROOT / 'scripts/build-studio.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class MirrorTests(unittest.TestCase):
    def test_legacy_offline_and_global_sources_do_not_defeat_the_mirrors(self):
        original = dict(PIP_INDEX_URL='https://pypi.org/simple', PIP_EXTRA_INDEX_URL='https://extra.example.test/simple',
                        UV_OFFLINE='1', PIP_NO_INDEX='1', NPM_CONFIG_OFFLINE='true',
                        NPM_CONFIG_REGISTRY='https://registry.npmjs.org')
        values = mirrors.environment(original)
        self.assertEqual(values['PIP_INDEX_URL'], mirrors.PIP_INDEX)
        self.assertEqual(values['UV_DEFAULT_INDEX'], mirrors.PIP_INDEX)
        self.assertEqual(values['npm_config_registry'], mirrors.NPM_REGISTRY)
        for key in ('PIP_EXTRA_INDEX_URL', 'UV_OFFLINE', 'PIP_NO_INDEX', 'NPM_CONFIG_OFFLINE', 'NPM_CONFIG_REGISTRY'):
            self.assertNotIn(key, values)
        self.assertEqual(original['UV_OFFLINE'], '1')

    def test_explicit_public_overrides_and_credential_rejection(self):
        env = mirrors.environment({'HAIKE_PIP_INDEX_URL': 'https://repo.huaweicloud.com/repository/pypi/simple',
                                   'HAIKE_NPM_REGISTRY': 'https://registry.npmmirror.com/'})
        self.assertEqual(env['PIP_INDEX_URL'], 'https://repo.huaweicloud.com/repository/pypi/simple')
        self.assertEqual(env['npm_config_registry'], mirrors.NPM_REGISTRY)
        for url in ('http://mirror.example.test/simple', 'https://name:secret@mirror.example.test/simple'):
            with self.assertRaises(ValueError):
                mirrors.environment({'HAIKE_PIP_INDEX_URL': url})

    def test_studio_install_defaults_to_domestic_registry_without_global_config_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'prototypes/haike-avatar-generator/dist/client'
            output.mkdir(parents=True)
            (output / 'index.html').write_text('test', encoding='utf-8')
            with patch.object(build, 'ROOT', root), \
                 patch.object(build.shutil, 'which', return_value='npm'), \
                 patch.object(build.subprocess, 'run') as run, \
                 patch.dict(os.environ, {}, clear=True):
                build.main()
                install = run.call_args_list[0]
                self.assertEqual(install.kwargs['env'].get('npm_config_registry'),
                                 'https://registry.npmmirror.com')
                self.assertNotIn('npm_config_registry', os.environ)


if __name__ == '__main__':
    unittest.main()
