"""Full-duration native renderer validation for all 18 preferred motion styles.

Only curated synthetic fixtures and locally generated picture/sound are used.
This sandbox does not submit a production queue job, forge ASR/HQ/payment
receipts, bypass a production approval or assert private creative acceptance.
"""
from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Haike_video'))
FIXTURES = ROOT / 'Haike_video/tests/fixtures/native-motion'
WORK = ROOT / '.local/mac-motion-tests'


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def call(argv, env, *, cwd=ROOT, timeout=14400):
    subprocess.run([str(v) for v in argv], cwd=cwd, env=env, check=True, timeout=timeout)


def link(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def remove_work(path):
    path = Path(path).resolve()
    if not path.is_relative_to(WORK.resolve()) or path == WORK.resolve() or path.is_symlink():
        raise ValueError('Test cleanup must stay inside this harness work directory')
    if path.is_dir():
        shutil.rmtree(path)


def assets(env):
    folder = WORK / 'synthetic-assets'; folder.mkdir(parents=True, exist_ok=True)
    font = ROOT / 'Haike_video/remotion-composer/a2e/public/fonts/NotoSansSC.ttf'
    if not (folder / 'font.ttf').is_file():
        link(font, folder / 'font.ttf')
    if not (folder / 'video.mp4').is_file():
        call([env['FFMPEG_BINARY'], '-v', 'error', '-n', '-f', 'lavfi', '-i',
              'color=c=0x154e63:s=1080x1920:r=30:d=180', '-vf',
              "drawgrid=w=120:h=120:t=2:c=white@0.4,drawtext=fontfile=font.ttf:text='TEST %{n}':fontsize=100:fontcolor=yellow:x='mod(t*120,w-200)':y='h/2+sin(t)*h/4'",
              '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '24', '-pix_fmt', 'yuv420p', '-an', 'video.mp4'], env, cwd=folder)
        call([env['FFMPEG_BINARY'], '-v', 'error', '-n', '-i', folder / 'video.mp4', '-frames:v', '1', folder / 'sample.png'], env)
    return folder


def public_inputs(folder, fixture, env, common):
    public = folder / 'public'; public.mkdir()
    for name in ('font.ttf', 'sample.png', 'video.mp4'):
        link(common / name, public / name)
    link(common / 'video.mp4', public / 'presenter.mp4')
    def filenames(value):
        if isinstance(value, dict):
            return set().union(*(filenames(v) for v in value.values())) if value else set()
        if isinstance(value, list):
            return set().union(*(filenames(v) for v in value)) if value else set()
        return {value} if isinstance(value, str) and value.endswith(('.mp4', '.png', '.jpg', '.jpeg', '.webp')) else set()
    for name in filenames(fixture['props']):
        assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,110}\.(?:mp4|png|jpg|jpeg|webp)', name)
        if not (public / name).exists():
            link(common / ('video.mp4' if name.endswith('.mp4') else 'sample.png'), public / name)
    call([env['FFMPEG_BINARY'], '-v', 'error', '-n', '-f', 'lavfi', '-i',
          'sine=frequency=440:sample_rate=48000:duration=' + str(fixture['duration']),
          '-af', 'volume=0.04', '-c:a', 'pcm_s16le', '-ac', '2', public / 'master.wav'], env)
    return public


ENTRIES = {
    'numbered': ('numbered02-04-production-v1/index.tsx', 'FullNumberedMotion'),
    'field-notes': ('field-notes-video-v1/index.tsx', 'FieldNotesVideo'),
    'chromatic06': ('chromatic-06-production-v1/Scene.tsx', 'Chromatic06Production'),
    'chromatic-suite': ('chromatic-suite-production-v1/Scene.tsx', 'ChromaticSuiteProduction'),
    'knowledge': ('knowledge-reference-public-v3/index.tsx', 'KnowledgeReferencePublic'),
    'dark': ('motiongit-public-components-v2/dark-v2/template/index.tsx', 'DarkFull'),
    'promo': ('promo-reference-phase-v3/index.tsx', 'PromoReferenceFull'),
}


def render_remotion(folder, fixture, env, public):
    p = deepcopy(fixture['props']); kind = fixture['kind']
    if kind == 'dark':
        p = p['props']
        # Exercise the installed native dependency seam as well as the original TSX.
        from backlot import motion_native_runtime as native
        native.environment(native.root(), native.COMPOSER, native.root() / 'ffmpeg', dark=True)
    if kind in {'numbered', 'field-notes', 'knowledge'}:
        write(public / 'episode.json', p)
        props = {}
    else:
        props = p
    if kind == 'knowledge':
        font_source = ROOT / 'Haike_video/templates/knowledge-reference-public-v3/fonts'
        if not font_source.is_dir():
            font_source = ROOT / 'Haike_video/templates/knowledge-reference-public-v1/fonts'
        for font in ('LXGWWenKai-Medium.ttf', 'LongCang.ttf', 'Fraunces.ttf', 'JetBrainsMono.ttf'):
            path = next((f for f in (ROOT / 'Haike_video/templates').rglob(font) if 'node_modules' not in f.parts), None)
            if path is None:
                raise ValueError('Exact OFL knowledge font missing: ' + font)
            link(path, public / 'fonts' / font)
    fps = p.get('fps', 30); frames = p.get('durationFrames', p.get('durationInFrames'))
    entry, composition = ENTRIES[kind]
    raw = folder / 'raw.mp4'
    request = {'templateId': fixture['template_id'], 'folder': str(folder), 'public': str(public),
               'entry': 'Haike_video/templates/' + entry, 'composition': composition, 'props': props,
               'frames': frames, 'fps': fps, 'output': str(raw), 'browser': env['REMOTION_BROWSER_EXECUTABLE'],
               'mezzanine': kind in {'dark', 'promo'}}
    write(folder / 'render-input.json', request)
    call([env['HAIKE_NODE_EXECUTABLE'], ROOT / 'scripts/mac-motion-render.cjs', folder / 'render-input.json'], env)
    output = folder / 'full.mp4'
    encoding = ['-c:v', 'libx264', '-preset', 'fast', '-b:v', '20500k', '-minrate', '20500k', '-maxrate', '20500k',
                '-bufsize', '2000k', '-x264-params', 'nal-hrd=cbr:force-cfr=1:filler=1', '-pix_fmt', 'yuv420p'] if kind in {'dark', 'promo'} else ['-c:v', 'copy']
    call([env['FFMPEG_BINARY'], '-v', 'error', '-n', '-i', raw, '-i', public / 'master.wav',
          '-map', '0:v:0', '-map', '1:a:0', '-t', str(frames / fps), *encoding,
          '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', output], env)
    return output, fps, frames, p


def render_html(folder, fixture, env, public):
    from backlot import motion_native_runtime as native
    from backlot.motion_platform import owned_module
    module = 'motion_public_poster_execution_v3' if fixture['template_id'] == 'vibrant-poster' else 'motion_public_execution_v2'
    execution = owned_module('backlot.' + module)
    execution.environment(native.root(), native.HTML, native.root() / 'ffmpeg')
    project = folder / 'synthetic-parent'; source = project / 'assets/motion-public'; source.mkdir(parents=True)
    for name, origin in [('video.mp4', 'video.mp4'), ('presenter.mp4', 'video.mp4'), ('voice.wav', 'master.wav'), ('music.wav', 'master.wav')]:
        link(public / origin, source / name)
    for path in public.iterdir():
        if path.suffix in {'.mp4', '.png', '.jpg', '.jpeg', '.webp'} and not (source / path.name).exists():
            link(path, source / path.name)
    spec = deepcopy(fixture['props'])
    spec['audio_sha256'] = sha(source / 'voice.wav')
    request = {'spec': spec, 'origins': {p.name: {} for p in source.iterdir()},
               'input_engine': 'observed-controls/3' if fixture['template_id'] == 'vibrant-poster' else 'observed-controls/2',
               'tool_root': str(native.root()), 'dependency_root': str(native.HTML), 'ffmpeg_root': str(native.root() / 'ffmpeg'),
               'frames': spec['frames'], 'request_sha256': sha(FIXTURES / (fixture['template_id'] + '.json')),
               'source_receipts': {'fixture_scope': 'local synthetic media coverage only, no HQ claim',
                                    'avatar_derivation': {'audio_speed_changed': False, 'timeline_windows': [[0, fixture['duration']]]}}}
    # This guard bounds only the sandbox fixture; it is not a queue claim.
    checksum = request['request_sha256']
    def guard():
        if sha(FIXTURES / (fixture['template_id'] + '.json')) != checksum:
            raise ValueError('Synthetic sandbox fixture changed during execution')
    request['_phase_guard'] = guard
    execution.build_project(project, folder, request)
    generated = folder / 'project'
    output = folder / 'full.mp4'
    # A sandbox renderer export does not call the production render phase or
    # manufacture the actual-image approval required for production admission.
    call([native.binary('node'), folder / 'runtime-source/scripts/render_project.mjs', generated / 'index.html',
          '--playwright-module', native.HTML / 'node_modules/playwright-core', '--browser', native.binary('browser'),
          '--fps', str(spec['fps']), '--width', str(spec['width']), '--height', str(spec['height']),
          '--output', output, '--audio', generated / 'final.wav'], env)
    return output, spec['fps'], spec['frames'], spec


def verify_output(output, fixture, fps, frames, props, env):
    probe = json.loads(subprocess.check_output([env['FFPROBE_BINARY'], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)], env=env))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert video['codec_name'] == 'h264' and video['pix_fmt'] == 'yuv420p'
    assert int(video['nb_frames']) == frames and abs(float(video['duration']) - frames / fps) < .04
    expected = (1440, 1800) if fixture['kind'] == 'dark' else ((1920, 1080) if fixture['kind'] == 'promo' or fixture['template_id'] == 'nana-mint-explainer-v1' else (1080, 1920))
    assert (video['width'], video['height']) == expected
    assert int(video['bit_rate']) >= 20_000_000 and min(video['width'], video['height']) >= 1080
    assert audio['sample_rate'] == '48000' and audio['channels'] == 2
    sound = subprocess.run([env['FFMPEG_BINARY'], '-v', 'info', '-i', str(output), '-af', 'volumedetect', '-f', 'null', '-'], env=env, capture_output=True, text=True, check=True)
    peak = float(re.search(r'max_volume:\s*([-\d.]+) dB', sound.stderr)[1])
    assert peak > -70, 'AAC stream must contain an actual nonzero test signal'
    call([env['FFMPEG_BINARY'], '-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'], env)
    md5 = subprocess.check_output([env['FFMPEG_BINARY'], '-v', 'error', '-i', str(output), '-map', '0:v:0', '-vf', 'fps=2,scale=128:-2', '-f', 'framemd5', '-'], env=env, text=True)
    hashes = [v.rsplit(',', 1)[-1].strip() for v in md5.splitlines() if not v.startswith('#')]
    assert len(set(hashes)) > 8, 'Actual encoded picture must move through the complete template'
    picture = output.parent / 'contacts.jpg'
    interval = max(fps, frames // 16)
    call([env['FFMPEG_BINARY'], '-v', 'error', '-n', '-i', output, '-vf',
          f"select='not(mod(n,{interval}))+eq(n,{frames-1})',scale=270:-2,tile=4x5:padding=4:margin=4", '-frames:v', '1', picture], env)
    return {'template_id': fixture['template_id'], 'version': fixture['preferred_version'], 'fixture_sha256': sha(FIXTURES / (fixture['template_id'] + '.json')),
            'ok': True, 'full_duration': frames / fps, 'frames': frames, 'fps': fps, 'width': video['width'], 'height': video['height'],
            'video_bitrate': int(video['bit_rate']), 'audio': '48kHz stereo AAC', 'audio_peak_dbfs': peak, 'full_decode': 'pass', 'moving_picture': True,
            'encoded_sha256': sha(output), 'contacts_sha256': sha(picture), 'canonical_visual_renderer': ENTRIES.get(fixture['kind'], ('observed-controls JS + retained HTML renderer', ''))[0],
            'paid_calls': 0, 'production_queue_submitted': False, 'real_ASR_or_HQ_acceptance': False,
            'scope': 'complete synthetic native renderer export; human visual/contact review recorded separately'}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--shard', type=int, default=0); parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--only', choices=[r['template_id'] for r in read(FIXTURES / 'manifest.json')['templates']]); args = parser.parse_args()
    assert 0 <= args.shard < args.shards
    module = importlib.util.spec_from_file_location('mac_deploy_motion', ROOT / 'scripts/mac-deploy.py')
    deploy = importlib.util.module_from_spec(module); module.loader.exec_module(deploy)
    env = deploy.environment(deploy.architecture()); env['PYTHONDONTWRITEBYTECODE'] = '1'; os.environ.update(env)
    from backlot.motion_platform import verify
    verify()
    WORK.mkdir(parents=True, exist_ok=True); common = assets(env)
    rows = read(FIXTURES / 'manifest.json')['templates']; results = []
    for index, row in enumerate(rows):
        if (args.only and row['template_id'] != args.only) or (not args.only and index % args.shards != args.shard):
            continue
        path = FIXTURES / row['file']; assert sha(path) == row['sha256']
        fixture = read(path); folder = WORK / fixture['template_id']
        receipt_path = folder / 'receipt.json'
        if receipt_path.is_file():
            receipt = read(receipt_path)
            assert receipt['fixture_sha256'] == row['sha256'] and receipt['encoded_sha256'] == sha(folder / 'full.mp4')
            results.append(receipt); continue
        if folder.exists():
            raise ValueError('Preserve incomplete test evidence before explicitly choosing a fresh harness directory')
        folder.mkdir(); started = time.monotonic(); public = public_inputs(folder, fixture, env, common)
        output, fps, frames, props = render_html(folder, fixture, env, public) if fixture['kind'] == 'html' else render_remotion(folder, fixture, env, public)
        receipt = verify_output(output, fixture, fps, frames, props, env)
        receipt.update(arch=deploy.architecture(), elapsed_seconds=round(time.monotonic()-started), github_run=os.environ.get('GITHUB_RUN_ID'))
        write(receipt_path, receipt); results.append(receipt); print(json.dumps(receipt, ensure_ascii=False), flush=True)
        for name in ('bundle', 'public', 'project', 'runtime-source', 'synthetic-parent', 'media-cache'):
            remove_work(folder / name)
        (folder / 'raw.mp4').unlink(missing_ok=True)
        remove_work(WORK / 'media-cache')
    summary = {'ok': True, 'arch': deploy.architecture(), 'template_count': len(results), 'shard': args.shard, 'shards': args.shards,
               'all_18': len(results) == 18, 'results': results, 'paid_calls': 0, 'physical_colleague_machine': False,
               'source_commit': os.environ.get('HAIKE_SOURCE_COMMIT', os.environ.get('GITHUB_SHA')),
               'derivation_sha256': sha(ROOT / 'Haike_video/config/motion-native-v1.json'),
               'runtime_spec_sha256': sha(ROOT / '_distribution-tools/macos-runtime.json')}
    write(WORK / ('summary-' + str(args.shard) + '.json'), summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
