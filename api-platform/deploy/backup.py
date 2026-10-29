"""Consistent private DB/vault/upload snapshot; run as the service owner."""
import os
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def main():
    data = Path('/var/lib/haike-api-platform')
    target = Path('/var/backups/haike-api-platform')
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = 'haike-api-' + datetime.now(UTC).strftime('%Y%m%d-%H%M%S') + '.tar.gz'
    with tempfile.TemporaryDirectory(dir=target) as scratch:
        snapshot = Path(scratch) / 'platform.sqlite3'
        with sqlite3.connect(f"file:{data / 'platform.sqlite3'}?mode=ro", uri=True) as source, sqlite3.connect(snapshot) as dest:
            source.backup(dest)
        bundle = Path(scratch) / name
        with tarfile.open(bundle, 'w:gz') as archive:
            archive.add(snapshot, arcname='platform.sqlite3')
            for child in data.iterdir():
                if not child.name.startswith('platform.sqlite3'):
                    archive.add(child, arcname=child.name)
        os.chmod(bundle, 0o600)
        bundle.replace(target / name)
    print('Private database and provider backup completed')


if __name__ == '__main__':
    main()
