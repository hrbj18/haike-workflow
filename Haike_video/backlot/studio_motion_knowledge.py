"""Versioned native knowledge protocol, using the existing MotionGit draft/queue UI.

Only declared public operations are dispatched. Unknown packages stay inspectable;
no template code or recipient envelope is extracted into a distributable template.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import shutil
import subprocess

from backlot import studio_motiongit as motion
from backlot.studio import atomic_private
from backlot.studio_investment_recompose import fingerprint
from backlot.work_catalog import WorkCatalog, read_json, sha

PROTOCOL = 'knowledge-story-v1'
SUPPORTED = {('knowledge-explainer-sketchnote', '2.7.3')}


def supported(package):
    return (package.get('template_id'), package.get('version')) in SUPPORTED


def bindings(value, assets):
    """Resolve only this protocol's declared material paths, never arbitrary JSON paths."""
    from backlot.studio_render import media_probe
    from backlot.studio_hum_production import _clock
    p = value['parameters']
    motion.require(p.get('creationProfile') == 'knowledge-story/1', '新主题须使用知识讲解路线，不能套用原片演出')
    audio = p.get('audio', {})
    voice, music = audio.get('narration', {}), audio.get('music', {})
    motion.require(voice.get('mode') == music.get('mode') == 'file', '本期口播制作须明确绑定完整人声和配乐')

    def material(name):
        motion.require(isinstance(name, str) and name in assets and Path(name).name == name
                       and not any(c in name for c in '/\\:'), '原生素材须使用已导入的平面绑定名')
        return Path(assets[name]['path'])

    voice_path = material(voice.get('path')); music_path = material(music.get('path'))
    clock = _clock(voice_path); duration = p['durationSeconds']; fps = p.get('fps', 60)
    motion.require(abs(clock['duration_seconds'] - duration) <= 1 / fps,
                   '原生配音须对齐整片时钟；尾部补静音须另存并保留原音证据，不能变速')
    motion.require(sha(voice_path) != sha(music_path) and media_probe(music_path).get('duration', 0) >= duration,
                   '独立配乐须覆盖全片，不能重复人声或暗中循环补长')
    ev = p.get('sentenceEvidence', {}); evidence = material(ev.get('path'))
    measured = read_json(evidence)
    motion.require(sha(evidence) == ev.get('sha256') and ev.get('audioSha256') == sha(voice_path)
                   and measured.get('audioSha256') == sha(voice_path)
                   and measured.get('method') == ev.get('method')
                   and measured.get('captions') == p.get('captions'), '同源句级证据与本期字幕、人声不一致')
    if p.get('wordEvidence'):
        row = p['wordEvidence']; motion.require(sha(material(row['path'])) == row['sha256'], '词级证据身份已变化')
    presenter = p.get('presenter', {})
    if presenter.get('mode') != 'none':
        source = material(presenter.get('path'))
        motion.require(presenter.get('mode') == 'intro-circle'
                       and media_probe(source).get('duration', 0) + .025 >= presenter.get('sourceStart', 0) + duration,
                       '原生连续圆窗需要真实完整人物，不能循环或冻结短片')
    return clock


def freeze(queue, draft_id):
    from backlot import studio_motiongit_render as render
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    value = motion.draft(draft_id); package = motion._get('packages', value['package_id'])
    motion.require(supported(package) and value['workflow'] == 'native' and package.get('verification') == 'verified',
                   '此原包版本的原生制作协议尚未接入，请保留并完成首次适配')
    motion.require(value.get('output_profile', 'native') == 'native', '本协议使用原生横屏或9:16独立版式')
    motion.validate_draft(draft_id)
    assets = render._assets(value); clock = bindings(value, assets)
    tools = {name: {'path': str(Path(path).resolve()), 'sha256': sha(path)}
             for name, path in zip(['ffmpeg', 'ffprobe'], resolve_ffmpeg_pair() or [])}
    motion.require(len(tools) == 2, '本机FFmpeg/ffprobe未配置')
    node = motion.node_executable(); motion.require(node and Path(node).is_file(), '本机Node.js未配置')
    tools['node'] = {'path': str(Path(node).resolve()), 'sha256': sha(node)}
    core = {'contract': render.CONTRACT, 'native_protocol': PROTOCOL, 'draft': value,
            'package_id': package['id'], 'package_sha256': package['sha256'],
            'helper_sha256': motion.helper_identity(package)['sha256'], 'assets': assets,
            'adapter_sha256': sha(__file__), 'transport_sha256': sha(motion.__file__),
            'component_sha256': sha(render.__file__), 'voice_clock': clock, 'tools': tools,
            'publication': False, 'paid_calls': 0}
    core['project_id'] = 'studio-' + fingerprint(core)[:16]
    digest = fingerprint(core)
    r = {**core, 'request_sha256': digest, 'render_id': 'motiongit-component-' + digest[:20]}
    project = queue.projects_root / r['project_id']; target = project / 'artifacts/motiongit-component-request.json'
    if not target.exists():
        from lib.checkpoint import init_project
        init_project(r['project_id'], title=value['title'], pipeline_type='animated-explainer', pipeline_dir=queue.projects_root)
        folder = project / 'assets/motiongit'; folder.mkdir(parents=True, exist_ok=True)
        for name, asset in assets.items():
            shutil.copyfile(asset['path'], folder / name)
            motion.require(sha(folder / name) == asset['sha256'], '素材冻结复制失败')
        atomic_private(target, r)
    motion.require(read_json(target) == r, '冻结请求已变化')
    motion.track_production(value, r)
    return r


