"""Original verified Remotion renderer, independent public/2 candidate."""
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil

from backlot.motion_public_io_v1 import atomic_private, read_json, sha
from backlot import motion_public_dark_v2 as shared
from backlot.motion_public_dark_schema_v2 import action_gate

ENGINE = 'dark-remotion/2'
DESCRIPTOR_SHA = '996578c8bebe4b147fda95454a20917a73aff8048840fc339102b12c0ce64ee1'


def descriptor():
    from backlot import motion_public_execution_v2 as e
    path = shared.SOURCE / 'REMOTION_RUNTIME.json'
    e.require(sha(path) == DESCRIPTOR_SHA, '原Remotion执行清单改变，禁止执行未知版本')
    sources = read_json(shared.SOURCE / 'SOURCE.json')['files']
    e.require({row['path'] for row in sources} == {'template/' + name for name in
              ('index.tsx','shared.tsx','GroupsA.tsx','GroupsB.tsx','presenter-clock.ts','types.ts','catalog.json')}, '原C十组源清单缺件或多件')
    e.require(all(sha(shared.SOURCE / row['path']) == row['sha256'] for row in sources), '原C十组TSX或目录元数据已变化，须冻结明确新身份')
    return read_json(path)


def environment(tool_root, dependency_root, ffmpeg_root):
    from backlot import motion_public_execution_v2 as e
    root = Path(dependency_root).resolve();tools = Path(tool_root).resolve();data = descriptor()
    e.require(tools == root / 'tools' and ffmpeg_root is not None, '原renderer工具映射须精确落在固定外供目录')
    out = []
    for row in data['files']:
        path = root / row['path']
        e.require(path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink()
                  and sha(path) == row['sha256'], '原Remotion/npm/native/browser/Node/许可文件缺失或改变：' + row['path'])
        out.append({'logical_path':'original-remotion/' + row['path'], 'sha256':row['sha256']})
    ffmpeg = Path(ffmpeg_root).resolve()
    e.require(sha(e.TEMPLATE / 'FFMPEG9.json') == e.FFMPEG9_DESCRIPTOR_SHA, '原C同摘要FFmpeg9描述改变')
    for row in read_json(e.TEMPLATE / 'FFMPEG9.json')['files']:
        path = ffmpeg / row['path']
        e.require(path.resolve().is_relative_to(ffmpeg) and path.is_file() and not path.is_symlink()
                  and sha(path) == row['sha256'], '原C同摘要FFmpeg9外供文件改变')
        out.append({'logical_path':'ffmpeg9/' + row['path'], 'sha256':row['sha256']})
    return data, out


def preflight(value):
    from backlot.motion_public_execution_v2 import require
    supplied = deepcopy(value)
    scope = supplied.get('composition', {}).pop('preview_scope', 'full-actions/1')
    require(scope in {'readiness-probe/1','full-actions/1'}, '原renderer预览范围未登记')
    normalized = shared.preflight(supplied, engine=ENGINE, environment_resolver=environment)
    normalized['spec']['preview_scope'] = scope
    normalized['reference']['implementation'] = 'C-owned cobalt complete ten-group TSX with two marketing-only label visibility guards rendered by original Remotion4.0.506 CLI; original protected native package identity not claimed'
    return normalized


