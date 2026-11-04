"""Production receipt around the unchanged native component queue renderer.

Action IDs select the real native controls. Measured ASR sentence/word anchors
create their original absolute cue inputs. The original package, plan review,
preview review, media gates and encoding remain the execution authority.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from backlot import motion_replay, studio_motiongit as motion
from backlot import studio_motiongit_render as native
from backlot.studio import atomic_private
from backlot.studio_investment_recompose import fingerprint
from backlot.work_catalog import read_json, sha, WorkError

CONTRACT = 'haike.motion-replay-imported-production/1'
KIND = 'studio_investment_recompose'
REQUEST_FILE = 'motion-replay-imported-production-request.json'


def require(ok, message):
    if not ok: raise WorkError(message)


def _bound(value):
    require(isinstance(value, dict) and set(value) == {'path','sha256'}, '本期证据须绑定path/sha256。')
    path = Path(value['path'])
    require(path.is_file() and not path.is_symlink() and sha(path) == value['sha256'], '本期源证据缺失或SHA变化。')
    return path


def caption_chunks(sentences, limit=18):
    """Split at real word boundaries while retaining every source character."""
    result=[]
    for sentence in sentences:
        text=sentence['text'];words=sentence.get('words',[])
        if not words:
            result.append({'s':sentence['start'],'e':sentence['end'],'text':text});continue
        positions=[];cursor=0;valid=True
        for word in words:
            at=text.find(word['text'],cursor)
            if at<0:valid=False;break
            cursor=at+len(word['text']);positions.append(cursor)
        if not valid:
            result.append({'s':sentence['start'],'e':sentence['end'],'text':text});continue
        first=0;char_start=0
        for index,word in enumerate(words):
            last=index==len(words)-1
            stop=len(text) if last else positions[index]
            next_stop=len(text) if index+1==len(words)-1 else positions[index+1] if not last else stop
            if not last and next_stop-char_start<=limit:continue
            result.append({'s':words[first]['start'],
                           'e':sentence['end'] if last else word['end'],
                           'text':text[char_start:stop]})
            first=index+1;char_start=stop
    require(''.join(c['text'] for c in result)==''.join(s['text'] for s in sentences), '字幕拆分没有完整保留ASR文本。')
    return result


def compile_timeline(spec, *, workspace):
    """Use measured anchors; never divide characters or time by scene count."""
    require(isinstance(spec, dict) and not set(spec) - {
        'template_id','version','workflow','title','base_timeline','semantic_scenes',
        'asr','script','assets','output_profile','source_receipts','semantic_overlays','caption_corrections'}, '制作规格包含未开放字段。')
    template = motion_replay.resolve(spec['template_id'], spec['version'])
    require(spec['workflow'] == 'motion-kit', '此独立生产合同当前只接入真实motion-kit组件路线。')
    transcript = read_json(_bound(spec['asr']))
    sentences = transcript.get('segments')
    require(isinstance(sentences,list) and sentences, '必须有本期真实ASR句级时钟。')
    script = read_json(_bound(spec['script']))
    require(isinstance(script.get('text'),str) and script['text'], '缺少完整本期文案。')
    base = deepcopy(spec['base_timeline'])
    require('segments' not in base and 'overlays' not in base and type(base.get('duration')) in {int,float}
            and math.isfinite(base['duration']) and base['duration']>0, '主时长必须来自本期完整声音，场景由动作计划编译。')
    rows=spec['semantic_scenes'];require(isinstance(rows,list) and rows, '语义动作计划为空。')
    known={a['id']:a for a in template['actions']}
    segments=[];events=[];cursor=0
    for index,row in enumerate(rows):
        require(isinstance(row,dict) and not set(row)-{'id','action_id','sentence_start','sentence_end','props','variant','presenter','transition','cues','start_in_silence'}, '语义场景字段无效。')
        if 'transition' in row:
            require(row['transition'] in {'cut','flash','wipe','blur','zoom','whip','glitch','iris','shutter','pixel','dip'},
                    '场景转场必须使用精确原包公开的transition值。')
        start,end=row.get('sentence_start'),row.get('sentence_end')
        require(type(start) is int and type(end) is int and start==cursor and start<end<=len(sentences), '场景须按真实ASR句连续覆盖全稿，不漏句或重排台词。')
        action=known.get(row.get('action_id'))
        require(action and action['implementation'].get('protocol')=='motion-kit'
                and action['implementation'].get('native_control'), '动作编号未绑定此精确包的真实motion-kit控件。')
        def boundary(scene):
            si=scene['sentence_start']
            if si==0:return 0.0
            proposed=float(scene.get('start_in_silence',sentences[si]['start']))
            require(float(sentences[si-1]['end'])<=proposed<=float(sentences[si]['start']),
                    '显式转场只能落在真实ASR句间空隙，不能截断口播或移动词时码。')
            return proposed
        t0=boundary(row)
        t1=base['duration'] if index==len(rows)-1 else boundary(rows[index+1])
        require(0<=t0<t1<=base['duration'] and t1-t0+.001>=action['parameters'].get('minDur',0), '语义窗口不足以完成原控件最短动作，请重新选完整动作。')
        cues=[]
        for cue in row.get('cues',[]):
            require(set(cue)<= {'id','sentence','word','authored_at'} and isinstance(cue.get('id'),str), '内部事件必须命名并绑定真实句或词。')
            if 'authored_at' in cue:
                require(set(cue)=={'id','authored_at'} and cue['authored_at']==0
                        and index==0 and t0==0 and sentences[0]['start']>=.2,
                        '仅允许在真实静音引导段的时间原点创作开场，不能伪造词时码。')
                at=0.0;anchor={'kind':'authored-opening','timeline_seconds':0,
                              'speech_begins_seconds':sentences[0]['start']}
            else:
                si=cue.get('sentence');require(type(si) is int and start<=si<end, '内部事件引用其他语义窗口。')
                if 'word' in cue:
                    words=sentences[si].get('words',[]);wi=cue['word']
                    require(type(wi) is int and 0<=wi<len(words), '内部事件缺少真实词级证据。')
                    source=words[wi];at=float(source['start'])
                else:source=sentences[si];at=float(source['start'])
                anchor={'asr_sentence':si,'asr_word':cue.get('word'),'text':source['text']}
            require(t0<=at<t1 and (not cues or at>cues[-1]), '内部语义事件须有序且落在原组内。')
            cues.append(at)
            events.append({'id':row['id']+'.'+cue['id'],'action_id':action['id'],
                'instant_seconds':at,'anchor':anchor})
        segment={'control':action['implementation']['native_control'],'t0':t0,'t1':t1,
                 'props':deepcopy(row['props']),'cues':cues}
        for key in ['variant','presenter','transition']:
            if key in row:segment[key]=row[key]
        segments.append(segment)
        events.append({'id':row['id']+'.window','action_id':action['id'],
            'window_seconds':[t0,t1],'asr_sentence_range':[start,end],
            'meaning':''.join(s['text'] for s in sentences[start:end])})
        cursor=end
    require(cursor==len(sentences),'动作计划没有覆盖完整真实ASR。')
    base['segments']=segments
    overlay_ids=[]
    for row in spec.get('semantic_overlays',[]):
        require(not set(row)-{'id','action_id','sentence_start','sentence_end','props','variant','area'},'语义叠加字段无效。')
        action=known.get(row.get('action_id'))
        require(action and action['implementation'].get('protocol')=='motion-kit'
                and action['implementation'].get('native_control'), '叠加动作未绑定真实原生控件。')
        start,end=row['sentence_start'],row['sentence_end']
        require(type(start) is int and type(end) is int and 0<=start<end<=len(sentences),'叠加须绑定本期真实句区间。')
        t0=float(sentences[start]['start']);t1=base['duration'] if end==len(sentences) else float(sentences[end]['start'])
        overlay={'control':action['implementation']['native_control'],'t0':t0,'t1':t1,'props':deepcopy(row['props'])}
        for key in ['variant','area']:
            if key in row:overlay[key]=deepcopy(row[key])
        base.setdefault('overlays',[]).append(overlay);overlay_ids.append(action['id'])
        events.append({'id':row['id']+'.window','action_id':action['id'],'window_seconds':[t0,t1],
                       'asr_sentence_range':[start,end],'role':'source-bound native overlay'})
    # The exact native caption schema consumes real ASR intervals; full approved
    # copy is separately retained and checked in the production content review.
    base['captions']=caption_chunks(sentences)
    applied=[]
    for correction in spec.get('caption_corrections',[]):
        require(set(correction)=={'from','to','expected_count'} and correction['from']
                and correction['to'] in script['text'], '字幕校正必须可追溯到完整已批准原稿。')
        count=sum(c['text'].count(correction['from']) for c in base['captions'])
        require(count==correction['expected_count'], '字幕校正次数与原ASR不一致，请重新检查显示映射。')
        for caption in base['captions']:caption['text']=caption['text'].replace(correction['from'],correction['to'])
        applied.append({**correction,'applied_count':count,'clock_changed':False})
    target_paths={
        'title':['line1','line2'],'steps':['steps.0','steps.1','steps.2'],
        'media':['title'],'gallery':['items.0.caption','items.1.caption','items.2.caption'],
        'device':['title'],'quote':['text'],'list':['items.0','items.1'],
        'cta':['kicker','text'],
    }
    purpose={'steps':'neutral-list','gallery':'provided-evidence','media':'provided-evidence',
             'device':'provided-evidence','list':'neutral-list','cta':'user-requested-action'}
    base['narrationMap']=[]
    for index,segment in enumerate(segments):
        control=segment['control']
        require(control in target_paths,'此生产候选未登记该控件的真实语义目标，须重新适配。')
        indices=[i for i,c in enumerate(base['captions']) if c['s']<segment['t1'] and c['e']>segment['t0']]
        beats=[]
        for i in indices:
            caption=base['captions'][i]
            focus=max([j for j,c in enumerate(segment['cues']) if c<=caption['s']+.001],default=0)
            targets=target_paths[control];target=targets[min(focus,len(targets)-1)]
            beats.append({'at':caption['s'],'until':caption['e'],'spokenText':caption['text'],
                          'timing':'sentence','target':target})
        base['narrationMap'].append({'shot':index,'start':segment['t0'],'end':segment['t1'],
            'spokenText':''.join(base['captions'][i]['text'] for i in indices),
            'purpose':purpose.get(control,'neutral-emphasis'),'timingSource':'provided-captions',
            'captionBinding':'continuous','captionIndices':indices,'beats':beats})
    require(transcript.get('audio_sha256') in {a['sha256'] for a in spec['assets'].values()}, 'ASR没有绑定本期实际完整音轨。')
    request={'workflow':'motion-kit','parameters':{'workflow':'motion-kit','timeline':base},
             'assets':spec['assets'],'title':spec['title'],
             'output_profile':spec.get('output_profile','native'),
             'action_ids':list(dict.fromkeys(row['action_id'] for row in rows))}
    prepared=motion_replay.prepare(spec['template_id'],spec['version'],request,workspace=workspace)
    require(prepared['status']=='prepared','本期原生输入未准备就绪。')
    receipt={'schema':'haike.motion-replay-consumption/1','template_id':spec['template_id'],
        'version':spec['version'],'package_sha256':prepared['package_verification']['sha256'],
        'workflow':'motion-kit','main_action_ids':request['action_ids'],
        'action_ids':list(dict.fromkeys(request['action_ids']+overlay_ids)),'events':events,
        'asr_sha256':spec['asr']['sha256'],'script_sha256':spec['script']['sha256'],
        'audio_sha256':transcript['audio_sha256'],'parameters_sha256':fingerprint(request['parameters']),
        'action_bindings':[deepcopy(known[a]) for a in dict.fromkeys(request['action_ids']+overlay_ids)],
        'source_verification':prepared['source_verification'],
        'source_receipts':deepcopy(spec.get('source_receipts',{})),
        'caption_corrections':applied,
        'coverage':{'asr_sentences':len(sentences),'covered_sentences':cursor,
                    'caption_chunks':len(base['captions']),'caption_text_complete':True,
                    'duration_seconds':base['duration'],'audio_speed_changed':False}}
    return prepared,receipt


def freeze(queue,spec,*,workspace):
    """Admit source-bound native input and write a distinct production receipt."""
    prepared,receipt=compile_timeline(spec,workspace=workspace)
    identity=fingerprint({'spec':spec,'receipt':receipt})
    admission=Path(workspace)/'.local/motion-production-admissions'/identity
    path=admission/'draft.json'
    # Existing draft IDs are resumed after all source validation, never cloned
    # merely because an observer or local producer restarted.
    if path.is_file():
        saved=read_json(path);draft=motion.draft(saved['id'])
        require(draft['parameters']==prepared['consumer']['body']['parameters'],'持久草稿与本期动作输入不同。')
    else:
        body=prepared['consumer']['body']
        draft=motion.save_draft(body['package_id'],body['workflow'],body['parameters'],
                               title=body['title'],output_profile=body['output_profile'])
        atomic_private(path,{'id':draft['id'],'identity':identity})
    indexed={r['slot']:r for r in motion.asset_list(draft['id'])['assets']}
    for alias,row in spec['assets'].items():
        if alias in indexed:
            require(indexed[alias]['sha256']==row['sha256'],'既有草稿上传与本期素材不同。')
        else:motion.save_asset(draft['id'],alias,_bound(row).read_bytes())
    original=native.freeze(queue,draft['id'])
    require(original['contract']==native.CONTRACT and not original.get('native_protocol'), '原生队列合同与选中组件路线不匹配。')
    core={'contract':CONTRACT,'project_id':original['project_id'],'native_request':original,
          'replay_receipt':receipt,'adapter_sha256':sha(__file__),'publication':False,'paid_calls':0}
    digest=fingerprint(core)
    request={**core,'request_sha256':digest,'render_id':'motion-replay-imported-'+digest[:20]}
    target=queue.projects_root/request['project_id']/'artifacts'/REQUEST_FILE
    if target.exists():require(read_json(target)==request,'本期统一复刻冻结记录不同，请保留旧请求。')
    else:atomic_private(target,request)
    atomic_private(queue.projects_root/request['project_id']/'artifacts/motion-replay-consumption.json',receipt)
    return request


def validate(queue,request):
    core={k:v for k,v in request.items() if k not in {'request_sha256','render_id','phase'}}
    require(request.get('contract')==CONTRACT and fingerprint(core)==request.get('request_sha256'), '统一复刻父请求身份不同。')
    expected=read_json(queue.projects_root/request['project_id']/'artifacts'/REQUEST_FILE)
    require(expected=={k:v for k,v in request.items() if k!='phase'},'统一复刻持久请求已变化。')
    original=request['native_request'];receipt=request['replay_receipt']
    require(original['project_id']==request['project_id'] and original['contract']==native.CONTRACT
            and fingerprint(original['draft']['parameters'])==receipt['parameters_sha256'], '原生消费参数没有绑定本期动作合同。')
    timeline=original['draft']['parameters']['timeline']
    actual=[f"haike.{receipt['template_id']}.motion-kit.{s['control']}" for s in timeline['segments']+timeline.get('overlays',[])]
    require(set(actual)==set(receipt['action_ids']),'原生实际控件与动作消费记录不一致。')
    template=motion_replay.resolve(receipt['template_id'],receipt['version'])
    motion_replay.verify_sources(template)
    require(sha(__file__)==request['adapter_sha256'],'本期独立生产适配器已变化，请冻结新请求。')
    return original


def submit(queue,request,*,phase='preview'):
    original=validate(queue,request);require(phase in {'preview','render'},'阶段无效。')
    approval=read_json(native._paths(queue,original)/'plan-semantic-review.json')
    suffix=phase+(':'+fingerprint(approval)[:16] if phase=='preview' and approval else '')
    return queue.submit(project_id=request['project_id'],kind=KIND,source='codex',priority='normal',
        parent_job_id=request['render_id'],frozen_request={**request,'phase':phase},
        idempotency_key=CONTRACT+':'+request['request_sha256']+':'+suffix,start_paused=True)


def review_plan(queue,request,evidence):return native.review_plan(queue,validate(queue,request),evidence)
def review(queue,request,evidence):return native.review(queue,validate(queue,request),evidence)


def run(queue,job):
    try:
        request=job['frozen_request'];original=validate(queue,request)
        # Delegation retains the actual queue job identity and original native
        # render ID, so native result/work/recovery receipts remain authoritative.
        return native.run(queue,{**job,'frozen_request':{**original,'phase':request['phase']}})
    except (WorkError,ValueError,OSError,KeyError) as exc:
        return {'status':'failed','stage':'统一复刻父合同待恢复','retryable':True,
                'safe_resume_point':'motion_replay_imported_production',
                'error':{'type':'MotionReplayProduction','message':str(exc)[:800]}}
