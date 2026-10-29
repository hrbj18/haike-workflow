"""Speech-clock, source-bound production for the complete ten-group dark template."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

from backlot.studio import atomic_private
from backlot.work_catalog import WorkCatalog, WorkError, read_json, regular_path, sha
from backlot.studio_investment_recompose import fingerprint
from backlot import studio_hum_production as speech
from backlot.production_queue import _sanitize as queue_safe
from lib.ffmpeg_locator import resolve_ffmpeg_pair

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates/motiongit-dark-full-v1'
CONTRACT='motiongit-dark-full-v1'
KIND='studio_investment_recompose'
REQUEST_FILE='dark-full-request.json'
OUTPUT_FILE='dark-full.mp4'
NOMUSIC_FILE='dark-full-nomusic.mp4'
PROFILE={'scale':1,'crf':1,'codec':'h264','image_format':'png','x264_preset':'fast','pixel_format':'yuv444p'}
EXPORT={'bitrate':20500000,'minimum_measured_bitrate':20000000,'audio_rate':48000,'true_peak_max':-1.5}
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
require=speech._require
CACHE_ROOT=Path(os.environ.get('HAIKE_RENDER_CACHE',str(Path.home()/'Documents/HaikeCache')))/CONTRACT


def catalog():
    return read_json(TEMPLATE/'catalog.json')


def template_files():
    return sorted(p for p in TEMPLATE.rglob('*') if p.is_file() and p.suffix in {'.tsx','.ts','.css','.json'}
                  and p.name not in {'video-template-spec.json','props.example.json'} and 'reference' not in p.relative_to(TEMPLATE).parts)


def runtime():
    paths=[Path(__file__),ROOT/'remotion-composer/package-lock.json',ROOT/'tools/video/video_compose.py',
           Path(speech.__file__),*template_files(),*map(Path,resolve_ffmpeg_pair())]
    require(all(p.is_file() for p in paths),'完整模板或本地渲染依赖缺失')
    return {str(p.resolve()):sha(p) for p in paths}


def required_names(props,audio):
    names={audio['voice'],*props['fontAssets'].values()}
    for m in props['media']:
        names.add(m['src']);names.add(m['thumbnail'])
    if props.get('presenter'):names.add(props['presenter']['src'])
    if props.get('referencePortrait'):names.add(props['referencePortrait'])
    if audio.get('music'):names.add(audio['music'])
    names.update(s['src'] for s in audio.get('sfx',[]))
    return names


def plan_shots(shots,frames,fps):
    """Keep complete action groups; allocate only the available reading time."""
    definitions={g['id']:g for g in catalog()['groups']}
    require(isinstance(shots,list) and 1<=len(shots)<=100,'shotPlan须为完整场景清单')
    minimum=[];weights=[]
    for s in shots:
        require(isinstance(s,dict) and s.get('group') in definitions,'shotPlan包含未知动作组')
        d=definitions[s['group']]
        minimum.append(math.ceil(d.get('minimumProjectSeconds',d['minimumSeconds'])*fps-.0001))
        weight=s.get('weight',1);require(speech._number(weight) and 0<weight<=100,'场景权重无效');weights.append(weight)
    require(sum(minimum)<=frames,'完整动作保护时长超过当前口播；须由Agent重新选用适合的完整场景')
    remainder=frames-sum(minimum);extras=[math.floor(remainder*w/sum(weights)) for w in weights]
    for i in range(remainder-sum(extras)):extras[i%len(extras)]+=1
    cursor=0;out=[]
    for original,base,extra in zip(shots,minimum,extras):
        s=deepcopy(original);weight=s.pop('weight',None);clips=s.pop('clipPlan',[])
        s.update(from_=cursor,frames=base+extra);s['from']=s.pop('from_')
        d=definitions[s['group']];s.setdefault('sourceStart',d['source']['start']);s.setdefault('sourceDuration',d['source']['end']-d['source']['start'])
        length=s['frames']/fps
        cues={c['id']:max(0,min(length-1/fps,(c['at']-s['sourceStart'])*length/s['sourceDuration'])) for c in d['cues']}
        # Action easing keeps its physical duration when a group is shortened.
        # Reserve the closing state rather than clipping the final animation.
        tail={'s02':('cost',1.35),'s05':('lane_result',1.1),'s06':('account_commit',.8),'s07':('code_video',.7),'s08':('comments',1.25)}.get(s['group'])
        if tail and tail[0] in cues:cues[tail[0]]=min(cues[tail[0]],length-tail[1])
        cues.update(s.get('cueTimes',{}));s['cueTimes']=cues
        s['videoWindows']=[]
        for clip in clips:
            require(set(clip)=={'mediaId','at','seconds','offset'} and speech._number(clip['at']) and 0<=clip['at']<1 and speech._number(clip['seconds']) and clip['seconds']>0,'素材窗口计划无效')
            start=round(clip['at']*s['frames']);duration=min(round(clip['seconds']*fps),s['frames']-start)
            require(duration>0,'素材播放窗口没有有效长度')
            s['videoWindows'].append({'mediaId':clip['mediaId'],'from':start,'frames':duration,'offset':clip['offset']})
        out.append(s);cursor+=s['frames']
    return out


def action_gate(scene,fps,definition):
    """Protect the observable state graph, not merely timestamps in range."""
    seconds=scene['frames']/fps
    cues={c['id']:(c['at']-scene.get('sourceStart',definition['source']['start']))*seconds/
          scene.get('sourceDuration',definition['source']['end']-definition['source']['start']) for c in definition['cues']}
    require(set(scene.get('cueTimes',{}))<=set(cues),'包含此动作组未声明的节点')
    cues.update(scene.get('cueTimes',{}));order=[cues[c['id']] for c in definition['cues']]
    require(all(a<=b+.000001 for a,b in zip(order,order[1:])),'完整动作节点顺序错误：'+scene['group'])
    def gap(first,last,minimum):
        require(cues[last]-cues[first]+.0001>=minimum,'完整动作尚未完成就退场：'+scene['group']+' '+first+'→'+last)
    def end(key,minimum):
        require(seconds-cues[key]+.0001>=minimum,'末尾动作尚未落定：'+scene['group']+' '+key)
    group=scene['group']
    if group=='s01':gap('statement_2','payoff',.38);end('payoff',.77)
    if group=='s02':gap('version_chips','all_checked',1.4);end('cost',1.35)
    if group=='s03':gap('review_note_3','previous_work',.38);end('previous_work',.5)
    if group=='s04':
        gap('category_4','wall_expand',.4);gap('cross_out','camera_demo',.38);gap('camera_demo','narrative_arc',.55);end('narrative_arc',.65)
    if group=='s05':gap('competition','lane_result',.65);end('lane_result',1.1)
    if group=='s06':gap('account','account_commit',.55);end('account_commit',.8)
    if group=='s07':
        gap('process','time_shift',1.0);gap('time_shift','work_video',.65);gap('work_video','output',1.65);gap('output','code_video',.7);end('code_video',.7)
    if group=='s08':gap('growth','call_to_action',1.0);gap('call_to_action','comments',.65);end('comments',1.25)
    if group=='s09':
        typing=scene['content'].get('typingSeconds',2.45)
        require(speech._number(typing) and .5<=typing<=8,'打字时长须为0.5至8秒')
        gap('prompt','signature',typing);end('signature',.5)
    if group=='review':end('conclusion',.65)
    return cues


def live_intervals(scene,fps,cues,reference):
    """Conservative visible phases of the renderer's live nodes, in local sec."""
    ids=scene['mediaIds'];primary=scene.get('mainMediaId') or (ids[0] if ids else None)
    end=scene['frames']/fps;out={}
    def add(identity,start,stop):
        if identity and stop>start:out.setdefault(identity,[]).append((max(0,start),min(end,stop)))
    def item(index):return ids[index%len(ids)] if ids else None
    group=scene['group']
    if group=='s02':add(primary,cues['grid']+.4,end)
    if group=='s03':add(primary,0,end)
    if group=='s04':
        add(primary,cues['category_1']+.2,cues['wall_expand']);add(primary,cues['camera_demo']+.2,end)
    if group=='s05':
        add(item(0),cues['software_window']+.2,cues['software_detail']+.1)
        add(item(1),cues['software_detail']+.2,cues['competition']+.1)
        add(primary,cues['competition']+.2,cues['lane_result']+.1)
    if group=='s07':
        add(primary,cues['work_video']+.2,cues['output']+.2);add(item(1),cues['code_video']+.2,end)
    if group=='s08' and not reference:
        add(item(scene['content'].get('comparisonMediaIndex',0)),cues['warning']+.2,cues['call_to_action']+.1)
        add(item(scene['content'].get('closingMediaIndex',1)),cues['comments']+.3,end)
    if group=='review':add(primary,cues['entry']+.2,end)
    return out