def build_project(project, folder, request):
    from backlot import motion_public_execution_v2 as e
    if (folder / 'prepared.json').exists():
        receipt = read_json(folder / 'prepared.json')
        e.require(all((folder / name).resolve().is_relative_to(folder.resolve()) and not (folder / name).is_symlink()
                      and sha(folder / name) == digest for name,digest in receipt['files'].items()), '原renderer已准备工程改变')
        return receipt
    e.require(not (folder / 'project').exists(), '保留原renderer未完成准备现场，不能覆盖重来')
    generated = folder / 'project';generated.mkdir();public = generated / 'public';public.mkdir()
    data = descriptor();runtime_root = Path(request['dependency_root'])
    # A per-request package root places source/media/cache under the work folder.
    # Node imports resolve through the explicitly restored ancestor runtime root.
    e.require(folder.resolve().is_relative_to(runtime_root.resolve()), '原renderer作业须在该隔离外供树内解析固定npm依赖')
    for name in ('package.json','tsconfig.json'):shutil.copy2(runtime_root / name, generated / name)
    shutil.copytree(shared.SOURCE / 'template', generated / 'template')
    p = deepcopy(request['spec']['props'])
    assets = {name:project / 'assets/motion-public' / name for name in request['origins']}
    for name in shared.required_names(p, request['spec']['audio']):
        if name not in {'voice.wav','music.wav'}:shutil.copy2(assets[name], public / name)
    shared.mix_audio(assets, folder, public, request)
    e.require(p.get('audio') == 'master.wav', '原C绑定音轨名变化，不能猜测替换')
    # The unchanged TSX continues to reference its original logical master name.
    (public / 'final.wav').rename(public / 'master.wav')
    audio_receipt = read_json(folder / 'audio-receipt.json')
    e.require(sha(public/'master.wav') == audio_receipt['mix_sha256'], '原C逻辑音轨重命名后字节变化')
    atomic_private(generated / 'props.json', p)
    atomic_private(generated / 'pipeline.json', {'engine':ENGINE,'runtime_descriptor_sha256':DESCRIPTOR_SHA,
        'source_template_files':[{'name':f.name,'sha256':sha(f)} for f in sorted((generated/'template').iterdir()) if f.is_file()],
        'profile':data['profile'],'outer_export':data['outer_export'],
        'command_changes_from_C':'Direct fixed local Node+CLI replaces npx resolution; explicit exact restored Chrome149; bundle cache disabled. Original renderer, TSX, dimensions, frame/speech/media/font clocks and encoding profile retained.'})
    files = {f.relative_to(folder).as_posix():sha(f) for f in generated.rglob('*') if f.is_file()}
    receipt = {'schema':'haike.original-remotion-dark-prepared/2','request_sha256':request['request_sha256'],'files':files,
               'full_original_template_closure':False,'original_renderer_retained':True,'fresh_regeneration':'pending execution'}
    atomic_private(folder / 'prepared.json', receipt)
    return receipt


def require_full_export_scope(request):
    from backlot.motion_public_execution_v2 import require
    require(request.get('spec', {}).get('preview_scope') == 'full-actions/1', '就绪小样不能准入整片，须另冻结完整动作预览并实际审核')


