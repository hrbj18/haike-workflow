"""Reuse working media tools, otherwise install hash-pinned mirror archives."""
from __future__ import annotations

import json
import http.client
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portable import app_update as core
from portable.update_service import https_url, SecureRedirect
from portable.system_browser import resolve as resolve_browser, identity as browser_identity

MAX_ARCHIVE = 512 * 1024 * 1024
RANGE_SIZE = 4 * 1024 * 1024


def open_range(url, first, last):
    https_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': 'Haike-Source-Setup/1',
        'Range': f'bytes={first}-{last}', 'Accept-Encoding': 'identity'})
    return urllib.request.build_opener(SecureRedirect()).open(req, timeout=15)


def read_bounded(response, out, limit, deadline):
    size = 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError('依赖下载进度超时。')
        chunk = response.read1(min(65536, limit - size + 1))
        if not chunk:
            return size
        size += len(chunk)
        if size > limit:
            raise ValueError('依赖归档超过大小限制。')
        out.write(chunk)


def checked_range(url, first, last, total):
    from io import BytesIO
    for attempt in range(3):
        try:
            with open_range(url, first, last) as response:
                expected = f'bytes {first}-{last}/{total}'
                if response.status != 206 or response.headers.get('Content-Range') != expected:
                    raise ValueError('依赖镜像分段响应无效。')
                output = BytesIO()
                size = read_bounded(response, output, last - first + 1, time.monotonic() + 60)
                if size != last - first + 1:
                    raise ValueError('依赖镜像分段不完整。')
                return output.getvalue()
        except (OSError, ValueError, http.client.HTTPException):
            if attempt == 2:
                raise


def download(url, partial):
    with open_range(url, 0, RANGE_SIZE - 1) as response, partial.open('wb') as out:
        if response.status == 200:
            # Servers without range support retain the ordinary bounded download.
            read_bounded(response, out, MAX_ARCHIVE, time.monotonic() + 600)
            return
        header = response.headers.get('Content-Range', '')
        match = re.fullmatch(r'bytes 0-(\d+)/(\d+)', header)
        if response.status != 206 or not match:
            raise ValueError('依赖镜像分段响应无效。')
        last, total = map(int, match.groups())
        if not 0 < total <= MAX_ARCHIVE or last != min(RANGE_SIZE, total) - 1:
            raise ValueError('依赖镜像归档大小无效。')
        if read_bounded(response, out, last + 1, time.monotonic() + 60) != last + 1:
            raise ValueError('依赖镜像分段不完整。')
        # Bound both concurrency and memory: at most four 4 MiB segments per batch.
        with ThreadPoolExecutor(max_workers=4) as pool:
            positions = range(last + 1, total, RANGE_SIZE)
            iterator = iter(positions)
            while batch := [start for _, start in zip(range(4), iterator)]:
                futures = [pool.submit(checked_range, url, start, min(start + RANGE_SIZE, total) - 1, total)
                           for start in batch]
                for future in futures:
                    out.write(future.result())


def version(path):
    if not path.is_file():
        return ''
    try:
        result = subprocess.run([str(path), '--version' if 'chrome' in path.name else '-version'],
                                capture_output=True, text=True, timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def obtain(row, root=ROOT):
    cache = root / '.local/dependency-cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (row['sha256'] + '.zip')
    if archive.is_file() and core.digest(archive) == row['sha256']:
        return archive
    for url in row['urls']:
        https_url(url)
        print('Downloading pinned media dependency: ' + url, flush=True)
        partial = archive.with_suffix('.part')
        try:
            download(url, partial)
            if core.digest(partial) != row['sha256']:
                raise ValueError('依赖镜像内容摘要不匹配。')
            os.replace(partial, archive)
            return archive
        except (OSError, ValueError, http.client.HTTPException):
            partial.unlink(missing_ok=True)
    raise ValueError('固定依赖的镜像/上游均未下载成功；保留已有环境，稍后重试。')


def install(root=ROOT):
    if os.name != 'nt':
        raise ValueError('此入口只适用于 Windows；Mac 使用 setup-mac.sh。')
    spec = json.loads((root / 'portable/dependency-downloads.json').read_text(encoding='utf-8'))
    browser = resolve_browser()
    candidates = [root / 'runtime/ffmpeg/bin', root / 'runtime/ffmpeg']
    ffmpeg_dir = next((p for p in candidates if version(p / 'ffmpeg.exe') and version(p / 'ffprobe.exe')), None)
    if not ffmpeg_dir:
        archive = obtain(spec['ffmpeg'], root)
        ffmpeg_dir = root / 'runtime/ffmpeg'
        ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                matches = [i for i in package.infolist() if Path(i.filename).name == name and not i.is_dir()]
                if len(matches) != 1 or matches[0].file_size > 256 * 1024 * 1024:
                    raise ValueError('固定 FFmpeg 归档结构不兼容。')
                with package.open(matches[0]) as src, (ffmpeg_dir / name).open('wb') as out:
                    shutil.copyfileobj(src, out)
            for info in package.infolist():
                if Path(info.filename).name in {'LICENSE', 'LICENSE.txt', 'COPYING.GPLv3'} and info.file_size < 1024 * 1024:
                    (ffmpeg_dir / 'LICENSE.txt').write_bytes(package.read(info))
                    break
    tools = {'ffmpeg': ffmpeg_dir / 'ffmpeg.exe', 'ffprobe': ffmpeg_dir / 'ffprobe.exe'}
    rows = {name: dict(path=str(path.relative_to(root)), version=version(path), sha256=core.digest(path))
            for name, path in tools.items()}
    if not all(row['version'] for row in rows.values()):
        raise ValueError('Windows 媒体运行时启动检查未通过。')
    rows['browser'] = browser_identity(browser)
    receipt = root / '.local/windows-media-runtime.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({'schema': 1, 'tools': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Media tools verified; installed browser reused without browser/model downloads.', flush=True)


if __name__ == '__main__':
    install()