def validate(queue, r):
    core = {k: v for k, v in r.items() if k not in {'request_sha256', 'render_id', 'phase'}}
    motion.require(fingerprint(core) == r['request_sha256'] and r.get('native_protocol') == PROTOCOL,
                   '原生知识请求身份无效')
    project = queue.projects_root / r['project_id']
    motion.require(read_json(project / 'artifacts/motiongit-component-request.json') == core | {
        'request_sha256': r['request_sha256'], 'render_id': r['render_id']}, '原生冻结记录已变化')
    p = motion._get('packages', r['package_id'])
    motion.require(supported(p) and p['sha256'] == r['package_sha256'] and sha(p['path']) == p['sha256']
                   and sha(p['helper']) == r['helper_sha256'], '原生包或工具身份已变化')
    paths = {n: {**a, 'path': str(project / 'assets/motiongit' / n)} for n, a in r['assets'].items()}
    motion.require(all(sha(a['path']) == a['sha256'] for a in paths.values()), '原生冻结素材已变化')
    motion.require(bindings(r['draft'], paths) == r['voice_clock'], '原生完整声音时钟已变化')
    folder = project / 'renders' / r['render_id']
    done = read_json(folder / 'result.json')
    if done:
        motion.require(sha(folder / 'native-final.mp4') == done.get('output_sha256')
                       and sha(folder / 'quality.json') == done.get('quality_sha256'), '已有成片或质量记录已变化')
    else:
        from backlot import studio_motiongit_render as render
        current_node = motion.node_executable()
        motion.require(sha(__file__) == r['adapter_sha256'] and sha(motion.__file__) == r['transport_sha256']
                       and sha(render.__file__) == r['component_sha256']
                       and current_node and Path(current_node).resolve() == Path(r['tools']['node']['path']).resolve()
                       and all(sha(t['path']) == t['sha256'] for t in r['tools'].values()),
                       '原生适配器或编码器已改变，请保留旧版后重新冻结')
    return p, project, folder


def review(queue, r, evidence):
    _, _, folder = validate(queue, r); state = read_json(folder / 'native-state.json')
    path = folder / 'native-preview/preview-review.json'; receipt = read_json(path)
    motion.require(state and receipt and evidence.get('preview_sha256') == sha(path)
                   and evidence.get('reviewer') and evidence.get('inspected_images') == state.get('images'),
                   '请实际检查本期全部原生预览，并绑定其完整身份')
    motion.require(all(sha(path.parent / i['name']) == i['sha256'] for i in receipt['images']), '原生预览图片已变化')
    receipt['reviewed'] = True; atomic_private(path, receipt)
    atomic_private(folder / 'visual-review.json', {**evidence, 'reviewed_preview_sha256': sha(path),
        'scope': 'sampled-native-preview', 'continuous_watching': 'pending', 'continuous_listening': 'pending'})
    return {'reviewed': True, 'scope': 'sampled-native-preview'}


