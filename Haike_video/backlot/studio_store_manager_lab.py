"""Queue-owned store-manager films using original media and a CRF1 render master."""
from pathlib import Path
import shutil
import subprocess

from backlot.studio import atomic_private
from backlot.studio_investment_recompose import KIND, fingerprint
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha

CONTRACT = 'store-manager-lab-v1'
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'templates/store-manager-lab-v1'
PROFILE = {'codec': 'h264', 'crf': 1, 'image_format': 'png', 'x264_preset': 'fast', 'pixel_format': 'yuv444p', 'scale': 1}
EXPORT = {'video_bitrate': 20500000, 'minimum_measured_bitrate': 20000000, 'audio_bitrate': 192000, 'pixel_format': 'yuv420p'}


def runtime():
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    files = [Path(__file__), TEMPLATE / 'index.tsx', ROOT / 'backlot/production_queue_worker.py', ROOT / 'tools/video/video_compose.py', Path('C:/Windows/Fonts/msyh.ttc'), Path('C:/Windows/Fonts/msyhbd.ttc'), Path('C:/Windows/Fonts/simhei.ttf'), Path('C:/Windows/Fonts/simsun.ttc')]
    files.extend(Path(p) for p in resolve_ffmpeg_pair())
    return {str(p): sha(p) for p in files}


def prepare(queue, props, sources, title):
    if props.get('style') not in (14, 15, 16, 17) or not isinstance(props.get('durationFrames'), int) or props['durationFrames'] != 180:
        raise WorkError('新店长短样仅支持14–17及6秒')
    required = {'avatar.mp4', 'master.wav', 'audio-receipt.json', 'asr.json'} | {s['src'] for s in props['shots']}
    if set(sources) != required or any(Path(n).name != n or '/' in n or '\\' in n for n in sources):
        raise WorkError('素材槽不完整或文件名无效')
    for s in props['shots']:
        if not 0 < s['frames'] <= 120 or s['offset'] < 0 or s['from'] < 0 or s['from'] + s['frames'] > props['durationFrames']:
            raise WorkError('实拍镜头时长或入出点无效')
    origins = {n: {'path': str(Path(p).resolve()), 'sha256': sha(p)} for n, p in sources.items()}
    core = {'contract': CONTRACT, 'title': title, 'props': props, 'origins': origins, 'runtime': runtime(), 'profile': PROFILE, 'export': EXPORT, 'cloud_calls': 0, 'publication': False}
    project_id = 'studio-' + fingerprint(core)[:16]
    core['project_id'] = project_id
    digest = fingerprint(core)
    request = {**core, 'request_sha256': digest, 'render_id': 'store-manager-' + digest[:20]}
    project = queue.projects_root / project_id
    frozen = project / 'artifacts/store-manager-request.json'
    if frozen.exists():
        request = read_json(frozen)
        validate(queue, request)
        return request
    from lib.checkpoint import init_project
    init_project(project_id, title=title, pipeline_type='animated-explainer', pipeline_dir=queue.projects_root)
    assets = project / 'assets/store-manager'
    assets.mkdir(parents=True, exist_ok=True)
    for name, item in origins.items():
        shutil.copy2(item['path'], assets / name)
    atomic_private(frozen, request)
    validate(queue, request)
    return request


def validate(queue, r):
    digest = fingerprint({k: v for k, v in r.items() if k not in ('request_sha256', 'render_id')})
    if r.get('contract') != CONTRACT or r.get('request_sha256') != digest or r.get('render_id') != 'store-manager-' + digest[:20] or r.get('profile') != PROFILE or r.get('export') != EXPORT:
        raise WorkError('店长模板冻结身份无效')
    project = WorkCatalog(queue.projects_root).project(r['project_id'])
    if read_json(project / 'artifacts/store-manager-request.json') != r:
        raise WorkError('冻结请求不一致')
    for name, item in r['origins'].items():
        if sha(regular_path(project / 'assets/store-manager' / name, project)) != item['sha256']:
            raise WorkError('冻结素材内容已变化')
    folder = project / 'renders' / r['render_id']
    receipt = read_json(folder / 'result.json')
    if receipt:
        if receipt.get('request_sha256') != digest or sha(folder / 'avatar-preview.mp4') != receipt.get('output_sha256'):
            raise WorkError('已完成成片身份不一致')
    elif runtime() != r['runtime']:
        raise WorkError('实现已变化，需新建冻结请求')
    return project