def validate_props(p,seconds):
    require(isinstance(p,dict) and not set(p)-{'width','height','fps','durationFrames','variant','brand','header','footer','scenes','media','captions','fontAssets','audio','presenter','referencePortrait'},'完整模板画面字段无效')
    reference=p.get('variant')=='reference'
    story=p.get('variant')=='native-story'
    require(p.get('variant') in {'reference','hedgerow','cobalt','native-story'},'请选择已登记的多屏设计')
    canvas=(1920,1080,60) if reference else (1440,1800,60 if story else 30)
    require((p['width'],p['height'],p['fps'])==canvas,'画布须使用本模板已设计的原版或4:5布局')
    require(type(p['durationFrames']) is int and seconds<=p['durationFrames']/p['fps']<=seconds+2.04,'完整口播时钟或尾部留白无效')
    require(all(speech._text(p.get(k),50,empty=k!='brand') for k in ['brand','header','footer']),'品牌或门店信息超出范围')
    require(isinstance(p.get('fontAssets'),dict) and set(p['fontAssets'])=={'body','display'}
            and all(speech._name(n) for n in p['fontAssets'].values()),'须绑定正文与标题真实字体')
    media=p.get('media');require(isinstance(media,list) and len(media)<=400,'素材清单最多400个独立来源')
    require(reference or 3<=len(media)<=(40 if story else 24),'海客模板真实素材数量超出当前设计范围')
    ids=set()
    for m in media:
        require(isinstance(m,dict) and not set(m)-{'id','src','thumbnail','kind','offset','label','fit','width','height'},'素材字段无效')
        require(speech._name(m.get('id')) and m['id'] not in ids,'素材编号重复或无效');ids.add(m['id'])
        require(m.get('kind') in {'image','video'} and speech._name(m.get('src')) and speech._name(m.get('thumbnail')),'素材须绑定安全文件名及真实封面')
        require(speech._number(m.get('offset')) and m['offset']>=0 and m.get('fit','contain')=='contain','素材须原速全幅显示')
    scenes=p.get('scenes');require(isinstance(scenes,list) and 1<=len(scenes)<=100,'场景清单无效')
    definitions={g['id']:g for g in catalog()['groups']};cursor=0;seen=set();order=[];cue_maps={}
    for i,s in enumerate(scenes):
        require(isinstance(s,dict) and not set(s)-{'id','group','from','frames','title','subtitle','mediaIds','mainMediaId','content','cueTimes','sourceStart','sourceDuration','videoWindows'},'场景字段无效')
        require(speech._name(s.get('id')) and s['id'] not in seen,'场景编号重复或无效');seen.add(s['id'])
        group=s.get('group');require(group in definitions,'未知原生动作组，不能以通用转场替代')
        require(not story or group in {'s01','s04','s08'},'多屏口播4:5目前只开放已适配的S01/S04/S08')
        require(type(s.get('from')) is int and s['from']==cursor and type(s.get('frames')) is int and s['frames']>0,'场景须连续覆盖完整口播')
        require(s['frames']/p['fps']+.0001>=definitions[group].get('minimumProjectSeconds',definitions[group]['minimumSeconds']),'场景不足以完成整组动作及阅读：'+group)
        cursor+=s['frames'];order.append(group)
        require(isinstance(s.get('mediaIds'),list) and len(s['mediaIds'])<=400 and set(s['mediaIds'])<=ids,'场景素材绑定无效')
        require(not s.get('mainMediaId') or s['mainMediaId'] in s['mediaIds'],'主素材必须属于本场景素材')
        require(speech._text(s.get('title',''),100,lines=3,empty=True) and speech._text(s.get('subtitle',''),160,lines=4,empty=True),'场景标题或说明无效')
        require(isinstance(s.get('content'),dict) and len(json.dumps(s['content'],ensure_ascii=False).encode())<=100000,'界面内容须为有界参数对象')
        require(speech._number(s.get('sourceStart')) and s['sourceStart']>=0 and speech._number(s.get('sourceDuration')) and 0<s['sourceDuration']<=600,'参考动作时间映射无效')
        for at in s.get('cueTimes',{}).values():require(speech._number(at) and 0<=at<s['frames']/p['fps'],'动作节点超出场景')
        cue_maps[s['id']]=action_gate(s,p['fps'],definitions[group])
        tail={'s01':('payoff',.77),'s05':('lane_result',1.1),'s06':('account_commit',.8),'s07':('code_video',.7),'s08':('comments',1.25)}.get(group)
        if tail and tail[0] in s.get('cueTimes',{}):require(s['cueTimes'][tail[0]]+tail[1]<=s['frames']/p['fps']+.0001,'末尾动作尚未落定，不能提前切走：'+group)
        for w in s.get('videoWindows',[]):
            require(isinstance(w,dict) and set(w)=={'mediaId','from','frames','offset'} and w['mediaId'] in s['mediaIds'],'视频播放窗口绑定无效')
            require(type(w['from']) is int and type(w['frames']) is int and w['from']>=0 and w['frames']>0 and w['from']+w['frames']<=s['frames'] and speech._number(w['offset']) and w['offset']>=0,'视频播放窗口超出动作场景')
        if group=='s02':require(i+1<len(scenes) and scenes[i+1]['group']=='s03','九格比较须接同一中央素材的连续聚焦组')
        if group=='s03':require(i>0 and scenes[i-1]['group']=='s02' and scenes[i-1].get('mainMediaId')==s.get('mainMediaId'),'聚焦组缺少同中央素材的前置九格组')
    require(cursor==p['durationFrames'],'场景未覆盖完整语音及尾部')
    by_id={m['id']:m for m in media}
    for scene in scenes:
        ids=scene['mediaIds'];primary=scene.get('mainMediaId') or (ids[0] if ids else None)
        needed=[]
        if scene['group'] in {'s02','s03','s04','s05','s07','review'}:needed.append(primary)
        if scene['group']=='s07' and ids:needed.append(ids[1%len(ids)])
        if scene['group']=='s08' and not reference and ids:
            for key,default in [('comparisonMediaIndex',0),('closingMediaIndex',1)]:
                index=scene['content'].get(key,default)
                require(type(index) is int and 0<=index<len(ids),'素材窗索引超出场景绑定范围')
                needed.append(ids[index])
        for identity in needed:
            if by_id.get(identity,{}).get('kind')=='video':
                require(any(w['mediaId']==identity for w in scene.get('videoWindows',[])),'主素材/接力窗口未安排真实播放区间：'+scene['id'])
                visible=live_intervals(scene,p['fps'],cue_maps[scene['id']],reference).get(identity,[])
                overlap=sum(max(0,min(w['from']/p['fps']+w['frames']/p['fps'],b)-max(w['from']/p['fps'],a))
                            for w in scene.get('videoWindows',[]) if w['mediaId']==identity for a,b in visible)
                require(overlap+.0001>=.25,'视频播放窗没有至少0.25秒落在素材槽可见阶段：'+scene['id'])
    for first,second in zip(scenes,scenes[1:]):
        if first['group']!='s02' or by_id.get(first.get('mainMediaId'),{}).get('kind')!='video':continue
        last=next((w for w in first.get('videoWindows',[]) if w['mediaId']==first['mainMediaId'] and w['from']+w['frames']==first['frames']),None)
        following=next((w for w in second.get('videoWindows',[]) if w['mediaId']==second['mainMediaId'] and w['from']==0),None)
        require(last and following and abs(last['offset']+last['frames']/p['fps']-following['offset'])<=1/p['fps'],'九格到聚焦的接力源时钟不连续')
    if reference:require(order==['s01','s02','s03','s04','s05','s06','s07','s08','s09','review'] and p['durationFrames']==7344,'完整原版必须全部十组、原顺序和122.4秒')
    captions=p.get('captions');require(isinstance(captions,list) and captions,'完整口播须绑定真实字幕')
    last=0
    for c in captions:
        require(isinstance(c,dict) and set(c)=={'text','startMs','endMs'} and speech._text(c.get('text'),64),'字幕字段无效')
        require(speech._number(c['startMs']) and speech._number(c['endMs']) and last<=c['startMs']<c['endMs']<=seconds*1000+.08,'字幕原始时钟无效')
        last=c['endMs']
    avatar=p.get('presenter')
    if avatar:
        require(not reference and isinstance(avatar,dict) and set(avatar)=={'src','from','frames','offset','modes'},'人物片字段无效')
        require(speech._name(avatar['src']) and type(avatar['from']) is int and type(avatar['frames']) is int and 0<=avatar['from']<avatar['from']+avatar['frames']<=p['durationFrames'] and speech._number(avatar['offset']) and avatar['offset']>=0,'人物来源或时窗无效')
        end=-1
        for mode in avatar['modes']:
            require(set(mode)=={'from','frames','mode'} and mode['mode'] in {'large','small','hidden'} and type(mode['from']) is int and type(mode['frames']) is int and mode['frames']>0 and avatar['from']<=mode['from'] and mode['from']>=end and mode['from']+mode['frames']<=avatar['from']+avatar['frames'],'人物显示模式超出同声源区间')
            end=mode['from']+mode['frames']


