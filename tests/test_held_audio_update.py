"""Historical local audio intents survive updates; active calls remain protected."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from portable import audio_update_guard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'portable'))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class HeldAudioUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.operations = []
        for letter in 'ab':
            identity = 'call_' + letter * 32
            folder = self.root / 'Haike_video/.backlot/audio-center-internal/local/operations' / identity
            folder.mkdir(parents=True)
            value = {'id': identity, 'status': 'submission_unknown', 'signature': letter * 64,
                'quote_id': 'iq_' + letter * 32, 'maximum': 100,
                'request': {'kind': 'tts', 'credential_identity': 'synthetic', 'text': 'synthetic'},
                'provider_state': {'bailian_chunks': {'0': {'status': 'submitting'}}}}
            (folder / 'operation.json').write_text(json.dumps(value), encoding='utf-8')
            (folder / '.lock').write_bytes(b'0')
            (folder / 'chunk-0000.wav').write_bytes(b'synthetic-completed-segment')
            self.operations.append(folder)
        self.guard = load('held_audio_guard', ROOT / 'portable/audio_update_guard.py')
        if os.name == 'nt':
            import shutil
            assert self.root.parent == Path(tempfile.gettempdir()).resolve()
            self.addCleanup(shutil.rmtree, self.guard.native_path(self.root))
        self.offline = load('held_audio_offline', ROOT / 'portable/legacy_upgrade.py')
        self.online = load('held_audio_online', ROOT / 'scripts/update-from-github.py')

    def test_two_old_unknown_operations_do_not_block_offline_upgrade(self):
        before = {str(p): p.read_bytes() for f in self.operations for p in f.iterdir()}
        with patch.object(self.offline.subprocess, 'run', return_value=type('R', (), {'returncode': 0, 'stdout': '[]'})()):
            self.offline.stopped(self.root)
        self.assertEqual(before, {str(p): p.read_bytes() for f in self.operations for p in f.iterdir()})

    def test_online_and_snapshot_preserve_original_intents_and_segments(self):
        expected = self.guard.require_idle(self.root)
        self.assertEqual(len(expected['held']), 2)
        self.online.idle(self.root, audio_guard=self.guard)
        backup = self.root / 'backup'; backup.mkdir()
        proof = self.guard.snapshot(self.root, backup, expected)
        self.assertEqual(proof['held'], expected['held'])
        self.guard.verify_preserved(self.root, expected)
        for item in proof['held']:
            for name, digest in item['files'].items():
                copy = backup / proof['directory'] / item['path'] / name
                self.assertEqual(self.guard.file_digest(copy), digest)
        (self.operations[0] / 'chunk-0000.wav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '发生变化'):
            self.guard.verify_preserved(self.root, expected)

    def test_running_states_missing_journal_or_lock_and_corruption_still_block(self):
        path = self.operations[0] / 'operation.json'; original = path.read_bytes()
        for status in ['submitting', 'processing', None]:
            value = json.loads(original); value['status'] = status
            path.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '音色操作'): self.guard.require_idle(self.root)
        path.write_bytes(original)
        (self.operations[0] / '.lock').unlink()
        with self.assertRaisesRegex(ValueError, '音色操作'): self.guard.require_idle(self.root)
        (self.operations[0] / '.lock').write_bytes(b'0')
        path.write_bytes(b'{invalid')
        with self.assertRaises(ValueError): self.guard.require_idle(self.root)

    def test_unknown_operation_with_live_os_lock_blocks(self):
        sys.path.insert(0, str(ROOT / 'Haike_video'))
        from lib.bailian_speech import operation_lock
        with operation_lock(self.operations[0]):
            with self.assertRaisesRegex(ValueError, '音色操作'): self.guard.require_idle(self.root)

    def test_online_preflight_reports_queue_and_audio_blockers_together(self):
        from unittest.mock import Mock
        queue = Mock()
        queue.require_idle.side_effect = ValueError('制作队列有正在执行的任务')
        value = json.loads((self.operations[0] / 'operation.json').read_bytes())
        value['status'] = 'processing'
        (self.operations[0] / 'operation.json').write_text(json.dumps(value), encoding='utf-8')
        blockers = self.online.idle_blockers(self.root, queue_guard=queue, audio_guard=self.guard)
        self.assertEqual(len(blockers), 2)
        self.assertIn('制作队列', blockers[0]); self.assertIn('音色操作', blockers[1])

    @unittest.skipUnless(os.name == 'nt', 'Windows MAX_PATH regression')
    def test_audio_backup_supports_nested_install_with_long_paths_disabled(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            if winreg.QueryValueEx(key, 'LongPathsEnabled')[0]:
                self.skipTest('real reproduction requires LongPathsEnabled=0')
        from shutil import copytree
        nested = self.root / 'haike_videoflow 2' / 'Haike_videoflow' / 'Haike_videoflow'
        nested.mkdir(parents=True)
        copytree(self.root / 'Haike_video', nested / 'Haike_video')
        backup = nested / '.local/release-updates/1027-to-1.2-20261102T063841089730Z'
        backup.mkdir(parents=True)
        expected = self.guard.require_idle(nested)
        proof = self.guard.snapshot(nested, backup, expected)
        self.assertEqual(proof['held'], expected['held'])
        self.guard.verify_preserved(nested, expected)


if __name__ == '__main__': unittest.main()
