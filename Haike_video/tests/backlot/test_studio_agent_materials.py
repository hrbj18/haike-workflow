"""The working Agent supplies observed decisions; no model API is contacted."""
from copy import deepcopy
import io
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backlot.studio import Studio, atomic_private
from backlot import studio_agent_materials as agent
from backlot.studio_network_materials import MaterialSearchError, public_result
from backlot.studio_storyboard import TrialRelay, options, produce, status
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def case(tmp_path, monkeypatch):
    studio = Studio(tmp_path / 'projects')
    atomic_private(studio.private / 'studio-ai/relay.json', {'analysis_mode': 'agent', 'network_sources': ['pexels']})
    draft = studio.save_draft({'template_id': 'avatar-deepblue-n1-v1', 'title': 'Agent流程测试',
        'text': '请用我的完整录音制作视频。', 'input': {'soundMode': 'audio', 'network_materials_enabled': True}})
    content = io.BytesIO(); Image.new('RGB', (640, 480), 'navy').save(content, format='PNG')
    asset = studio.save_asset(draft['id'], 'observed.png', 'image', content.getvalue())
    cues = [{'text': '第一句。', 'startMs': 0, 'endMs': 1400}, {'text': '第二句。', 'startMs': 1600, 'endMs': 3000}]
    folder = agent.directory(studio, draft)
    monkeypatch.setattr('backlot.studio_network_materials.preflight', lambda _: {'account_id': 3})
    monkeypatch.setattr(TrialRelay, 'call', lambda *_a, **_kw: pytest.fail('Agent workflow called relay'))
    return SimpleNamespace(studio=studio, draft=draft, asset=asset, cues=cues, folder=folder)


def wait_for_plan(case):
    with pytest.raises(MaterialSearchError) as stopped:
        produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('not a supplier stage'))
    assert stopped.value.status == 'awaiting_agent'
    return agent.context(case.studio, case.draft)


def payload(case, *, existing=True):
    ctx = agent.context(case.studio, case.draft)
    raw = {'draft_revision': case.draft['revision'], 'clock_sha256': ctx['clock_sha256'],
           'scenes': [dict(from_cue=i, to_cue=i, script_start=i*4, script_end=(i+1)*4,
                label='已观察画面', asset_id=case.asset['id'] if existing else '', query='电脑 | computer',
                illustration_prompt='', reason='代表帧与本段录音描述一致') for i in range(2)]}
    if existing:
        raw['materials'] = [{'asset_id': case.asset['id'], 'sha256': sha(case.studio.asset(case.asset['id'], case.draft['id'])),
            'source': 'pexels', 'source_url': 'https://www.pexels.com/video/computer-123/',
            'rights_confirmed': True, 'observed_frames': [0], 'reason': '已查看上传图片，显示录音所述的电脑画面'}]
    return raw


def test_default_agent_does_not_require_a_relay_key(case):
    assert status(case.studio)['analysis_mode'] == 'agent'
    assert status(case.studio)['configured'] is False
    assert options(case.studio, case.draft)['_analysis_mode'] == 'agent'
    assert options(case.studio, case.draft)['allow_images'] is False


def test_full_recording_uses_real_asr_not_user_one_sentence_instruction(case):
    ctx = wait_for_plan(case)
    assert ctx['script'] == '第一句。第二句。' and ctx['script'] != case.draft['text']
    assert ctx['cues'] == case.cues
    assert ctx['status'] == 'needs_plan'
    assert public_result(case.folder, case.draft)['status'] == 'awaiting_agent'


def test_reviewed_uploaded_footage_compiles_on_original_clock_without_llm(case):
    wait_for_plan(case)
    original = case.studio.draft(case.draft['id'])
    accepted = agent.apply(case.studio, case.draft, payload(case))
    assert accepted['next'] == 'resume_original_job'
    plan = produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('no search needed'))
    assert plan['model'] == 'current-agent' and plan['status'] == 'ready'
    assert [(s['start'], s['end']) for s in plan['scenes']] == [(0, 1.6), (1.6, 3.2)]
    assert all(s['asset']['provenance']['reviewed_by'] == 'current-agent' for s in plan['scenes'])
    assert case.studio.draft(case.draft['id']) == original
    assert agent.context(case.studio, case.draft)['status'] == 'ready'
    assert produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('resume repeated search')) == plan


@pytest.mark.parametrize('mutation', ['revision', 'clock', 'asset_sha', 'reason', 'source_url', 'coverage'])
def test_stale_or_unobserved_agent_results_are_rejected(case, mutation):
    wait_for_plan(case); data = payload(case)
    if mutation == 'revision': data['draft_revision'] += 1
    if mutation == 'clock': data['clock_sha256'] = 'f' * 64
    if mutation == 'asset_sha': data['materials'][0]['sha256'] = 'f' * 64
    if mutation == 'reason': data['materials'][0]['reason'] = ''
    if mutation == 'source_url': data['materials'][0]['source_url'] = 'https://example.invalid/private?token=secret'
    if mutation == 'coverage': data['scenes'][0]['from_cue'] = 1
    with pytest.raises(WorkError): agent.apply(case.studio, case.draft, data)
    assert not (case.folder / 'agent-analysis.json').exists()


