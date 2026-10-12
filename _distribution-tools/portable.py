"""Bundle-local deployment utilities; no paid API calls or collection jobs."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def download(url, destination):
    request = urllib.request.Request(url, headers={'User-Agent': 'Haike-Portable-Setup/1'})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open('wb') as handle:
        size = 0
        report_at = 32 * 1024**2
        while chunk := response.read(1024**2):
            handle.write(chunk)
            size += len(chunk)
            if size >= report_at:
                print(f'Downloaded {size // 1024**2} MB...', flush=True)
                report_at += 32 * 1024**2


def runtime():
    spec = json.loads((ROOT / '_distribution-tools/runtime-downloads.json').read_text(encoding='utf-8'))['ffmpeg']
    target = ROOT / 'runtime/ffmpeg'
    receipt_path = target / 'INSTALL-RECEIPT.json'
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if all((target / name).is_file() and file_sha256(target / name) == receipt['files'][name]
                   for name in ('ffmpeg.exe', 'ffprobe.exe')):
                print('FFmpeg/FFprobe already installed and verified; no download needed.')
                return
        except (OSError, ValueError, KeyError):
            pass
    cache = Path(os.environ.get('LOCALAPPDATA', str(ROOT / '.portable'))) / 'haike-cache/downloads'
    cache.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            print('Resolving FFmpeg Windows x64 build and publisher SHA256...', flush=True)
            request = urllib.request.Request(spec['checksums_url'], headers={'User-Agent': 'Haike-Portable-Setup/1'})
            with urllib.request.urlopen(request, timeout=60) as response:
                checksums = response.read(256 * 1024).decode('utf-8')
            expected = next(line.split()[0].lower() for line in checksums.splitlines()
                            if len(line.split()) == 2 and line.split()[1].lstrip('*') == spec['asset'])
            if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
                raise RuntimeError('Invalid publisher checksum')
            archive = cache / f'ffmpeg-{expected}.zip'
            if not archive.is_file() or file_sha256(archive) != expected:
                with tempfile.TemporaryDirectory(prefix='ffdl-', dir=cache) as temporary:
                    partial = Path(temporary) / 'download.zip'
                    print('Downloading FFmpeg/FFprobe from ' + spec['url'], flush=True)
                    download(spec['url'], partial)
                    if file_sha256(partial) != expected:
                        raise RuntimeError('FFmpeg SHA256 mismatch; publisher may have updated the release. Retrying.')
                    os.replace(partial, archive)
            with tempfile.TemporaryDirectory(prefix='ffinstall-', dir=target.parent) as temporary:
                staging = Path(temporary)
                with zipfile.ZipFile(archive) as package:
                    for name in ('ffmpeg.exe', 'ffprobe.exe', 'LICENSE.txt'):
                        matches = [info for info in package.infolist() if not info.is_dir()
                                   and Path(info.filename).name == name]
                        if len(matches) != 1:
                            raise RuntimeError('FFmpeg package lacks a unique ' + name)
                        with package.open(matches[0]) as src, (staging / name).open('wb') as dest:
                            shutil.copyfileobj(src, dest)
                versions = {}
                for name in ('ffmpeg.exe', 'ffprobe.exe'):
                    output = subprocess.check_output([str(staging / name), '-version'], timeout=30, text=True)
                    versions[name] = output.splitlines()[0]
                receipt = {'provider': spec['provider'], 'url': spec['url'], 'archive_sha256': expected,
                           'versions': versions, 'files': {p.name: file_sha256(p) for p in staging.iterdir()}}
                for file in staging.iterdir():
                    os.replace(file, target / file.name)
                (staging / receipt_path.name).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
                os.replace(staging / receipt_path.name, receipt_path)
            print('FFmpeg/FFprobe downloaded, SHA256 verified and installed.', flush=True)
            return
        except Exception as error:
            print(f'FFmpeg installation attempt {attempt + 1}/3 failed: {error}', flush=True)
            if attempt == 2:
                raise RuntimeError('FFmpeg download failed. Check access to github.com and rerun scripts/setup.ps1. '
                                   'Download sources are listed in _distribution-tools/runtime-downloads.json.') from error
            time.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Install verified FFmpeg binaries only.')
    parser.add_argument('action', choices=['runtime'])
    parser.parse_args()
    runtime()
