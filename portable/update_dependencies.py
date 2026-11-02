"""Inspect capabilities, then stage missing dependencies using pinned mirrors.

Inspection is read-only. Preparation writes downloads/staging only; the existing
transaction installer owns all changes to installed runtime and environment files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import urllib.request
from uuid import uuid4
import zipfile

MAX_DOWNLOAD = 800_000_000
COMPONENTS = {'python', 'node', 'uv', 'msvc', 'ffmpeg', 'browser'}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe(root, name):
    parts = PurePosixPath(name).parts
    require(name and not name.startswith('/') and '\\' not in name and ':' not in name
            and all(p not in {'.', '..'} for p in parts), '依赖路径越界')
    path = Path(root)
    for part in parts:
        path = path / part
        require(not path.is_symlink() and not (hasattr(path, 'is_junction') and path.is_junction()),
                '依赖路径不能经过链接')
    require(path.resolve().is_relative_to(Path(root).resolve()), '依赖路径越界')
    return path


def allowed(name):
    return '..' not in PurePosixPath(name).parts and '\\' not in name and ':' not in name and (any(name.startswith('runtime/' + key + '/') for key in COMPONENTS)
            or name.startswith('Haike_video/.venv/')) and not any(
                p.casefold() in {'.git', 'projects', 'data', '.backlot'} or p.casefold().startswith('.env')
                for p in PurePosixPath(name).parts)


def environment(root, staged=None):
    result = os.environ.copy()
    result.pop('PYTHONHOME', None)
    result.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
                  PYTHONIOENCODING='utf-8', PIP_NO_INDEX='1', UV_OFFLINE='1',
                  HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
    roots = [Path(staged), Path(root)] if staged else [Path(root)]
    result['PYTHONPATH'] = os.pathsep.join(str(p / 'Haike_video/.venv/Lib/site-packages') for p in roots)
    result['PATH'] = os.pathsep.join(str(p / 'runtime' / key) for p in roots for key in ['msvc', 'node', 'python']) + os.pathsep + result.get('PATH', '')
    return result


def run(arguments, root, staged=None, timeout=25):
    try:
        result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout, env=environment(root, staged),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0, result.stdout
    except (OSError, subprocess.SubprocessError):
        return False, ''


def inspect(root):
    root = Path(root).resolve()
    python = root / 'runtime/python/python.exe'
    ok, _ = run([python, '-s', '-c', 'import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8'], root)
    result = {'python': ok}
    ok, version = run([root / 'runtime/node/node.exe', '--version'], root)
    result['node'] = ok and bool(re.match(r'v(?:2[2-9]|[3-9]\d)\.', version))
    ok, codecs = run([root / 'runtime/ffmpeg/bin/ffmpeg.exe', '-hide_banner', '-encoders'], root)
    probe, _ = run([root / 'runtime/ffmpeg/bin/ffprobe.exe', '-version'], root)
    result['ffmpeg'] = ok and probe and 'libx264' in codecs and 'aac' in codecs
    browser = root / 'runtime/browser/chrome-headless-shell.exe'
    try:
        with browser.open('rb') as stream:
            result['browser'] = stream.read(2) == b'MZ'
        if result['browser']:
            result['browser'], _ = run([browser, '--version'], root, timeout=10)
    except OSError:
        result['browser'] = False
    result['msvc'] = all((root / 'runtime/msvc' / n).is_file() for n in ['msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'])
    if result['python'] and result['msvc']:
        dlls = [str(root / 'runtime/msvc' / n) for n in ['vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll']]
        result['msvc'], _ = run([python, '-s', '-c', 'import ctypes; [ctypes.WinDLL(p) for p in ' + repr(dlls) + ']'], root)
    # scipy belongs to the versioned native-template resources, which are
    # validated separately. It is not a missing base-environment dependency.
    packages, _ = run([python, '-s', '-c', 'import fastapi,uvicorn,jsonschema,yaml,PIL,cv2,numpy,aiohttp,dashscope,multipart'], root)
    result['python_packages'] = packages
    return {'schema': 1, 'components': result, 'missing': [k for k, v in result.items() if not v],
            'download_required': any(not v for v in result.values())}


def download(root, name, spec):
    require(re.fullmatch('[a-f0-9]{64}', spec.get('sha256', '')), '依赖下载缺少固定SHA：' + name)
    cache = safe(root, '.local/github-updates/dependencies/' + spec['sha256'] + '.zip')
    if cache.is_file() and digest(cache) == spec['sha256']:
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    for url in spec['urls']:
        require(url.startswith('https://'), '依赖仅允许HTTPS下载')
        part = cache.with_suffix('.' + uuid4().hex + '.part')
        try:
            count = 0
            with urllib.request.urlopen(url, timeout=60) as response, part.open('xb') as output:
                require(response.geturl().startswith('https://'), '依赖下载被重定向到非HTTPS地址')
                while block := response.read(1024 * 1024):
                    count += len(block); require(count <= MAX_DOWNLOAD, '依赖下载过大')
                    output.write(block)
            require(digest(part) == spec['sha256'], '依赖摘要不符：' + name)
            os.replace(part, cache)
            return cache
        except (OSError, ValueError):
            pass
        finally:
            part.unlink(missing_ok=True)
    raise ValueError('国内依赖下载未完成，已保留原程序：' + name)


def extract(archive, stage, name, spec):
    with zipfile.ZipFile(archive) as zipped:
        require(len(zipped.infolist()) < 50000 and sum(r.file_size for r in zipped.infolist()) < 3_000_000_000,
                '依赖解压数量或体积过大')
        prefix = spec.get('prefix', '')
        if name == 'ffmpeg':
            prefix = zipped.namelist()[0].split('/')[0] + '/'
        for row in zipped.infolist():
            parts = PurePosixPath(row.filename).parts
            require(not row.filename.startswith('/') and '\\' not in row.filename and ':' not in row.filename
                    and '..' not in parts and ((row.external_attr >> 16) & 0o170000) != 0o120000, '依赖包有越界路径或链接')
            if row.is_dir() or not row.filename.startswith(prefix):
                continue
            relative = row.filename[len(prefix):]
            if name in {'msvc', 'uv'}:
                if name == 'msvc' and not (row.filename.endswith('.dll') and '/Scripts/' in row.filename):
                    continue
                if name == 'uv' and not row.filename.endswith(('uv.exe', 'LICENSE-MIT', 'LICENSE-APACHE')):
                    continue
                relative = parts[-1]
            path = safe(stage, 'runtime/' + name + '/' + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(row))


def prepare(root, bundle, report=None):
    root, bundle = Path(root).resolve(), Path(bundle).resolve()
    report = report or inspect(root)
    if not report['missing']:
        return None
    spec = json.loads((bundle / 'dependency-downloads.json').read_bytes())
    stage = safe(root, '.local/github-updates/dependency-stages/' + uuid4().hex)
    stage.mkdir(parents=True)
    missing = set(report['missing'])
    for name in sorted(missing & COMPONENTS):
        extract(download(root, name, spec[name]), stage, name, spec[name])
    if 'python_packages' in missing:
        uv = stage / 'runtime/uv/uv.exe'
        if not uv.is_file():
            uv = root / 'runtime/uv/uv.exe'
        if not uv.is_file():
            extract(download(root, 'uv', spec['uv']), stage, 'uv', spec['uv'])
            uv = stage / 'runtime/uv/uv.exe'
        python = stage / 'runtime/python/python.exe'
        if not python.is_file():
            python = root / 'runtime/python/python.exe'
        env = environment(root, stage)
        env.pop('PIP_NO_INDEX', None); env.pop('UV_OFFLINE', None)
        env.update(UV_PYTHON_DOWNLOADS='never', UV_LINK_MODE='copy')
        venv = stage / 'Haike_video/.venv'
        log = stage / 'install.log'
        with log.open('ab') as stream:
            make = subprocess.run([str(uv), 'venv', '--python', str(python), str(venv)], env=env,
                stdout=stream, stderr=stream, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            require(make.returncode == 0, '无法准备本机制作依赖，请查看：' + str(log))
            installed = False
            for index in spec['pypi']:
                install = subprocess.run([str(uv), 'pip', 'install', '--python', str(venv / 'Scripts/python.exe'),
                    '--index-url', index, '-r', str(bundle / 'video-dependencies.txt')], env=env,
                    stdout=stream, stderr=stream, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if install.returncode == 0:
                    installed = True; break
            require(installed, '国内Python依赖安装失败，原程序未改变；日志：' + str(log))
        # The staged interpreter is only for preparation. Installed environments
        # must refer to the recipient's final Python rather than this staging path.
        base = root / 'runtime/python'
        (venv / 'pyvenv.cfg').write_text(f'home = {base}\ninclude-system-site-packages = false\nexecutable = {base / "python.exe"}\n', encoding='utf-8')
    rows = []
    for file in sorted(stage.rglob('*')):
        if not file.is_file() or file.name == 'install.log' or '__pycache__' in file.parts:
            continue
        name = file.relative_to(stage).as_posix()
        require(allowed(name), '依赖修复包含非运行文件：' + name)
        rows.append({'path': name, 'size': file.stat().st_size, 'sha256': digest(file),
                     'prepared': str(file), 'repair': True, 'resource': True,
                     'mutable': file.name == 'pyvenv.cfg'})
    plan = stage / 'dependencies.json'
    plan.write_text(json.dumps({'schema': 1, 'target': str(root), 'rows': rows}, ensure_ascii=False), encoding='utf-8')
    return plan


def rows(root, plan):
    root = Path(root).resolve()
    plan = Path(plan).resolve(strict=True)
    require(plan.is_relative_to(safe(root, '.local/github-updates/dependency-stages')), '依赖修复记录不属于此安装')
    value = json.loads(plan.read_bytes())
    require(value['schema'] == 1 and Path(value['target']).resolve() == root, '依赖修复目标不匹配')
    require(len(value['rows']) < 50000, '依赖修复文件过多')
    for row in value['rows']:
        require(allowed(row['path']), '依赖修复试图覆盖用户文件')
        file = Path(row['prepared']).resolve(strict=True)
        require(file == safe(plan.parent, row['path']).resolve() and file.stat().st_size == row['size']
                and digest(file) == row['sha256'], '准备好的依赖已损坏，请保留原程序并重新准备')
    return value['rows']
