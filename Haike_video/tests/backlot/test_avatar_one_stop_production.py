import pytest
import json
import wave
from backlot.avatar_one_stop_production import word_map, semantic_clock, allocate_clips, clean_captions
from backlot.work_catalog import WorkError


def test_semantics_follow_new_word_segmentation_and_nonlinear_timing():
    old = [{'text': '孩子', 'start': 1, 'end': 2}, {'text': '体验', 'start': 2, 'end': 3},
           {'text': '机器人', 'start': 3, 'end': 4}]
    new = [{'text': '孩', 'start': .2, 'end': .5}, {'text': '子', 'start': .5, 'end': .9},
           {'text': '体验', 'start': 1, 'end': 3}, {'text': '机器人', 'start': 4, 'end': 6}]
    mapping = word_map(old, new)
    assert mapping[1] == 2 and mapping[2] == 3
    clock = semantic_clock(old, new, mapping, 150, 210)
    assert clock(60) == 30 and clock(90) == 120 and clock(150) == 210
    with pytest.raises(WorkError, match='差异较大'):
        word_map(old, [{'text': '另一篇完全不同的原文', 'start': 0, 'end': 3}])


def test_longer_new_narration_adds_real_alternatives_instead_of_loop_or_frozen_tail():
    sources = {name: {'sha256': name, 'source_offset': 0} for name in ['a.mp4', 'b.mp4', 'c.mp4']}
    durations = {name: 4 for name in sources}
    clips = [{'src': name, 'objectPosition': '50% 58%'} for name in sources]
    result = allocate_clips(clips[:2], 200, 530, sources, durations, clips)
    assert [c['src'] for c in result] == list(sources)
    assert result[0]['from'] == 200 and result[-1]['to'] == 530
    assert all(c['to']-c['from'] <= 120 and c['sourceFrom'] == 0 for c in result)
    assert all(a['to'] == b['from'] for a, b in zip(result, result[1:]))
    with pytest.raises(WorkError, match='素材时长不足'):
        allocate_clips(clips[:2], 0, 241, sources, durations, clips[:2])


def test_caption_reflow_preserves_text_and_removes_short_orphan_fragment():
    original = [{'from':0,'to':100,'text':'它在新闻里、在课本里、在同学嘴里——唯一的问'},
                {'from':100,'to':114,'text':'题是，'},
                {'from':120,'to':200,'text':'从\\"知道AI\\"变成\\"会用AI\\"。'}]
    rows = clean_captions(original)
    assert len(rows) == 2 and rows[0]['to'] == 114
    assert '\\' not in ''.join(row['text'] for row in rows)
    assert all(len(row['text']) <= 38 and len(row['text'].splitlines()) <= 2 for row in rows)


