"""Preserve inactive local audio intents; reconcile relay intents with GET only."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from urllib import parse, request

try:
    from .app_update import native_path, logical_path
except ImportError:
    import importlib.util
    _core_path = Path(__file__).with_name('release_core.py')
    if not _core_path.is_file():
        _core_path = Path(__file__).with_name('app_update.py')
    _spec = importlib.util.spec_from_file_location('haike_audio_path_core', _core_path)
    _core = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_core)
    native_path, logical_path = _core.native_path, _core.logical_path

TERMINAL = {'succeeded', 'failed', 'cancelled'}


def owned(root, relative):
    path = root / relative
    if (native_path(path).is_symlink()
            or any(native_path(p).is_symlink() or native_path(p).is_junction()
                   for p in path.parents if p != root and p.is_relative_to(root))
            or not logical_path(native_path(path).resolve()).is_relative_to(root)):
        raise ValueError('音色操作记录路径异常，原数据已保留')
    return path


def get(base, key, suffix):
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    req = request.Request(base + suffix, headers={'Authorization': 'Bearer ' + key})
    with request.build_opener(request.ProxyHandler({}), NoRedirect()).open(req, timeout=20) as response:
        data = response.read(32_000_001)
    if len(data) > 32_000_000:
        raise ValueError('音色原操作响应过大，结果仍待核对')
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError('音色原操作响应无效，结果仍待核对')
    return value


def reconcile(root, *, fetch=get):
    """Only persist authenticated terminal receipts; never submit or retry a job.

    The standalone bootstrap cannot import unverified target application code.
    Match AudioCenter's account identity and use optimistic writes so a changed
    intent or account is never cleared by an older response.
    """
    root = Path(root).resolve(strict=True)
    database = owned(root, 'Haike_video/.backlot/studio.sqlite3')
    config_file = owned(root, 'Haike_video/.backlot/haike-api/client-config.json')
    if not database.is_file() or not config_file.is_file():
        return []
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        columns = {r[1] for r in db.execute('PRAGMA table_info(studio_audio_operations)')}
        if not {'account', 'id', 'quote_id', 'attempts', 'outcome'}.issubset(columns):
            return []
        rows = db.execute('SELECT account,id,quote_id,attempts FROM studio_audio_operations '
                          'WHERE attempts>0 AND outcome IS NULL').fetchall()
    if not rows:
        return []
    try:
        config_bytes = config_file.read_bytes()
        if len(config_bytes) > 1_000_000:
            return []
        config = json.loads(config_bytes)
        base, key = config['base_url'].rstrip('/'), config['api_key']
        url = parse.urlsplit(base)
        if (url.path != '/v2' or url.username or url.password or url.query or url.fragment
                or not url.hostname or not isinstance(key, str) or not key):
            return []
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'127.0.0.1', 'localhost', '::1'}):
            return []
        summary = fetch(base, key, '/account/summary')
        account_id = summary.get('account_id') or summary.get('account_name')
        if not account_id:
            return []
        account = hashlib.sha256(json.dumps([base, account_id], ensure_ascii=False).encode()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    receipts = []
    for owner, operation, quote, attempts in rows:
        if owner != account or not isinstance(operation, str) or not re.fullmatch('call_[a-f0-9]{32}', operation):
            continue
        try:
            journal = owned(root, f'Haike_video/.backlot/audio-center/{account}/intents/{operation}.json')
            if not journal.is_file() or journal.stat().st_size > 1_000_000:
                continue
            intent = json.loads(journal.read_text(encoding='utf-8'))
            body = intent.get('body') or {}
            if (intent.get('idempotency_key') != operation or body.get('call_intent_id') != operation
                    or body.get('quote_id') != quote):
                continue
            job = fetch(base, key, '/requests/' + operation)
            status = job.get('status')
            job_id = job.get('id')
            if (status not in TERMINAL or not isinstance(job_id, str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,160}', job_id)
                    or intent.get('job_id') and intent['job_id'] != job_id):
                continue
            if config_file.read_bytes() != config_bytes:
                break
            receipt = {'id': operation, 'operation_id': operation, 'status': status, 'result': None,
                       'job_id': job_id, 'charged_micros': str(job.get('charged_micros', '0')),
                       'reconciled_at': datetime.now(timezone.utc).isoformat(), 'source': 'authenticated-original-request-get'}
            with closing(sqlite3.connect(database, timeout=5)) as db:
                with db:
                    changed = db.execute('UPDATE studio_audio_operations SET outcome=? '
                        'WHERE account=? AND id=? AND quote_id=? AND attempts=? AND outcome IS NULL',
                        (json.dumps(receipt, ensure_ascii=False), account, operation, quote, attempts)).rowcount
            if changed:
                receipts.append({'operation_id': operation, 'status': status})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
            # A timeout/404/malformed reply cannot establish rejection or release.
            continue
    return receipts


def file_digest(path):
    with native_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lock_free(path):
    path = native_path(path)
    """Probe the producer's existing OS lock without creating/changing its bytes."""
    if not path.is_file() or path.stat().st_size != 1:
        return False
    try:
        with path.open('r+b') as handle:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle, fcntl.LOCK_UN)
        return True
    except OSError:
        return False