def _source_check(p,audio,paths,provenance,*,fonts=True):
    require(set(paths)==required_names(p,audio),'sources须准确覆盖本期所有素材、音轨与字体')
    mapped=deepcopy(p);mapped['scenes']=[];mapped['presenterClips']=[]
    mapped.pop('presenter',None)
    base_rows={r['id']:r for r in provenance.get('media',[])}
    rows=deepcopy(provenance.get('media',[]));mapped_media=deepcopy(p['media'])
    media_by_id={m['id']:m for m in p['media']}
    for scene in p['scenes']:
        for i,w in enumerate(scene.get('videoWindows',[])):
            m=deepcopy(media_by_id[w['mediaId']]);require(m['kind']=='video','图片不能声明视频播放窗口')
            m['id']=scene['id']+'-window-'+str(i);m['offset']=w['offset'];mapped_media.append(m)
            row=deepcopy(base_rows.get(w['mediaId'],{}));row['id']=m['id'];rows.append(row)
            mapped['scenes'].append({'id':m['id'],'module':'focus','mediaId':m['id'],'frames':w['frames']*30/p['fps']})
    mapped['media']=mapped_media
    sync=[]
    if p.get('presenter'):
        # The shared source checker uses a 30fps clock. Convert presentation
        # frames and their same-source proof together, preserving real seconds.
        v=p['presenter'];factor=30/p['fps']
        mapped['presenterClips']=[{'id':'presenter','src':v['src'],'from':v['from']*factor,'frames':v['frames']*factor,'offset':v['offset']}]
        sync=deepcopy(provenance.get('presenterClips',[]))
        for row in sync:
            if row.get('id')=='presenter':
                for key in ('globalFrom','frames'):
                    if speech._number(row.get(key)):row[key]*=factor
    copied=deepcopy(provenance);copied['media']=rows;copied['presenterClips']=sync
    extra={p['referencePortrait']} if p.get('referencePortrait') and p['referencePortrait'] not in {m['src'] for m in p['media']} else set()
    if extra:
        from PIL import Image
        for name in extra:
            with Image.open(paths[name]) as image:require(min(image.size)>=240,'原版示例人物图像素不足')
    probed=speech._validate_sources(mapped,audio,{k:v for k,v in paths.items() if k not in extra},copied,check_fonts=False)
    if fonts:
        from PIL import ImageFont
        font=ImageFont.truetype(str(paths[p['fontAssets']['body']]),35 if p['variant']=='reference' else 70)
        width=1560 if p['variant']=='reference' else 1264
        require(all(font.getlength(c['text'])<=width for c in p['captions']),'实际字体字幕超宽，请按真实词时码分句')
    return probed


