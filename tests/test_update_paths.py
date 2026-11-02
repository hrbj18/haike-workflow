"""Real Windows paths > MAX_PATH, without changing machine policy or project IDs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from portable import app_update as core
from tests import test_app_update as fixtures

ROOT = Path(__file__).resolve().parents[1]


class UpdatePathTests(unittest.TestCase):
    def test_native_adapter_does_not_change_persisted_logical_identity(self):
        path = Path(tempfile.gettempdir()).resolve() / '海客 installation' / ('x' * 160) / 'file.py'
        self.assertEqual(core.logical_path(core.native_path(path)), path)
        if os.name == 'nt': self.assertTrue(str(core.native_path(path)).startswith('\\\\?\\'))
        spec = importlib.util.spec_from_file_location('online_path_test', ROOT / 'scripts/update-from-github.py')
        online = importlib.util.module_from_spec(spec); spec.loader.exec_module(online)
        self.assertEqual(online.native_path(path), core.native_path(path))
        self.assertEqual(online.logical_path(online.native_path(path)), path)

    @unittest.skipUnless(os.name == 'nt', 'Windows filesystem integration')
    def test_long_program_backup_manual_and_automatic_rollback(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name).resolve()
        assert folder.parent == Path(tempfile.gettempdir()).resolve()
        self.addCleanup(shutil.rmtree, core.native_path(folder))
        fixture = fixtures.AppUpdateTests()
        root, bundle, original, plan = fixture.fixture(folder)
        name = 'Haike_video/backlot/' + 'component-' + 'x' * 62 + '/' + 'nested-' + 'y' * 65 + '/module.py'
        before, after = b'# preserved long program', b'# replacement long program'
        fixture.write(root, name, before); fixture.write(bundle / 'payload', name, after)
        manifest = json.loads((root / 'PACKAGE-MANIFEST.json').read_bytes())
        manifest['files'].append({'path': name, 'size': len(before), 'sha256': hashlib.sha256(before).hexdigest(), 'mutable': False})
        (root / 'PACKAGE-MANIFEST.json').write_bytes(core.json_bytes(manifest))
        plan['files'].append({'path': name, 'size': len(after), 'sha256': hashlib.sha256(after).hexdigest(),
                             'before_sha256': hashlib.sha256(before).hexdigest()})
        (bundle / 'UPDATE-MANIFEST.json').write_bytes(core.json_bytes(plan))
        result = core.apply_update(bundle, root, health_check=lambda *_: True)
        backup = Path(result['backup']); copy = backup / 'files' / name
        self.assertGreater(len(str(copy)), 259)
        self.assertEqual(core.native_path(copy).read_bytes(), before)
        self.assertEqual(core.native_path(root / name).read_bytes(), after)
        receipt = core._read(backup / 'receipt.json')
        self.assertTrue(receipt['backup_complete']); self.assertTrue(receipt['program_changes_started'])
        self.assertEqual(receipt['installation'], str(root))
        self.assertNotIn('\\\\?\\', receipt['installation'])
        core.rollback(root, backup)
        self.assertEqual(core.native_path(root / name).read_bytes(), before)
        with self.assertRaisesRegex(core.UpdateError, '已回退'):
            core.apply_update(bundle, root, health_check=lambda *_: False)
        self.assertEqual(core.native_path(root / name).read_bytes(), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows bootstrap extraction')
    def test_single_file_bootstrap_extracts_long_payload_paths(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        self.addCleanup(shutil.rmtree, core.native_path(root))
        spec = importlib.util.spec_from_file_location('long_bootstrap', ROOT / 'scripts/update-from-github.py')
        online = importlib.util.module_from_spec(spec); spec.loader.exec_module(online)
        archive = root / 'program.zip'
        name = 'payload/Haike_video/backlot/' + 'x' * 100 + '/' + 'y' * 70 + '/test.py'
        with zipfile.ZipFile(archive, 'w') as zipped:
            for item, data in [('UPGRADE.json', b'{}'), ('legacy_upgrade.py', b'# stub'), (name, b'# long payload')]:
                zipped.writestr('haike-update-1.2/' + item, data)
        bundle = online.extract_program(root, archive)
        self.assertGreater(len(str(bundle / name)), 259)
        self.assertEqual(core.native_path(bundle / name).read_bytes(), b'# long payload')
