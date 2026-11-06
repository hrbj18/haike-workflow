"""Durable orchestration across process loss, scope changes and different inputs."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backlot.avatar_one_stop import OneStop, STAGES
from backlot.avatar_one_stop_policy import digest, CLONE_MODEL, WORKFLOW_ID, VERSION, SPEECH_RATE_RULE
from backlot.avatar_one_stop_tools import OneStopTools, agent, succeeded
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


@pytest.fixture
def setup(tmp_path):
    portrait, audio, reference = [tmp_path/name for name in ('person.png', 'sample.wav', 'reference.png')]
    for path in (portrait, audio, reference):
        path.write_bytes(path.name.encode())
    script = tmp_path/'script.json'
    text = '这是一条用于测试完整自动制作的原文。'
    script.write_text(json.dumps({'title': '测试原文', 'text': text}, ensure_ascii=False), 'utf-8')
    policy = {'schema': 'haike.avatar-agent-production-policy/1',
              'template': {'template_id': 'chromatic-six-11', 'version': VERSION},
              'avatar_generation': {'workflow_id': WORKFLOW_ID, 'budget_rh_coins_per_video': 2000},
              'voice_clone': {'model': CLONE_MODEL},
              'paid_authorization': {'standing_authorized': True, 'other_paid_stages_authorized': True},
              'speech_rate': {'target_characters_per_second': 4.87,
                  'calibration_test': {'version': 'test-v1', 'text': '测' * 92,
                      'text_sha256': hashlib.sha256(('测' * 92).encode()).hexdigest(), 'effective_characters': 92}},
              'image_refinement': {'reference_image': {'path': str(reference), 'sha256': digest(reference)}, 'prompt': '双图参考'},
              'default_script': {'script_json': str(script), 'script_json_sha256': digest(script),
                                 'text_sha256': hashlib.sha256(text.encode()).hexdigest()}}
    path = tmp_path/'policy.json'
    atomic_private(path, policy)
    class Studio:
        private = tmp_path/'private'
        def draft(self, identity):
            return {'id': 'studio-'+'a'*16, 'kind': 'avatar', 'revision': 1}
        def asset(self, identity, draft_id):
            return {'person': portrait, 'audio': audio}[identity]
    request = {'draft_id': 'studio-'+'a'*16, 'portrait_id': 'person', 'audio_id': 'audio', 'consent': True}
    return Studio(), path, request


class Tools:
    account = 'account-a'
    unknown = True
    def verify_scope(self):
        return self.account
    def refinement(self, value, folder, save):
        return agent('refine_portrait', '双参考精修')
    def clone(self, value, folder, save):
        if 'clone' not in value['paid']:
            value['paid']['clone'] = {'provider_operation': 'original-accepted-call'}
            save()
        if self.unknown:
            raise WorkError('受理结果未知，只能查询原调用')
        return succeeded({'voice_id': 'the-new-voice'})
    def storyboard(self, value, folder, save):
        return agent('review_storyboard', '检查新语音实际分镜')
    def quality(self, value, folder, save):
        return agent('review_video', '检查实际新成片')
    def composition(self, value, folder, save):
        return succeeded({'output_path': str(folder/'new-result.mp4'), 'output_sha256': 'actual-sha', 'work_id': 'new-work'})
    def apply(self, value, folder, data):
        return succeeded({'reason': data['reason']})
    def __getattr__(self, name):
        if name in STAGES:
            return lambda value, folder, save: succeeded()
        raise AttributeError(name)


def test_restart_preserves_accepted_call_and_completed_stages(setup):
    studio, policy, request = setup
    tools = Tools()
    service = OneStop(studio, tools=tools, policy_path=policy)
    task = service.create(request)
    identity = task['id']
    assert service.create(request)['id'] == identity
    assert len(service.list()) == 1
    assert service.advance(identity)['stage'] == 'refinement'
    service.apply(identity, {'stage': 'refinement', 'reason': '实际双图检查通过'})
    paused = service.advance(identity)
    assert paused['status'] == 'paused' and paused['stage'] == 'clone'
    paid = service.get(identity, private=True)['paid']
    # Fresh instance, same task files. The accepted operation remains immutable.
    resumed = OneStop(studio, tools=Tools(), policy_path=policy)
    resumed.tools.unknown = False
    assert resumed.advance(identity)['stage'] == 'storyboard'
    assert resumed.get(identity, private=True)['paid'] == paid
    resumed.apply(identity, {'stage': 'storyboard', 'reason': '已检查所有实际素材和新时间轴'})
    assert resumed.advance(identity)['stage'] == 'quality'
    resumed.apply(identity, {'stage': 'quality', 'reason': '实际新成片检查完成'})
    result = resumed.advance(identity)
    assert result['status'] == 'completed' and result['result']['work_id'] == 'new-work'
    assert resumed.advance(identity) == result
    assert all(row['status'] == 'succeeded' for row in result['stages'])
    assert 'private' not in json.dumps(result) and 'provider_operation' not in json.dumps(result)


def test_different_input_and_account_cannot_overwrite_or_read_original(setup):
    studio, policy, request = setup
    service = OneStop(studio, tools=Tools(), policy_path=policy)
    first = service.create(request)
    (policy.parent/'person.png').write_bytes(b'different person')
    second = service.create(request)
    assert first['id'] != second['id']
    assert service.get(first['id'], private=True)['inputs']['portrait']['sha256'] != service.get(second['id'], private=True)['inputs']['portrait']['sha256']
    foreign = Tools()
    foreign.account = 'different-account'
    other = OneStop(studio, tools=foreign, policy_path=policy)
    with pytest.raises(WorkError, match='不存在或不属于'):
        other.get(first['id'])
    with pytest.raises(WorkError):
        service.file('../anything', 'video')
    assert service.list()[0]['budget_rh_coins'] == 2000


def test_native_audio_unknown_result_queries_same_operation_without_requote(tmp_path):
    class Center:
        calls = 0
        quotes = 0
        resolved = False
        def quote(self, request):
            self.quotes += 1
            return {'id': 'original-quote', 'operation_id': 'call_'+'a'*32, 'max_charge_micros': '600'}
        def operation(self, identity):
            if not (tmp_path/'accepted.json').exists():
                raise WorkError('不存在', 'missing')
            return {'status': 'submission_unknown'}
        def submit(self, request):
            self.calls += 1
            atomic_private(tmp_path/'accepted.json', request)
            raise TimeoutError('a private supplier URL must never reach public state')
        def job(self, identity):
            assert identity == 'call_'+'a'*32
            return {'status': 'succeeded' if self.resolved else 'submission_unknown', 'result': {'voice': {'id': 'v'}} if self.resolved else {}}
    tools = object.__new__(OneStopTools)
    tools.center, tools.internal_audio = Center(), False
    value = {'paid': {}}
    save = lambda: atomic_private(tmp_path/'parent.json', value)
    with pytest.raises(TimeoutError):
        tools._audio_paid(value, 'clone', {'model': 'haike/voice-clone'}, save)
    value = json.loads((tmp_path/'parent.json').read_text('utf-8'))
    assert tools._audio_paid(value, 'clone', {}, save) is None
    tools.center.resolved = True
    assert tools._audio_paid(value, 'clone', {}, save)['voice']['id'] == 'v'
    assert tools.center.calls == tools.center.quotes == 1


def test_complete_user_audio_never_clones_or_auditions():
    tools = object.__new__(OneStopTools)
    value = {'audio_role': 'narration'}
    assert tools.clone(value, None, None)['result']['skipped']
    assert tools.audition(value, None, None)['result']['skipped']


def test_new_tasks_freeze_fixed_text_pace_rule(setup):
    studio, policy, request = setup
    before = digest(policy)
    service = OneStop(studio, tools=Tools(), policy_path=policy)
    task = service.create(request)
    frozen = service.get(task['id'], private=True)['policy']['speech_rate']
    assert frozen['calibration_mode'] == 'fixed_text_baseline'
    assert frozen['calibration_test']['effective_characters'] == 92
    assert frozen['baseline_rate'] == 1.0 and frozen['target_characters_per_second'] == 4.9
    assert frozen['characters_per_five_seconds'] == {'minimum': 23.5, 'maximum': 25.5, 'target': 24.5}
    assert frozen['max_full_text_attempts'] == 3
    assert service.defaults()['characters_per_five_seconds'] == frozen['characters_per_five_seconds']
    assert digest(policy) == before
    labels = {row['id']: row['label'] for row in task['stages']}
    assert labels['audition'] == '固定文案测速'


def test_tampered_fixed_test_cannot_create_new_paid_work(setup):
    studio, policy, request = setup
    data = json.loads(policy.read_text('utf-8'))
    data['speech_rate']['calibration_test']['text'] = '变' * 92
    atomic_private(policy, data)
    with pytest.raises(WorkError, match='固定测速文案内容或字数'):
        OneStop(studio, tools=Tools(), policy_path=policy).create(request)


@pytest.mark.parametrize('baseline_seconds,expected_rates', [(61.0, [1.0]), (64.0, [1.0, 1.05])])
def test_full_text_baseline_reuses_accepted_audio_or_remeasures_adjustment(tmp_path, baseline_seconds, expected_rates):
    tools = object.__new__(OneStopTools)
    # Use 299 effective characters and real WAV frame counts for pace decisions.
    text = '字' * 299 + '，。'
    value = {'script': {'text': text, 'text_sha256': 'same-script'}, 'stages': {},
             'policy': {'speech_rate': {'calibration_mode': 'full_text_baseline',
                 'target_characters_per_second': 4.9,
                 'characters_per_five_seconds': {'minimum': 24, 'maximum': 25, 'target': 24.5}}}}
    tools._tts = lambda *args: pytest.fail('full-text calibration must not submit a short audition')
    audition = tools.audition(value, tmp_path, lambda: None)
    assert audition['result']['skipped'] and audition['result']['rate'] == 1.0
    # An old short-text estimate must not influence a new full-text baseline.
    value['stages']['audition'] = {'result': {'rate': .95}}
    calls = []
    def tts(value, folder, name, script, rate, save):
        calls.append(rate)
        assert script == text
        path = folder / (name + '.wav')
        seconds = baseline_seconds if name == 'narration' else 61.0
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(1000)
            audio.writeframes(b'\x00\x00' * int(seconds * 1000))
        return path
    tools._tts = tts
    result = tools.narration(value, tmp_path, lambda: None)['result']
    assert calls == expected_rates and result['rate'] == expected_rates[-1]
    assert result['pace_check'] == 'within_five_second_band'
    assert 24 <= result['characters_per_five_seconds'] <= 25
    assert result['duration_seconds'] == 61.0 and result['audio_sha256'] == digest(tmp_path / 'narration.wav')
    if len(calls) == 2:
        assert digest(tmp_path / 'narration-adjust-1.wav') == result['audio_sha256']


def test_full_narration_corrects_slow_short_audition_before_freezing_clock(tmp_path, monkeypatch):
    from backlot import avatar_one_stop_tools as module
    tools=object.__new__(OneStopTools)
    calls=[]
    def tts(value, folder, name, text, rate, save):
        calls.append((name,rate))
        target=folder/(name+'.wav')
        target.write_bytes(name.encode())
        return target
    tools._tts=tts
    monkeypatch.setattr(module,'wav_duration',lambda p:66.442125 if p.name=='narration.wav' else 61.0)
    value={'script':{'text':'字'*299,'text_sha256':'script'},
        'policy':{'speech_rate':{'target_characters_per_second':4.871709777149124}},
        'stages':{'audition':{'result':{'rate':.95}},'narration':{'status':'running'}}}
    outcome=tools.narration(value,tmp_path,lambda:None)
    assert abs(outcome['result']['deviation_percent'])<=3
    assert outcome['result']['rate']==1.05
    assert calls==[('narration',.95),('narration-adjust-1',1.05)]


def test_explicit_rate_survives_audition_and_is_not_auto_lowered(tmp_path, monkeypatch):
    from backlot import avatar_one_stop_tools as module
    tools=object.__new__(OneStopTools)
    value={'script':{'text':'字'*299,'text_sha256':'script'},
        'policy':{'speech_rate':{'target_characters_per_second':4.87,'fixed_rate':1.15}},'stages':{}}
    tools._tts=lambda *args:pytest.fail('explicit rate must skip short audition')
    audition=tools.audition(value,tmp_path,lambda:None)
    assert audition['result']['rate']==1.15 and audition['result']['skipped']
    calls=[]
    def tts(value,folder,name,text,rate,save):
        calls.append(rate)
        path=folder/(name+'.wav')
        path.write_bytes(b'existing-supplier-output')
        return path
    tools._tts=tts
    monkeypatch.setattr(module,'wav_duration',lambda p:55)
    result=tools.narration(value,tmp_path,lambda:None)['result']
    assert result['rate']==1.15 and result['pace_check']=='explicit_rate' and calls==[1.15]


def test_full_narration_calibration_resumes_same_candidates_and_is_bounded(tmp_path, monkeypatch):
    from backlot import avatar_one_stop_tools as module
    tools=object.__new__(OneStopTools)
    value={'script':{'text':'字'*299,'text_sha256':'script'},
        'policy':{'speech_rate':{'target_characters_per_second':4.871709777149124}},
        'stages':{'audition':{'result':{'rate':.95}}}}
    calls=[]
    pending=True
    def tts(value,folder,name,text,rate,save):
        calls.append((name,rate))
        if name.endswith('adjust-1') and pending:
            return None
        path=folder/(name+'.wav')
        path.write_bytes(name.encode())
        return path
    tools._tts=tts
    monkeypatch.setattr(module,'wav_duration',lambda p:66.442125 if p.name=='narration.wav' else 61)
    assert tools.narration(value,tmp_path,lambda:None)['status']=='waiting'
    pending=False
    assert tools.narration(value,tmp_path,lambda:None)['status']=='succeeded'
    assert calls==[('narration',.95),('narration-adjust-1',1.05)]*2
    assert len(value['stages']['narration']['calibration_attempts'])==2
    value['stages']['narration']={}
    calls.clear()
    monkeypatch.setattr(module,'wav_duration',lambda p:66.442125)
    with pytest.raises(WorkError,match='未继续ASR或数字人'):
        tools.narration(value,tmp_path,lambda:None)
    assert len(calls)==len(value['stages']['narration']['calibration_attempts'])==3


def test_user_stopped_revision_cannot_restart_on_advance(setup):
    studio,policy,request=setup
    tools=Tools()
    service=OneStop(studio,tools=tools,policy_path=policy)
    task=service.create(request)
    value=service.get(task['id'],private=True)
    value.update(status='stopped',message='用户停止错误倍率调整')
    service._save(value)
    tools.refinement=lambda *a:pytest.fail('stopped task must never restart generation')
    result=service.advance(task['id'])
    assert result['status']=='stopped' and result['revision']==value['revision']
    assert service.advance(task['id'])==result


def test_explicit_rate_cannot_bypass_measured_five_second_band(tmp_path,monkeypatch):
    from backlot import avatar_one_stop_tools as module
    tools=object.__new__(OneStopTools)
    calls=[]
    def tts(value,folder,name,text,rate,save):
        calls.append(rate)
        path=folder/(name+'.wav')
        path.write_bytes(b'full-narration')
        return path
    tools._tts=tts
    value={'script':{'text':'字'*299,'text_sha256':'script'},'stages':{},
        'policy':{'speech_rate':{'target_characters_per_second':4.9,'fixed_rate':1.15,
            'characters_per_five_seconds':{'minimum':24,'maximum':25}}}}
    monkeypatch.setattr(module,'wav_duration',lambda path:54.260875)
    with pytest.raises(WorkError,match='每5秒27.55字'):
        tools.narration(value,tmp_path,lambda:None)
    assert calls==[1.15] and value['stages']['narration']['calibration_attempts'][0]['accepted'] is False
    value['stages']={}
    value['policy']['speech_rate']['fixed_rate']=1.05
    monkeypatch.setattr(module,'wav_duration',lambda path:61)
    result=tools.narration(value,tmp_path,lambda:None)['result']
    assert 24<=result['characters_per_five_seconds']<=25


def test_relaxed_target_reuses_2508_take_and_stops_without_another_candidate(tmp_path):
    tools = object.__new__(OneStopTools)
    calls = []
    def tts(value, folder, name, text, rate, save):
        calls.append((name, rate))
        assert name == 'narration'  # A qualified original take must not request an adjustment.
        path = folder / 'narration.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\x01\x00' * 1430817)
        return path
    tools._tts = tts
    value = {'script': {'text': '字' * 299, 'text_sha256': 'script'}, 'stages': {},
        'policy': {'speech_rate': {**SPEECH_RATE_RULE, 'fixed_rate': 1.15}}}
    result = tools.narration(value, tmp_path, lambda: None)['result']
    assert result['characters_per_five_seconds'] == pytest.approx(25.0765821206)
    assert result['rate'] == 1.15 and result['pace_check'] == 'within_five_second_band'
    assert calls == [('narration', 1.15)]
    assert len(value['stages']['narration']['calibration_attempts']) == 1


def test_rate_revision_preserves_original_and_reuses_checked_assets(setup):
    studio,policy,request=setup
    tools=Tools()
    tools.unknown=False
    service=OneStop(studio,tools=tools,policy_path=policy)
    original=service.create(request)
    service.advance(original['id'])
    folder=service._folder(original['id'])
    (folder/'refinement').mkdir()
    (folder/'refinement/result.png').write_bytes(b'checked-original-image')
    service.apply(original['id'],{'stage':'refinement','reason':'已看两图精修结果'})
    service.advance(original['id'])
    historical=service.get(original['id'],private=True)
    historical.pop('preflight')
    atomic_private(folder/'task.json',historical)
    before=digest(folder/'task.json')
    latest=json.loads(policy.read_text('utf-8'))
    latest['speech_rate'].update(target_characters_per_second=4.9,
        characters_per_five_seconds={'minimum':24,'maximum':25})
    atomic_private(policy,latest)
    data={'speech_rate':1.15,'reason':'用户指出原版语速偏慢，修订为侯总默认1.15','request_id':'pace-v2'}
    revised=service.revise(original['id'],data)
    assert revised['id']!=original['id'] and revised['revision_of']==original['id']
    assert service.revise(original['id'],data)['id']==revised['id']
    value=service.get(revised['id'],private=True)
    assert value['budget_group_id']==original['id'] and value['budget_rh_coins']==2000
    assert value['policy']['speech_rate']['fixed_rate']==1.15
    assert value['policy']['speech_rate']['characters_per_five_seconds']=={'minimum':23.5,'maximum':25.5,'target':24.5}
    assert value['stages']['clone']['result']['voice_id']=='the-new-voice'
    assert value['paid']['clone']['provider_operation']=='original-accepted-call'
    assert digest(service._folder(revised['id'])/'refinement/result.png')==digest(folder/'refinement/result.png')
    assert digest(folder/'task.json')==before
    seeded = service.revise(original['id'], {**data, 'synthesis_seed': 1})
    assert seeded['id'] != revised['id']
    assert service.revise(original['id'], {**data, 'synthesis_seed': 1})['id'] == seeded['id']
    seeded_value = service.get(seeded['id'], private=True)
    assert seeded_value['policy']['speech_rate']['synthesis_seed'] == 1
    assert seeded_value['budget_group_id'] == original['id']
    assert digest(folder/'task.json') == before
    with pytest.raises(WorkError, match='种子'):
        service.revise(original['id'], {**data, 'synthesis_seed': True})
    with pytest.raises(WorkError,match='0.05'):
        service.revise(original['id'],{**data,'speech_rate':1.13})


def test_quality_selects_only_reviewed_native_version_without_publication(tmp_path, monkeypatch):
    from backlot.work_catalog import WorkCatalog
    root = tmp_path/'projects'
    project = root/'new-person'
    project.mkdir(parents=True)
    (project/'project.json').write_text('{"title":"本期作品"}', 'utf-8')
    monkeypatch.setattr('backlot.work_catalog.probe',lambda p:{'duration':66,'width':1080,'height':1920,'has_audio':True})
    base, final = project/'base.mp4', project/'final.mp4'
    base.write_bytes(b'original-template-badge')
    final.write_bytes(b'new-person-generic-badge')
    catalog = WorkCatalog(root)
    catalog.register(project.name, base)
    work = catalog.register(project.name, final)
    folder = tmp_path/'task'
    folder.mkdir()
    atomic_private(folder/'quality.json',{'technical':'pass','output_sha256':digest(final)})
    tools = object.__new__(OneStopTools)
    tools.studio = SimpleNamespace(projects_root=root)
    value = {'stages':{'composition':{'result':{'output_path':str(final),'work_id':work['work_id']}}}}
    receipt = {'stage':'quality','observed_sha256':digest(base),'visual_passed':True,
        'audio_review':'technical_only','reason':'实际新人物和字幕代表帧通过，声音仅技术量测'}
    with pytest.raises(WorkError,match='检查对象已经变化'):
        tools.apply(value,folder,receipt)
    assert not catalog.list()
    receipt['observed_sha256'] = digest(final)
    assert tools.apply(value,folder,receipt)['status']=='succeeded'
    verified = catalog.get(work['work_id'])
    chosen = next(v for v in verified['versions'] if v['version_id']==verified['final_version_id'])
    assert chosen['sha256']==digest(final) and len(catalog.list())==1
    assert verified['confirmations'][-1]['actor']=='avatar-one-stop-agent'
    assert verified['targets']==verified['attempts']==verified['materials']==[]
    tools.apply(value,folder,receipt)
    assert len(catalog.get(work['work_id'])['confirmations'])==1