def preflight(value):
    require(isinstance(value,dict) and not set(value)-{'title','props','sources','audio','provenance','shotPlan'},'完整模板输入字段无效')
    require(speech._text(value.get('title'),100),'作品名称无效')
    paths=speech._sources(value.get('sources'));clock=speech._clock(paths[value['audio']['voice']])
    audio=speech._audio_plan(value['audio'],paths,clock)
    p=deepcopy(value['props']);reference=p.get('variant')=='reference'
    high_fps=reference or p.get('variant')=='native-story'
    p.update(width=1920 if reference else 1440,height=1080 if reference else 1800,fps=60 if high_fps else 30,
             durationFrames=audio['durationFrames']*(2 if high_fps else 1),audio='master.wav')
    if value.get('shotPlan'):
        require(not value['props'].get('scenes'),'精确场景与自动shotPlan只能二选一')
        p['scenes']=plan_shots(value['shotPlan'],p['durationFrames'],p['fps'])
    else:
        definitions={g['id']:g for g in catalog()['groups']}
        for scene in p.get('scenes',[]):
            if scene.get('group') in definitions:
                d=definitions[scene['group']];scene.setdefault('sourceStart',d['source']['start']);scene.setdefault('sourceDuration',d['source']['end']-d['source']['start'])
    validate_props(p,clock['duration_seconds'])
    _source_check(p,audio,paths,value['provenance'])
    return {'props':p,'audio':audio,'paths':paths,'provenance':speech.canonical_provenance(value['provenance'])}