def submit(queue, r):
    validate(queue, r)
    return queue.submit(project_id=r['project_id'], kind=KIND, source='codex', priority='normal', parent_job_id=r['render_id'], frozen_request=r, idempotency_key=CONTRACT + ':' + r['request_sha256'], start_paused=True)


def run(queue, job):
    r = job['frozen_request']
    try:
        if job['kind'] != KIND or job['project_id'] != r['project_id']:
            raise WorkError('队列身份不匹配')
        project = validate(queue, r)
        folder = project / 'renders' / r['render_id']
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / 'avatar-preview.mp4'
        if not read_json(folder / 'result.json'):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            from lib.ffmpeg_locator import resolve_ffmpeg_pair
            ffmpeg, ffprobe = resolve_ffmpeg_pair()
            public = folder / 'public'
            public.mkdir(exist_ok=True)
            for name in r['origins']:
                shutil.copy2(project / 'assets/store-manager' / name, public / name)
            shutil.copy2(TEMPLATE / 'index.tsx', folder / 'index.tsx')
            atomic_private(folder / 'props.json', r['props'])
            duration = r['props']['durationFrames'] / 30
            edits = {'render_runtime': 'remotion', 'composition_mode': 'atelier', 'renderer_family': 'bespoke', 'timeline': {'duration_seconds': duration}, 'bespoke': {'entry': str(folder / 'index.tsx'), 'composition_id': 'HaikeStoreManager', 'art_direction': str(TEMPLATE / 'README.md'), 'props_path': str(folder / 'props.json'), 'public_dir': str(public), 'concurrency': 2, **PROFILE}}
            raw = folder / 'mezzanine-crf1.mp4'
            result = VideoCompose().execute({'operation': 'render', 'output_path': str(raw), 'edit_decisions': edits, 'asset_manifest': {'assets': []}, 'script_text': read_json(public / 'asr.json').get('text', '')})
            if not result.success:
                raise WorkError(str(result.error), 'unavailable')
            command = [ffmpeg, '-y', '-v', 'error', '-i', str(raw), '-i', str(public / 'master.wav'), '-map', '0:v:0', '-map', '1:a:0', '-t', str(duration), '-c:v', 'libx264', '-preset', 'slow', '-b:v', '20500k', '-minrate', '20500k', '-maxrate', '20500k', '-bufsize', '2000k', '-x264-params', 'nal-hrd=cbr:force-cfr=1:filler=1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(output)]
            subprocess.run(command, check=True, capture_output=True, creationflags=0x08000000)
            import json
            streams = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(output)], creationflags=0x08000000))
            video = next(s for s in streams['streams'] if s['codec_type'] == 'video')
            info, audio = media_probe(output), measure_audio(output)
            if video['width'] != 1440 or video['height'] != 1800 or video['codec_name'] != 'h264' or abs(info['duration'] - duration) > .08 or int(video.get('bit_rate', 0)) < EXPORT['minimum_measured_bitrate'] or audio['true_peak_dbtp'] > -1.5:
                raise WorkError('成片尺寸、码率、时长或声音峰值未通过', 'unavailable')
            subprocess.run([ffmpeg, '-v', 'error', '-i', str(output), '-f', 'null', '-'], check=True, capture_output=True, creationflags=0x08000000)
            atomic_private(folder / 'quality.json', {'media': info, 'video_stream': video, 'audio': audio, 'render_command': (result.data or {}).get('render_command'), 'export_command': command, 'full_decode': 'passed', 'visual_review': 'pending', 'listening': 'pending'})
            validate(queue, r)
            atomic_private(folder / 'result.json', {'request_sha256': r['request_sha256'], 'output_sha256': sha(output), 'quality_sha256': sha(folder / 'quality.json'), 'cloud_calls': 0, 'publication': False})
        work = WorkCatalog(queue.projects_root).register(r['project_id'], output, work_key='main', mode='manual', event_id=job['job_id'], quality_passed=False, actor='store-manager', title=r['title'], summary='店长账号6秒风格测试；4:5；视频流实测≥20Mbps；待视听审阅，未发布')
        return {'status': 'completed', 'stage': '店长账号成片完成，待审阅', 'result': {'output_path': str(output), 'output_sha256': sha(output), 'work_id': work['work_id'], 'cloud_calls': 0}}
    except WorkError as e:
        return {'status': 'failed', 'stage': str(e), 'error': {'type': 'StoreManager', 'message': str(e)}, 'retryable': e.code == 'unavailable', 'safe_resume_point': 'store_manager'}
