"""Read-only update classification; unknown cloud results remain held, never retried."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect(path):
    path = Path(path).resolve()
    result = {'held': [], 'blocked_count': 0, 'blocked_statuses': {}}
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='production_jobs'").fetchone():
            return result
        columns = {r['name'] for r in db.execute('PRAGMA table_info(production_jobs)')}
        can_prove_held = {'job_id', 'worker_id', 'lease_expires_at'} <= columns
        for row in db.execute("SELECT * FROM production_jobs WHERE status NOT IN ('completed','failed','cancelled') OR status IS NULL"):
            if can_prove_held and row['status'] == 'ambiguous' and row['worker_id'] is None and row['lease_expires_at'] is None:
                # Hash every field without disclosing frozen credentials/requests.
                value = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in dict(row).items()}
                identity = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                    separators=(',', ':')).encode()).hexdigest()
                result['held'].append({'job_id': row['job_id'], 'sha256': identity})
            else:
                result['blocked_count'] += 1
                status = str(row['status'])
                result['blocked_statuses'][status] = result['blocked_statuses'].get(status, 0) + 1
    result['held'].sort(key=lambda r: r['job_id'])
    return result


def require_idle(path):
    result = inspect(path)
    if result['blocked_count']:
        raise ValueError(f"目标副本仍有{result['blocked_count']}条执行、排队或未释放执行权的制作任务，请先安全结束；历史待核对记录原样保留")
    return result


def snapshot(path, backup, expected):
    """Snapshot locally after services stop; never change the live queue database."""
    if not expected['held']:
        return None
    actual = require_idle(path)
    if actual['held'] != expected['held']:
        raise ValueError('待核对任务在升级前发生变化，请保留原记录并重新检查')
    copy = Path(backup) / 'preserved-production-queue.sqlite3'
    if copy.exists():
        raise ValueError('任务备份已存在，不能覆盖')
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(copy)) as destination:
            source.backup(destination)
    if inspect(copy)['held'] != expected['held']:
        raise ValueError('待核对任务备份校验失败，原程序未改变')
    return {'filename': copy.name, 'sha256': digest(copy), 'held': expected['held']}


def verify_preserved(path, expected):
    actual = inspect(path)
    if actual['held'] != expected['held']:
        raise ValueError('升级后待核对任务记录发生变化；已保留任务数据库快照，请核对升级备份')
