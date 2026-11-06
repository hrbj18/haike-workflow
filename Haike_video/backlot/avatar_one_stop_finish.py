"""Queue-owned local finishing for template 11's legacy hard-coded presenter badge.

The frozen template/runtime remains immutable. This child keeps its original
parent and audio, replaces only the badge within actual presenter windows, and
registers a separate checked output version in the same native project.
"""
from __future__ import annotations

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

from backlot.avatar_one_stop_policy import digest, fingerprint
from backlot.avatar_one_stop_tools import media_command, read
from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog, WorkError

CONTRACT = 'haike.avatar-one-stop-finish/1'


def prepare(queue, parent_id):
    from backlot.avatar_one_stop_production import completed_media
    parent = queue.get(parent_id, include_private=True)
    base = completed_media(queue, parent_id)
    original = parent['frozen_request']
    if original.get('contract') != 'motion-replay-chromatic-suite-production-v1' or original.get('template_id') != 'chromatic-six-11':
        raise WorkError('人物铭牌修正只适用于已完成的模板11原父任务')
    project = Path(queue.projects_root)/parent['project_id']
    font = project/'assets/chromatic-suite-production'/original['props']['font']
    frame = project/'artifacts'/('one-stop-badge-scan-'+base['output_sha256'][:16]+'.png')
    if not frame.is_file():
        clip = original['props']['presenters'][0]
        media_command(['-ss', (clip['from']+clip['to'])/60, '-i', base['output_path'], '-frames:v', '1', frame])
    # Measure the peach strip in this exact rendered parent; no edits to its
    # protected React files or integrity manifest are needed.
    with Image.open(frame) as image:
        image = image.convert('RGB')
        if image.size != (1080, 1920):
            raise WorkError('原父成片尺寸不符，不能按旧坐标覆盖人物铭牌')
        solid = []
        for y in range(1525, 1605):
            pixels = [image.getpixel((x, y)) for x in range(778, 1001)]
            match = sum(all(abs(a-b) <= 12 for a, b in zip(pixel, (255,173,143))) for pixel in pixels)
            if match/len(pixels) > .96:
                solid.append(y)
    if not solid or not 1535 <= min(solid) <= 1580:
        raise WorkError('原人物铭牌位置未通过实帧核对，保留原视频供Agent检查')
    y = min(solid)
    core = {'contract': CONTRACT, 'project_id': parent['project_id'], 'source_job_id': parent_id,
            'source_request_sha256': original['request_sha256'],
            'source_relative': Path(base['output_path']).relative_to(project).as_posix(),
            'source_sha256': base['output_sha256'], 'font_relative': font.relative_to(project).as_posix(),
            'font_sha256': digest(font), 'frames': original['props']['durationInFrames'], 'fps': 30,
            'windows': [{'from': c['from'], 'to': c['to']} for c in original['props']['presenters']],
            'badge': {'x':774, 'y':y, 'width':231, 'height':1605-y, 'text':'AI数字人',
                      'background':'#FFAD8F', 'ink':'#102C43'},
            'title': original['title'], 'publication': False, 'new_provider_calls': False}
    identity = fingerprint(core)
    request = {**core, 'request_sha256': identity, 'render_id':'one-stop-finish-'+identity[:20]}
    path = project/'artifacts'/(request['render_id']+'.json')
    if path.is_file() and read(path) != request:
        raise WorkError('原铭牌修正请求已经变化，请恢复原版本', 'conflict')
    atomic_private(path, request)
    return request


def validate(queue, request):
    core = {k:v for k,v in request.items() if k not in {'request_sha256','render_id'}}
    if (request.get('contract') != CONTRACT or fingerprint(core) != request.get('request_sha256')
            or request.get('render_id') != 'one-stop-finish-'+request['request_sha256'][:20]
            or request.get('publication') is not False or request.get('new_provider_calls') is not False
            or request.get('badge',{}).get('text') != 'AI数字人'
            or not re.fullmatch(r'studio-[a-f0-9]{16}', request.get('project_id',''))):
        raise WorkError('原人物铭牌修正合同身份不符', 'conflict')
    project = (Path(queue.projects_root)/request['project_id']).resolve()
    for key, sha in [('source_relative','source_sha256'),('font_relative','font_sha256')]:
        path = (project/request[key]).resolve()
        if not path.is_relative_to(project) or not path.is_file() or digest(path) != request[sha]:
            raise WorkError('原成片或字体已变化，停止本地修正', 'conflict')
    parent = queue.get(request['source_job_id'], include_private=True)
    if (parent['status'] != 'completed' or parent['project_id'] != request['project_id']
            or parent['frozen_request']['request_sha256'] != request['source_request_sha256']
            or parent['result']['output_sha256'] != request['source_sha256']):
        raise WorkError('铭牌修正未绑定原完成父任务', 'conflict')
    original = parent['frozen_request']
    badge = request['badge']
    if (original.get('contract') != 'motion-replay-chromatic-suite-production-v1'
            or original.get('template_id') != 'chromatic-six-11' or request['fps'] != 30
            or request['frames'] != original['props']['durationInFrames']
            or request['windows'] != [{'from':c['from'],'to':c['to']} for c in original['props']['presenters']]
            or (badge['x'],badge['width'],badge['background'],badge['ink']) != (774,231,'#FFAD8F','#102C43')
            or not 1535 <= badge['y'] <= 1580 or badge['y']+badge['height'] != 1605
            or request['font_sha256'] != original['origins'][original['props']['font']]['sha256']):
        raise WorkError('铭牌修正超出原人物范围、时钟、字体或样式，保留原成片', 'conflict')
    if read(project/'artifacts'/(request['render_id']+'.json')) != request:
        raise WorkError('原修正请求文件已变化', 'conflict')
    return project