def operation_files(root, folder):
    files = {}
    for path in sorted(native_path(folder).rglob('*')):
        path = logical_path(path)
        path = owned(root, path.relative_to(root))
        if native_path(path).is_file():
            files[path.relative_to(folder).as_posix()] = file_digest(path)
        elif not native_path(path).is_dir():
            raise ValueError('音色操作包含无法备份的文件，原数据已保留')
    return files


def inspect(root, *, private=None):
    root = Path(root).resolve()
    private = owned(root, Path(private).relative_to(root) if private else 'Haike_video/.backlot')
    result = {'held': [], 'blocked_count': 0}
    database = owned(root, private.relative_to(root) / 'studio.sqlite3')
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='studio_audio_operations'").fetchone():
                # Relay rows do not persist an execution state or OS lock. Do not
                # infer inactivity from attempts/outcome, or from network failure.
                result['blocked_count'] += db.execute('SELECT COUNT(*) FROM studio_audio_operations WHERE attempts>0 AND outcome IS NULL').fetchone()[0]
    directory = owned(root, private.relative_to(root) / 'audio-center-internal')
    for record in sorted(native_path(directory).glob('*/operations/*/operation.json')):
        record = logical_path(record)
        record = owned(root, record.relative_to(root))
        if native_path(record).stat().st_size > 32_000_000:
            raise ValueError('音色操作记录过大，原数据已保留')
        try:
            value = json.loads(native_path(record).read_text(encoding='utf-8-sig'))
        except (ValueError, OSError) as error:
            raise ValueError('音色操作记录无法读取，原数据已保留') from error
        if not isinstance(value, dict):
            raise ValueError('音色操作记录无效，原数据已保留')
        if value.get('status') in {'succeeded', 'failed'}:
            continue
        request_data = value.get('request')
        held = (value.get('status') == 'submission_unknown'
            and re.fullmatch(r'call_[a-f0-9]{32}', record.parent.name)
            and value.get('id') == record.parent.name
            and re.fullmatch(r'[a-f0-9]{64}', str(value.get('signature', '')))
            and re.fullmatch(r'iq_[a-f0-9]{32}', str(value.get('quote_id', '')))
            and type(value.get('maximum')) is int and value['maximum'] >= 0
            and isinstance(request_data, dict) and request_data.get('kind') in {'tts', 'clone'}
            and isinstance(request_data.get('credential_identity'), str) and request_data['credential_identity']
            and isinstance(value.get('provider_state', {}), dict)
            and lock_free(owned(root, record.parent.relative_to(root) / '.lock')))
        if held:
            result['held'].append({'id': value['id'], 'path': record.parent.relative_to(root).as_posix(),
                'files': operation_files(root, record.parent)})
        else:
            result['blocked_count'] += 1
    return result


def require_idle(root, *, private=None):
    result = inspect(root, private=private)
    if result['blocked_count']:
        raise ValueError(f"仍有{result['blocked_count']}条执行中、持锁或无法确认已停止的音色操作；可恢复的本地历史记录原样保留")
    return result


def verify_preserved(root, expected):
    if require_idle(root)['held'] != expected['held']:
        raise ValueError('升级前后待核对音色操作或片段发生变化，请保留原数据和备份')


def snapshot(root, backup, expected):
    if not expected['held']:
        return None
    root = Path(root).resolve()
    verify_preserved(root, expected)
    destination = Path(backup) / 'preserved-audio-operations'
    native_path(destination).mkdir(exist_ok=False)
    for item in expected['held']:
        for name, digest in item['files'].items():
            source = owned(root, Path(item['path']) / name)
            copy = owned(destination, Path(item['path']) / name)
            native_path(copy.parent).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(native_path(source), native_path(copy))
            if file_digest(copy) != digest:
                raise ValueError('音色操作备份校验失败，原程序未改变')
    verify_preserved(root, expected)
    return {'directory': destination.name, 'held': expected['held']}
