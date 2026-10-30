"""Reject private credentials and personalized MotionGit envelopes in public assets."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import zipfile


def check(path):
    path = Path(path)
    if path.suffix.lower() != '.zip':
        return
    def inspect(archive, depth=0):
        if depth > 2 or len(archive.infolist()) > 30000:
            raise ValueError('公开附件层数或文件数量超限')
        for item in archive.infolist():
            name = item.filename.lower()
            if ('personal/motiongit.key.json' in name or name.endswith(('.env.local', '.private.json',
                    '.sqlite', '.sqlite3', '/cookies.txt', '/storage_state.json'))):
                raise ValueError('公开附件包含个人凭据或用户数据：' + item.filename)
            if name.endswith('.motion'):
                if item.file_size > 386 * 1024 * 1024:
                    raise ValueError('原包大小超限')
                with zipfile.ZipFile(io.BytesIO(archive.read(item))) as nested:
                    inspect(nested, depth+1)
    with zipfile.ZipFile(path) as archive:
        inspect(archive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifacts', nargs='+', type=Path)
    args = parser.parse_args()
    for path in args.artifacts:
        check(path)
    print('Public release boundary check passed: ' + str(len(args.artifacts)) + ' assets')


if __name__ == '__main__':
    main()
