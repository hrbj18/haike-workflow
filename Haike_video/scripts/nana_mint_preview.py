"""Frozen local reference-template checks, executed through the unified queue."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.work_catalog import WorkCatalog
from lib.checkpoint import init_project

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'templates/nana-mint-explainer-v1'
CONTRACT = 'haike-nana-mint-preview-v1'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def critical_frames(content, explicit=None):
    total = round(content['duration'] * content['fps'])
    if explicit:
        frames = sorted(set(int(n) for n in explicit.split(',')))
    else:
        states = {0, total - 1}
        for scene in content['scenes']:
            first, last = round(scene['start'] * content['fps']), round(scene['end'] * content['fps'])
            states.update([min(last - 1, first + 24), max(first, last - 2)])
            states.update(min(last - 1, first + round(at * content['fps']) + 9) for at in scene.get('cues', {}).values())
        frames = sorted(states)
    if any(n < 0 or n >= total for n in frames):
        raise ValueError('检查帧超出完整声音时钟。')
    return frames


def validate(data):
    loader = importlib.util.spec_from_file_location('nana_prepare', TEMPLATE / 'prepare.py')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    episode = read(data / 'episode.json')
    if episode.get('contract') != 'haike-nana-mint-episode-v1' or episode.get('paid_calls') != 0:
        raise ValueError('本入口只接受本地零新增付费的模板输入。')
    module.validate_episode(episode['content'])
    if read(data / 'public/content.json') != episode['content']:
        raise ValueError('浏览器内容与冻结的本期输入不一致。')
    for name, item in episode['files'].items():
        actual = (data / 'public' / name).resolve()
        if not actual.is_relative_to((data / 'public').resolve()) or str(actual) != item['path'] or sha(actual) != item['sha256']:
            raise ValueError('本期媒体身份已改变：' + name)
    return episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, help='Runtime owner; defaults to --install-root. Queue/projects still belong to --install-root.')
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--mode', choices=['frames', 'render'], default='frames')
    parser.add_argument('--frames', help='Explicit critical frames; default derives all scene/cue boundaries from this episode clock.')
    args = parser.parse_args()
    install, data = args.install_root.resolve(), args.data.resolve()
    episode = validate(data)
    content = episode['content']
    runtime_root = args.runtime_root.resolve() if args.runtime_root else install
    runtime = {name: runtime_root / part for name, part in {'node': 'runtime/node/node.exe', 'browser': 'runtime/browser/chrome-headless-shell.exe', 'ffmpeg': 'runtime/ffmpeg/bin/ffmpeg.exe', 'ffprobe': 'runtime/ffmpeg/bin/ffprobe.exe'}.items()}
    if not all(p.is_file() for p in runtime.values()) or not (data / 'bundle/index.html').is_file():
        raise ValueError('请核对离线运行时并先构建同源检查包。')
    total = round(content['duration'] * content['fps'])
    frames = critical_frames(content, args.frames)
    paths = [Path(__file__), data / 'episode.json', ROOT / 'templates/warm-workbench-v1/webpack.cjs', ROOT / 'remotion-composer/package-lock.json', *runtime.values()]
    for directory in [TEMPLATE, ROOT / 'motion-components/snapcn', data / 'public', data / 'bundle']:
        paths += [p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() != '.md' and not {'node_modules', '__pycache__'}.intersection(p.parts)]
    identity = {str(p): sha(p) for p in sorted(set(paths))}
    core = {'contract': CONTRACT, 'mode': args.mode, 'frames': frames if args.mode == 'frames' else [], 'identity': identity, 'duration': content['duration'], 'provider': 'local-only', 'paid_calls': 0, 'scope': 'private reference-based development; no publication'}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    if args.mode == 'render':
        review = read(data / 'design-review.json')
        # Require actual reviewed images AND this exact implementation/media/bundle.
        if review.get('status') != 'pass' or not review.get('frame_identity'):
            raise ValueError('完整导出前需实际查看本期关键状态。')
        for name, value in review['frame_identity'].items():
            if sha(name) != value:
                raise ValueError('已审核图片身份已改变。')
        if review.get('identity') != identity:
            raise ValueError('源码、媒体或检查包已变化，请重新生成并审核检查帧。')
    projects = install / 'Haike_video/projects'
    project_id, render_id = 'nana-mint-' + digest[:12], args.mode + '-' + digest[:16]
    init_project(project_id, title='薄荷章节讲解 · Nana参考模板', pipeline_type='animated-explainer', pipeline_dir=projects)
    out = projects / project_id / 'renders' / render_id
    out.mkdir(parents=True, exist_ok=True)
    frozen = {**core, 'project_id': project_id, 'render_id': render_id, 'data': str(data)}
    write(projects / project_id / 'artifacts/nana-mint-request.json', frozen)
    queue = ProductionQueue(install / 'Haike_video/.backlot/production-queue.sqlite3', projects)
    job = queue.submit(project_id=project_id, kind='studio_investment_recompose', source='codex', priority='normal', parent_job_id=render_id, frozen_request=frozen, idempotency_key=CONTRACT + ':' + digest, start_paused=True)
    ledger = read(data / 'jobs.json') if (data / 'jobs.json').exists() else []
    receipt = {'mode': args.mode, 'job_id': job['job_id'], 'project_id': project_id, 'output': str(out), 'request_sha256': digest}
    if not any(row['job_id'] == job['job_id'] for row in ledger):
        ledger.append(receipt); write(data / 'jobs.json', ledger)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)

    def execute(claim):
        if claim['frozen_request']['contract'] != CONTRACT:
            raise ValueError('执行合同不同。')
        for name, value in claim['frozen_request']['identity'].items():
            if sha(name) != value:
                raise ValueError('冻结文件变化：' + name)
        target = out / ('frames' if args.mode == 'frames' else 'silent.mp4')
        cmd = [str(runtime['node']), str(TEMPLATE / 'render.cjs'), args.mode, str(data), str(target), str(runtime['browser']), ','.join(map(str, frames))]
        with (out / 'render.log').open('w', encoding='utf-8') as log:
            subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=3600, creationflags=0x08000000)
        if args.mode == 'frames':
            proof = {str(n): {'file': str(target / f'{n:04d}.png'), 'sha256': sha(target / f'{n:04d}.png')} for n in frames}
            write(out / 'frame-proofs.json', proof)
            write(data / 'latest-frame-job.json', {**receipt, 'identity': identity, 'proof': proof})
            return {'status': 'completed', 'stage': '薄荷章节模板检查帧完成', 'result': {'preview_dir': str(target), 'frames': len(proof)}}
        final = out / 'nana-mint-template.mp4'
        subprocess.run([str(runtime['ffmpeg']), '-nostdin', '-v', 'error', '-y', '-i', str(target), '-i', str(data / 'public' / content['voice']), '-map', '0:v:0', '-map', '1:a:0', '-t', str(content['duration']), '-c:v', 'copy', '-af', 'alimiter=limit=0.78:level=false:latency=true', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(final)], check=True, capture_output=True, timeout=120, creationflags=0x08000000)
        probe = json.loads(subprocess.check_output([str(runtime['ffprobe']), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(final)], timeout=30))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        if int(video.get('nb_frames', 0)) != total or int(video.get('bit_rate', 0)) < 20000000 or (video['width'], video['height']) != (1920, 1080):
            raise ValueError('完整导出帧数、分辨率或20Mbps门槛失败。')
        subprocess.run([str(runtime['ffmpeg']), '-nostdin', '-v', 'error', '-i', str(final), '-f', 'null', '-'], check=True, capture_output=True, timeout=180, creationflags=0x08000000)
        write(out / 'quality.json', {'sha256': sha(final), 'probe': probe, 'full_decode': 'pass', 'visual': 'pending-encoded-frame-review', 'continuous_listen': 'pending', 'platform': 'pending', 'paid_calls': 0})
        work = WorkCatalog(projects).register(project_id, final, work_key='nana-mint-template', mode='manual', event_id=job['job_id'], quality_passed=False, title='薄荷章节讲解 · 参考复刻样片', actor=CONTRACT, summary='本地参考样片，待最终审美与听看确认，未发布', ffprobe=runtime['ffprobe'])
        return {'status': 'completed', 'stage': '薄荷章节模板样片完成', 'result': {'output_path': str(final), 'work_id': work['work_id']}}

    if job['status'] == 'completed':
        result = job
    elif job['status'] == 'paused':
        result = ProductionQueueWorker(queue, projects, handlers={'studio_investment_recompose': execute}, worker_id='nana-mint-preview', lease_seconds=300).run_local_recompose(job['job_id'])
    else:
        raise RuntimeError('先读取原任务及日志，不创建重复任务：' + job['status'])
    print(json.dumps({'job_id': job['job_id'], 'status': result['status'], 'output': str(out)}, ensure_ascii=False), flush=True)
    if result['status'] != 'completed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
