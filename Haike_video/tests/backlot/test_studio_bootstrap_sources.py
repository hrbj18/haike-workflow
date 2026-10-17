"""A configured material source works without granting unrelated provider rights."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from backlot.studio import Studio, atomic_private
from backlot.studio_storyboard import (
    CHAT_MODEL, TrialRelay, frozen_chat_model, make_plan, network_sources,
    options, produce, resolve_scene, selected_chat_model, status,
)
from backlot.studio_network_materials import MaterialSearchError
from backlot.work_catalog import WorkError


@pytest.fixture
def case(tmp_path):
    studio = Studio(tmp_path / 'projects')
    config = {'analysis_mode': 'relay', 'api_key': 'synthetic-private-test-value', 'base_url': 'https://provider.example/v1',
              'chat_model': 'configured-vision-model', 'network_sources': ['pexels']}
    atomic_private(studio.private / 'studio-ai/relay.json', config)
    draft = studio.save_draft({'template_id': 'avatar-deepblue-n1-v1', 'title': '配置验收',
                              'text': '第一句。第二句。', 'input': {'soundMode': 'audio', 'network_materials_enabled': True}})
    cues = [{'text': '第一句。', 'startMs': 0, 'endMs': 1400}, {'text': '第二句。', 'startMs': 1600, 'endMs': 3000}]
    raw = {'scenes': [dict(from_cue=i, to_cue=i, script_start=i*4, script_end=(i+1)*4,
                           label='素材画面', asset_id='', query='电脑 | computer',
                           illustration_prompt='', reason='适合口播的示意画面') for i in range(2)]}
    return SimpleNamespace(studio=studio, config=config, draft=draft, cues=cues, raw=raw, root=tmp_path)


def test_explicit_pexels_configuration_keeps_no_illustration_rule(case):
    policy = options(case.studio, case.draft)
    assert policy['_network_sources'] == ['pexels'] and policy['skip_douyin'] is True
    assert policy['allow_images'] is False and policy['max_images'] == 0
    calls = []
    def unexpected(_):
        pytest.fail('Unselected provider must not be called or authorized')
    def pexels(_):
        calls.append('pexels')
        return {'id': 'real-selected-source'}
    sources = SimpleNamespace(douyin=unexpected, pexels=pexels, illustration=unexpected)
    assert resolve_scene({}, policy, sources)['id'] == 'real-selected-source'
    assert calls == ['pexels']
    assert not case.config.get('douyin_commercial_authorized')


def test_empty_explicit_source_stops_without_other_provider_or_graphic_fallback(case):
    def unexpected(_):
        pytest.fail('No silent provider or image fallback')
    sources = SimpleNamespace(douyin=unexpected, pexels=lambda _: None, illustration=unexpected)
    with pytest.raises(MaterialSearchError, match='未找到适合') as error:
        resolve_scene({}, options(case.studio, case.draft), sources)
    assert error.value.status == 'no_materials'


@pytest.mark.parametrize('value', [[], ['other'], ['pexels', 'pexels'], ['pexels', True], 'pexels', {}])
def test_invalid_source_configuration_is_visible(case, value):
    atomic_private(case.studio.private / 'studio-ai/relay.json', {**case.config, 'network_sources': value})
    with pytest.raises(WorkError, match='来源配置无效'):
        options(case.studio, case.draft)


def test_explicit_source_does_not_bypass_live_login_preflight(case, monkeypatch):
    def no_login(_):
        raise MaterialSearchError('请先恢复素材账号登录', 'login_required')
    monkeypatch.setattr('backlot.studio_network_materials.preflight', no_login)
    monkeypatch.setattr('backlot.studio_storyboard.make_plan', lambda *a: pytest.fail('No model call before login'))
    with pytest.raises(MaterialSearchError, match='恢复素材账号'):
        produce(case.studio, case.draft, case.root / 'render', case.cues, 3.2, None)


def test_configured_chat_model_is_used_and_frozen_per_job(case):
    payloads = []
    def transport(payload, image):
        payloads.append(payload)
        return {'choices': [{'message': {'content': json.dumps(case.raw, ensure_ascii=False)}}]}
    relay = TrialRelay(case.studio, case.root / 'calls', transport)
    plan = make_plan(case.studio, case.draft, case.cues, 3.2, relay)
    assert plan['model'] == payloads[0]['model'] == case.config['chat_model']
    atomic_private(case.studio.private / 'studio-ai/relay.json', {**case.config, 'chat_model': 'another-model'})
    assert frozen_chat_model(case.studio, relay.folder) == case.config['chat_model']
    assert frozen_chat_model(case.studio, case.root / 'new-job') == 'another-model'
    assert selected_chat_model(case.studio) == 'another-model'


def test_legacy_receipts_keep_the_observed_chat_model(case):
    folder = case.root / 'legacy-calls'
    atomic_private(folder / 'original.json', {'model': CHAT_MODEL, 'image': False, 'status': 'unknown'})
    assert frozen_chat_model(case.studio, folder) == CHAT_MODEL


def test_source_choice_is_frozen_when_resuming_a_partial_plan(case, monkeypatch):
    image = io.BytesIO()
    Image.new('RGB', (300, 300), 'navy').save(image, format='PNG')
    asset = case.studio.save_asset(case.draft['id'], 'synthetic.png', 'image', image.getvalue())
    from backlot.studio_storyboard import validate_plan
    plan = {'scenes': validate_plan(case.raw, case.draft, case.cues, 3.2), 'duration': 3.2}
    monkeypatch.setattr('backlot.studio_network_materials.preflight', lambda _: {'account_id': 3})
    monkeypatch.setattr('backlot.studio_storyboard.make_plan', lambda *args: deepcopy(plan))
    calls = []
    class Sources:
        def __init__(self, *args): pass
        def douyin(self, _): pytest.fail('Resume must retain explicit Pexels source')
        def pexels(self, scene):
            calls.append(scene['id'])
            if scene['id'] == 'scene-2' and calls.count('scene-2') == 1:
                raise WorkError('本段暂不可用', 'unavailable')
            return {**asset, 'provenance': {'source': 'pexels'}}
    monkeypatch.setattr('backlot.studio_storyboard.Sources', Sources)
    folder = case.root / 'render'
    with pytest.raises(WorkError, match='暂不可用'):
        produce(case.studio, case.draft, folder, case.cues, 3.2, None)
    assert json.loads((folder / 'storyboard.json').read_text(encoding='utf-8'))['network_sources'] == ['pexels']
    atomic_private(case.studio.private / 'studio-ai/relay.json', {**case.config, 'network_sources': ['douyin', 'pexels']})
    assert produce(case.studio, case.draft, folder, case.cues, 3.2, None)['status'] == 'ready'
    assert calls == ['scene-1', 'scene-2', 'scene-2']


def test_public_configuration_status_never_contains_private_key(case):
    projected = status(case.studio)
    assert projected['chat_model'] == case.config['chat_model']
    assert projected['network_sources'] == ['pexels']
    assert case.config['api_key'] not in json.dumps(projected)