def test_context_and_apply_http_keep_revision_and_original_receipt(case):
    from backlot.studio_api import router
    app = FastAPI(); app.state.studio = case.studio; app.include_router(router)
    client = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 1234))
    path = f"/api/studio/drafts/{case.draft['id']}/agent-materials"
    assert client.get(path).json()['status'] == 'pending_audio'
    wait_for_plan(case)
    response = client.post(path, json=payload(case), headers={'origin': 'http://127.0.0.1'})
    assert response.status_code == 200 and response.json()['ok']
    assert client.post(path, json={**payload(case), 'draft_revision': 9}, headers={'origin': 'http://127.0.0.1'}).status_code == 409


def test_candidate_waits_for_actual_agent_observation_then_reuses_decision(case, monkeypatch):
    wait_for_plan(case); agent.apply(case.studio, case.draft, payload(case, existing=False))
    monkeypatch.setattr('backlot.studio_render.media_probe', lambda _: {'duration': 6.0})
    monkeypatch.setattr('backlot.studio_storyboard.image_preview', lambda path, frame, at: frame.write_bytes(b'fixture-frame'))
    source = case.folder / 'candidate.mp4'; source.write_bytes(b'synthetic-video-content')
    scene = {'id': 'scene-1', 'label': '电脑画面', 'query': 'computer'}
    provenance = {'source': 'pexels', 'source_url': 'https://www.pexels.com/video/computer-123/'}
    with pytest.raises(MaterialSearchError):
        agent.review(case.studio, case.draft, case.folder, scene, source, 'pexels-123', provenance)
    ctx = agent.context(case.studio, case.draft); assert ctx['status'] == 'needs_review'
    candidate = ctx['candidates'][0]
    decision = {'candidate_id': candidate['candidate_id'], 'sha256': candidate['sha256'], 'suitable': True,
                'observed_frames': [f['at_seconds'] for f in candidate['frames']], 'reason': '已观看三个代表帧，电脑场景符合本段要求'}
    agent.apply(case.studio, case.draft, {'draft_revision': case.draft['revision'], 'clock_sha256': ctx['clock_sha256'], 'decisions': [decision]})
    assert agent.review(case.studio, case.draft, case.folder, scene, source, 'pexels-123', provenance) is True
    assert agent.frame(case.studio, case.draft, candidate['candidate_id'], 0).is_file()
    with pytest.raises(WorkError): agent.frame(case.studio, case.draft, '../outside', 0)
    with pytest.raises(WorkError):
        agent.apply(case.studio, case.draft, {'draft_revision': case.draft['revision'], 'clock_sha256': ctx['clock_sha256'],
                    'decisions': [{**decision, 'sha256': 'f'*64}]})


def test_agent_relay_guard_never_sends_even_with_an_old_saved_key(tmp_path):
    studio = Studio(tmp_path / 'projects')
    atomic_private(studio.private / 'studio-ai/relay.json', {'analysis_mode': 'agent', 'api_key': 'old-optional-key'})
    relay = TrialRelay(studio, tmp_path / 'requests', transport=lambda *_: pytest.fail('unexpected model call'))
    with pytest.raises(WorkError, match='未调用中转'):
        relay.call('storyboard', {'model': 'unused', 'messages': []})
    assert not list((tmp_path / 'requests').glob('*.json'))


def test_cached_agent_plan_rechecks_clock_and_audio_identity(case):
    wait_for_plan(case); agent.apply(case.studio, case.draft, payload(case))
    produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('no supplier'))
    with pytest.raises(WorkError, match='时钟'):
        produce(case.studio, case.draft, case.folder, case.cues, 3.4, lambda *_: pytest.fail('must stop before supplier'))
    with pytest.raises(WorkError, match='时钟'):
        produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('must stop before supplier'), audio_sha256='f'*64)


def test_agent_can_fill_an_unresolved_scene_but_not_replace_an_adopted_scene(case):
    wait_for_plan(case)
    query_only = payload(case, existing=False)
    agent.apply(case.studio, case.draft, query_only)
    # Search has not adopted a candidate. An Agent may now supply an observed
    # local upload on the same original ASR and paid intent.
    agent.apply(case.studio, case.draft, payload(case))
    plan = produce(case.studio, case.draft, case.folder, case.cues, 3.2, lambda *_: pytest.fail('no supplier'))
    assert plan['status'] == 'ready'
    changed = payload(case); changed['scenes'][0]['query'] = 'another query'
    with pytest.raises(WorkError, match='已采用'):
        agent.apply(case.studio, case.draft, changed)
