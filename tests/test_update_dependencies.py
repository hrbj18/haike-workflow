"""Dependency repair stages verified files without altering an installation."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('update_dependency_fixture', ROOT / 'portable/update_dependencies.py')
deps = importlib.util.module_from_spec(spec); spec.loader.exec_module(deps)


class Response(io.BytesIO):
    def geturl(self):
        return 'https://registry.npmmirror.com/verified.zip'


class DependencyUpdateTests(unittest.TestCase):
    def test_complete_dependencies_need_no_download_or_staging(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(deps, 'download') as network:
            root = Path(directory)
            self.assertIsNone(deps.prepare(root, root, {'missing': []}))
            network.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_missing_node_is_prepared_from_checksum_pinned_domestic_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bundle = root / 'bundle'; bundle.mkdir()
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as zipped:
                zipped.writestr('node-v22/node.exe', b'MZnew-node')
            data = stream.getvalue()
            config = {'node': {'prefix': 'node-v22/', 'sha256': hashlib.sha256(data).hexdigest(),
                              'urls': ['https://registry.npmmirror.com/node.zip']}}
            (bundle / 'dependency-downloads.json').write_text(json.dumps(config))
            with patch.object(deps.urllib.request, 'urlopen', return_value=Response(data)) as network:
                plan = deps.prepare(root, bundle, {'missing': ['node']})
            network.assert_called_once()
            self.assertFalse((root / 'runtime/node/node.exe').exists())
            rows = deps.rows(root, plan)
            self.assertEqual(rows[0]['path'], 'runtime/node/node.exe')
            self.assertEqual(Path(rows[0]['prepared']).read_bytes(), b'MZnew-node')
            Path(rows[0]['prepared']).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, '已损坏'):
                deps.rows(root, plan)

    def test_bad_mirror_bytes_are_rejected_without_touching_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); p = root / 'runtime/node/node.exe'; p.parent.mkdir(parents=True); p.write_bytes(b'old')
            config = {'sha256': 'a' * 64, 'urls': ['https://registry.npmmirror.com/node.zip']}
            with patch.object(deps.urllib.request, 'urlopen', return_value=Response(b'<html>error</html>')):
                with self.assertRaisesRegex(ValueError, '原程序'):
                    deps.download(root, 'node', config)
            self.assertEqual(p.read_bytes(), b'old')
            self.assertFalse(list(root.rglob('*.part')))

    def test_traversal_and_user_data_are_not_dependency_destinations(self):
        for name in ['Haike_video/config.yaml', 'creatorhub/data/account.sqlite3',
                     'Haike_video/.venv/../../projects/old.mp4', 'runtime/node/../outside.exe']:
            with self.subTest(path=name), tempfile.TemporaryDirectory() as directory:
                self.assertFalse(deps.allowed(name))
                if '..' in name:
                    with self.assertRaises(ValueError):
                        deps.safe(Path(directory), name)
        self.assertTrue(deps.allowed('Haike_video/.venv/Lib/site-packages/jsonschema/__init__.py'))


if __name__ == '__main__':
    unittest.main()
