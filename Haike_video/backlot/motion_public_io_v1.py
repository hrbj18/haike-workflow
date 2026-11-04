"""Versioned execution-owned hashing and private JSON IO; standard library only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class WorkError(ValueError):
    """Public component validation failure, before any paid or published action."""


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8')
    return hashlib.sha256(encoded).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text('utf8'))
    except FileNotFoundError:
        return {}


def atomic_private(path, value):
    path = Path(path)
    if path.is_symlink():
        raise WorkError('私有记录不能覆盖链接')
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.pending', dir=path.parent)
    with os.fdopen(descriptor, 'w', encoding='utf8', newline='\n') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
