"""Untrusted package paths/config are rejected before changing an installation."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeploymentBoundaryTests(unittest.TestCase):
    def test_source_checkout_does_not_require_a_private_profile(self):
        module = load('install-private-profile')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(module.subprocess, 'run', side_effect=AssertionError('must not spawn')):
                self.assertEqual(module.install(Path(directory), Path('unused')), {'profile_present': False, 'paid_calls': 0})

    def test_profile_tampering_or_escape_is_rejected_before_import(self):
        module = load('install-private-profile')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / 'private-profile'
            profile.mkdir()
            doc = profile / 'config.private.md'
            doc.write_bytes(b'configuration')
            row = {'path': 'config.private.md', 'size': doc.stat().st_size, 'sha256': hashlib.sha256(doc.read_bytes()).hexdigest()}
            manifest = profile / 'PROFILE-MANIFEST.json'
            manifest.write_text(json.dumps({'schema': 'haike.private-colleague-profile/1', 'files': [row]}))
            self.assertEqual(module.profile_files(root), profile)
            doc.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                module.profile_files(root)
            row['path'] = '../outside.md'
            manifest.write_text(json.dumps({'schema': 'haike.private-colleague-profile/1', 'files': [row]}))
            with self.assertRaises(ValueError):
                module.profile_files(root)

    def test_native_archive_names_cannot_escape_destination(self):
        module = load('mac-deploy')
        with tempfile.TemporaryDirectory() as directory:
            for bad in ('../outside', '/etc/passwd', 'C:/secrets', 'folder\\escape'):
                with self.subTest(path=bad), self.assertRaises(ValueError):
                    module.contained(Path(directory), bad)
            self.assertEqual(module.contained(Path(directory), 'python/bin/python3'), Path(directory) / 'python/bin/python3')


if __name__ == '__main__':
    unittest.main()
