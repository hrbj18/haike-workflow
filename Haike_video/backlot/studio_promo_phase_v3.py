"""Independent promo /3 phase controller. C /1 remains immutable.

Renderer inheritance is blocked until INHERITANCE.json is frozen and verified.
No personal/protected template package is read by this producer.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
import math
import re
import shutil
import subprocess
import json
import uuid
from backlot.studio import atomic_private
from backlot.work_catalog import read_json, sha, WorkError, WorkCatalog
from backlot.studio_investment_recompose import fingerprint
from backlot import studio_hum_production as speech
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'templates/promo-reference-phase-v3'
CONTRACT = 'haike.promo-reference-full/3'
REGISTRY_VERSION = '3.0.0-reference-public.3'
GALLERY_ID = 'motion-package-mg-8d3e5baeef9310e4b49b41de'
KIND = 'studio_investment_recompose'
REQUEST_FILE = 'promo-phase-v3-request.json'
ASSET_DIR = 'promo-reference-full'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

REFERENCE={'template_id':'motiongit-promo-user','version':'2.6.4','package_sha256':'8d3e5baeef9310e4b49b41de93e07fee23c65fd606c2271f63e94c99815650fe','implementation':'independently authored from publicly viewable58.75s reference; no protected core'}
RECIPES={'orange','wall','detail','quote','notice','brand'}

def require(ok,message):
    if not ok:raise WorkError(message)

def bound(value):
    require(isinstance(value,dict) and set(value)=={'path','sha256'},'源文件须绑定path/sha256')
    p=Path(value['path']);require(p.is_file() and not p.is_symlink() and sha(p)==value['sha256'],'源文件缺失或SHA改变')
    return p

def toolchain():
    import os
    from backlot import studio_motiongit as motion
    supplied=os.environ.get('REMOTION_BROWSER_EXECUTABLE')
    candidates=[Path(supplied)] if supplied else [ROOT.parent/'runtime/browser/chrome-headless-shell.exe',ROOT/'runtime/browser/chrome-headless-shell.exe',ROOT.parent/'.local/template-upgrade-20261102/runtime-smoke/runtime/browser/chrome-headless-shell.exe']
    browser=next((p for p in candidates if p.is_file()),None);node=motion.node_executable()
    require(browser and node and Path(node).is_file(),'促销组件缺少已安装的Node或浏览器，请由运行时准备恢复')
    return Path(node),browser

def preflight(value):
    require(isinstance(value,dict) and not set(value)-{'title','brand','asr','script','assets','scenes','media','material_review','source_receipts'},'独立促销输入字段无效')
    assets=value.get('assets',{})
    require(isinstance(assets,dict) and all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',n) and not n.startswith('.') for n in assets),'资产名无效')
    paths={n:bound(a) for n,a in assets.items()}
    require({'voice.wav','music.wav','body.ttf'}<=set(paths),'缺少完整声音、独立配乐或OFL字体')
    asr=read_json(bound(value['asr']));script=read_json(bound(value['script']))
    require(asr.get('audio_sha256')==sha(paths['voice.wav']) and isinstance(script.get('text'),str),'真实ASR须绑定本期完整声音')
    sentences=asr.get('segments',[])
    require(sentences and all(s.get('words') for s in sentences),'须有真实句词时码')
    from backlot.motion_replay_imported_production import caption_chunks
    captions=caption_chunks(sentences,limit=24)
    for c in captions:c['text']=c['text'].replace('跟他','跟它').replace('1分钱','一分钱')
    for previous,current in zip(captions,captions[1:]):
        prefix=re.match(r'^[，,、。！？!?；;：:]+',current['text'])
        if prefix:
            previous['text']+=prefix.group();current['text']=current['text'][len(prefix.group()):]
    norm=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',s).lower()
    require(norm(''.join(c['text'] for c in captions))==norm(script['text']),'不得删减本期完整稿')
    clock=speech._clock(paths['voice.wav'])
    audio=speech._audio_plan({'voice':'voice.wav','music':'music.wav','musicGainDb':-13,'tailSeconds':0},paths,clock)
    frames=audio['durationFrames']*2;duration=frames/60
    media=deepcopy(value.get('media'));require(isinstance(media,list) and 4<=len(media)<=24,'作品墙须有4至24项真实素材')
    ids=set();proven=read_json(bound(value['material_review']))
    from PIL import Image,ImageFont
    from backlot.studio_render import media_probe
    for m in media:
        require(isinstance(m,dict) and set(m)=={'id','src','thumbnail','kind','label'} and isinstance(m['id'],str) and m['id'] not in ids,'素材身份无效')
        ids.add(m['id'])
        require(m['src'] in paths and m['thumbnail'] in paths and m['kind'] in {'image','video'} and 0<len(m['label'])<=20,'素材文件或标签无效')
        with Image.open(paths[m['thumbnail']]) as im:require(min(im.size)>=240,'缩略图像素不足')
        if m['kind']=='video':
            match=next((r for r in proven if r.get('alias')==m['src']),None)
            require(match and match.get('sha256')==sha(paths[m['src']]),'实拍须绑定原始实际看帧清单及源SHA')
            info=media_probe(paths[m['src']]);m['sourceDuration']=info['duration']
            require(info.get('video') and match.get('frames') and all(Path(f['image']).is_file() for f in match['frames']),'实拍缺少真实看帧记录')
        else:
            with Image.open(paths[m['src']]) as im:require(min(im.size)>=240,'真实图片像素不足')
    scenes=deepcopy(value.get('scenes'));require(isinstance(scenes,list) and scenes,'缺少完整原参考动作链')
    cursor=0;recipes=[]
    by_id={m['id']:m for m in media}
    for i,s in enumerate(scenes):
        require(isinstance(s,dict) and not set(s)-{'id','sentence_start','sentence_end','recipe','title','subtitle','labels','events','windows'},'促销镜头含未开放字段')
        a,b=s.pop('sentence_start',None),s.pop('sentence_end',None)
        require(type(a) is int and type(b) is int and a==cursor and a<b<=len(sentences),'镜头须依次覆盖全部真实句')
        cursor=b;s['start']=0 if i==0 else float(sentences[a]['start']);s['end']=duration if i==len(scenes)-1 else float(sentences[b]['start'])
        require(s.get('recipe') in RECIPES and s['end']-s['start']>=3,'动作类型或完整阅读窗无效')
        recipes.append(s['recipe'])
        require(isinstance(s.get('title'),str) and 0<len(s['title'])<=30 and len(s.get('subtitle',''))<=70,'标题超出原参考版式容量')
        require(isinstance(s.get('labels'),list) and 1<=len(s['labels'])<=6 and all(isinstance(x,str) and len(x)<=34 for x in s['labels']),'画面短标签无效')
        cues=[]
        for e in s.pop('events',[]):
            si,wi=e.get('sentence'),e.get('word')
            require(set(e)<= {'sentence','word'} and type(si) is int and a<=si<b,'事件必须绑定实际句词')
            require(wi is None or type(wi) is int and 0<=wi<len(sentences[si]['words']),'词时码编号无效')
            cues.append(float(sentences[si]['start'] if wi is None else sentences[si]['words'][wi]['start']))
        require(cues and cues==sorted(cues) and all(s['start']<=t<s['end']-.1 for t in cues),'动作须有真实时码与落定窗口')
        s['cues']=cues
        for w in s.get('windows',[]):
            require(set(w)=={'mediaId','start','end','offset'} and w['mediaId'] in by_id and by_id[w['mediaId']]['kind']=='video','视频窗口须绑定真实源')
            require(s['start']<=w['start']<w['end']<=s['end'] and w['offset']>=0 and w['offset']+w['end']-w['start']<=by_id[w['mediaId']]['sourceDuration']+.025,'实拍不得循环、冻结、变速或超出源区间')
    require(cursor==len(sentences) and recipes==['orange','wall','detail','quote','notice','brand'],'必须完整保留橙字、四列墙、同卡详情、情境转述、边界与品牌收尾')
    require(isinstance(value.get('source_receipts'),dict),'须保留原稿与素材授权')
    font=ImageFont.truetype(str(paths['body.ttf']),46)
    require(all(font.getlength(c['text'])<=1740 for c in captions),'字幕超过真实字体版心')
    for scene in scenes:
        require(ImageFont.truetype(str(paths['body.ttf']),76).getlength(scene['title'])<=1640 and ImageFont.truetype(str(paths['body.ttf']),30).getlength(scene['subtitle'])<=1640,'标题或辅助行超过真实字体容量')
        if scene['recipe']=='orange':
            require(all(ImageFont.truetype(str(paths['body.ttf']),154).getlength(label)<=1640 for label in scene['labels']),'橙底大字超过真实字体容量')
        if scene['recipe']=='detail':
            require(all(ImageFont.truetype(str(paths['body.ttf']),55).getlength(label)<=1160 for label in scene['labels']),'详情文字超过两行真实字体容量')
        if scene['recipe']=='quote':require(len(scene['labels'])==2,'情境转述须同时有正文与明确语境')
    props={'width':1920,'height':1080,'fps':60,'durationFrames':frames,'title':value['title'],'brand':value.get('brand','海客AI社区服务店'),'font':'body.ttf','audio':'master.wav','captions':captions,'scenes':scenes,'media':media}
    return {'props':props,'audio':audio,'paths':paths,'voice_clock':clock,'reference':deepcopy(REFERENCE),'source_receipts':deepcopy(value['source_receipts']),'evidence':{'asr':value['asr'],'script':value['script'],'material_review':value['material_review'],'caption_count':len(captions),'full_text':True}}

def prepare_contract(template, request, *, workspace):
    """Read-only public preparation; fixed /2 consumer, never a queue write."""
    require(Path(workspace).resolve() == ROOT.parent, '请在所属工作区准备阶段v3')
    require((template.get('template_id'),template.get('version'),template.get('gallery_id')) ==
            (REFERENCE['template_id'],REGISTRY_VERSION,GALLERY_ID), '阶段v3精确登记或canonical展示身份无效')
    require(isinstance(request,dict) and not set(request)-{'template_id','version','workflow','input','action_ids'}, '阶段v3准备字段无效')
    require(request.get('template_id',REFERENCE['template_id']) == REFERENCE['template_id']
            and request.get('version',REGISTRY_VERSION) == REGISTRY_VERSION
            and request.get('workflow','promo-reference-phase-v3') == 'promo-reference-phase-v3', '阶段v3路线或版本无效')
    if 'input' not in request:
        return {'status':'blocked','submitted':False,'blockers':['请绑定完整声音、真实句词、原稿、OFL字体及已审实拍与六段动作链'],'consumer':None}
    value=deepcopy(request['input']);n=preflight(value)
    used=[f"haike.motiongit-promo-user.reference-public.{s['recipe']}" for s in n['props']['scenes']]
    require(len(used)==6 and set(used)=={a['id'] for a in template['actions']}, '阶段v3须保留完整六段动作')
    require('action_ids' not in request or len(request['action_ids'])==len(used) and set(request['action_ids'])==set(used), '阶段v3动作选择不完整')
    return {'status':'prepared','submitted':False,'blockers':[],'production_contract':CONTRACT,'gallery_id':GALLERY_ID,
        'renderer':deepcopy(template['renderer']),'action_bindings':deepcopy(template['actions']),'props':n['props'],
        'timeline':{'clock':n['voice_clock'],'events':[{'scene_id':s['id'],'recipe':s['recipe'],'start':s['start'],'end':s['end'],'cues':s['cues']} for s in n['props']['scenes']]},
        'consumer':{'entrypoint':'backlot.studio_promo_phase_v3:prepare','input':value,'requires_existing_queue':True,'category':'independent_project_adapter'},
        'reproduction':{'implementation_identity':'promo-reference-phase-v3','reference_identity':n['reference'],'original_personal_package_required':False,'full_audio':True,'full_text':True,'paid_calls':0},
        'validation_scope':'只读完整输入/实际主钟/原字节renderer继承；阶段v3实际出片与视听另验'}


def runtime():
    inheritance = read_json(TEMPLATE / 'INHERITANCE.json')
    require(inheritance.get('state') == 'frozen', 'C最终动作源码尚未冻结，阶段v3不可执行')
    pinned = inheritance.get('files', {})
    require(pinned and {'render.cjs', 'index.tsx'} <= set(pinned), '缺少冻结渲染实现')
    require(all(Path(name).name == name and not (TEMPLATE/name).is_symlink()
                and (TEMPLATE/name).is_file() and sha(TEMPLATE/name) == digest
                for name, digest in pinned.items()), '阶段v3继承源码缺失或字节改变')
    paths = [Path(__file__), Path(speech.__file__), ROOT/'remotion-composer/package-lock.json',
             TEMPLATE/'INHERITANCE.json', *[TEMPLATE/n for n in sorted(pinned)],
             *map(Path, resolve_ffmpeg_pair()), *toolchain()]
    require(all(p.is_file() for p in paths), '阶段v3运行组件缺失')
    return {str(p.resolve()): sha(p) for p in paths}


def _base(r):
    return {k: v for k, v in r.items() if k not in {'phase', 'review_binding'}}


def _freeze(queue, core, paths):
    core = deepcopy(core)
    core['project_id'] = 'studio-' + fingerprint(core)[:16]
    digest = fingerprint(core)
    r = {**core, 'request_sha256': digest, 'render_id': 'promo-phase-v3-' + digest[:20]}
    from lib.checkpoint import init_project
    project = queue.projects_root/r['project_id']
    record = project/'artifacts'/REQUEST_FILE
    if record.exists():
        require(read_json(record) == r, '本期阶段v3冻结记录冲突')
    else:
        init_project(r['project_id'], title=r['title'], pipeline_type='animated-explainer', pipeline_dir=queue.projects_root)
        destination = project/'assets'/ASSET_DIR
        destination.mkdir(parents=True, exist_ok=True)
        for name, path in paths.items():
            require(Path(name).name == name and not name.startswith('.'), '素材逻辑路径无效')
            shutil.copy2(path, destination/name)
        atomic_private(record, r)
    validate(queue, r)
    return r


def prepare(queue, value):
    n = preflight(value)
    require(shutil.disk_usage(queue.projects_root).free >= 2*1024**3, '阶段v3需至少2GiB可用作业空间')
    core = {'contract': CONTRACT, 'title': value['title'], 'props': n['props'], 'audio': n['audio'],
            'voice_clock': n['voice_clock'], 'reference': n['reference'], 'source_receipts': n['source_receipts'],
            'evidence': n['evidence'], 'origins': {name: {'path': str(p), 'sha256': sha(p)} for name,p in n['paths'].items()},
            'runtime': runtime(), 'preview_revision': 'initial', 'publication': False, 'paid_calls': 0}
    return _freeze(queue, core, n['paths'])


def new_preview_revision(queue, r, *, reason, confirmed=False):
    require(confirmed is True and isinstance(reason, str) and reason.strip(), '重做预览须明确确认并说明原因')
    project, _ = validate(queue, _base(r))
    # Old outputs, approval, queue state and source request are never edited.
    core = {k:v for k,v in _base(r).items() if k not in {'request_sha256','render_id','project_id'}}
    core.update(preview_revision=uuid.uuid4().hex, previous_request_sha256=r['request_sha256'])
    paths = {name: project/'assets'/ASSET_DIR/name for name in r['origins']}
    result = _freeze(queue, core, paths)
    atomic_private(queue.projects_root/result['project_id']/'artifacts/revision-reason.json',
                   {'previous_request_sha256': r['request_sha256'], 'reason': reason.strip()})
    return result


def validate(queue, r, *, execution=True):
    base = _base(r)
    core = {k:v for k,v in base.items() if k not in {'request_sha256','render_id'}}
    require(r.get('contract') == CONTRACT and fingerprint(core) == r.get('request_sha256'), '阶段v3请求身份改变')
    require(re.fullmatch(r'studio-[0-9a-f]{16}', r.get('project_id',''))
            and r.get('render_id') == 'promo-phase-v3-' + r['request_sha256'][:20], '阶段v3项目/输出身份无效')
    require(r.get('publication') is False and r.get('paid_calls') == 0, '阶段v3只允许本地非发布制作')
    require(r.get('preview_revision') == 'initial' or re.fullmatch(r'[0-9a-f]{32}', r.get('preview_revision','')), '预览revision无效')
    project = queue.projects_root/r['project_id'];folder = project/'renders'/r['render_id']
    require(project.resolve().is_relative_to(queue.projects_root.resolve()) and not project.is_symlink(), '项目路径越界')
    require(read_json(project/'artifacts'/REQUEST_FILE) == base, '阶段v3冻结记录改变')
    for name, row in r['origins'].items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',name) and not name.startswith('.'), '冻结素材名无效')
        path = project/'assets'/ASSET_DIR/name
        require(path.is_file() and not path.is_symlink() and sha(path) == row['sha256'], '冻结素材缺失或SHA改变：'+name)
    if execution:
        require(runtime() == r['runtime'], '阶段v3执行组件或工具链改变；保留原版本，不豁免SHA')
        if r.get('phase') == 'render':
            require(r.get('review_binding') == _review_binding(folder,r), '正式导出未绑定当前明确批准的完整预览')
    return project, folder


def _preview_binding(folder, r):
    path = folder/'preview.json';receipt = read_json(path)
    require(path.is_file() and not path.is_symlink() and receipt.get('request_sha256') == r['request_sha256']
            and receipt.get('preview_revision') == r['preview_revision'], '本期预览回执缺失或身份不符')
    rows = receipt.get('images')
    require(isinstance(rows,list) and rows and all(isinstance(row,dict) for row in rows), '预览图片清单缺失')
    names = [row.get('name') for row in rows]
    require(all(isinstance(n,str) and re.fullmatch(r'[A-Za-z0-9_.-]+',n) and not n.startswith('.') for n in names)
            and len(names) == len(set(names)), '预览图片名无效或重复')
    from PIL import Image
    images = []
    for row in rows:
        image = folder/'preview'/row['name']
        require(image.is_file() and not image.is_symlink() and sha(image) == row.get('sha256'), '预览图片缺失或SHA改变：'+row['name'])
        with Image.open(image) as decoded:decoded.verify()
        images.append({'name':row['name'], 'sha256':row['sha256']})
    return {'request_sha256':r['request_sha256'], 'preview_revision':r['preview_revision'],
            'preview_sha256':sha(path), 'images':images}


def _review_binding(folder, r):
    binding = _preview_binding(folder, r)
    approval = read_json(folder/'visual-review.json')
    require(approval.get('decision') == 'approve', '当前完整预览未明确批准，拒绝或要求修改后不能导出')
    require(approval.get('binding') == binding and isinstance(approval.get('reviewer'),str)
            and approval['reviewer'].strip(), '当前完整预览批准身份已失效')
    return binding


def review(queue, r, evidence):
    _, folder = validate(queue,_base(r))
    require(isinstance(evidence,dict) and isinstance(evidence.get('decision'),str)
            and evidence['decision'] in {'approve','reject','changes_requested'},
            '审核决定必须显式选择approve、reject或changes_requested')
    preview_jobs = _phase_jobs(queue,r,'preview')
    require(preview_jobs and preview_jobs[0]['status'] == 'completed' and not preview_jobs[0]['cancel_requested'],
            '须先完成原preview父任务，不能跨过取消或未知状态审核')
    binding = _preview_binding(folder,r)
    require(evidence.get('preview_sha256') == binding['preview_sha256']
            and evidence.get('inspected_images') == binding['images']
            and isinstance(evidence.get('reviewer'),str) and evidence['reviewer'].strip(), '审核须绑定本期全部实际预览图片')
    atomic_private(folder/'visual-review.json', {'decision':evidence['decision'], 'binding':binding, 'reviewer':evidence['reviewer'].strip(),
        'note':evidence.get('note',''), 'continuous_watching':'pending', 'continuous_listening':'pending', 'device_listening':'pending'})
    return {'reviewed':True, 'decision':evidence['decision'], 'approved':evidence['decision']=='approve', 'binding':binding, 'scope':'sampled-preview'}


def _phase_jobs(queue,r,phase):
    # No public-list limit or filename/prefix matching; this is a read only query.
    with queue._connection() as connection:
        rows = connection.execute('SELECT job_id,frozen_request FROM production_jobs WHERE project_id=? AND kind=? AND parent_job_id=?',
                                  (r['project_id'],KIND,r['render_id'])).fetchall()
    jobs = []
    for row in rows:
        existing = json.loads(row['frozen_request'])
        if existing.get('phase') == phase and _base(existing) == _base(r):jobs.append(queue.get(row['job_id'],include_private=True))
    require(len(jobs) <= 1, '同一冻结请求存在多个阶段父任务，须明确核对，不自动选择')
    return jobs


def _output_binding(folder, r, expected_review=None):
    path = folder/'result.json';quality_path = folder/'quality.json';output = folder/'promo-reference-full.mp4'
    done = read_json(path);quality = read_json(quality_path)
    require(done and quality and all(p.is_file() and not p.is_symlink() for p in [path,quality_path,output]), '完整成片或质量记录缺失')
    require(done.get('request_sha256') == r['request_sha256'] and done.get('props_sha256') == fingerprint(r['props'])
            and quality.get('request_sha256') == r['request_sha256'] and quality.get('full_decode') == 'passed'
            and sha(output) == done.get('output_sha256') and sha(quality_path) == done.get('quality_sha256'), '缓存成片或质量身份改变')
    binding = done.get('review_binding')
    require(isinstance(binding,dict) and binding.get('request_sha256') == r['request_sha256']
            and binding.get('preview_revision') == r['preview_revision'] and quality.get('review_binding') == binding
            and (expected_review is None or binding == expected_review), '缓存成片审核身份不符')
    return {'output_path':str(output),'output_sha256':done['output_sha256'],'quality_sha256':done['quality_sha256']}


def health(queue,r):
    """No queue/asset writes. Cached availability and execution readiness differ."""
    result = {'request_sha256':r.get('request_sha256')}
    try:_,folder = validate(queue,r,execution=False)
    except Exception as exc:return {**result,'frozen_inputs':{'status':'invalid','reason':str(exc)},'execution':{'status':'blocked'},'preview':{'status':'unchecked'},'output':{'status':'unchecked'}}
    result['frozen_inputs'] = {'status':'valid'}
    try:
        require(runtime() == r['runtime'], '执行源码/依赖/工具链SHA不同')
        result['execution'] = {'status':'ready'}
    except Exception as exc:result['execution'] = {'status':'blocked','reason':str(exc)}
    for name, check, marker in [('preview',lambda:_preview_binding(folder,r),folder/'preview.json'),
                                 ('output',lambda:_output_binding(folder,r),folder/'result.json')]:
        try:result[name] = {'status':'valid',**check()}
        except Exception as exc:
            any_files = marker.exists() or (folder/('preview' if name=='preview' else 'promo-reference-full.mp4')).exists()
            result[name] = {'status':'invalid' if any_files else 'missing','reason':str(exc)}
    try:
        decision=read_json(folder/'visual-review.json').get('decision')
        binding=_preview_binding(folder,r)
        stored=read_json(folder/'visual-review.json')
        require(stored.get('binding')==binding and isinstance(stored.get('reviewer'),str) and stored['reviewer'].strip(), '审核记录缺失或身份改变')
        require(decision in {'approve','reject','changes_requested'}, '审核决定缺失或无效')
        result['review']={'status':'valid' if decision=='approve' else 'not_approved','decision':decision,'binding':binding}
    except Exception as exc:result['review'] = {'status':'missing_or_invalid','reason':str(exc)}
    return result


def submit(queue,r,*,phase='preview'):
    _, folder = validate(queue,r)
    require(phase in {'preview','render'}, '制作阶段无效')
    frozen = {**_base(r),'phase':phase}
    key = CONTRACT+':'+r['request_sha256']+':'+phase
    if phase == 'render':
        previews = _phase_jobs(queue,r,'preview')
        require(previews and previews[0]['status'] == 'completed' and not previews[0]['cancel_requested'],
                '原preview父任务尚未完成或已取消/未知，不能新建render父')
        binding = _review_binding(folder,r)
        frozen['review_binding'] = binding
        key += ':'+fingerprint(binding)
    existing = _phase_jobs(queue,r,phase)
    if existing:
        require(existing[0]['frozen_request'] == frozen, '已有阶段绑定不同；须显式创建新预览revision')
        job = queue.get(existing[0]['job_id'])
    else:
        job = queue.submit(kind=KIND, project_id=r['project_id'], source='codex', priority='normal',
                           parent_job_id=r['render_id'], frozen_request=frozen,idempotency_key=key,start_paused=True)
    require(queue.get(job['job_id'],include_private=True)['frozen_request'] == frozen,
            '幂等键已绑定不同的冻结内容，保留原父并核对')
    # Recheck after atomic queue admission to detect legacy duplicate parents.
    _phase_jobs(queue,r,phase)
    return {**job,'availability':health(queue,r)}


def _render(queue,r,project,folder):
    """Local formulas inherited from C; no renderer is invoked by unit tests."""
    assets={n:project/'assets/promo-reference-full'/n for n in r['origins']}
    public=folder/'public';public.mkdir(exist_ok=True)
    for name,path in assets.items():
        if name not in {'voice.wav','music.wav'}:shutil.copy2(path,public/name)
    atomic_private(folder/'props.json',r['props'])
    for p in TEMPLATE.iterdir():
        if p.suffix in {'.tsx','.ts','.cjs'}:
            (folder/'template').mkdir(exist_ok=True);shutil.copy2(p,folder/'template'/p.name)
    node,browser=toolchain()
    command=[str(node),str(TEMPLATE/'render.cjs'),str(ROOT/'remotion-composer'),str(folder),r['phase'],str(browser)]
    if r['phase']=='preview':
        subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW,timeout=1200)
        return
    output=folder/'promo-reference-full.mp4'
    audio_receipt=speech.mix_master(r['audio'],assets,public/'master.wav');atomic_private(folder/'audio-receipt.json',audio_receipt)
    subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW,timeout=7200)
    ff,_=resolve_ffmpeg_pair();duration=r['props']['durationFrames']/60
    export=[ff,'-nostdin','-y','-v','error','-i',str(folder/'mezzanine.mp4'),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k','-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
    subprocess.run(export,check=True,capture_output=True,creationflags=NO_WINDOW)
    from backlot.studio_render import media_probe
    from backlot.studio_investment_audio_v5 import measure_audio
    info=media_probe(output);v=info['video'];a=info['audio'];loud=measure_audio(output)
    require((v['width'],v['height'])==(1920,1080) and v['codec_name']=='h264' and v['pix_fmt']=='yuv420p' and int(v['nb_frames'])==r['props']['durationFrames'] and int(v['bit_rate'])>=20000000 and a['channels']==2 and str(a['sample_rate'])=='48000' and loud['true_peak_dbtp']<=-1.5,'促销成片技术指标未通过')
    subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
    atomic_private(folder/'quality.json',{'request_sha256':r['request_sha256'],'review_binding':r['review_binding'],'media':info,'audio':loud,'full_decode':'passed','export_command':export,'continuous_watching':'pending','continuous_listening':'pending','device_listening':'pending','visual_review_sha256':sha(folder/'visual-review.json'),'full_text_evidence':r['evidence']})


def validate_claim(queue,job_id):
    """Read-only preclaim gate for the fixed root /3 dispatcher."""
    job=queue.get(job_id,include_private=True);r=job.get('frozen_request') or {}
    require(job.get('kind')==KIND and r.get('contract')==CONTRACT
            and job.get('project_id')==r.get('project_id') and job.get('parent_job_id')==r.get('render_id'), '阶段v3待领取父身份不符')
    require((job['status']=='paused' or job['status']=='failed' and job['retryable'])
            and not job['cancel_requested'], '原父状态不允许领取，保留原任务')
    validate(queue,r)
    require(r.get('phase') in {'preview','render'}, '阶段无效')
    if r['phase']=='render':
        previews=_phase_jobs(queue,r,'preview')
        require(previews and previews[0]['status']=='completed' and not previews[0]['cancel_requested'], '原preview父尚未完成或已取消/未知')
    return {'job_id':job_id,'claim_ready':True,'request_sha256':r['request_sha256'],'phase':r['phase']}


def _claimed(queue,job,r):
    actual=queue.get(job['job_id'],include_private=True)
    require(actual['status']=='running' and actual['kind']==KIND
            and actual['project_id']==r['project_id'] and actual['parent_job_id']==r['render_id']
            and actual['frozen_request']==r
            and all(job.get(k)==actual.get(k) for k in ['job_id','kind','project_id','parent_job_id','worker_id','attempt_count'])
            and isinstance(actual.get('worker_id'),str) and actual['worker_id'],
            '阶段v3领取身份/工作者/尝试次数与原冻结父不符')
    expiry=actual.get('lease_expires_at')
    try:deadline=datetime.fromisoformat(expiry.replace('Z','+00:00')) if isinstance(expiry,str) else None
    except ValueError:deadline=None
    require(deadline and deadline.tzinfo is not None and deadline>datetime.now(timezone.utc), '阶段v3原父领取租约已失效')
    return actual


def run(queue,job):
    r=job['frozen_request']
    try:
        actual=_claimed(queue,job,r)
        project,folder=validate(queue,r);folder.mkdir(parents=True,exist_ok=True)
        require(r.get('phase') in {'preview','render'}, '阶段无效')
        require(not actual['cancel_requested'], '原父任务已请求取消，保留现场')
        if r['phase']=='render':
            previews=_phase_jobs(queue,r,'preview')
            require(previews and previews[0]['status']=='completed' and not previews[0]['cancel_requested'], '原预览父状态不允许导出')
            require(r.get('review_binding')==_review_binding(folder,r), '正式导出冻结审核绑定已失效')
        current=health(queue,r)
        if r['phase']=='preview' and current['preview']['status']=='valid':
            return {'status':'completed','stage':'本期原预览已核对','result':current['preview']}
        if r['phase']=='render' and current['output']['status']=='valid':
            return {'status':'completed','stage':'本期缓存成片与质量身份已核对','result':_output_binding(folder,r,r['review_binding'])}
        marker=folder/(r['phase']+'-started.json')
        stale=(folder/'preview').exists() or (folder/'preview.json').exists() if r['phase']=='preview' else any((folder/n).exists() for n in ['result.json','quality.json','promo-reference-full.mp4','mezzanine.mp4'])
        require(not marker.exists() and not stale, '阶段现场已有缺件/中断产物，请保留现场并显式创建新预览revision')
        atomic_private(marker,{'request_sha256':r['request_sha256'],'phase':r['phase'],'queue_job_id':job['job_id']})
        _render(queue,r,project,folder)
        if r['phase']=='preview':
            receipt=read_json(folder/'preview.json')
            # Renderer bytes stay unchanged: controller adds identity after it returns.
            atomic_private(folder/'preview.json',{**receipt,'request_sha256':r['request_sha256'],'preview_revision':r['preview_revision']})
            binding=_preview_binding(folder,r)
            return {'status':'completed','stage':'本期实际预览已生成，须逐图审核','result':binding}
        _claimed(queue,job,r)
        require(r['review_binding']==_review_binding(folder,r), '导出期间批准已失效；保留现场，不记成功')
        require(not queue.get(job['job_id'],include_private=True)['cancel_requested'], '原父任务已请求取消，保留现场')
        atomic_private(folder/'result.json',{'request_sha256':r['request_sha256'],'props_sha256':fingerprint(r['props']),
            'review_binding':r['review_binding'],'output_sha256':sha(folder/'promo-reference-full.mp4'),
            'quality_sha256':sha(folder/'quality.json'),'paid_calls':0,'publication':False})
        output=_output_binding(folder,r,r['review_binding'])
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output['output_path'],work_key='main',mode='manual',
            event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title'])
        return {'status':'completed','stage':'阶段v3完整成片已合成，视听复核待验','result':{**output,'work_id':work['work_id'],'qa_status':'pending'}}
    except Exception as exc:
        return {'status':'failed','stage':'阶段v3保留原现场，待明确恢复','error':{'type':type(exc).__name__,'message':str(exc)[:1000]},
                'retryable':False,'safe_resume_point':'promo-phase-v3-explicit-revision'}