def prepare(queue,value):
    n=preflight(value)
    clean={'contract':CONTRACT,'title':value['title'],'props':n['props'],'audio':n['audio'],'provenance':n['provenance'],
           'origins':{name:{'path':str(path),'sha256':sha(path)} for name,path in n['paths'].items()},
           'runtime':runtime(),'profile':PROFILE,'export':EXPORT,'cloud_calls':0,'publication':False}
    clean['asset_directory']=str((CACHE_ROOT/'assets'/fingerprint(clean['origins'])[:24]).resolve())
    core=queue_safe(clean,redact_local_paths=False)
    require(core==clean,'制作字段含不能进入冻结记录的内容，请修正来源字段')
    core['project_id']='studio-'+fingerprint(core)[:16]
    digest=fingerprint(core);r={**core,'request_sha256':digest,'render_id':CONTRACT+'-'+digest[:20]}
    project=queue.projects_root/r['project_id'];request=project/'artifacts'/REQUEST_FILE
    if request.exists():validate(queue,read_json(request));return read_json(request)
    from lib.checkpoint import init_project
    init_project(r['project_id'],title=r['title'],pipeline_type='animated-explainer',pipeline_dir=queue.projects_root)
    assets=Path(r['asset_directory']);assets.mkdir(parents=True,exist_ok=True)
    for name,path in n['paths'].items():
        if not (assets/name).exists():shutil.copy2(path,assets/name)
        require(sha(assets/name)==r['origins'][name]['sha256'],'冻结素材复制校验失败')
    atomic_private(request,r);validate(queue,r);return r


