"""Portable standalone InfiniteTalk validation kit. No historical deliverable imports."""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, re, shutil, subprocess, sys, time, wave
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
SUCCESS = {'SUCCESS', 'SUCCEEDED', 'COMPLETED'}
FAILED = {'FAILED', 'ERROR', 'CANCELED', 'CANCELLED'}
BASE = 'https://www.runninghub.cn'
SECRETS = set()

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def write(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    tmp.replace(p)

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def say(**kw): print(json.dumps(kw, ensure_ascii=False), flush=True)
def require(ok, message):
    if not ok: raise RuntimeError(message)

@contextmanager
def lock(folder):
    """OS-held lock releases after a crash, without clearing any durable ledger."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'.operation.lock').open('a+b') as f:
        f.seek(0, 2)
        if f.tell() == 0: f.write(b'0'); f.flush()
        f.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally:
            f.seek(0)
            if os.name == 'nt': msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(f, fcntl.LOCK_UN)

def workspace(value=None):
    if value or os.environ.get('HAIKE_WORKSPACE'):
        candidates = [Path(value or os.environ['HAIKE_WORKSPACE']).resolve()]
    else:
        candidates = [Path.cwd(), *Path.cwd().parents, *ROOT.parents]
    for c in candidates:
        repo = c if c.name == 'Haike_video' else c/'Haike_video'
        if (repo/'lib/env_loader.py').is_file(): return repo.resolve()
    raise RuntimeError('未找到已部署 Haike_video；使用 --workspace 指定工作区根目录')

def setup(value=None):
    repo = workspace(value)
    libs = repo/'.venv/Lib/site-packages'
    if libs.is_dir() and str(libs) not in sys.path: sys.path.append(str(libs))
    sys.path.insert(0, str(repo))
    from lib.env_loader import load_env
    load_env(repo)
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    pair = resolve_ffmpeg_pair()
    require(pair, '项目 FFmpeg/FFprobe 未安装；请运行现有项目预检')
    return repo, tuple(map(str, pair))

def config():
    c = read(ROOT/'capability.json')
    local = ROOT/'kit.local.json'
    if local.exists():
        overrides = read(local)
        require(set(overrides) <= {'workflow_id', 'runninghub_key_env'}, '本地绑定只允许 workflow_id / runninghub_key_env')
        c.update(overrides)
    return c

def credentials(c):
    names = [c['runninghub_key_env']] if c.get('runninghub_key_env') else ['RUNNINGHUB_CONSUMER_API_KEY', 'RUNNINGHUB_API_KEY']
    key = next((os.environ.get(n, '').strip() for n in names if os.environ.get(n, '').strip()), '')
    # This kit pins its current workflow. An unrelated project's legacy ID must never override it.
    wid = str(c.get('workflow_id') or '').strip()
    require(key, '项目尚未配置 RunningHub API Key；请在项目本地秘密配置中设置，不要写入交付包')
    require(re.fullmatch(r'\d{15,22}', wid), '工作流绑定缺失；使用包内默认ID，或在kit.local.json明确填写同事导入后的新ID')
    identity = read(ROOT/'reference/工作流ID与版本.json')
    retired = {identity['previous_test_launch_workflow_id'],identity['original_448x560_workflow_id']}
    require(wid not in retired, '检测到旧工作流ID，已停止；请删除旧kit.local.json绑定或改为最新导入ID')
    SECRETS.add(key)
    return key, wid

def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items() if not any(x in k.lower() for x in ('apikey','authorization','wss','token'))}
    if isinstance(value, list): return [clean(v) for v in value]
    if isinstance(value, str):
        for secret in SECRETS:
            if secret:value=value.replace(secret,'[已隐藏]')
        for name in ('RUNNINGHUB_API_KEY','RUNNINGHUB_CONSUMER_API_KEY','DASHSCOPE_API_KEY'):
            secret = os.environ.get(name)
            if secret: value = value.replace(secret, '[已隐藏]')
    return value

def request(method, path, key, body=None, timeout=60):
    import requests
    r = requests.request(method, BASE+path, headers={'Authorization':'Bearer '+key}, json=body, timeout=timeout, allow_redirects=False)
    require(r.status_code == 200, 'RunningHub HTTP '+str(r.status_code)+'；保留任务记录后检查权限或网络')
    v = r.json()
    require(isinstance(v, dict), 'RunningHub 响应格式异常')
    require(v.get('code') in (None, 0, 200, '0', '200'), 'RunningHub 拒绝请求，代码 '+str(v.get('code')))
    return v

def body(v): return v['data'] if isinstance(v.get('data'), dict) else v

def account(key): return body(request('POST','/uc/openapi/accountStatus',key,{'apikey':key}))

def upload(p, key):
    import requests
    p = Path(p)
    require(p.stat().st_size <= 30*1024*1024, '单个上传素材超过30MiB，需先用项目音频工具转为24k单声道PCM')
    with p.open('rb') as f:
        r = requests.post(BASE+'/openapi/v2/media/upload/binary', headers={'Authorization':'Bearer '+key}, files={'file':(p.name,f)}, timeout=180, allow_redirects=False)
    require(r.status_code == 200, '上传失败，HTTP '+str(r.status_code))
    v = r.json(); require(v.get('code') in (None,0,200,'0','200'), '上传接口拒绝素材')
    d = v.get('data'); name = (d.get('fileName') or d.get('filename') or d.get('name')) if isinstance(d,dict) else d
    require(isinstance(name,str) and name, '上传未返回素材文件名')
    return name

def wav_info(path):
    with wave.open(str(path),'rb') as w:
        require((w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype()) == (1,2,24000,'NONE'), '音频须为24kHz、单声道、PCM16 WAV；不自动改变上传人声')
        return w.getnframes(), w.getframerate()

def make_plan(audio, ratio, seconds=None, segment_seconds=45):
    c = config(); samples, rate = wav_info(audio)
    require(ratio in c['ratios'], '比例不受支持')
    require(0.04 <= segment_seconds <= c['max_segment_seconds'] and abs(segment_seconds*25-round(segment_seconds*25)) < 1e-7, '分段时长须为0.04秒的倍数且不超过45秒')
    if seconds is not None:
        require(math.isfinite(seconds) and 0 < seconds <= samples/rate, '测试秒数须大于0且不超过音频总时长')
        samples = min(samples, round(seconds*rate))
    require(0 < samples <= 600*rate, '此交付范围为0至10分钟')
    total = (samples*25+rate-1)//rate
    stride = round(segment_seconds*25); segments = []
    for start in range(0,total,stride):
        frames = min(stride,total-start)
        start_sample = start*rate//25; end_sample = min(samples,(start+frames)*rate//25)
        dur = (end_sample-start_sample)/rate
        guard = max(900,math.ceil(dur*60))
        segments.append({'index':len(segments)+1,'start_frame':start,'frames':frames,'start_sample':start_sample,'end_sample':end_sample,'start_seconds':start/25,'seconds':dur,'max_compute_seconds':guard,'reserve_coins':math.ceil(guard*.4)+2})
    return {'version':c['version'],'ratio':ratio,'fps':25,'samples':samples,'sample_rate':rate,'seconds':samples/rate,'frames':total,'dimensions':c['ratios'][ratio]['output'],'segments':segments,'reserve_coins':sum(s['reserve_coins'] for s in segments),'estimate_basis':'0.4RH币/秒为本机历史参考，不是人民币换算或价格保证'}

def graph_for(plan, seg, image_remote, audio_remote, checkpoint_remote=None, prefix='IT_AGENT'):
    g = read(ROOT/'workflows/InfiniteTalk_V5.3.1_API.json')
    g['36']['inputs']['image'] = image_remote
    g['100']['inputs']['image'] = checkpoint_remote or image_remote
    g['34']['inputs']['audio'] = audio_remote
    g['103']['inputs']['value'] = seg['start_seconds']; g['104']['inputs']['value'] = seg['seconds']
    # Explicit selector prevents near-ratio files or continuation frames from changing output geometry.
    code = config()['ratios'][plan['ratio']]['selector']
    g['41']['inputs'] = {'expression':str(code)}
    for nid, label in [('87','sr'),('93','segment'),('107','native_checkpoint')]:
        g[nid]['inputs']['filename_prefix'] = f'{prefix}/{seg["index"]:03d}/{label}'
    validate_graph(g)
    return g

def validate_graph(g):
    require(g['14']['inputs']['colormatch'] == 'disabled', 'MKL必须关闭')
    require(g['87']['class_type'] == 'easy saveVideo' and g['88']['inputs']['output_value'] == ['87',1], '超分合并必须使用任务本地文件路径')
    require(g['108']['inputs']['complete_audio'] == ['101',0], '本段完整配音连接异常')
    for n in g.values():
        for v in n.get('inputs',{}).values():
            if isinstance(v,list) and len(v)==2 and isinstance(v[0],str) and isinstance(v[1],int):
                require(v[0] in g, '工作流存在悬空连线')

def probe(pair, path, count=True):
    args = [pair[1],'-v','error'] + (['-count_frames'] if count else []) + ['-show_streams','-show_format','-of','json',str(path)]
    return json.loads(subprocess.check_output(args, timeout=180))

def verify_video(pair, path, plan, frames=None):
    v = probe(pair,path); video = next(s for s in v['streams'] if s['codec_type']=='video')
    require([int(video['width']),int(video['height'])] == plan['dimensions'], '成片尺寸不符')
    require(video['r_frame_rate']=='25/1', '成片帧率不符')
    require(int(video['nb_read_frames']) == (frames if frames is not None else plan['frames']), '成片帧数不符')
    return v

def download(url, target):
    """Resume 1MiB blocks with four read-only workers; never retries model submission."""
    import requests
    from urllib.parse import urlsplit
    u = urlsplit(url)
    require(u.scheme=='https' and u.hostname, '拒绝非HTTPS下载地址')
    target = Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    began=time.monotonic()
    def get(start,end):
        for attempt in range(4):
            try:
                require(time.monotonic()-began<1200,'本次下载已到20分钟恢复点；保留分块并用同名命令继续')
                r=requests.get(url,headers={'Range':f'bytes={start}-{end}'},timeout=(15,45),allow_redirects=False)
                if r.status_code==200:
                    require(start==0 and len(r.content)>0, '下载服务不支持断点续传')
                    return r.content,len(r.content),True
                require(r.status_code==206, '下载失败，HTTP '+str(r.status_code))
                m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers.get('Content-Range',''))
                require(m and int(m[1])==start and int(m[2])==min(end,int(m[3])-1) and len(r.content)==int(m[2])-start+1, '下载字节范围校验失败')
                return r.content,int(m[3]),False
            except (requests.RequestException,RuntimeError):
                if attempt==3: raise
                time.sleep(2**attempt)
    block=1024*1024; data,total,whole=get(0,block-1)
    require(0 < total < 2_000_000_000, '下载大小异常')
    parts=target.with_name(target.name+'.parts'); parts.mkdir(exist_ok=True)
    identity={'url_sha256':hashlib.sha256(url.encode()).hexdigest(),'bytes':total}
    mark=parts/'identity.json'
    if mark.exists(): require(read(mark)==identity,'下载地址已变化，请保留旧分片另选恢复目录')
    else: write(mark,identity)
    if whole:
        tmp=target.with_name(target.name+'.part');tmp.write_bytes(data);tmp.replace(target);return
    (parts/'00000000').write_bytes(data)
    def one(i):
        p=parts/f'{i:08d}'; start=i*block; end=min(total-1,start+block-1)
        if p.exists() and p.stat().st_size==end-start+1:return
        b,t,w=get(start,end);require(t==total and not w,'下载总长度发生变化')
        p.write_bytes(b)
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(one,range(1,math.ceil(total/block))))
    tmp=target.with_name(target.name+'.part')
    with tmp.open('wb') as f:
        for i in range(math.ceil(total/block)):f.write((parts/f'{i:08d}').read_bytes())
    require(tmp.stat().st_size==total,'下载文件不完整');tmp.replace(target)

def assets(a):
    require(a.audio and a.image, '请显式提供 --audio 完整WAV和 --image 人物图；交付包不包含私人样例')
    c=config(); audio=Path(a.audio).resolve() if a.audio else ROOT/c['sample_audio']
    image=Path(a.image).resolve() if a.image else ROOT/c['ratios'][a.ratio]['image']
    require(audio.is_file() and image.is_file(), '输入图片或音频不存在')
    return image,audio

def doctor(a,pair):
    c=config(); verify_package()
    import requests, dotenv
    from PIL import Image
    g=read(ROOT/'workflows/InfiniteTalk_V5.3.1_API.json')
    validate_graph(g)
    from schema_check import check
    static=check(g,read(ROOT/'reference/node_specs.json'))
    require(static['passed'],'静态节点规格检查失败：'+str(static['errors']))
    if a.image:
        with Image.open(Path(a.image)) as im: im.verify()
    if a.audio:
        wav_info(Path(a.audio))
    filters=subprocess.check_output([pair[0],'-hide_banner','-bsfs'],stderr=subprocess.STDOUT,timeout=30).decode(errors='replace')
    require('setts' in filters,'FFmpeg缺少setts过滤器，无法保证拼接时间戳')
    result={'offline':'pass','package_hashes':'pass','ffmpeg_setts':'pass','schema_check':static,'voice_id':c['voice']['id'],'voice_account_access':'尚未实调，不把本地ID校验当作授权证明','cloud_checked':False}
    if a.cloud:
        key,wid=credentials(c); acc=account(key)
        schemas=request('GET','/proxy-plus/'+key+'/object_info',key,timeout=120)
        missing=sorted({n['class_type'] for n in read(ROOT/'workflows/InfiniteTalk_V5.3.1_API.json').values()}-set(schemas))
        require(not missing,'缺少RunningHub节点：'+','.join(missing))
        live=check(g,schemas);require(live['passed'],'当前平台模型/节点参数不兼容：'+str(live['errors']))
        result.update(cloud_checked=True,account_available=True,workflow_binding=wid,workflow_access='需以导入后可访问或首次提交结果为准',current_tasks=acc.get('currentTaskCounts'),all_node_classes_available=True,live_schema_check=live)
    say(**result)

def verify_package():
    p=ROOT/'SHA256SUMS.json'
    require(p.exists(),'包完整性清单缺失')
    for item in read(p)['files']:
        rel=item['path']
        content=(ROOT/rel).read_bytes().replace(b'\r\n',b'\n')
        require(hashlib.sha256(content).hexdigest()==item['sha256'],'交付文件被更改：'+rel+'；请保留原包，修改副本并单独记录')

def assemble(folder,pair):
    plan=read(folder/'plan.json'); source=folder/'audio.wav'
    for seg in plan['segments']:
        verify_video(pair,folder/f'segment_{seg["index"]:03d}/video.mp4',plan,seg['frames'])
    listing=folder/'concat.txt'
    def quote(p):return str(p.resolve()).replace('\\','/').replace("'","'\\''")
    listing.write_text('\n'.join("file '"+quote(folder/f'segment_{s["index"]:03d}/video.mp4')+"'\nduration "+str(s['frames']/25) for s in plan['segments'])+'\n',encoding='utf-8')
    before=folder/'mux_before_pts.mp4'; final=folder/'完整口播.mp4'
    commands=[
        [pair[0],'-hide_banner','-nostdin','-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-i',str(source),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',str(before)],
        [pair[0],'-hide_banner','-nostdin','-y','-v','error','-i',str(before),'-map','0:v:0','-map','0:a:0','-c','copy','-bsf:v','setts=pts=PTS-STARTPTS:dts=DTS-STARTPTS','-avoid_negative_ts','disabled','-movflags','+faststart',str(final)]]
    for command in commands:subprocess.run(command,check=True,capture_output=True,timeout=300)
    v=verify_video(pair,final,plan)
    timestamps=subprocess.check_output([pair[1],'-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(final)],timeout=180)
    ts=[float(f['best_effort_timestamp_time']) for f in json.loads(timestamps)['frames']]
    require(len(ts)==plan['frames'] and max(abs(t-i/25) for i,t in enumerate(ts))<0.0001,'最终视频时钟不连续')
    audio=next(s for s in v['streams'] if s['codec_type']=='audio')
    require(abs(float(audio.get('start_time',0)))<0.001 and abs(float(audio['duration'])-plan['seconds'])<0.1,'最终音轨时钟不符')
    subprocess.run([pair[0],'-nostdin','-v','error','-i',str(final),'-f','null','-'],check=True,capture_output=True,timeout=300)
    report={'state':'review_ready','final_file':final.name,'sha256':sha(final),'frames':plan['frames'],'video_pts_continuous':True,'audio_master':'audio.wav','subjective_review':'待连续观看口型、手势、接缝和亮度','completed_at':now()}
    write(folder/'result.json',report);say(**report)
    return final

def run(a,pair):
    import requests
    from PIL import Image
    c=config();verify_package();key,wid=credentials(c)
    from schema_check import check
    checked=check(read(ROOT/'workflows/InfiniteTalk_V5.3.1_API.json'),read(ROOT/'reference/node_specs.json'))
    require(checked['passed'],'模板节点规格已损坏')
    require(a.budget_coins and math.isfinite(a.budget_coins) and a.budget_coins>0,'run必须指定正数 --budget-coins（RH币）')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,60}',a.name),'任务名只能包含英文字母、数字、下划线、短横线')
    image,audio=assets(a);plan=make_plan(audio,a.ratio,a.seconds,a.segment_seconds)
    require(plan['reserve_coins']<=a.budget_coins,'保守预留超预算；减少测试秒数或调整明确授权的RH币上限')
    folder=ROOT/'runs'/a.name
    with lock(folder):
        contract={'image_sha256':sha(image),'source_audio_sha256':sha(audio),'plan':plan,'workflow_id':wid,'key_fingerprint':hashlib.sha256(key.encode()).hexdigest()[:16],'graph_sha256':sha(ROOT/'workflows/InfiniteTalk_V5.3.1_API.json'),'budget_coins':a.budget_coins}
        cp=folder/'contract.json'
        if cp.exists():require(read(cp)==contract,'同名任务的素材、参数、账号或预算已变化，已停止；恢复时使用原命令')
        else:
            write(cp,contract);write(folder/'plan.json',plan);shutil.copy2(image,folder/'reference.png')
            with wave.open(str(audio),'rb') as src:
                params=src.getparams();data=src.readframes(plan['samples'])
            with wave.open(str(folder/'audio.wav'),'wb') as dst:dst.setparams(params);dst.writeframes(data)
        require((folder/'reference.png').is_file() and sha(folder/'reference.png')==sha(image),'任务人物图缓存不完整')
        require(wav_info(folder/'audio.wav')[0]==plan['samples'],'任务音频缓存不完整')
        binding=folder/'uploads.json'
        if not binding.exists():write(binding,{'image':upload(folder/'reference.png',key),'audio':upload(folder/'audio.wav',key)})
        refs=read(binding)
        say(provider='RunningHub',instance='plus / 请求48G',workflow_id=wid,seconds=plan['seconds'],segments=len(plan['segments']),budget_rh_coins=a.budget_coins,automatic_paid_resubmit=False)
        for seg in plan['segments']:
            case=folder/f'segment_{seg["index"]:03d}';ledger=case/'ledger.json';case.mkdir(exist_ok=True)
            st=read(ledger) if ledger.exists() else None
            if st and st.get('state')=='verified':
                require(sha(case/'video.mp4')==st['video_sha256'] and sha(case/'native_checkpoint.png')==st['checkpoint_sha256'],'已完成片段文件被更改')
                continue
            if st:require(st.get('task_id'),'上次提交结果不明，保留记录并核对RunningHub任务列表；不要换任务名盲目重发')
            if not st:
                # All reservations, including an earlier failure of unknown cost, remain reserved.
                total_reserved=0
                for planned in plan['segments']:
                    state_path=folder/f'segment_{planned["index"]:03d}/ledger.json'
                    recorded=read(state_path) if state_path.exists() else {}
                    coins=(recorded.get('usage') or {}).get('consumeCoins')
                    total_reserved+=max(planned['reserve_coins'],float(coins or 0))
                require(total_reserved<=a.budget_coins,'实际扣币超过预留后触及本次预算；保留完成片段，停止新任务')
                acc=account(key)
                require(float(acc.get('remainCoins') or 0)>=seg['reserve_coins'],'账户余额低于本段保守预留')
                require(int(acc.get('currentTaskCounts') or 0)<3,'账号并发已满；稍后使用同名命令恢复')
                checkpoint=None
                if seg['index']>1:
                    prior=folder/f'segment_{seg["index"]-1:03d}/native_checkpoint.png'
                    require(prior.is_file(),'上一段原生尾帧缺失；先恢复上一段')
                    checkpoint=upload(prior,key)
                g=graph_for(plan,seg,refs['image'],refs['audio'],checkpoint,'IT_AGENT/'+a.name)
                write(case/'submitted_api.json',g)
                st={'state':'submitting','submitted_at':now(),'segment':seg};write(ledger,st)
                try:
                    raw=request('POST','/task/openapi/create',key,{'apiKey':key,'workflowId':wid,'instanceType':'plus','nodeInfoList':[],'workflow':json.dumps(g,ensure_ascii=False)},timeout=90)
                    d=body(raw);tid=d.get('taskId');require(tid,'提交未返回任务ID')
                    st.update(state='submitted',task_id=str(tid));write(ledger,st)
                    write(case/'submission.json',clean(raw))
                except Exception:
                    st.update(state='ambiguous');write(ledger,st)
                    raise RuntimeError('提交结果不明或被拒绝；已落账并停止，先核对云端任务，不自动重发') from None
            require(st['state'].upper() not in FAILED,'任务已失败或取消；保留已有产物，核账后人工决定新尝试')
            last_log=0;poll_failure_since=None
            while True:
                try:
                    raw=request('POST','/openapi/v2/query',key,{'taskId':st['task_id']},timeout=35)
                    d=body(raw);status=str(d.get('status') or 'UNKNOWN').upper();poll_failure_since=None
                except (requests.RequestException,RuntimeError,ValueError):
                    if poll_failure_since is None:poll_failure_since=time.monotonic()
                    if time.monotonic()-poll_failure_since>120:raise RuntimeError('持续查询失败；任务ID已保存，用同名命令恢复查询，勿重新提交') from None
                    time.sleep(10);continue
                elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(st['submitted_at'])).total_seconds()
                if status=='RUNNING' and not st.get('first_running_at'):st['first_running_at']=now()
                running=(datetime.now(timezone.utc)-datetime.fromisoformat(st['first_running_at'])).total_seconds() if st.get('first_running_at') else 0
                st.update(state=status,updated_at=now(),elapsed_seconds=round(elapsed),running_seconds=round(running))
                if 'usage' in d:st['usage']=clean(d['usage'])
                write(ledger,st);write(case/'query.json',clean(raw))
                if time.monotonic()-last_log>45 or status in SUCCESS|FAILED:
                    say(segment=seg['index'],task_id=st['task_id'],status=status,elapsed_seconds=round(elapsed));last_log=time.monotonic()
                if status in SUCCESS:break
                require(status not in FAILED,'云端任务失败或取消；已保存状态，自动重试关闭')
                known_coins=float((st.get('usage') or {}).get('consumeCoins') or 0)
                if elapsed>=3500 or running>=seg['max_compute_seconds'] or known_coins>seg['reserve_coins'] or (not st.get('first_running_at') and elapsed>=900):
                    if not st.get('cancel_requested'):
                        # Persist intent before cancellation. An ambiguous cancel is queried, never resubmitted.
                        st['cancel_requested']=True;write(ledger,st)
                        try:request('POST','/task/openapi/cancel',key,{'apiKey':key,'taskId':st['task_id']})
                        except Exception:pass
                    raise RuntimeError('触及时长保护，已请求取消；重新运行仅查询同一任务以核账，不自动新建任务')
                time.sleep(10)
            results=d.get('results') or []
            finals=[r for r in results if str(r.get('nodeId'))=='93' and r.get('url')]
            checkpoints=[r for r in results if str(r.get('nodeId','')).endswith('_107') and r.get('url')]
            require(len(finals)==1 and checkpoints,'云端成功但成片/原生尾帧缺失，保留同一任务恢复')
            for result,target in [(checkpoints[-1],case/'native_checkpoint.png'),(finals[0],case/'video.mp4')]:
                if not target.exists():download(result['url'],target)
            with Image.open(case/'native_checkpoint.png') as im:im.verify()
            verify_video(pair,case/'video.mp4',plan,seg['frames'])
            st.update(state='verified',video_sha256=sha(case/'video.mp4'),checkpoint_sha256=sha(case/'native_checkpoint.png'));write(ledger,st)
        assemble(folder,pair)

def tts(a,pair):
    import requests
    from lib import bailian_speech as api
    c=config();v=c['voice'];require(api.configured(),'项目尚未配置百炼 DASHSCOPE_API_KEY')
    require(v.get('id') and a.text, '请使用项目配音中心准备完整WAV；独立tts需明确配置本人音色和 --text 文件')
    text=Path(a.text).read_text(encoding='utf-8-sig') if a.text else (ROOT/'assets/speech.txt').read_text(encoding='utf-8')
    text=''.join(text.splitlines()).strip();require(0<len(text)<=1000,'本包整段TTS已验证范围为1至1000字符；更长先按语意切文案，勿假定云端无限长输入')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,60}',a.name),'任务名不合法')
    folder=ROOT/'runs'/('tts_'+a.name)
    with lock(folder):
        identity=api.fingerprint({'model':v['model'],'voice':v['id'],'rate':v['rate'],'text':text,'account':api.headers()['Authorization']})
        ledger=folder/'ledger.json';st=read(ledger) if ledger.exists() else None
        if st:
            require(st.get('identity')==identity,'同名配音参数或账号变化')
            require(st['state'] in {'accepted','completed'},'此前配音受理结果未确认，先核账，禁止盲目重发')
        else:
            st={'state':'submitting','identity':identity,'submitted_at':now()};write(ledger,st)
            say(provider=v['provider'],model=v['model'],voice=v['name'],rate=v['rate'],characters=len(text))
            try:
                r=requests.post(api.api_base()+'/services/audio/tts/SpeechSynthesizer',headers=api.headers(),json={'model':v['model'],'input':{'text':text,'voice':v['id'],'rate':v['rate'],'format':'wav','sample_rate':24000}},timeout=(15,300),allow_redirects=False)
                data=api.response_json(r);url=(data.get('output',{}).get('audio') or {}).get('url');require(url,'配音未返回音频地址')
                st.update(state='accepted',audio_url=url,usage=data.get('usage'),request_id=data.get('request_id'));write(ledger,st)
            except Exception:
                st['state']='ambiguous';write(ledger,st)
                raise RuntimeError('配音失败或受理结果不明；账号音色权限需核验，已保留记录不重发') from None
        raw=folder/'provider_audio.wav';out=folder/'配音.wav'
        if not raw.exists():api.download(st['audio_url'],raw)
        if not out.exists():subprocess.run([pair[0],'-nostdin','-y','-v','error','-i',str(raw),'-ac','1','-ar','24000','-c:a','pcm_s16le',str(out)],check=True,capture_output=True,timeout=90)
        samples,rate=wav_info(out);st.update(state='completed',sha256=sha(out));write(ledger,st)
        say(state='completed',audio=str(out),seconds=samples/rate,voice_id=v['id'],rate=v['rate'])

def main():
    p=argparse.ArgumentParser(description='InfiniteTalk V5.3.1 同事测试交付包；默认检查不扣费')
    p.add_argument('action',choices=['doctor','plan','run','assemble','tts'])
    p.add_argument('--workspace');p.add_argument('--cloud',action='store_true')
    p.add_argument('--ratio',choices=['4x5','16x9','1x1','9x16'],default='4x5')
    p.add_argument('--audio');p.add_argument('--image');p.add_argument('--text')
    p.add_argument('--name',default='sample');p.add_argument('--seconds',type=float)
    p.add_argument('--segment-seconds',type=float,default=45);p.add_argument('--budget-coins',type=float)
    a=p.parse_args();repo,pair=setup(a.workspace)
    if a.action=='doctor':doctor(a,pair)
    elif a.action=='plan':
        image,audio=assets(a);say(**make_plan(audio,a.ratio,a.seconds,a.segment_seconds))
    elif a.action=='run':run(a,pair)
    elif a.action=='tts':tts(a,pair)
    else:
        require(re.fullmatch(r'[A-Za-z0-9_-]{1,60}',a.name),'任务名不合法')
        with lock(ROOT/'runs'/a.name):assemble(ROOT/'runs'/a.name,pair)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:main()
    except KeyboardInterrupt:
        say(state='stopped_locally',message='本地监控已停，云任务可能仍运行；同名命令恢复查询');sys.exit(130)
    except Exception as exc:
        # Exception text from HTTP libraries can embed credentialed URLs. Print our own errors only.
        message=str(exc) if type(exc) is RuntimeError else '请检查本地依赖/网络/文件；任务记录保留，禁止盲目重发'
        message=re.sub(r'https?://\S+','[云端地址已隐藏]',message)
        say(state='stopped',error_class=type(exc).__name__,message=clean(message),automatic_paid_resubmit=False);sys.exit(1)
