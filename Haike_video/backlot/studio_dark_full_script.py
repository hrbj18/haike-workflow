"""Recoverable script/material facade; delegates speech to existing Studio services.

No template rendering, provider selection, avatar generation or publication lives
here. A ready result is exactly the input accepted by studio_dark_full.preflight.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import wave

from backlot import studio_asr, studio_dark_full as adapter
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha
from lib.bailian_speech import operation_lock


def require(ok, message):
    if not ok:
        raise WorkError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def spoken(text):
    return re.sub(r'[\W_]+', '', text, flags=re.UNICODE).casefold()


def pcm_identity(path):
    with wave.open(str(path), 'rb') as wav:
        require(wav.getcomptype() == 'NONE', '缓存口播须为完整PCM WAV')
        data = wav.readframes(wav.getnframes())
        return {'samples': wav.getnframes(), 'sample_rate': wav.getframerate(),
                'channels': wav.getnchannels(), 'sample_width': wav.getsampwidth(),
                'pcm_sha256': hashlib.sha256(data).hexdigest()}


def audio_center(studio):
    from backlot.studio_services import audio_mode, budget_policy, refresh_private_environment
    refresh_private_environment()
    if audio_mode(studio) == 'internal':
        from backlot.studio_audio_internal import InternalAudioCenter
        return InternalAudioCenter(studio, pricing=budget_policy(studio).get('audio_pricing', {}))
    from backlot.studio_audio import AudioCenter
    return AudioCenter(studio)


def menu_summary():
    from tools.tool_registry import registry
    return registry.provider_menu_summary()


def normalize_audio(source, target):
    """Only decode/resample; no atempo, trimming, duration rounding or padding."""
    try:
        identity = pcm_identity(source)
        if (identity['sample_rate'], identity['channels'], identity['sample_width']) == (24000, 1, 2):
            shutil.copy2(source, target)
            return
    except (wave.Error, EOFError):
        pass
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff, _ = resolve_ffmpeg_pair()
    subprocess.run([ff, '-nostdin', '-y', '-v', 'error', '-i', str(source), '-vn', '-ac', '1',
                    '-ar', '24000', '-c:a', 'pcm_s16le', str(target)], check=True,
                   capture_output=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def measured_captions(result, duration, script):
    """Require observed words; never distribute a sentence clock over letters."""
    words, previous, segment_ends = [], 0., set()
    for segment in result.get('segments', []):
        require(isinstance(segment.get('words'), list) and segment['words'], '识别缺少真实词级边界，请保留音轨并核对原ASR任务')
        for w in segment['words']:
            a, b, t = w.get('start'), w.get('end'), w.get('text')
            require(type(a) in {int,float} and type(b) in {int,float} and math.isfinite(a) and math.isfinite(b)
                    and previous <= a < b <= duration + .08 and isinstance(t,str) and t.strip(), '识别词级时钟无效，未伪造字幕')
            words.append({'text':t, 'start':a, 'end':min(b,duration)})
            previous=b
        segment_ends.add(len(words))
    require(words and spoken(''.join(w['text'] for w in words)) == spoken(script),
            '识别文字与原文不一致，请审阅实际ASR；不能按文案伪造对齐或重复配音')
    script_breaks, position = set(), 0
    for character in script:
        if character in '。！？!?；;，,：:\n': script_breaks.add(position)
        position += len(spoken(character))
    cues, current, position = [], None, 0
    for index, w in enumerate(words, 1):
        require(len(w['text']) <= 18, '真实词单元过长，请提供更细的原始ASR边界')
        if current and (w['start']-current['endMs']/1000 > .28 or len(current['text']+w['text']) > 16):
            cues.append(current);current=None
        if current:
            current.update(text=current['text']+w['text'], endMs=w['end']*1000)
        else:
            current={'text':w['text'], 'startMs':w['start']*1000, 'endMs':w['end']*1000}
        position += len(spoken(w['text']))
        # Split only at observed word ends; punctuation never invents a clock.
        if index in segment_ends or position in script_breaks or w['text'].endswith(tuple('。！？!?；;，,')):
            cues.append(current);current=None
    if current:cues.append(current)
    return cues,words


class Budget:
    """Reservations survive unknown supplier bills and preserve other task calls."""
    def __init__(self, path):
        self.path=Path(path)

    def reserve(self, operation, stage, maximum):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with operation_lock(self.path.parent/(self.path.stem+'-lock')):
            value=read(self.path) if self.path.exists() else {'currency':'CNY','limit_micros':1000000,'calls':[],'known_spend_micros':0}
            require(type(maximum) is int and maximum>0, '本次费用上限须为正整数微元')
            previous=next((c for c in value['calls'] if c.get('operation_id')==operation),None)
            if previous:
                require(previous.get('reserved_micros')==maximum, '原调用预算已冻结，请保留原费用上限恢复')
                return
            reserved=sum(int(c.get('reserved_micros',0)) for c in value['calls'])
            require(int(value.get('known_spend_micros',0))+reserved+maximum<=int(value['limit_micros']), '本次调用超过总任务预算，尚未提交')
            value['calls'].append({'purpose':'dark-full-script '+stage,'operation_id':operation,'reserved_micros':maximum,
                                   'status':'reserved','actual_cost_status':'unconfirmed'})
            value['reserved_micros']=reserved+maximum
            atomic_private(self.path,value)

    def record(self, operation, job):
        with operation_lock(self.path.parent/(self.path.stem+'-lock')):
            value=read(self.path)
            row=next(c for c in value['calls'] if c.get('operation_id')==operation)
            row['status']=job.get('status','submission_unknown')
            # Direct-provider charged_micros=None is not zero spend. Keep its
            # entire reservation until an independently reconciled bill exists.
            row['actual_cost_status']='unconfirmed'
            row['accepted']=job.get('accepted')
            for key in ('operation_id','upstream_id','usage'):
                if job.get(key) is not None:row['provider_operation_id' if key=='operation_id' else key]=job[key]
            if job.get('status')=='failed' and job.get('accepted') is False:
                row['reserved_micros']=0;row['actual_cost_status']='definitive-not-accepted'
            value['reserved_micros']=sum(int(c.get('reserved_micros',0)) for c in value['calls'])
            atomic_private(self.path,value)


class ScriptFacade:
    def __init__(self, studio, directory, request=None, *, center=None, sdk=None,
                 menu=menu_summary, asr_status=None, asr_snapshot=None, preflight=adapter.preflight):
        self.studio,self.directory=studio,Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.request_path=self.directory/'request.json';self.state_path=self.directory/'state.json'
        if request is not None:
            require(isinstance(request,dict) and not set(request)-{'title','script','recipe','reuse','motion_events','voice_performance'}, '脚本入口字段无效')
            require(isinstance(request.get('script'),str) and 0<len(request['script'].strip())<=10000, '请提供1至10000字完整文案')
            require(isinstance(request.get('recipe'),dict), '请提供已审阅的素材与完整镜头配方')
            request=deepcopy(request);request['script']=request['script'].strip()
            if self.request_path.exists():
                require(read(self.request_path)==request,'文案或配方已改变，请用新项目目录；原调用和产物保留')
            else:atomic_private(self.request_path,request)
        require(self.request_path.exists(),'未找到原脚本请求，恢复时不要新建付费任务')
        self.request=read(self.request_path);self.identity=fingerprint(self.request)
        self.center,self.sdk,self.menu=center,sdk,menu
        self.asr_status=asr_status or (lambda:studio_asr.status(studio))
        self.asr_snapshot=asr_snapshot or (lambda:studio_asr.snapshot(studio))
        self.preflight_adapter=preflight
        self.state=read(self.state_path) if self.state_path.exists() else {'fingerprint':self.identity,'status':'needs_voice','stages':{}}
        require(self.state['fingerprint']==self.identity,'原请求身份已改变，未重新提交')

    def save(self):atomic_private(self.state_path,self.state)

    def reload(self):
        if self.state_path.exists():self.state=read(self.state_path)
        require(self.state['fingerprint']==self.identity,'原请求身份已改变，停止恢复')

    def _center(self):
        if self.center is None:self.center=audio_center(self.studio)
        return self.center

    def _sdk(self):
        if self.sdk is None:self.sdk=self.studio.client()
        return self.sdk

    def _inspect(self):
        # Required ordering: compact provider inventory, then actual current
        # account preference. Neither call submits a generation request.
        menu=self.menu()
        try:
            voices=self._center().voices();selected=voices.get('preferences',{}).get('voice_id')
            row=next((v for v in voices.get('items',[]) if v['id']==selected),None)
            safe={k:row.get(k) for k in ('id','name','model','model_id','provider','available','preferences')} if row else None
            return {'provider_menu':menu,'selected_voice':safe,'asr':self.asr_status()}
        except WorkError:
            return {'provider_menu':menu,'selected_voice':None,'asr':self.asr_status(),
                    'message':'尚未配置可用的配音服务和默认音色，请在现有API/音色中心完成设置。'}

    def _reuse(self):
        reuse=self.request.get('reuse')
        if not reuse:return False
        require(set(reuse)=={'script','voice_info','captions'},'缓存复用须提供原脚本、口播回执和真实字幕三个明确来源')
        script=read(reuse['script']);info=read(reuse['voice_info']);cues=read(reuse['captions'])
        if isinstance(cues,dict):
            require(cues.get('voice_sha256')==info.get('sha256') and cues.get('clock')=='provider-word-timestamps',
                    '原字幕容器没有同音轨词级时钟证据')
            cues=[{'text':c['text'],'startMs':c['start']*1000,'endMs':c['end']*1000} for c in cues.get('captions',[])]
        require(script.get('text','').strip()==self.request['script'],'原始配音文案与当前文案不同，不能借用旧口播')
        require(info.get('status')=='succeeded' and isinstance(info.get('operation_id'),str),'口播任务缺少成功来源记录')
        op=self._center().operation(info['operation_id'])
        require(op.get('status')=='succeeded' and op.get('request',{}).get('kind')=='tts'
                and op['request'].get('text','').strip()==self.request['script'], '原供应商操作的真实文案未匹配，不能只凭声明SHA复用')
        source=Path(info['voice']);require(source.is_file() and sha(source)==info.get('sha256'),'旧口播文件已变化')
        clock=adapter.speech._clock(source)
        require(all(info.get(k)==clock[k] for k in ('samples','sample_rate','channels','sample_width')),'旧口播样本时钟已变化')
        provider_file=self._center().preview(info['operation_id'])
        require(pcm_identity(provider_file)==pcm_identity(source),'供应商原音频与口播PCM不一致，不能复用剪切/重排音轨')
        lineage=self.request['recipe'].get('provenance',{}).get('captions',{})
        require(lineage.get('voice_sha256')==info['sha256'] and lineage.get('source_sha256')==sha(Path(reuse['captions'])), '字幕回执没有绑定同一口播与原字幕文件')
        require(isinstance(cues,list) and spoken(''.join(c['text'] for c in cues))==spoken(self.request['script']), '缓存字幕未完整对应当前文案')
        self.state.update(voice={'path':str(source.resolve()),'sha256':sha(source),'clock':clock,'operation_id':info['operation_id'],'reused':True},
                          captions=cues,status='needs_review',cache_proof={'script_file_sha256':sha(Path(reuse['script'])),
                          'operation_id':info['operation_id'],'operation_text_sha256':fingerprint(op['request']['text']),
                          'provider_audio_sha256':sha(provider_file),'pcm':pcm_identity(source),
                          'captions_sha256':sha(Path(reuse['captions']))})
        return True

    def inspect(self):
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            self.state['services']=self._inspect()
            if not self.state.get('voice'):self._reuse()
            if not self.state.get('voice'):
                self.state['status']='needs_voice'
                self.state['message']='请使用当前已配置音色报价并确认配音，或绑定有真实原任务证据的完整口播。'
            self.save();return deepcopy(self.state)

    def quote(self, stage):
        require(stage in {'tts','asr'},'阶段只支持tts或asr')
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            if stage in self.state['stages']:return deepcopy(self.state['stages'][stage])
            if stage=='tts' and self.state.get('voice',{}).get('reused'):
                return {'status':'cached','operation_id':self.state['voice']['operation_id'],
                        'max_charge_micros':'0','cache_proof':deepcopy(self.state['cache_proof'])}
            if stage=='asr' and self.state.get('voice',{}).get('reused') and self.state.get('captions'):
                return {'status':'cached','max_charge_micros':'0','captions_sha256':self.state['cache_proof']['captions_sha256']}
            if stage=='tts':
                self.state['services']=self._inspect()
                row=self.state['services'].get('selected_voice')
                require(row and row.get('available') is not False,'尚未配置可用默认音色，当前状态needs_voice')
                payload={'model':row['model'],'input':{'voice_id':row['id'],'text':self.request['script'],
                         'speech_rate':row.get('preferences',{}).get('speech_rate',1),'purpose':'production'}}
                q=self._center().quote(payload)
                data={'quote':q,'operation_id':q['operation_id'],'payload_sha256':fingerprint(payload),
                      'scope':getattr(self._center(),'account',None),'status':'quoted'}
            else:
                require(self.state.get('voice'),'请先完成或复用完整口播，再报价字幕阶段')
                frozen=self.asr_snapshot();self.state['asr_snapshot']=frozen
                if frozen['provider']=='local-whisper':
                    data={'quote':{'model':'local/whisper','max_charge_micros':'0'},'status':'local_ready'}
                else:
                    sdk=self._sdk();voice=Path(self.state['voice']['path'])
                    prepared=(sdk.prepare_asr_audio(voice) if frozen['provider']=='bailian' else sdk.upload(voice,'audio'))
                    model=frozen.get('model','haike/tencent-asr')
                    q=sdk.quote(model,{'audio_file':prepared['id']},'dark-full-script-'+self.identity[:16])
                    operation='call_'+fingerprint({'facade':self.identity,'stage':'asr','quote':q['id']})[:32]
                    data={'quote':q,'operation_id':operation,'status':'quoted','audio_sha256':self.state['voice']['sha256']}
            self.state['stages'][stage]=data;self.save();return deepcopy(data)

    def confirm(self, stage, maximum, budget_path, *, confirmed=False, project_maximum=1000000):
        require(confirmed is True,'请明确确认当前报价和费用上限')
        require(type(maximum) is int and 0<maximum<=project_maximum,'费用上限无效')
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            require(stage in self.state['stages'],'请先保存本阶段真实报价')
            data=self.state['stages'][stage]
            require(data.get('status')!='local_ready','免费本地识别请使用resume，不提交付费调用')
            require(int(data['quote']['max_charge_micros'])<=maximum,'报价超过本阶段授权上限，尚未提交')
            previous=data.get('maximum')
            require(previous in {None,maximum},'原调用费用上限已冻结，恢复时不能改变')
            committed=sum(int(s.get('maximum',0)) for s in self.state['stages'].values())
            require(committed+(0 if previous else maximum)<=project_maximum,'本项目已承诺费用超过本次总上限')
            budget=Budget(budget_path);budget.reserve(data['operation_id'],stage,maximum)
            data.update(maximum=maximum,budget_path=str(Path(budget_path).resolve()))
            if data.get('attempted'):
                try:return self._resume(stage)
                except WorkError as e:
                    # Explicit confirm may restore a pre-acceptance gap using
                    # precisely the same centre operation; never a new quote.
                    if stage!='tts' or e.code!='missing':raise
            data.update(attempted=True,status='submitting');self.save() # before provider boundary
            if stage=='tts':
                require(data.get('scope')==getattr(self._center(),'account',None),'配音账号已改变，停止提交原报价')
                try:
                    job=self._center().submit({'quote_id':data['quote']['id'],'operation_id':data['operation_id'],
                                              'max_charge_micros':maximum,'confirmed':True})
                except Exception:
                    data['status']='submission_unknown';self.save();raise WorkError('原配音提交结果待核对，请恢复同一操作，不要新建报价') from None
            else:
                data['intent']=data['operation_id'];self.save()
                try:
                    returned=self._sdk().confirm(data['quote'],maximum,data['operation_id'])
                    require(returned==data['intent'],'SDK意图与已保存原操作不一致')
                    job=self._sdk().resume(data['intent'])
                except Exception:
                    data['status']='submission_unknown';self.save()
                    raise WorkError('原识别意图已保存，提交结果待核对；请恢复同一操作，不要新建任务') from None
            return self._consume(stage,job)

    def _consume(self, stage, job):
        data=self.state['stages'][stage];data.update(status=job.get('status','submission_unknown'),job=job)
        if data.get('budget_path'):Budget(data['budget_path']).record(data['operation_id'],job)
        self.save()
        if job.get('status')!='succeeded':return deepcopy(self.state)
        if stage=='tts':
            source=self._center().preview(data['operation_id']);target=self.directory/'voice.wav'
            if target.exists() and self.state.get('voice'):
                require(sha(target)==self.state['voice']['sha256'],'已保存口播文件已改变，不能覆盖来源证据')
            if not target.exists():normalize_audio(source,target)
            identity=pcm_identity(target);clock=adapter.speech._clock(target)
            require((identity['sample_rate'],identity['channels'],identity['sample_width'])==(24000,1,2),'配音输出未规范为完整24kHz PCM')
            self.state.update(voice={'path':str(target.resolve()),'sha256':sha(target),'clock':clock,
                                    'operation_id':data['operation_id'],'reused':False},status='needs_alignment')
        else:
            result=job.get('result') or {};raw=self.directory/'asr-result.json';atomic_private(raw,result)
            cues,words=measured_captions(result,self.state['voice']['clock']['duration_seconds'],self.request['script'])
            atomic_private(self.directory/'asr-words.json',words)
            self.state.update(captions=cues,status='needs_review',asr_evidence={'source':str(raw.resolve()),'sha256':sha(raw),
                              'voice_sha256':self.state['voice']['sha256'],'operation_id':data.get('operation_id'),
                              'method':'existing-Studio-ASR-observed-word-boundaries'})
        self.save();return deepcopy(self.state)

    def _resume(self, stage):
        data=self.state['stages'].get(stage);require(data is not None,'没有原阶段记录，先报价')
        if data.get('status')=='local_ready':
            require(stage=='asr','本地阶段无效')
            result=studio_asr.transcribe(self.studio,self.state['asr_snapshot'],Path(self.state['voice']['path']),
                                        self.directory,self.state['voice']['clock']['duration_seconds'])
            return self._consume(stage,{'status':'succeeded','result':result})
        require(data.get('attempted'),'报价尚未确认，不会在查询操作中首次收费')
        if stage=='tts':job=self._center().job(data['operation_id'])
        else:
            require(data.get('intent'),'原ASR意图待核对；未自动重新确认或提交')
            job=self._sdk().resume(data['intent'])
        return self._consume(stage,job)

    def resume(self, stage):
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            return self._resume(stage)

    def bind_recipe(self, recipe):
        """Revise only the local storyboard after the measured audio is known.

        Audio/ASR operation identities remain in the immutable original request;
        editing this later material revision can never create another TTS call.
        """
        require(isinstance(recipe,dict) and not set(recipe)-{'title','props','sources','audio','provenance','shotPlan'},
                '素材配方只能包含完整模板开放输入字段')
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            require(self.state.get('voice'),'先取得实际口播时长，再修订本地镜头配方')
            digest=fingerprint(recipe);path=self.directory/'plans'/(digest+'.json')
            if not path.exists():atomic_private(path,recipe)
            self.state['material_plan']={'path':str(path.resolve()),'sha256':sha(path)}
            self.save();return deepcopy(self.state['material_plan'])

    def export(self):
        with operation_lock(self.directory/'facade-lock'):
            self.reload()
            require(self.state.get('voice') and self.state.get('captions'),'先完成真实口播与字幕时钟，再导出制作输入')
            plan=self.state.get('material_plan')
            if plan:
                require(sha(Path(plan['path']))==plan['sha256'],'已保存素材配方已变化，请绑定新修订')
            value=read(plan['path']) if plan else deepcopy(self.request['recipe'])
            value['title']=self.request.get('title') or value.get('title','脚本素材完整短片')
            value['sources'][value['audio']['voice']]=self.state['voice']['path']
            value['props']['captions']=deepcopy(self.state['captions'])
            lineage=value.setdefault('provenance',{});voice=self.state['voice']
            lineage['voice']={'source':str(self.state_path.resolve()),'sha256':voice['sha256'],'authorized':True,
                              'provider_operation_id':voice['operation_id'],'script_sha256':fingerprint(self.request['script']),
                              'samples':voice['clock']['samples'],'sample_rate':voice['clock']['sample_rate'],
                              'speech_trimmed':False,'speech_reordered':False,'playback_rate':1}
            if not voice['reused']:
                lineage['captions']={**self.state['asr_evidence'],'voice_sha256':voice['sha256']}
                value['props'].pop('presenter',None);lineage['presenterClips']=[]
                # New voice must not inherit a previous movie's sound clock.
                require(not value['audio'].get('sfx') or self.request.get('motion_events'),
                        '新口播须提供动作音效映射motion_events，不能硬复制旧音效时刻')
            if self.request.get('motion_events'):
                clock=voice['clock'];frames=math.ceil((clock['samples']/clock['sample_rate']+value['audio'].get('tailSeconds',.25))*30)
                scenes=adapter.plan_shots(value['shotPlan'],frames,30);by_id={s['id']:s for s in scenes};sound=[]
                for event in self.request['motion_events']:
                    s=by_id[event['sceneId']];when=s['from']/30+s['cueTimes'][event['cueId']]-event.get('transientOffsetSeconds',0)
                    sound.append({'src':event['src'],'atSeconds':max(0,when),'gainDb':event['gainDb']})
                value['audio']['sfx']=sound
            value['sources']={k:v for k,v in value['sources'].items() if k in adapter.required_names(value['props'],value['audio'])}
            audio_names={e['src'] for e in value['audio'].get('sfx',[])}|({value['audio']['music']} if value['audio'].get('music') else set())
            lineage['audio']={k:v for k,v in lineage.get('audio',{}).items() if k in audio_names}
            value['provenance']=adapter.speech.canonical_provenance(lineage)
            normalized=self.preflight_adapter(value)
            target=self.directory/'input.json';atomic_private(target,value)
            self.state.update(status='ready',output={'input':str(target.resolve()),'sha256':sha(target),
                              'frames':normalized['props']['durationFrames'],'fps':normalized['props']['fps'],
                              'cloud_render_submitted':False,'publication':False})
            self.save();return deepcopy(self.state['output'])