def test_hq_cumulative_reservation_blocks_before_any_supplier_process(tmp_path, monkeypatch):
    from backlot import avatar_one_stop_production as production
    with wave.open(str(tmp_path/'narration.wav'), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0'*(90*24000))
    plan = {'windows': [{'from':0, 'to':1350}, {'from':1350, 'to':2700}]}
    (tmp_path/'storyboard-approved.json').write_text(json.dumps(plan), 'utf-8')
    monkeypatch.setattr(production, 'validate_plan', lambda *args: None)
    monkeypatch.setattr(production.subprocess, 'run', lambda *args, **kwargs: pytest.fail('over-budget flow reached supplier process'))
    with pytest.raises(WorkError, match='全部数字人片段累计预留'):
        production.avatar({'budget_rh_coins':2000}, tmp_path, lambda: None)


def test_revision_cannot_get_another_full_rh_budget(tmp_path, monkeypatch):
    from backlot import avatar_one_stop_production as production
    from types import SimpleNamespace
    original_id='os_'+'a'*32
    original=tmp_path/original_id
    original.mkdir()
    (original/'task.json').write_text(json.dumps({'id':original_id,
        'paid':{'avatar':{'known_usage_rh_coins':1700,'plan':{'reserve_coins':1600}}}}),'utf-8')
    folder=tmp_path/('os_'+'b'*32)
    folder.mkdir()
    with wave.open(str(folder/'narration.wav'),'wb') as audio:
        audio.setparams((1,2,24000,0,'NONE','not compressed'))
        audio.writeframes(b'\0\0'*24000)
    (folder/'storyboard-approved.json').write_text(json.dumps({'windows':[{'from':0,'to':30}]}),'utf-8')
    monkeypatch.setattr(production,'validate_plan',lambda *a:None)
    monkeypatch.setattr(production,'hq_executor',lambda:SimpleNamespace(config=lambda:{'workflow_id':production.WORKFLOW_ID},
        make_plan=lambda *a,**k:{'reserve_coins':301}))
    monkeypatch.setattr(production.subprocess,'run',lambda *a,**k:pytest.fail('revision exceeded shared cap'))
    with pytest.raises(WorkError,match='累计预留'):
        production.avatar({'id':folder.name,'budget_group_id':original_id,'budget_rh_coins':2000},folder,lambda:None)


def test_download_recovery_only_reads_successful_existing_objects(tmp_path):
    from backlot.avatar_one_stop_production import recover_hq_downloads
    from types import SimpleNamespace
    accepted = tmp_path/'segment_001'
    unknown = tmp_path/'segment_002'
    for case, status in [(accepted,'SUCCESS'),(unknown,'UNKNOWN')]:
        case.mkdir()
        (case/'ledger.json').write_text(json.dumps({'task_id':case.name}), 'utf-8')
        (case/'query.json').write_text(json.dumps({'status':status,'results':[{'nodeId':'93','url':'https://original.example/video'}]}), 'utf-8')
    calls = []
    def download(url, path):
        calls.append((url,path))
        path.write_bytes(b'existing-provider-result')
    executor = SimpleNamespace(body=lambda value:value, SUCCESS={'SUCCESS'}, download=download)
    assert recover_hq_downloads(executor,tmp_path)
    assert len(calls)==1 and calls[0][1].parent == accepted
    receipt = json.loads((accepted/'video.mp4.download.json').read_text('utf-8'))
    assert receipt['task_id']=='segment_001' and receipt['new_generation'] is False and receipt['tls_verification'] is True
    assert not recover_hq_downloads(executor,tmp_path)
    assert not (unknown/'video.mp4').exists() and len(calls)==1


def test_original_url_failure_preserves_charge_and_allows_native_download_recovery(tmp_path):
    from backlot.avatar_one_stop_production import recover_hq_downloads,record_hq_usage
    from types import SimpleNamespace
    case=tmp_path/'segment_001'
    case.mkdir()
    (case/'ledger.json').write_text(json.dumps({'task_id':'existing-task','usage':{'consumeCoins':'398'}}),'utf-8')
    (case/'query.json').write_text(json.dumps({'status':'SUCCESS','results':[{'nodeId':'93','url':'https://original.example/file'}]}),'utf-8')
    def unavailable(*args):
        raise TimeoutError('private signed URL must not be logged')
    executor=SimpleNamespace(body=lambda v:v,SUCCESS={'SUCCESS'},download=unavailable)
    assert recover_hq_downloads(executor,tmp_path) is False
    pending=json.loads((case/'video.mp4.recovery-pending.json').read_text('utf-8'))
    assert pending['error_class']=='TimeoutError' and pending['new_generation'] is False
    assert 'private signed' not in json.dumps(pending)
    ledger={'plan':{'reserve_coins':362}}
    saved=[]
    record_hq_usage(ledger,tmp_path,lambda:saved.append(True))
    assert saved and ledger['known_usage_rh_coins']==398
    assert ledger['task_ids']==['existing-task'] and ledger['unconfirmed_segments']==0


def test_local_media_reads_private_queue_result_without_leaking_paths(tmp_path):
    from backlot.production_queue import ProductionQueue
    from backlot.avatar_one_stop_production import completed_media
    from backlot.avatar_one_stop_policy import digest
    project = tmp_path/'projects/studio-test'
    project.mkdir(parents=True)
    (project/'project.json').write_text('{"title":"new actual output"}', 'utf-8')
    render_id = 'chromatic-suite-'+'a'*20
    directory = project/'renders'/render_id
    directory.mkdir(parents=True)
    video, qa = directory/'chromatic-six-11-full.mp4', directory/'qa.json'
    video.write_bytes(b'new-video-body')
    qa.write_text('{"technical":"pass"}', 'utf-8')
    queue = ProductionQueue(tmp_path/'queue.sqlite3', project.parent)
    frozen = {'contract':'motion-replay-chromatic-suite-production-v1','template_id':'chromatic-six-11',
              'project_id':project.name,'render_id':render_id,'request_sha256':'f'*64}
    (directory/'result.json').write_text(json.dumps({'output_sha256':digest(video),
        'qa_sha256':digest(qa),'request_sha256':frozen['request_sha256']}),'utf-8')
    job = queue.submit(project_id=project.name, kind='studio_investment_recompose', source='codex',
        priority='normal', parent_job_id='new-render', frozen_request=frozen, idempotency_key='private-media-test', start_paused=True)
    queue.claim_local_recompose(job['job_id'], 'test-worker')
    public = queue.finish(job['job_id'], 'test-worker', status='completed', stage='done', result={
        'output_path':str(video),'qa_report':str(qa),'output_sha256':digest(video),'work_id':'real-work'})
    assert public['result']['output_path'] == '[LOCAL_PATH]'
    result = completed_media(queue,job['job_id'],digest(video))
    assert result['output_path']==str(video) and result['qa_report']==str(qa)
    video.write_bytes(b'tampered-result')
    with pytest.raises(WorkError, match='文件身份不一致'):
        completed_media(queue,job['job_id'])


def test_local_finisher_remains_bound_to_parent_windows_and_badge(tmp_path):
    from copy import deepcopy
    from types import SimpleNamespace
    from backlot.avatar_one_stop_finish import CONTRACT, validate
    from backlot.avatar_one_stop_policy import digest, fingerprint
    project = tmp_path/('studio-'+'a'*16)
    (project/'artifacts').mkdir(parents=True)
    source, font = project/'parent.mp4', project/'font.ttf'
    source.write_bytes(b'actual-parent-body')
    font.write_bytes(b'original-template-font')
    windows = [{'from':0,'to':204},{'from':1800,'to':1994}]
    parent = {'status':'completed','project_id':project.name,
        'frozen_request':{'request_sha256':'f'*64,'contract':'motion-replay-chromatic-suite-production-v1',
            'template_id':'chromatic-six-11','props':{'font':'font.ttf','durationInFrames':1994,'presenters':windows},
            'origins':{'font.ttf':{'sha256':digest(font)}}},'result':{'output_sha256':digest(source)}}
    queue = SimpleNamespace(projects_root=tmp_path,get=lambda identity,**kwargs:parent)
    original = {'contract':CONTRACT,'project_id':project.name,'source_job_id':'original-parent',
        'source_request_sha256':'f'*64,'source_relative':source.name,'source_sha256':digest(source),
        'font_relative':font.name,'font_sha256':digest(font),'fps':30,'frames':1994,'windows':windows,
        'badge':{'x':774,'y':1557,'width':231,'height':48,'text':'AI数字人','background':'#FFAD8F','ink':'#102C43'},
        'title':'new person','publication':False,'new_provider_calls':False}

    def frozen(core):
        request = {**core,'request_sha256':fingerprint(core),'render_id':'one-stop-finish-'+fingerprint(core)[:20]}
        (project/'artifacts'/(request['render_id']+'.json')).write_text(json.dumps(request),'utf-8')
        return request

    assert validate(queue,frozen(original))==project
    altered = deepcopy(original)
    altered['windows'][0]['to'] += 1
    with pytest.raises(WorkError,match='范围、时钟'):
        validate(queue,frozen(altered))
    altered = deepcopy(original)
    altered['badge']['x'] = 10
    with pytest.raises(WorkError,match='范围、时钟'):
        validate(queue,frozen(altered))