def preview_frames(props, scope='full-actions/1'):
    fps, end = props['fps'], props['durationFrames'];frames = {0,end-1}
    if scope == 'readiness-probe/1':
        return sorted(frames | {min(end-1,round(t*fps)) for t in (.65,4.36,4.4,38.26,67.22,98.6,102.8,108.9)})
    definitions = {group['id']:group for group in shared.catalog()['groups']}
    for scene in props['scenes']:
        start, stop = scene['from'], scene['from'] + scene['frames']
        frames.update((start,min(stop-1,start+round(.1*fps)),(start+stop)//2,stop-1))
        for at in action_gate(scene,fps,definitions[scene['group']]).values():
            frames.update(start+round((at+offset)*fps) for offset in (0,.3,.65) if start+round((at+offset)*fps)<stop)
        for clip in scene.get('videoWindows', []):
            first = start+clip['from'];last = first+clip['frames']-1
            frames.update((first,(first+last)//2,last))
    for mode in props['presenter']['modes']:
        start, stop = mode['from'], mode['from'] + mode['frames']
        frames.update((max(0,start-1),start,min(end-1,start+round(.3*fps)),min(end-1,stop-1)))
    return sorted(frames)


def render_project(project, folder, request):
    from backlot import motion_public_execution_v2 as e
    data = descriptor();root = Path(request['dependency_root']);generated = folder/'project';p = request['spec']['props']
    profile = data['profile'];node = root/data['executables']['node'];cli = root/data['executables']['cli']
    common = [node,cli,'render',generated/'template/index.tsx','DarkFull',
        '--props='+str(generated/'props.json'),'--public-dir='+str(generated/'public'),
        '--browser-executable='+str(root/data['executables']['browser']),'--bundle-cache=false',
        '--scale=1','--concurrency=2','--codec=h264','--image-format=png','--x264-preset=fast','--pixel-format=yuv444p']
    if request['phase'] == 'preview':
        preview = folder/'preview';e.require(not preview.exists(), '保留原实际预览，不覆盖现有图片')
        sequence_name = 'preview-frames'
        staged_preview = generated / sequence_name
        e.require(not staged_preview.exists(), '保留前次未完成的原renderer取样现场')
        scope = request['spec']['preview_scope']
        frames = preview_frames(p,scope)
        # This fixed Remotion version treats a dot anywhere in a directory path
        # as an extension. Pass a dot-free basename in the pinned project cwd;
        # leave the vendor renderer and the workspace's .local layout unchanged.
        e._command([*common,sequence_name,'--sequence','--frames='+','.join(map(str,frames)),
            '--image-sequence-pattern=frame-[frame].[ext]'], generated, request, 'original-dark-preview', timeout=7200)
        files = sorted(staged_preview.glob('*.png'));e.require(len(files)==len(frames), '原renderer完整动作取样图片不足')
        actual = [int(re.fullmatch(r'frame-(\d+)\.png',f.name).group(1)) for f in files]
        e.require(actual==frames, '原renderer实际预览帧号与请求不符')
        images = [{'name':f.name,'sha256':sha(f)} for f in files]
        e.require(staged_preview.resolve().is_relative_to(folder.resolve()) and preview.resolve().is_relative_to(folder.resolve())
                  and not staged_preview.is_symlink() and not preview.exists(), '实际预览目录移动越界或目标已存在')
        staged_preview.rename(preview)
        atomic_private(folder/'preview.json', {'request_sha256':request['request_sha256'],'images':images,
            'times':[frame/p['fps'] for frame in frames],'frames':frames,'scope':scope,
            'original_renderer_retained':True,'original_fidelity':'pending actual image inspection'})
        return {'status':'completed','stage':'原Remotion就绪小样完成，不能准入整片' if scope=='readiness-probe/1' else '原Remotion完整十组实际预览就绪，待逐图对照',
                'result':{'images':images,'preview_sha256':sha(folder/'preview.json'),'qa_status':'pending'}}
    require_full_export_scope(request)
    e.require_current_review(folder, request)
    output, raw = folder/'motion-public.mp4', folder/'mezzanine-crf1.mp4'
    if not (folder/'result.json').exists():
        e._command([*common,raw,'--crf=1'], generated, request, 'original-dark-render', timeout=7200)
        duration = p['durationFrames']/p['fps']
        e._command([e._ffmpeg(request),'-nostdin','-v','error','-n','-i',raw,'-i',generated/'public/master.wav',
            '-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-preset','slow','-b:v','20500k',
            '-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1',
            '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',output],
            folder, request, 'original-dark-export', timeout=7200)
        info = json.loads(e._command([e._ffprobe(request),'-v','error','-count_frames','-show_streams','-show_format','-of','json',output], folder, request, 'original-dark-probe'))
        video = next(s for s in info['streams'] if s['codec_type']=='video');audio = next(s for s in info['streams'] if s['codec_type']=='audio')
        e.require(int(video['nb_read_frames'])==p['durationFrames'] and int(video['bit_rate'])>=20_000_000
                  and (video['width'],video['height'])==(p['width'],p['height']) and video['avg_frame_rate']=='30/1'
                  and video['codec_name']=='h264' and video['pix_fmt']=='yuv420p' and audio['sample_rate']=='48000' and audio['channels']==2,
                  '原renderer整片帧数、码率、画布或音轨未通过')
        e._command([e._ffmpeg(request),'-nostdin','-v','error','-xerror','-i',output,'-f','null','-'], folder, request, 'original-dark-decode')
        e._command([e._ffmpeg(request),'-nostdin','-v','info','-i',output,'-af','loudnorm=I=-16:TP=-1.8:LRA=11:print_format=json','-f','null','-'], folder, request, 'original-dark-loudness')
        text = (folder/'original-dark-loudness.stderr.log').read_text('utf8');loud = json.loads(text[text.rfind('{'):text.rfind('}')+1])
        e.require(float(loud['input_tp'])<=-1.5, '原renderer最终AAC真峰值未通过')
        atomic_private(folder/'result.json', {'output_sha256':sha(output),'media':info,'loudness':loud,'full_decode':'passed',
            'original_renderer_retained':True,'original_fidelity':'pending actual comparison','continuous_listening':'pending',
            'full_original_template_closure':False,'fresh_regeneration':'actual isolated original renderer export, not previous artifact early return'})
    e.require(sha(output)==read_json(folder/'result.json')['output_sha256'], '原renderer完成成片字节变化')
    return {'status':'completed','stage':'原Remotion完整十组已实际合成，待画面与连续听看',
            'result':{'output_path':str(output),'output_sha256':sha(output),'qa_status':'pending'}}