def run(queue, job):
    from backlot import studio_motiongit_render as render
    from backlot.studio_render import media_probe
    from backlot.studio_investment_audio_v5 import measure_audio
    from backlot.work_catalog import WorkError
    r = job['frozen_request']
    try:
        package, project, folder = validate(queue, r); folder.mkdir(parents=True, exist_ok=True)
        state_path = folder / 'native-state.json'; state = read_json(state_path)
        if not state:
            short = motion.ROOT / '.local/mkn' / r['request_sha256'][:16]
            short.parent.mkdir(parents=True, exist_ok=True)
            created = motion.helper_command(package, 'new', short)
            state = {'workflow': 'native', 'native_protocol': PROTOCOL, 'instanceDirectory': created['instanceDirectory'],
                     'cache': str(motion.ROOT / '.local/md/knowledge-rc54-v1')}
            atomic_private(state_path, state)
        inst = Path(state['instanceDirectory']); motion.require(inst.is_dir(), '原生实例已丢失；保留成片/素材，复制草稿重新生成预览')
        from backlot.studio_motion_runtime import profile
        installed = profile(package, 'native')
        execution_package = package
        if installed:
            state['cache'] = installed['cache_argument_path']
            state['runtime_profile'] = installed['id']
            execution_package = {**package, 'offline_dependencies': True, 'dependency_cache': installed['cache_path']}
        def execute(operation, *args, timeout=300):
            cache_args = ['--cache', state['cache']] if state.get('cache') else []
            return motion.helper_command(execution_package, 'run', '--instance', inst, *cache_args,
                                         operation, *args, timeout=timeout, temporary_root=motion.ROOT / '.local/mt')
        if not state.get('setup'):
            if installed:
                motion.require(execute('doctor').get('ok') is True, '安装内原生运行环境未通过检查，请修复本次更新')
            else:
                execute('setup', timeout=1200)
            state['setup'] = True; atomic_private(state_path, state)
        materials = inst / 'materials'; materials.mkdir(exist_ok=True)
        for name, asset in r['assets'].items():
            target = materials / name
            if not target.exists(): shutil.copyfile(project / 'assets/motiongit' / name, target)
            motion.require(sha(target) == asset['sha256'], '原生实例素材已改变')
        params = inst / 'parameters.json'
        if not params.exists(): atomic_private(params, r['draft']['parameters'])
        motion.require(read_json(params) == r['draft']['parameters'], '原生本期参数已变化')
        plan = inst / 'plan/plan.json'; p = r['draft']['parameters']
        if not state.get('preview_receipt'):
            if not plan.exists():
                execute('check-params', '--params', params, '--inputs', materials)
                execute('plan', '--params', params, '--inputs', materials, '--out', inst / 'plan')
            made = execute('prepare', '--plan', plan, '--out', inst / 'project')
            motion.require(made.get('ok') is True, '原生字体、阅读或连续性预检未通过')
            times = sorted({min(p['durationSeconds'] - .05, s['start'] + o) for s in p['segments']
                            for o in [.5, (s['end'] - s['start']) / 3, (s['end'] - s['start']) * 2 / 3, s['end'] - s['start'] - .2]})
            import json
            preview = execute('preview', '--plan', plan, '--out', inst / 'stills', '--times', json.dumps(times))
            motion.require(preview.get('ok') is True and len(preview.get('files', [])) == len(times), '原生预览未覆盖本期镜头')
            target = folder / 'native-preview'; target.mkdir(exist_ok=True); images = []
            for i, raw in enumerate(preview['files']):
                path = Path(raw['file']).resolve()
                motion.require(path.is_relative_to((inst / 'stills').resolve()) and path.is_file()
                               and sha(path) == raw['sha256'], '原生预览来源或图片SHA不一致')
                name = f'frame-{i:04}.png'; shutil.copyfile(path, target / name)
                images.append({'name': name, 'sha256': sha(target / name), 'time': raw['time']})
            atomic_private(target / 'preview-review.json', {'request_sha256': r['request_sha256'], 'reviewed': False,
                'plan_sha256': sha(plan), 'params_sha256': sha(params), 'images': images, 'prepare': made})
            state.update(preview_directory=str(target), preview_receipt=str(target / 'preview-review.json'),
                         images_directory=str(target), images=[i['name'] for i in images], plan_sha256=sha(plan))
            atomic_private(state_path, state)
        if r['phase'] == 'preview':
            return {'status': 'completed', 'stage': '原生知识预览已生成，请核对全部画面', 'result': {'qa_status': 'pending', 'images': len(state['images'])}}
        review_path = Path(state['preview_receipt']); visual = read_json(folder / 'visual-review.json')
        preview_receipt = read_json(review_path)
        motion.require(preview_receipt.get('reviewed') and visual.get('reviewed_preview_sha256') == sha(review_path)
                       and all(sha(review_path.parent / i['name']) == i['sha256'] for i in preview_receipt['images'])
                       and state['plan_sha256'] == sha(plan), '本期原生预览/计划尚未通过实际画面审核')
        output = folder / 'native-final.mp4'; done = read_json(folder / 'result.json')
        if not done:
            raw = inst / 'native-film.mp4'
            # A killed native renderer can leave a partial file. Preserve it and
            # resume with a fresh destination rather than trusting mere existence.
            if raw.exists():
                try:
                    prior = media_probe(raw)
                    usable = prior.get('audio') and abs(prior.get('duration', 0) - p['durationSeconds']) <= .08
                except (OSError, ValueError, KeyError):
                    usable = False
                if not usable:
                    from uuid import uuid4
                    raw = inst / ('native-film-recovery-' + uuid4().hex + '.mp4')
            if not raw.exists(): execute('render', '--plan', plan, '--out', raw, timeout=1800)
            raw_info = media_probe(raw); fps = p.get('fps', 60); width, height = (1920,1080) if p['layout'] == 'landscape' else (1080,1920)
            motion.require(raw_info.get('audio') and (raw_info['video']['width'],raw_info['video']['height']) == (width,height)
                           and abs(raw_info['duration'] - p['durationSeconds']) <= .08, '原生输出画幅、人声或整片时钟不一致')
            conversion = render.encoding_layout(raw_info['video'], False)
            candidate = folder / 'encoded-candidate.mp4'
            command = [r['tools']['ffmpeg']['path'], '-nostdin', '-y', '-v', 'error', '-i', str(raw)]
            if conversion['filter']: command += ['-vf', conversion['filter']]
            command += ['-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k',
                '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p',*conversion['options'],
                '-af','loudnorm=I=-16:TP=-2.5:LRA=11,aresample=48000','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
                '-movflags','+faststart',str(candidate)]
            subprocess.run(command, check=True, capture_output=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            info = media_probe(candidate); video = info['video']; audio = measure_audio(candidate)
            motion.require(int(video.get('bit_rate',0)) >= 20000000 and audio['true_peak_dbtp'] <= -1.5
                           and (video['width'],video['height']) == (width,height) and video['codec_name'] == 'h264'
                           and video['pix_fmt'] == 'yuv420p' and abs(float(Fraction(video['avg_frame_rate'])) - fps) < .001
                           and int(video['nb_frames']) == round(p['durationSeconds'] * fps)
                           and abs(info['duration'] - p['durationSeconds']) <= .08, '原生成片帧数、画幅、码率或音轨峰值未通过')
            subprocess.run([r['tools']['ffmpeg']['path'],'-nostdin','-v','error','-i',str(candidate),'-f','null','-'],check=True,capture_output=True)
            motion.require(not output.exists(), '已存在未登记成片，请保留并核对原结果')
            candidate.rename(output)
            atomic_private(folder / 'quality.json', {'media': info, 'audio': audio, 'full_decode': 'passed', 'color_conversion': conversion,
                'export_command': command, 'visual_review': 'sampled-native-preview', 'continuous_watching': 'pending', 'continuous_listening': 'pending'})
        work = WorkCatalog(queue.projects_root).register(r['project_id'], output, work_key='main', mode='manual', event_id=job['job_id'],
            quality_passed=False, actor=PROTOCOL, title=r['draft']['title'], summary='原生知识动效模板；完整本期声音；视听终审待完成；未发布')
        version = next(v for v in work['versions'] if v['sha256'] == sha(output))
        atomic_private(folder / 'result.json', {'request_sha256': r['request_sha256'], 'output_sha256': sha(output),
            'quality_sha256': sha(folder / 'quality.json'), 'work_id': work['work_id'], 'version_id': version['version_id']})
        return {'status': 'completed', 'stage': '原生知识成片已导出，等待观看', 'result': {'work_id': work['work_id'],
            'version_id': version['version_id'], 'output_path': str(output), 'output_sha256': sha(output), 'qa_status': 'pending'}}
    except (WorkError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        return {'status': 'failed', 'stage': '原生知识制作待恢复', 'error': {'type': 'NativeKnowledge', 'message': str(exc)[:800]},
                'retryable': True, 'safe_resume_point': PROTOCOL}
