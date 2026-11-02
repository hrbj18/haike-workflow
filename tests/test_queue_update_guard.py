from contextlib import closing
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('queue_guard_test', ROOT / 'portable/queue_update_guard.py')
guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)


class QueueGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.path = self.root / 'queue.sqlite3'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE production_jobs(job_id TEXT,status TEXT,worker_id TEXT,lease_expires_at TEXT,frozen_request TEXT)')
            db.executemany('INSERT INTO production_jobs VALUES (?,?,?,?,?)',
                [(f'PQ-{i:020d}', 'ambiguous', None, None, '{"synthetic":"preserve"}') for i in range(7)])
            db.commit()

    def test_seven_held_unknown_results_are_read_only_and_do_not_block(self):
        before = self.path.read_bytes()
        result = guard.require_idle(self.path)
        self.assertEqual(len(result['held']), 7)
        self.assertEqual(result['blocked_count'], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_online_and_offline_guards_share_held_policy_without_task_writes(self):
        sys.path.insert(0, str(ROOT / 'portable'))
        def load(name, file):
            spec = importlib.util.spec_from_file_location(name, file)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
        online = load('held_online', ROOT / 'scripts/update-from-github.py')
        offline = load('held_offline', ROOT / 'portable/legacy_upgrade.py')
        target = self.root / 'target'
        destination = target / 'Haike_video/.backlot/production-queue.sqlite3'
        destination.parent.mkdir(parents=True); destination.write_bytes(self.path.read_bytes())
        before = destination.read_bytes()
        online.idle(target, queue_guard=guard)
        with patch.object(offline.subprocess, 'run', return_value=type('Result', (), {'returncode':0,'stdout':'[]'})()):
            offline.stopped(target)
        self.assertEqual(destination.read_bytes(), before)

    def test_active_unknown_and_unknown_schema_still_block(self):
        for status, worker, lease in [('running', 'worker', 'future'), ('queued', None, None),
                ('paused', None, None), ('awaiting_human', None, None),
                ('ambiguous', 'worker', None), ('ambiguous', None, 'future'), (None, None, None)]:
            with self.subTest(status=status, worker=worker, lease=lease), closing(sqlite3.connect(self.path)) as db:
                db.execute('UPDATE production_jobs SET status=?,worker_id=?,lease_expires_at=? WHERE job_id=?',
                    (status, worker, lease, 'PQ-00000000000000000000')); db.commit()
                with self.assertRaises(ValueError): guard.require_idle(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TABLE production_jobs'); db.execute('CREATE TABLE production_jobs(status TEXT)')
            db.execute("INSERT INTO production_jobs VALUES ('ambiguous')"); db.commit()
        with self.assertRaises(ValueError): guard.require_idle(self.path)

    def test_snapshot_retains_all_records_and_detects_any_row_change(self):
        expected = guard.require_idle(self.path)
        proof = guard.snapshot(self.path, self.root, expected)
        copy = self.root / proof['filename']
        self.assertEqual(guard.inspect(copy)['held'], expected['held'])
        self.assertEqual(hashlib.sha256(copy.read_bytes()).hexdigest(), proof['sha256'])
        guard.verify_preserved(self.path, expected)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE production_jobs SET frozen_request='changed' WHERE job_id='PQ-00000000000000000000'"); db.commit()
        with self.assertRaisesRegex(ValueError, '发生变化'): guard.verify_preserved(self.path, expected)
        self.assertEqual(guard.inspect(copy)['held'], expected['held'])

    def test_real_worker_never_claims_or_retries_held_records(self):
        sys.path.insert(0, str(ROOT / 'Haike_video'))
        from backlot.production_queue import ProductionQueue, ProductionQueueConflict
        path = self.root / 'real.sqlite3'
        queue = ProductionQueue(path, self.root / 'projects')
        with closing(sqlite3.connect(path)) as db:
            for i in range(7):
                db.execute('INSERT INTO production_jobs(job_id,idempotency_key,project_id,project_title,kind,source,priority,priority_rank,status,stage,parent_job_id,frozen_request,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f'PQ-{i:020d}', f'synthetic-{i}', 'synthetic', 'synthetic', 'studio_avatar', 'synthetic', 'normal', 0,
                     'ambiguous', '云端结果需核对', 'synthetic-parent', '{}', '2026-01-01', '2026-01-01'))
            db.commit()
        before = guard.inspect(path)['held']
        self.assertIsNone(queue.claim_next('update-test'))
        with self.assertRaises(ProductionQueueConflict): queue.retry('PQ-00000000000000000000')
        self.assertEqual(guard.inspect(path)['held'], before)