def submit(queue, request, *, phase=None):
    if phase not in {None,'preview','render'}:
        raise WorkError('人物铭牌修正只接受本地合成')
    validate(queue, request)
    return queue.submit(project_id=request['project_id'], kind='studio_investment_recompose', source='codex',
        priority='normal', parent_job_id=request['render_id'], frozen_request=request,
        idempotency_key=CONTRACT+':'+request['request_sha256'], start_paused=True)


def result(queue, request):
    project = validate(queue, request)
    folder = project/'renders'/request['render_id']
    output, qa = folder/'one-stop-final.mp4', folder/'qa.json'
    receipt = read(folder/'result.json')
    if (digest(output) != receipt['output_sha256'] or digest(qa) != receipt['qa_sha256']
            or receipt['request_sha256'] != request['request_sha256']):
        raise WorkError('修正成片或检查回执身份不符', 'conflict')
    return {'output_path':str(output), 'output_sha256':receipt['output_sha256'], 'qa_report':str(qa),
            'work_id':receipt['work_id'], 'finishing_contract':CONTRACT, 'base_output_sha256':request['source_sha256']}


def run(queue, job):
    request = job['frozen_request']
    try:
        project = validate(queue, request)
        folder = project/'renders'/request['render_id']
        folder.mkdir(parents=True, exist_ok=True)
        output, qa = folder/'one-stop-final.mp4', folder/'qa.json'
        if not (folder/'result.json').is_file():
            b = request['badge']
            badge = Image.new('RGB',(b['width'],b['height']),b['background'])
            draw = ImageDraw.Draw(badge)
            font = ImageFont.truetype(str(project/request['font_relative']), 23)
            bounds = draw.textbbox((0,0),b['text'],font=font)
            draw.text(((b['width']-bounds[2]+bounds[0])/2,(b['height']-bounds[3]+bounds[1])/2-bounds[1]),
                      b['text'],font=font,fill=b['ink'])
            badge.save(folder/'badge.png')
            enable = '+'.join(f"between(n,{c['from']},{c['to']-1})" for c in request['windows'])
            seconds = request['frames']/30
            filters = f"[0:v][1:v]overlay={b['x']}:{b['y']}:enable='{enable}':format=auto[out]"
            media_command(['-i',project/request['source_relative'],'-loop','1','-framerate','30','-i',folder/'badge.png',
                '-filter_complex',filters,'-map','[out]','-map','0:a:0','-t',seconds,
                '-c:v','libx264','-preset','fast','-b:v','21000k','-minrate','21000k','-maxrate','21000k','-bufsize','2100k',
                '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p',
                '-c:a','copy','-movflags','+faststart',output],timeout=600)
            from backlot.motion_replay_chromatic_production import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            media = media_probe(output)
            video = media.get('video') or {}
            audio = measure_audio(output)
            if ((video.get('width'),video.get('height')) != (1080,1920)
                    or int(video.get('nb_frames',0)) != request['frames']
                    or video.get('avg_frame_rate') != '30/1' or int(video.get('bit_rate',0)) < 20_000_000
                    or not media.get('audio') or audio['true_peak_dbtp'] > -1.5):
                raise WorkError('本地铭牌修正成片技术检查未通过')
            media_command(['-xerror','-i',output,'-f','null','-'],timeout=300)
            atomic_private(qa,{'technical':'pass','full_decode':'pass','media':media,'audio':audio,
                'source_parent_job_id':request['source_job_id'],'base_output_sha256':request['source_sha256'],
                'audio_stream_copied':True,'speech_stretched':False,'visual_review':'pending',
                'continuous_listening':'pending','external_speaker_test':'pending'})
            work = WorkCatalog(queue.projects_root).register(request['project_id'],output,work_key='main',mode='manual',
                event_id=job['job_id'],quality_passed=False,actor='avatar-one-stop-finish',title=request['title'],
                summary='本期人物与Plus配音；模板11通用AI数字人铭牌；原云任务复用，待实际检查，未发布')
            atomic_private(folder/'result.json',{'output_sha256':digest(output),'qa_sha256':digest(qa),
                'request_sha256':request['request_sha256'],'work_id':work['work_id'],'publication':False})
        return {'status':'completed','stage':'一条龙人物铭牌修正与HD检查完成','result':result(queue,request)}
    except Exception as error:
        return {'status':'failed','stage':'原本地人物铭牌修正待恢复',
                'error':{'type':type(error).__name__,'message':str(error) if isinstance(error,WorkError) else '本地修正未完成，请恢复原任务'},
                'retryable':True,'safe_resume_point':'avatar_one_stop_finish'}


def ensure_finished(studio, queue, value, save):
    from backlot.avatar_one_stop_production import production_queue
    from backlot.motion_replay_production import submit_frozen, execute
    queue = production_queue(studio, queue)
    composition = value['stages']['composition']
    request = prepare(queue, composition['queue_id'])
    job = submit_frozen(queue, request)
    composition['finish_queue_id'] = job['job_id']
    save()
    job = execute(queue,job['job_id'],confirmed=True,resume_local=True)
    if job['status'] != 'completed':
        raise WorkError('本地人物铭牌修正未完成，保留原合成视频与全部云端产物')
    return result(queue, request)
