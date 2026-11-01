"""Offline installed-tool smoke test; never produces or approves an episode."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

try:
    from . import app_update as core
except ImportError:
    spec = importlib.util.spec_from_file_location('haike_selftest_core', Path(__file__).with_name('app_update.py'))
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

SOURCES = ['portable/template_selftest.py', 'Haike_video/remotion-composer/runtime-selftest.mjs',
           'Haike_video/remotion-composer/src/RuntimeSelftest.tsx']


def require(ok, message):
    if not ok:
        raise core.UpdateError(message)


def environment(root, output):
    # Do not borrow a developer's PYTHONPATH, user venv, Chrome or global tools.
    env = {k: v for k, v in os.environ.items() if k.casefold() in {
        'systemroot', 'windir', 'comspec', 'pathext', 'number_of_processors', 'processor_architecture'}}
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1', HAIKE_PORTABLE_OFFLINE='1',
               PIP_NO_INDEX='1', UV_OFFLINE='1', NPM_CONFIG_OFFLINE='true', TEMP=str(output), TMP=str(output))
    env['PATH'] = os.pathsep.join([str(root / p) for p in ['runtime/python', 'runtime/node', 'runtime/ffmpeg/bin']]
                                 + [str(Path(env.get('SystemRoot', env.get('SYSTEMROOT', 'C:/Windows'))) / 'System32')])
    env['PYTHONPATH'] = str(root / 'Haike_video/.venv/Lib/site-packages')
    env['CHROME_PATH'] = str(root / 'runtime/browser/chrome-headless-shell.exe')
    return env


def execute(command, root, env, *, timeout=90):
    result = subprocess.run(list(map(str, command)), cwd=root, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, '安装内运行自检未通过：' + result.stderr[-1600:])
    return result.stdout


def run(root, capability_sha256, runtime_manifest=None):
    root = Path(root).resolve()
    require(isinstance(capability_sha256, str) and len(capability_sha256) == 64, '自检缺少交付身份')
    output = core.safe_path(root, '.local/template-selftests/' + capability_sha256[:16] + '-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    tools = {k: core.safe_path(root, name) for k, name in {
        'python': 'runtime/python/python.exe', 'node': 'runtime/node/node.exe',
        'ffmpeg': 'runtime/ffmpeg/bin/ffmpeg.exe', 'ffprobe': 'runtime/ffmpeg/bin/ffprobe.exe',
        'browser': 'runtime/browser/chrome-headless-shell.exe'}.items()}
    require(all(p.is_file() for p in tools.values()), '安装内Python/Node/FFmpeg/浏览器不完整')
    env = environment(root, output)
    probes = []
    for row in (runtime_manifest or {}).get('profiles', []):
        python = core.safe_path(root, row['cache'] + '/' + row['venv'] + '/Scripts/python.exe')
        code = ('import json,numpy as n; assert n.dot([2,3],[4,5])==23; '
                + ('from scipy import signal; assert len(signal.resample(n.arange(4.),8))==8; ' if 'scipy.signal' in row['imports'] else '')
                + "print(json.dumps({'ok':True,'numpy':n.__version__}))")
        result = json.loads(execute([python, '-I', '-c', code], root, env).strip())
        probes.append({'id': row['id'], **result})
    video = output / 'codec.mp4'
    execute([tools['ffmpeg'], '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=96x96:r=30:d=0.2',
             '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=0.2',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video], root, env)
    media = json.loads(execute([tools['ffprobe'], '-v', 'error', '-show_streams', '-of', 'json', video], root, env))
    require(any(s.get('codec_name') == 'h264' and s.get('width') == 96 for s in media['streams'])
            and any(s.get('codec_name') == 'aac' for s in media['streams']), '安装内编码器未输出预期音视频')
    execute([tools['ffmpeg'], '-nostdin', '-v', 'error', '-i', video, '-f', 'null', '-'], root, env)
    rendered = execute([tools['node'], core.safe_path(root, SOURCES[1]), root, output], root, env, timeout=150)
    result = json.loads(rendered.strip().splitlines()[-1])
    require(result.get('ok') and result.get('frames') == [0, 1], '安装内浏览器渲染自检未返回两帧')
    code = ("from PIL import Image;import sys;from pathlib import Path;p=Path(sys.argv[1]);"
            "a=Image.open(p/'frame-0.png').convert('RGB');b=Image.open(p/'frame-1.png').convert('RGB');"
            "assert a.size==b.size==(96,96);assert a.getpixel((12,12))==(255,255,255);"
            "assert b.getpixel((12,12))==(22,88,212);assert b.getpixel((28,12))==(255,255,255);print('pixel-check-pass')")
    execute([tools['python'], '-s', '-c', code, output], root, env)
    files = {name: core.digest(output / name) for name in ['codec.mp4', 'frame-0.png', 'frame-1.png']}
    receipt = {'schema': 'haike.template-selftest/1', 'status': 'passed', 'capability_sha256': capability_sha256,
               'install_root': str(root),
               'created_at': datetime.now(timezone.utc).isoformat(), 'scope': 'installed-dependencies-only',
               'native_profiles': probes, 'tool_hashes': {k: core.digest(p) for k, p in tools.items()},
               'files': files, 'paid_calls': 0, 'episode_review': False}
    core._atomic_write(output / 'result.json', core.json_bytes(receipt))
    core._atomic_write(core.safe_path(root, '.local/template-selftests/latest.json'),
                       core.json_bytes({'directory': output.relative_to(root).as_posix(), 'sha256': core.digest(output / 'result.json')}))
    return {'status': 'passed', 'receipt': str(output / 'result.json'), 'scope': receipt['scope'], 'paid_calls': 0}


def recorded(root, capability_sha256):
    root = Path(root).resolve()
    try:
        pointer = core._read(core.safe_path(root, '.local/template-selftests/latest.json'))
        directory = pointer.get('directory', '')
        require(isinstance(directory, str) and directory.startswith('.local/template-selftests/'), '自检回执位置无效')
        folder = core.safe_path(root, directory); path = folder / 'result.json'
        require(path.is_file() and core.digest(path) == pointer.get('sha256'), '自检回执已改变')
        value = core._read(path)
        require(value.get('schema') == 'haike.template-selftest/1' and value.get('status') == 'passed'
                and value.get('install_root') == str(root) and value.get('capability_sha256') == capability_sha256,
                '自检身份不匹配')
        tool_names = {'python': 'runtime/python/python.exe', 'node': 'runtime/node/node.exe',
                      'ffmpeg': 'runtime/ffmpeg/bin/ffmpeg.exe', 'ffprobe': 'runtime/ffmpeg/bin/ffprobe.exe',
                      'browser': 'runtime/browser/chrome-headless-shell.exe'}
        require(set(value.get('tool_hashes', {})) == set(tool_names)
                and all(core.digest(core.safe_path(root, tool_names[k])) == digest for k, digest in value['tool_hashes'].items()),
                '自检工具已改变')
        require(set(value.get('files', {})) == {'codec.mp4', 'frame-0.png', 'frame-1.png'}
                and all(core.digest(core.safe_path(folder, name)) == digest for name, digest in value['files'].items()),
                '自检产物已改变')
        return {'status': 'passed', 'receipt': str(path), 'scope': value['scope'], 'paid_calls': 0}
    except (ValueError, OSError, KeyError, TypeError):
        return {'status': 'pending'}
