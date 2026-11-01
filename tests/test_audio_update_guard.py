"""Authenticated old-intent recovery uses GET only and preserves unknown work."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from portable import audio_update_guard as guard


class AudioUpdateGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.base = 'http://127.0.0.1:17894/v2'
        self.account = hashlib.sha256(json.dumps([self.base, 'synthetic-account'], ensure_ascii=False).encode()).hexdigest()
        self.operation = 'call_' + 'a' * 32
        private = self.root / 'Haike_video/.backlot'
        self.config = private / 'haike-api/client-config.json'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps({'base_url': self.base, 'api_key': 'fake-local-test-key'}), encoding='utf-8')
        self.database = private / 'studio.sqlite3'
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('CREATE TABLE studio_audio_operations(account TEXT,id TEXT,quote_id TEXT,attempts INTEGER,outcome TEXT)')
            db.execute('INSERT INTO studio_audio_operations VALUES(?,?,?,?,NULL)',
                       (self.account, self.operation, 'synthetic-quote', 1)); db.commit()
        self.journal = private / f'audio-center/{self.account}/intents/{self.operation}.json'
        self.journal.parent.mkdir(parents=True)
        self.journal.write_text(json.dumps({'idempotency_key': self.operation, 'job_id': 'gj_original',
            'body': {'call_intent_id': self.operation, 'quote_id': 'synthetic-quote'}}), encoding='utf-8')
        self.calls = []
        self.status = 'succeeded'

    def fetch(self, base, key, suffix):
        self.assertEqual(base, self.base)
        self.assertEqual(key, 'fake-local-test-key')
        self.calls.append(suffix)
        if suffix == '/account/summary':
            return {'account_id': 'synthetic-account'}
        self.assertEqual(suffix, '/requests/' + self.operation)
        return {'id': 'gj_original', 'status': self.status, 'charged_micros': '120'}

    def outcome(self):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('SELECT outcome FROM studio_audio_operations').fetchone()[0]
        return json.loads(row) if row else None

    def test_terminal_receipt_unblocks_old_intent_without_new_submission(self):
        config, journal = self.config.read_bytes(), self.journal.read_bytes()
        for status in ['succeeded', 'failed', 'cancelled']:
            with self.subTest(status=status):
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute('UPDATE studio_audio_operations SET outcome=NULL'); db.commit()
                self.status = status
                receipts = guard.reconcile(self.root, fetch=self.fetch)
                self.assertEqual(receipts, [{'operation_id': self.operation, 'status': status}])
                self.assertEqual(self.outcome()['job_id'], 'gj_original')
                count = len(self.calls)
                self.assertEqual(guard.reconcile(self.root, fetch=self.fetch), [])
                self.assertEqual(len(self.calls), count)
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(self.journal.read_bytes(), journal)
        self.assertTrue(all(p == '/account/summary' or p.startswith('/requests/') for p in self.calls))

    def test_unknown_or_network_failure_never_clears_intent(self):
        for status in ['running', 'submission_unknown', None]:
            self.status = status
            self.assertEqual(guard.reconcile(self.root, fetch=self.fetch), [])
            self.assertIsNone(self.outcome())
        def unavailable(*args):
            raise TimeoutError('synthetic unavailable account')
        self.assertEqual(guard.reconcile(self.root, fetch=unavailable), [])
        self.assertIsNone(self.outcome())

    def test_wrong_account_or_job_cannot_release_guard(self):
        def other_account(base, key, suffix):
            return {'account_id': 'different-account'}
        self.assertEqual(guard.reconcile(self.root, fetch=other_account), [])
        self.assertIsNone(self.outcome())
        def other_job(base, key, suffix):
            value = self.fetch(base, key, suffix)
            if suffix.startswith('/requests/'): value['id'] = 'gj_another'
            return value
        self.assertEqual(guard.reconcile(self.root, fetch=other_job), [])
        self.assertIsNone(self.outcome())

    def test_changed_attempt_or_config_preserves_pending_row(self):
        for change in ['attempt', 'quote', 'config']:
            def changed(base, key, suffix):
                value = self.fetch(base, key, suffix)
                if suffix.startswith('/requests/'):
                    if change == 'attempt':
                        with closing(sqlite3.connect(self.database)) as db:
                            db.execute('UPDATE studio_audio_operations SET attempts=attempts+1'); db.commit()
                    elif change == 'quote':
                        with closing(sqlite3.connect(self.database)) as db:
                            db.execute("UPDATE studio_audio_operations SET quote_id='changed-quote'"); db.commit()
                    else:
                        self.config.write_text('{}', encoding='utf-8')
                return value
            self.assertEqual(guard.reconcile(self.root, fetch=changed), [])
            self.assertIsNone(self.outcome())
            with closing(sqlite3.connect(self.database)) as db:
                db.execute("UPDATE studio_audio_operations SET quote_id='synthetic-quote'"); db.commit()


if __name__ == '__main__':
    unittest.main()
