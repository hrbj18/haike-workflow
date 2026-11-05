"""C project-owned dark schema, AGPL-3.0 inherited from Haike_video/LICENSE.

Derived from the explicitly approved C complete ten-group schema. No original
protected MotionGit source and no legacy production helper is imported.
"""
import json
import math
import re
from pathlib import Path
from backlot.motion_public_io_v1 import read_json, WorkError

def require(value,message):
    if not value:raise WorkError(message)

class _LocalChecks:
    @staticmethod
    def _number(value):return type(value) in (int,float) and math.isfinite(value)
    @staticmethod
    def _name(value):return isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}",value) is not None
    @staticmethod
    def _text(value,maximum,*,lines=1,empty=False):
        return isinstance(value,str) and (empty or bool(value.strip())) and len(value)<=maximum and len(value.splitlines())<=lines
speech=_LocalChecks()

def catalog():
    return read_json(Path(__file__).resolve().parents[1]/'templates/motiongit-public-components-v2/dark-v2/template/catalog.json')

def required_names(props,audio):
    names={audio['voice'],*props['fontAssets'].values()}
    for m in props['media']:
        names.add(m['src']);names.add(m['thumbnail'])
    if props.get('presenter'):names.add(props['presenter']['src'])
    if props.get('referencePortrait'):names.add(props['referencePortrait'])
    if audio.get('music'):names.add(audio['music'])
    names.update(s['src'] for s in audio.get('sfx',[]))
    return names

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