def validate(queue,r):
    digest=fingerprint({k:v for k,v in r.items() if k not in {'request_sha256','render_id'}})
    require(r.get('contract')==CONTRACT and r.get('request_sha256')==digest and r.get('render_id')==CONTRACT+'-'+digest[:20]
            and r.get('profile')==PROFILE and r.get('export')==EXPORT and r.get('cloud_calls')==0 and r.get('publication') is False,'完整模板冻结身份无效')
    project=WorkCatalog(queue.projects_root).project(r['project_id'])
    require(read_json(project/'artifacts'/REQUEST_FILE)==r,'冻结请求已改变')
    folder=project/'renders'/r['render_id'];receipt=read_json(folder/'result.json')
    if receipt:
        # Completed media is immutable; playback must not need the old compiler
        # or its disposable source cache after an application upgrade.
        require(receipt.get('request_sha256')==digest and sha(folder/OUTPUT_FILE)==receipt.get('output_sha256') and sha(folder/'quality.json')==receipt.get('quality_sha256') and sha(folder/'audio-receipt.json')==receipt.get('audio_receipt_sha256'),'完成产物或质量记录已改变')
        if receipt.get('nomusic_output_sha256'):require(sha(folder/NOMUSIC_FILE)==receipt['nomusic_output_sha256'],'无配乐备选成片已变化')
        return project
    asset_root=Path(r['asset_directory'])
    require(asset_root==(CACHE_ROOT/'assets'/fingerprint(r['origins'])[:24]).resolve(),'冻结素材目录身份无效')
    paths={n:regular_path(asset_root/n,asset_root) for n in r['origins']}
    require(all(speech._name(n) and sha(paths[n])==row['sha256'] for n,row in r['origins'].items()),'冻结素材已变化')
    clock=speech._clock(paths[r['audio']['voice']]);require(clock==r['audio']['voice_clock'],'完整口播样本数已变化')
    raw_audio={k:v for k,v in r['audio'].items() if k not in {'durationFrames','voice_clock','mix_profile'}}
    require(speech._audio_plan(raw_audio,paths,clock)==r['audio'],'冻结声音计划与真实音轨不一致')
    validate_props(r['props'],clock['duration_seconds'])
    _source_check(r['props'],r['audio'],paths,r['provenance'],fonts=True)
    require(runtime()==r['runtime'],'模板源码或依赖已改变，请冻结新版本')
    return project


