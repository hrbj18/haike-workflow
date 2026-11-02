"""Reconcile existing relay intents with GET only before an installation update."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib import parse, request

TERMINAL = {'succeeded', 'failed', 'cancelled'}


def owned(root, relative):
    path = root / relative
    if (path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root and p.is_relative_to(root))
            or not path.resolve().is_relative_to(root)):
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
