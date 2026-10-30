"""Versioned editable full-template drafts; execution stays in the existing lane.

Only this module reads trusted server recipe paths. Browser requests bind owned
asset IDs and safe slot names and never choose a filesystem source directory.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import threading
from uuid import uuid4
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from backlot import studio_dark_full as adapter
from backlot.production_queue import _sanitize, ProductionQueueError, ProductionQueueConflict
from backlot.studio import Studio, timestamp
from backlot.work_api import call
from backlot.work_catalog import WorkError, read_json, sha

router=APIRouter(prefix='/api/studio/dark-full')
TASK_ROOT=Path(__file__).resolve().parents[2]/'.local/motion-full-20261028'
IDENTITY=re.compile(r'studio-[0-9a-f]{16}')
THEMES={'elder':'hedgerow','child':'cobalt'}
MAX_UPLOAD=256*1024*1024
_DISPATCH_LOCK=threading.Lock()
_INFLIGHT=set()


def require(ok,message,code='invalid'):
    if not ok:raise WorkError(message,code)


def safe(value):
    value=_sanitize(value,redact_local_paths=True)
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items() if k not in {'sources','origins','runtime','path','private'}}
    if isinstance(value,list):return [safe(v) for v in value]
    if isinstance(value,str) and value.startswith('/') and not value.startswith(('/api/','/projects','/settings','/avatar')):return '[LOCAL_PATH]'
    return value


def mutation(request,raw=False):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):raise HTTPException(403,'请从本机海客工作台提交')
    expected='application/octet-stream' if raw else 'application/json'
    if expected not in request.headers.get('content-type',''):raise HTTPException(415,'请求格式不支持')


def queue(request):
    from backlot.server import _ensure_production_queue
    return _ensure_production_queue(request.app)


class DraftStore:
    def __init__(self,projects_root):
        self.studio=Studio(projects_root)
        with self.studio.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS dark_full_drafts(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dark_full_runs(draft_id TEXT,revision INTEGER,digest TEXT, data TEXT NOT NULL,PRIMARY KEY(draft_id,revision,digest));''')
            db.execute('CREATE TABLE IF NOT EXISTS dark_full_dispatch(job_id TEXT PRIMARY KEY,data TEXT NOT NULL)')

    def get(self,identity,db=None):
        require(isinstance(identity,str) and IDENTITY.fullmatch(identity),'草稿编号无效')
        if db is None:
            with self.studio.db() as con:return self.get(identity,con)
        row=db.execute('SELECT data FROM dark_full_drafts WHERE id=?',(identity,)).fetchone()
        require(row is not None,'完整模板草稿不存在','missing')
        return json.loads(row[0])

    def write(self,value,revision,db):
        previous=db.execute('SELECT revision FROM dark_full_drafts WHERE id=?',(value['id'],)).fetchone()
        require((not previous and revision in {0,None}) or (previous and revision==previous[0]),'草稿已更新，请重新读取后继续','conflict')
        value=deepcopy(value);value.update(revision=(previous[0]+1 if previous else 1),updated_at=timestamp())
        db.execute('INSERT INTO dark_full_drafts VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,data=excluded.data',(value['id'],value['revision'],json.dumps(value,ensure_ascii=False)))
        return value

    def public(self,value):
        output={k:value[k] for k in ['id','revision','title','theme','script','recipe','updated_at','needs_alignment']}
        output['bindings']=[{'slot':name,'sha256':row['sha256'],'bytes':row.get('bytes',0),'kind':row.get('kind','file'),
                             'url':f"/api/studio/dark-full/drafts/{value['id']}/media/{quote(name,safe='')}"} for name,row in value['sources'].items()]
        return safe(output)

    def list(self):
        with self.studio.db() as db:rows=db.execute('SELECT data FROM dark_full_drafts ORDER BY rowid DESC').fetchall()
        return [self.public(json.loads(r[0])) for r in rows]

    def save(self,data):
        require(isinstance(data,dict) and not set(data)-{'id','revision','title','theme','script','recipe'},'草稿包含未开放字段；文件请经上传绑定')
        theme=data.get('theme','elder');require(theme in THEMES,'请选择长者或亲子主题')
        title=data.get('title','海客完整动效视频');script=data.get('script','')
        require(isinstance(title,str) and 0<len(title)<=100 and isinstance(script,str) and len(script)<=10000,'标题或文案长度无效')
        recipe=data.get('recipe',{});require(isinstance(recipe,dict) and not set(recipe)-{'props','audio','provenance','shotPlan'},'制作参数须使用开放字段，不能包含本地路径或服务配置')
        require(len(json.dumps(recipe).encode())<=600000,'制作参数过大')
        require(_sanitize(recipe,redact_local_paths=False)==recipe,'制作参数包含服务凭据字段')
        require(safe(recipe)==recipe,'制作参数不能包含本地文件路径')
        identity=data.get('id') or 'studio-'+uuid4().hex[:16]
        with self.studio.db() as db:
            old=self.get(identity,db) if data.get('id') else None
            if old:require(data.get('revision')==old['revision'],'草稿已更新，请重新读取后继续','conflict')
            value={'id':identity,'title':title,'theme':theme,'script':script,'recipe':deepcopy(recipe),'sources':deepcopy(old['sources']) if old else {},
                   'needs_alignment':bool(old and (old['needs_alignment'] or old['script']!=script))}
            value['recipe'].setdefault('props',{})['variant']=THEMES[theme]
            if old and all(value[k]==old[k] for k in ['title','theme','script','recipe','needs_alignment']):return self.public(old)
            return self.public(self.write(value,data.get('revision',0),db))

    def copy_recipe(self,theme):
        require(theme in THEMES,'主题不存在','missing')
        file=TASK_ROOT/theme/'input.json';require(file.is_file(),'本机尚未保存此主题的制作配方','missing')
        original=read_json(file);identity='studio-'+uuid4().hex[:16]
        sources={};folder=self.studio.projects_root/identity/'assets/dark-full';folder.mkdir(parents=True,exist_ok=True)
        for name,path in original.get('sources',{}).items():
            require(adapter.speech._name(name),'配方素材槽名称无效')
            source=Path(path);require(source.is_file() and not source.is_symlink(),'配方中有未就绪的素材')
            source_sha=sha(source);target=folder/(source_sha+source.suffix.lower())
            if not target.exists():
                try:os.link(source,target)
                except OSError:
                    require(shutil.disk_usage(folder).free>=source.stat().st_size+64*1024*1024,'托管目录磁盘空间不足；原配方保留，请清理制作缓存或由Agent迁移后再复制')
                    shutil.copy2(source,target)
            require(sha(target)==source_sha,'复制配方的素材身份校验失败')
            sources[name]={'path':str(target),'sha256':source_sha,'bytes':target.stat().st_size,'kind':media_kind(name)}
        recipe=safe({k:deepcopy(original[k]) for k in ['props','audio','provenance','shotPlan'] if k in original})
        captions=recipe.get('props',{}).get('captions',[])
        value={'id':identity,'title':original.get('title','海客完整动效视频'),'theme':theme,'script':''.join(c['text'] for c in captions),'recipe':recipe,'sources':sources,'needs_alignment':False}
        with self.studio.db() as db:return self.public(self.write(value,0,db))

    def clone(self,identity,revision):
        value=self.get(identity);require(value['revision']==revision,'草稿已更新，请重新读取','conflict')
        value['id']='studio-'+uuid4().hex[:16];value['title']=value['title'][:94]+' · 副本'
        # Sources are immutable uploaded blobs. Copying a draft does not mutate or
        # replace the source draft; uploads in the new draft receive new blobs.
        with self.studio.db() as db:return self.public(self.write(value,0,db))

    def material_path(self,identity,slot):
        value=self.get(identity);row=value['sources'].get(slot);require(row is not None,'素材槽不存在','missing')
        path=Path(row['path']);root=self.studio.projects_root.resolve()
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root) and sha(path)==row['sha256'],'素材已变化或不属于本工作台')
        return path

    def upload(self,identity,revision,filename,kind,slot,content,rights):
        require(rights is True,'请确认拥有该素材的使用权')
        value=self.get(identity);require(value['revision']==revision,'草稿已更新，请重新读取','conflict')
        require(adapter.speech._name(slot),'请使用安全的素材槽文件名')
        require(kind==media_kind(slot),'上传类型与素材槽不一致')
        require(slot!=value['recipe'].get('audio',{}).get('voice') or Path(filename).suffix.lower()=='.wav','完整口播请上传PCM WAV，或先由现有配音流程转存为WAV')
        owner=OwnedAssets(self);asset=owner.save_asset(identity,filename,kind,content);path=owner.asset(asset['id'],identity)
        if slot==value['recipe'].get('audio',{}).get('voice'):adapter.speech._clock(path)
        with self.studio.db() as db:
            value=self.get(identity,db)
            value['sources'][slot]={'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size,'kind':kind,'asset_id':asset['id']}
            recipe=value['recipe'];audio=recipe.get('audio',{});provenance=recipe.setdefault('provenance',{})
            if slot==audio.get('voice'):
                value['needs_alignment']=True;provenance['voice']={'sha256':sha(path),'source':'本次已授权上传口播','authorized':True}
            for m in recipe.get('props',{}).get('media',[]):
                if slot in {m.get('src'),m.get('thumbnail')}:
                    for row in provenance.get('media',[]):
                        if row.get('id')==m['id']:row['reviewed']=False
            for name,row in provenance.get('audio',{}).items():
                if name==slot:row.update(sha256=sha(path),source='本次已授权上传配乐或音效')
            return self.public(self.write(value,revision,db))

    def captions(self,identity,revision,captions):
        value=self.get(identity);voice=value['recipe'].get('audio',{}).get('voice');row=value['sources'].get(voice)
        require(row is not None,'请先绑定本期完整口播')
        require(isinstance(captions,list) and 0<len(captions)<=2000,'字幕清单无效')
        previous=0
        for c in captions:
            require(isinstance(c,dict) and set(c)=={'text','startMs','endMs'} and isinstance(c['text'],str) and 0<len(c['text'])<=64,'字幕字段或行长无效')
            require(type(c['startMs']) in {float,int} and type(c['endMs']) in {float,int} and previous<=c['startMs']<c['endMs'],'字幕必须使用连续递增的真实时间码');previous=c['endMs']
        normalize=lambda s:re.sub(r'[\W_]+','',s)
        require(not value['script'] or normalize(value['script'])==normalize(''.join(c['text'] for c in captions)),'字幕内容没有完整对应当前口播文案')
        with self.studio.db() as db:
            value=self.get(identity,db);value['recipe'].setdefault('props',{})['captions']=captions
            value['recipe'].setdefault('provenance',{})['captions']={'voice_sha256':row['sha256'],'method':'user-imported-real-srt'}
            value['needs_alignment']=False
            return self.public(self.write(value,revision,db))

    def input(self,identity,revision):
        value=self.get(identity);require(value['revision']==revision,'草稿已更新，请重新读取','conflict')
        require(not value['needs_alignment'],'本期口播或文案已改变，请用现有ASR更新真实字幕时码')
        recipe=deepcopy(value['recipe']);require({'props','audio','provenance'}<=set(recipe),'请先载入本机配方，或由Agent补齐制作参数')
        try:names=adapter.required_names(recipe['props'],recipe['audio'])
        except (KeyError,TypeError):raise WorkError('缺少完整口播、字体或素材槽声明') from None
        missing=names-set(value['sources']);require(not missing,'待补素材槽：'+'、'.join(sorted(missing)))
        shots=recipe.get('shotPlan') or recipe['props'].get('scenes',[])
        require(1<=len(shots)<=len(adapter.catalog()['groups']),'请选择本期口播能容纳的完整动作组；约30秒推荐3至4组')
        for scene in shots:
            if scene.get('group') in {'s02','s03','s04','s05','s07','s08','review'}:
                windows=scene.get('clipPlan') or scene.get('videoWindows') or []
                require(any(w.get('mediaId')==scene.get('mainMediaId') for w in windows) or not any(m.get('kind')=='video' and m.get('id')==scene.get('mainMediaId') for m in recipe['props'].get('media',[])),'新动作组尚未安排主素材播放区间，请由Agent完成取段')
        return {'title':value['title'],**recipe,'sources':{name:str(self.material_path(identity,name)) for name in names}}

    def next_stage(self,identity):
        value=self.get(identity);recipe=value['recipe'];voice=recipe.get('audio',{}).get('voice');bound=voice in value['sources']
        stage='needs_voice' if not bound else 'needs_alignment' if value['needs_alignment'] or not recipe.get('props',{}).get('captions') else 'needs_review'
        return {'status':stage,'draft_revision':value['revision'],'script':value['script'],'cloud_calls':0,
                'actions':[{'method':'GET','endpoint':'/api/studio/audio-center','purpose':'读取当前账号实际可用音色与服务'},
                           {'method':'POST','endpoint':'/api/studio/audio-center/quotes','purpose':'具备真实模型和音色后按原配音流程报价，未在此发起调用'},
                           {'method':'GET','endpoint':'/api/studio/dark-full/readiness','purpose':'读取现有ASR适配器的真实配置能力；未发起识别'},
                           {'method':'POST','endpoint':f'/api/studio/dark-full/drafts/{identity}/captions','purpose':'绑定现有ASR导出的真实SRT时码'}],
                'message':'先使用已配置的配音服务或上传完整口播；配音仍需要可用服务与费用授权。' if not bound else '换口播后须重做真实字幕、素材取段和必要的人物同步；保留现有产物。'}


class OwnedAssets(Studio):
    def __init__(self,store):
        self.__dict__.update(store.studio.__dict__);self.store=store
    def draft(self,identity):return self.store.get(identity)
    def save_asset(self,draft_id,filename,kind,content):
        if len(content)<=80*1024*1024:return super().save_asset(draft_id,filename,kind,content)
        # Scope the larger source-video allowance to this complete-template
        # owner. General Studio uploads keep their established 80 MiB limit.
        self.draft(draft_id);suffix=Path(filename).suffix.lower()
        require(kind=='video' and suffix in {'.mp4','.mov'} and len(content)<=MAX_UPLOAD,'视频最多256MB；音频和图片仍为80MB')
        asset_id=uuid4().hex;folder=self.projects_root/draft_id/'assets/studio';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(asset_id+suffix);path.write_bytes(content)
        try:
            from backlot.studio_render import media_probe
            probe=media_probe(path);require(probe.get('video') and 0<probe['duration']<=600,'视频不可读取或超过10分钟')
        except Exception:
            path.unlink(missing_ok=True);raise WorkError('素材无法读取，请检查格式与时长') from None
        with self.db() as db:db.execute('INSERT INTO studio_assets VALUES(?,?,?,?,?)',(asset_id,draft_id,Path(filename).name[:160],kind,str(path)))
        return {'id':asset_id,'name':Path(filename).name[:160],'kind':kind,'url':f'/api/studio/assets/{asset_id}'}


def media_kind(name):
    ext=Path(name).suffix.lower()
    return 'video' if ext in {'.mp4','.mov','.m4v','.webm'} else 'audio' if ext in {'.wav','.mp3','.m4a','.ogg'} else 'image' if ext in {'.jpg','.jpeg','.png','.webp'} else 'file'


def store(request):
    value=getattr(request.app.state,'dark_full_drafts',None)
    if value is None:
        from backlot.studio_api import studio
        value=DraftStore(studio(request).projects_root);request.app.state.dark_full_drafts=value
    return value


@router.get('/catalog')
def catalog():
    result=deepcopy(adapter.catalog());previews=read_json(TASK_ROOT/'workbench-previews.json').get('groups',{})
    for i,g in enumerate(result['groups']):
        g['number']=i+1;g['preview']=f"/api/studio/dark-full/catalog/{g['id']}/preview" if g['id'] in previews else None
        g['preview_kind']=previews.get(g['id'],{}).get('kind','image');g['preview_label']=previews.get(g['id'],{}).get('label','预览待绑定')
    result['recipes']=[{'id':k,'variant':v,'available':(TASK_ROOT/k/'input.json').is_file()} for k,v in THEMES.items()]
    return safe(result)


@router.get('/catalog/{group_id}/preview')
def group_preview(group_id:str):
    entry=read_json(TASK_ROOT/'workbench-previews.json').get('groups',{}).get(group_id)
    if not entry:raise HTTPException(404,'本机尚未绑定此动作组的预览')
    path=Path(entry.get('path',''))
    if not path.is_file() or path.is_symlink() or path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.mp4'}:raise HTTPException(404,'预览不可用')
    return FileResponse(path,headers={'Cache-Control':'no-cache'})


@router.get('/drafts')
def drafts(request:Request):return {'drafts':call(store(request).list)}


@router.get('/readiness')
def readiness(request:Request):
    from backlot.studio_asr import status
    return safe({'asr':call(status,store(request).studio),'voice_center_endpoint':'/api/studio/audio-center',
                 'tts_execution':'requires_existing_audio_center_quote','cloud_calls':0})


@router.post('/drafts')
def save(request:Request,data:dict=Body(...)):
    mutation(request);return call(store(request).save,data)


@router.post('/recipes/{theme}/copy')
def copy_recipe(theme:str,request:Request):
    mutation(request);return call(store(request).copy_recipe,theme)


@router.get('/drafts/{identity}')
def draft(identity:str,request:Request):return call(lambda:store(request).public(store(request).get(identity)))


@router.post('/drafts/{identity}/clone')
def clone(identity:str,request:Request,data:dict=Body(...)):
    mutation(request);return call(store(request).clone,identity,data.get('revision'))


@router.post('/drafts/{identity}/assets')
async def upload(identity:str,request:Request,revision:int,slot:str,kind:str,filename:str,rights_confirmed:bool=False):
    mutation(request,raw=True);chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_UPLOAD:raise HTTPException(413,'视频上传最多256MB')
        chunks.append(chunk)
    import asyncio
    return await asyncio.to_thread(call,store(request).upload,identity,revision,filename,kind,slot,b''.join(chunks),rights_confirmed)


@router.get('/drafts/{identity}/media/{slot}')
def media(identity:str,slot:str,request:Request):return FileResponse(call(store(request).material_path,identity,slot))


@router.post('/drafts/{identity}/captions')
def captions(identity:str,request:Request,data:dict=Body(...)):
    mutation(request);return call(store(request).captions,identity,data.get('revision'),data.get('captions'))


@router.get('/drafts/{identity}/next-stage')
def next_stage(identity:str,request:Request):return call(store(request).next_stage,identity)


@router.post('/drafts/{identity}/preflight')
def preflight(identity:str,request:Request,data:dict=Body(...)):
    mutation(request)
    def run():
        result=adapter.preflight(store(request).input(identity,data.get('revision')));p=result['props']
        return {'valid':True,'seconds':p['durationFrames']/p['fps'],'frames':p['durationFrames'],'fps':p['fps'],'groups':[s['group'] for s in p['scenes']],'cloud_calls':0}
    return call(run)


@router.post('/drafts/{identity}/prepare')
def prepare(identity:str,request:Request,data:dict=Body(...)):
    mutation(request);s=store(request);revision=data.get('revision')
    def run():
        frozen=adapter.prepare(queue(request),s.input(identity,revision))
        record={k:frozen[k] for k in ['project_id','render_id','request_sha256']}
        with s.studio.db() as db:
            require(s.get(identity,db)['revision']==revision,'准备期间草稿已更新，请重新检查','conflict')
            db.execute('INSERT OR IGNORE INTO dark_full_runs VALUES(?,?,?,?)',(identity,revision,frozen['request_sha256'],json.dumps(record)))
        return {**record,'draft_revision':revision,'seconds':frozen['props']['durationFrames']/frozen['props']['fps'],'prepared':True,'cloud_calls':0}
    return safe(call(run))


def adopt_completed(s,q,identity,revision,project_id):
    """Attach a CLI-produced result only when the current draft is identical.

    Local source paths may differ after a managed copy; actual bytes, reviewed
    ranges, semantic props, audio and all public provenance must still match.
    """
    require(isinstance(project_id,str) and IDENTITY.fullmatch(project_id),'成片工程编号无效')
    frozen=read_json(q.projects_root/project_id/'artifacts'/adapter.REQUEST_FILE)
    adapter.validate(q,frozen)
    job=q.find_by_idempotency_key(adapter.CONTRACT+':'+frozen['request_sha256'])
    require(job and job['status']=='completed','此工程还没有已完成的完整模板成片')
    current=adapter.preflight(s.input(identity,revision))
    require(current['props']==frozen['props'] and current['audio']==frozen['audio']
            and safe(current['provenance'])==safe(frozen['provenance'])
            and {n:sha(p) for n,p in current['paths'].items()}=={n:r['sha256'] for n,r in frozen['origins'].items()},
            '成片与当前草稿内容、时钟或素材不同，请保留原版本并重新准备')
    record={k:frozen[k] for k in ['project_id','render_id','request_sha256']}
    with s.studio.db() as db:
        require(s.get(identity,db)['revision']==revision,'登记期间草稿已更新，请重新读取','conflict')
        db.execute('INSERT OR IGNORE INTO dark_full_runs VALUES(?,?,?,?)',(identity,revision,frozen['request_sha256'],json.dumps(record)))
    return {**record,'draft_revision':revision,'adopted':True,'cloud_calls':0}


@router.post('/drafts/{identity}/adopt')
def adopt(identity:str,request:Request,data:dict=Body(...)):
    mutation(request)
    if set(data)!={'revision','project_id'}:raise HTTPException(422,'登记成片只接受当前草稿版本和工程编号')
    return safe(call(adopt_completed,store(request),queue(request),identity,data['revision'],data['project_id']))


def recorded(request,identity,digest):
    s=store(request);s.get(identity)
    with s.studio.db() as db:row=db.execute('SELECT revision,data FROM dark_full_runs WHERE draft_id=? AND digest=? ORDER BY revision DESC',(identity,digest)).fetchone()
    require(row is not None,'本期准备记录不存在，请先检查并准备','missing')
    return row[0],json.loads(row[1])


def dispatch(request,job):
    """Use the existing exclusive claimant; no new ordering or render queue."""
    if job['status'] not in {'paused','failed'} or job['status']=='failed' and not job.get('retryable'):return
    identity=job['job_id'];s=store(request);q=queue(request)
    with _DISPATCH_LOCK:
        if identity in _INFLIGHT:return
        _INFLIGHT.add(identity)
    def note(status,message):
        with s.studio.db() as db:db.execute('INSERT OR REPLACE INTO dark_full_dispatch VALUES(?,?)',(identity,json.dumps({'status':status,'message':message,'updated_at':timestamp()},ensure_ascii=False)))
    note('waiting','原任务已保存，等待统一制作通道领取。')
    def execute():
        try:
            from backlot.production_queue_worker import ProductionQueueWorker
            result=ProductionQueueWorker(q,q.projects_root,worker_id='dark-full-ui-'+uuid4().hex[:8],lease_seconds=7200).run_local_recompose(identity)
            note('returned','本次执行已返回：'+str(result.get('stage') or result.get('status')))
        except ProductionQueueConflict:
            current=q.get(identity)
            note('busy','原任务已在制作中。' if current['status']=='running' else '统一制作通道正被占用；已保留原任务，稍后点击“恢复原任务”。')
        except Exception:
            note('attention','原任务尚未开始或需要检查；请刷新实际队列状态后恢复，保留已有产物。')
        finally:
            with _DISPATCH_LOCK:_INFLIGHT.discard(identity)
    threading.Thread(target=execute,daemon=True,name='dark-full-claim-'+identity).start()


@router.post('/drafts/{identity}/submit')
def submit(identity:str,request:Request,data:dict=Body(...)):
    mutation(request)
    def run():
        revision,record=recorded(request,identity,data.get('request_sha256'))
        require(revision==data.get('revision')==store(request).get(identity)['revision'],'草稿版本改变，请重新准备','conflict')
        q=queue(request);frozen=read_json(q.projects_root/record['project_id']/'artifacts'/adapter.REQUEST_FILE)
        job=adapter.submit(q,frozen)
        dispatch(request,job)
        return {**record,'draft_revision':revision,'job':job}
    return safe(call(run))


@router.get('/drafts/{identity}/productions')
def productions(identity:str,request:Request):
    s=store(request);s.get(identity);q=queue(request)
    with s.studio.db() as db:rows=db.execute('SELECT revision,data FROM dark_full_runs WHERE draft_id=? ORDER BY rowid DESC',(identity,)).fetchall()
    out=[]
    for row in rows:
        record=json.loads(row[1]);job=q.find_by_idempotency_key(adapter.CONTRACT+':'+record['request_sha256'])
        item={**record,'draft_revision':row[0],'job':job}
        if job:
            with s.studio.db() as db:attempt=db.execute('SELECT data FROM dark_full_dispatch WHERE job_id=?',(job['job_id'],)).fetchone()
            if attempt:item['dispatch']=json.loads(attempt[0])
        if job and job['status']=='completed':
            item['video_url']=f"/api/studio/dark-full/drafts/{identity}/productions/{record['request_sha256']}/video"
            item['work_id']=job.get('result',{}).get('work_id');item['version_id']=job.get('result',{}).get('version_id')
        out.append(item)
    return safe({'productions':out})


@router.post('/drafts/{identity}/productions/{digest}/resume')
def resume(identity:str,digest:str,request:Request,data:dict=Body(...)):
    mutation(request)
    def run():
        _,record=recorded(request,identity,digest);q=queue(request);job=q.find_by_idempotency_key(adapter.CONTRACT+':'+digest)
        require(job is not None,'此版本尚未提交制作')
        require(job['status'] in {'paused','running','completed'} or job['status']=='failed' and job.get('retryable'),'原任务当前不可直接恢复，请先检查失败原因与冻结输入','conflict')
        dispatch(request,job)
        return {**record,'job':job}
    try:return safe(call(run))
    except ProductionQueueError:raise HTTPException(409,'原任务当前不能恢复，请刷新状态') from None


@router.get('/drafts/{identity}/productions/{digest}/video')
def video(identity:str,digest:str,request:Request,nomusic:bool=False):
    _,record=call(recorded,request,identity,digest);q=queue(request);job=q.find_by_idempotency_key(adapter.CONTRACT+':'+digest)
    if not job or job['status']!='completed':raise HTTPException(404,'此版本尚未完成')
    frozen=read_json(q.projects_root/record['project_id']/'artifacts'/adapter.REQUEST_FILE)
    project=call(adapter.validate,q,frozen);path=project/'renders'/record['render_id']/(adapter.NOMUSIC_FILE if nomusic else adapter.OUTPUT_FILE)
    if not path.is_file() or path.is_symlink():raise HTTPException(404,'此版本文件不可用')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'no-cache'})
