"""Offline, manifest-driven template reproduction. Never calls cloud services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def local(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Path outside package: ' + name)
    return path


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def verify():
    records = read(ROOT / 'SHA256-MANIFEST.json')
    failures = []
    for row in records:
        path = local(row['file'])
        if not path.is_file() or path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
            failures.append(row['file'])
    if failures:
        raise ValueError('Package integrity failed: ' + ', '.join(failures[:20]))
    print('SHA256 verified:', len(records), 'files')


def doctor():
    missing = []
    for name in ('node', 'npm', 'ffmpeg', 'ffprobe'):
        path = shutil.which(name)
        print(name, path or 'MISSING')
        if not path:
            missing.append(name)
    if sys.version_info < (3, 10):
        missing.append('Python >=3.10 (recommended 3.12)')
    if shutil.which('node'):
        version = subprocess.check_output([shutil.which('node'), '--version'], encoding='utf-8').strip()
        if int(version.lstrip('v').split('.')[0]) < 22:
            missing.append('Node.js >=22')
    if not (ROOT / 'node_modules/@remotion/cli/remotion-cli.js').is_file():
        missing.append('npm ci')
    print('OS:', sys.platform, '| Mac hardware verification must run on the recipient machine.')
    print('Fonts: bundled OFL fonts are a portable substitute; exact original fonts are not distributed.')
    if missing:
        raise ValueError('Install missing dependencies: ' + ', '.join(missing))


def materialize(job):
    work = ROOT / '.work' / job['id']
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'source'
    shutil.copytree(local(job['source']), source, dirs_exist_ok=True)
    public = work / 'public'
    public.mkdir(exist_ok=True)
    for name, row in job['assets'].items():
        destination = (public / name).resolve()
        if not destination.is_relative_to(public.resolve()):
            raise ValueError('Invalid public asset name')
        original = local(row['file'])
        if digest(original) != row['sha256']:
            raise ValueError('Asset changed: ' + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if digest(destination) == row['sha256']:
                continue
            raise ValueError('Work asset changed; use a separate job: ' + name)
        # Copy, rather than hardlink: editing a work asset must not mutate the shared pool.
        shutil.copy2(original, destination)
    shutil.copytree(ROOT / 'fonts', public / 'kit-fonts', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'tools/font-loader.ts', source / 'font-loader.ts')
    entry = source / job['entry']
    original = entry.read_text(encoding='utf-8-sig')
    if 'registerRoot(' not in original:
        raise ValueError('Unsupported entry; expected explicit registerRoot call')
    entry.write_text("import {registerRootWithFonts} from './font-loader';\n" +
                     original.replace('registerRoot(', 'registerRootWithFonts('), encoding='utf-8')
    return work, entry, public


def render(job_id, smoke=False):
    doctor()
    manifest = read(ROOT / 'KIT.json')
    job = next((j for j in manifest['jobs'] if j['id'] == job_id), None)
    if job is None:
        raise ValueError('No frozen example for this ID. Run list; source-only designs require new input validation.')
    work, entry, public = materialize(job)
    output_dir = ROOT / 'exports'
    output_dir.mkdir(exist_ok=True)
    output = output_dir / (job_id + ('-smoke' if smoke else '') + '.mp4')
    if output.exists():
        raise ValueError('Output already exists; preserve or rename it before another render: ' + str(output))
    frames = min(6, job['frames']) if smoke else job['frames']
    duration = frames / job['fps']
    intermediate = work / ('smoke-mezzanine.mp4' if smoke else 'mezzanine.mp4')
    command = [shutil.which('node'), ROOT / 'node_modules/@remotion/cli/remotion-cli.js',
               'render', entry, job['composition'], intermediate,
               '--props=' + str(local(job['props'])), '--public-dir=' + str(public),
               '--codec=h264', '--image-format=png', '--crf=1', '--x264-preset=fast',
               '--pixel-format=yuv444p', '--concurrency=2', '--muted', '--overwrite']
    if smoke:
        command.append('--frames=0-' + str(frames - 1))
    receipt = work / 'run.json'
    receipt.write_text(json.dumps({'status': 'rendering', 'job': job_id, 'cloud_calls': 0,
                                  'font_profile': 'portable-ofl-v1', 'smoke': smoke}, indent=2), encoding='utf-8')
    run(command)
    cmd = [shutil.which('ffmpeg'), '-v', 'error', '-n', '-i', intermediate]
    if job.get('audio'):
        cmd += ['-i', public / job['audio'], '-map', '0:v:0', '-map', '1:a:0']
    else:
        cmd += ['-map', '0:v:0', '-an']
    cmd += ['-t', str(duration), '-c:v', 'libx264', '-preset', 'slow', '-b:v', '20500k',
            '-minrate', '20500k', '-maxrate', '20500k', '-bufsize', '2000k',
            '-x264-params', 'nal-hrd=cbr:force-cfr=1:filler=1', '-pix_fmt', 'yuv420p']
    if job.get('audio'):
        cmd += ['-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2']
    cmd += ['-movflags', '+faststart', output]
    run(cmd)
    info = json.loads(subprocess.check_output([shutil.which('ffprobe'), '-v', 'error',
        '-show_streams', '-show_format', '-of', 'json', str(output)], encoding='utf-8'))
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (video['width'], video['height']) != (job['width'], job['height']):
        raise ValueError('Unexpected output dimensions')
    if int(video.get('nb_frames', 0)) != frames or (not smoke and int(video.get('bit_rate', 0)) < 20000000):
        raise ValueError('Unexpected frame count or bitrate; keep file for diagnosis')
    run([shutil.which('ffmpeg'), '-v', 'error', '-i', output, '-f', 'null', '-'])
    receipt.write_text(json.dumps({'status': 'smoke_pass' if smoke else 'technical_pass', 'output': output.name,
        'sha256': digest(output), 'media': info, 'smoke': smoke, 'cloud_calls': 0,
        'font_profile': 'portable-ofl-v1', 'visual_review': 'pending', 'device_listening': 'pending',
        'platform': sys.platform}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Export:', output)
    print('Review subtitle widths, font substitutions, avatar entry/exit and sound before use.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'verify', 'doctor', 'render'])
    parser.add_argument('id', nargs='?')
    parser.add_argument('--smoke', action='store_true', help='Render six frames only; not a full-film acceptance')
    args = parser.parse_args()
    if args.command == 'list':
        for item in read(ROOT / 'KIT.json')['jobs']:
            print(item['id'], item['width'], 'x', item['height'], item['frames'] / item['fps'], 's')
    elif args.command == 'verify':
        verify()
    elif args.command == 'doctor':
        doctor()
    else:
        if not args.id:
            parser.error('render requires a job id')
        render(args.id, args.smoke)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('STOP:', error, file=sys.stderr)
        sys.exit(1)
