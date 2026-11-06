"""Reuse working media tools, otherwise install hash-pinned mirror archives."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portable import app_update as core
from portable.update_service import https_url, SecureRedirect


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
            req = urllib.request.Request(url, headers={'User-Agent': 'Haike-Source-Setup/1'})
            with urllib.request.build_opener(SecureRedirect()).open(req, timeout=60) as response, partial.open('wb') as out:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise ValueError('依赖归档超过大小限制。')
                    out.write(chunk)
            if core.digest(partial) != row['sha256']:
                raise ValueError('依赖镜像内容摘要不匹配。')
            os.replace(partial, archive)
            return archive
        except (OSError, ValueError):
            partial.unlink(missing_ok=True)
    raise ValueError('固定依赖的镜像/上游均未下载成功；保留已有环境，稍后重试。')


def install(root=ROOT):
    if os.name != 'nt':
        raise ValueError('此入口只适用于 Windows；Mac 使用 setup-mac.sh。')
    spec = json.loads((root / 'portable/dependency-downloads.json').read_text(encoding='utf-8'))
    browser = root / 'runtime/browser/chrome-headless-shell.exe'
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
    if not version(browser):
        archive = obtain(spec['browser'], root)
        target = browser.parent
        target.mkdir(parents=True, exist_ok=True)
        prefix = spec['browser']['prefix']
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                if not info.filename.startswith(prefix) or info.is_dir():
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000 or info.file_size > 512 * 1024 * 1024:
                    raise ValueError('浏览器归档包含不支持的文件。')
                path = core.safe_path(target, info.filename[len(prefix):])
                path.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as src, path.open('wb') as out:
                    shutil.copyfileobj(src, out)
    tools = {'ffmpeg': ffmpeg_dir / 'ffmpeg.exe', 'ffprobe': ffmpeg_dir / 'ffprobe.exe', 'browser': browser}
    rows = {name: dict(path=str(path.relative_to(root)), version=version(path), sha256=core.digest(path))
            for name, path in tools.items()}
    if not all(row['version'] for row in rows.values()):
        raise ValueError('Windows 媒体运行时启动检查未通过。')
    receipt = root / '.local/windows-media-runtime.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({'schema': 1, 'tools': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Media tools verified; browser uses npmmirror, existing FFmpeg reused when available.', flush=True)


if __name__ == '__main__':
    install()
