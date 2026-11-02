"""Historical local audio intents survive updates; active calls remain protected."""
import importlib.util
import json
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


if __name__ == '__main__': unittest.main()