def submit(queue,r):
    validate(queue,r)
    require(queue_safe(r,redact_local_paths=False)==r,'冻结请求不满足无凭据队列合同')
    return queue.submit(project_id=r['project_id'],kind=KIND,source='codex',priority='normal',parent_job_id=r['render_id'],
                        frozen_request=r,idempotency_key=CONTRACT+':'+r['request_sha256'],start_paused=True)


def run(queue,job):
    r=job['frozen_request']
    try:
        require(job['kind']==KIND and job['project_id']==r['project_id'],'队列执行身份不一致')
        project=validate(queue,r);folder=project/'renders'/r['render_id'];folder.mkdir(parents=True,exist_ok=True)
        output=folder/OUTPUT_FILE
        if not read_json(folder/'result.json'):
            from tools.video.video_compose import VideoCompose
            from backlot.studio_render import media_probe
            from backlot.studio_investment_audio_v5 import measure_audio
            ff,_=resolve_ffmpeg_pair()
            scratch=CACHE_ROOT/r['render_id']
            scratch.mkdir(parents=True,exist_ok=True);public=scratch/'public';public.mkdir(exist_ok=True)
            paths={n:Path(r['asset_directory'])/n for n in r['origins']}
            for name,path in paths.items():
                if name not in {r['audio']['voice'],r['audio'].get('music'),*(s['src'] for s in r['audio'].get('sfx',[]))}:shutil.copy2(path,public/name)
            master=speech.mix_master(r['audio'],paths,public/'master.wav')
            make_nomusic=bool(r['audio'].get('music'))
            if make_nomusic:
                no_music={k:deepcopy(v) for k,v in r['audio'].items() if k not in {'music','musicGainDb','musicOffsetSeconds','loopMusic'}}
                master['nomusic']=speech.mix_master(no_music,paths,scratch/'nomusic.wav')
            atomic_private(folder/'audio-receipt.json',master)
            for path in template_files():
                target=scratch/'template'/path.relative_to(TEMPLATE);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            atomic_private(scratch/'props.json',r['props']);atomic_private(folder/'props.json',r['props'])
            duration=r['props']['durationFrames']/r['props']['fps']
            edits={'render_runtime':'remotion','composition_mode':'atelier','renderer_family':'bespoke','timeline':{'duration_seconds':duration},
                   'bespoke':{'entry':str(scratch/'template/index.tsx'),'composition_id':'DarkFull','art_direction':str(TEMPLATE/'design-direction.md'),
                              'props_path':str(scratch/'props.json'),'public_dir':str(public),'concurrency':2,**PROFILE}}
            atomic_private(folder/'edit-decisions.json',edits)
            raw=scratch/'mezzanine-crf1.mp4'
            result=VideoCompose().execute({'operation':'render','output_path':str(raw),'edit_decisions':edits,'asset_manifest':{'assets':[]},'script_text':''})
            atomic_private(folder/'render-report.json',{'success':result.success,'data':result.data,'error':str(result.error) if result.error else None})
            require(result.success,'完整模板渲染失败：'+str(result.error))
            command=[ff,'-nostdin','-y','-v','error','-i',str(raw),'-i',str(public/'master.wav'),'-map','0:v:0','-map','1:a:0','-t',str(duration),
                     '-c:v','libx264','-preset','slow','-b:v','20500k','-minrate','20500k','-maxrate','20500k','-bufsize','2000k',
                     '-x264-params','nal-hrd=cbr:force-cfr=1:filler=1','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
            subprocess.run(command,check=True,capture_output=True,creationflags=NO_WINDOW)
            info=media_probe(output);v=info.get('video') or {};a=info.get('audio') or {};loud=measure_audio(output)
            require((v.get('width'),v.get('height'))==(r['props']['width'],r['props']['height']) and int(v.get('nb_frames',0))==r['props']['durationFrames'] and abs(info['duration']-duration)<=.08 and abs(float(Fraction(v.get('avg_frame_rate','0/1')))-r['props']['fps'])<.001 and v.get('codec_name')=='h264' and v.get('pix_fmt')=='yuv420p' and int(v.get('bit_rate',0))>=EXPORT['minimum_measured_bitrate'] and a.get('channels')==2 and str(a.get('sample_rate'))=='48000' and loud['true_peak_dbtp']<=-1.5,'成片画布/帧数/码率/音轨未通过')
            subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
            no_loud=None
            if make_nomusic:
                no_command=[ff,'-nostdin','-y','-v','error','-i',str(output),'-i',str(scratch/'nomusic.wav'),'-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(folder/NOMUSIC_FILE)]
                subprocess.run(no_command,check=True,capture_output=True,creationflags=NO_WINDOW)
                no_loud=measure_audio(folder/NOMUSIC_FILE);require(no_loud['true_peak_dbtp']<=-1.5,'无配乐备选音轨峰值失败')
                subprocess.run([ff,'-nostdin','-v','error','-xerror','-i',str(folder/NOMUSIC_FILE),'-f','null','-'],check=True,capture_output=True,creationflags=NO_WINDOW)
            atomic_private(folder/'quality.json',{'media':info,'audio':loud,'nomusic_audio':no_loud,'full_decode':'passed','voice_clock':r['audio']['voice_clock'],
                           'original_assets_sha_verified':True,'audio_receipt_sha256':sha(folder/'audio-receipt.json'),'render_command':(result.data or {}).get('render_command'),
                           'export_command':command,'visual_review':'pending','continuous_watching':'pending','device_listening':'pending','avatar_lip_sync':'pending' if r['props'].get('presenter') else 'not-applicable'})
            atomic_private(folder/'result.json',{'request_sha256':r['request_sha256'],'output_sha256':sha(output),'nomusic_output_sha256':sha(folder/NOMUSIC_FILE) if make_nomusic else None,'audio_receipt_sha256':sha(folder/'audio-receipt.json'),
                           'quality_sha256':sha(folder/'quality.json'),'cloud_calls':0,'publication':False})
        work=WorkCatalog(queue.projects_root).register(r['project_id'],output,work_key='main',mode='manual',event_id=job['job_id'],quality_passed=False,actor=CONTRACT,title=r['title'])
        version=next(v for v in work['versions'] if v['sha256']==sha(output))
        return {'status':'completed','stage':'完整多屏模板已合成，等待观看','result':{'output_path':str(output),'output_sha256':sha(output),'qa_status':'pending','work_id':work['work_id'],'version_id':version['version_id']}}
    except Exception as exc:
        return {'status':'failed','stage':'完整模板制作未完成，原请求保留','error':{'type':type(exc).__name__,'message':str(exc)[:1600]},'retryable':True,'safe_resume_point':'dark-full-local'}
