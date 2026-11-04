"""Independent behavior checks. Run from Haike_video with python -m pytest."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from backlot import motion_replay as replay
from backlot.motion_replay_numbered_06_11 import prepare as direct_prepare

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / 'Haike_video/config/motion-replay/numbered-06-11.json'
DOCUMENT = json.loads(REGISTRY.read_text(encoding='utf-8'))
TEMPLATES = [t for t in DOCUMENT['templates'] if t['version']=='1.1.0']


def test_registry_and_event_bindings():
    replay.validate_registry(DOCUMENT)
    assert len(TEMPLATES) == 6
    for template in TEMPLATES:
        assert len(template['actions']) == 4
        assert len(template['timeline']['events']) > 10
        assert template['timeline']['mode'] == 'source_locked'
        assert template['timeline']['retiming']['supported'] is False
        for action in template['actions']:
            assert 'ReplayNumbered' in action['implementation']['wrapper']


@pytest.mark.parametrize('template', TEMPLATES, ids=lambda t:t['template_id'])
def test_default_preserves_formal_profile_and_blocks(template):
    result = replay.prepare(template['template_id'], '1.1.0')
    assert result['status'] == 'blocked'
    assert result['profile'] == 'formal'
    assert result['render_profile']['width'] == 1080
    assert result['render_profile']['silent'] is False
    assert result['blockers'] and result['input_props'] is None
    assert result['submitted'] is False


@pytest.mark.parametrize('template', TEMPLATES, ids=lambda t:t['template_id'])
def test_real_reference_inputs_and_actions(template):
    actions = [a['id'] for a in template['actions']]
    result = replay.prepare(template['template_id'], '1.1.0',
        {'profile':'historical_preview', 'action_ids':actions})
    assert result['status'] == 'prepared'
    assert result['local_verification']['historical_manifest_entries'] == 301
    props = result['input_props']
    assert props['replay']['actionIds'] == actions
    assert props['episode']['durationInFrames'] == 720
    assert props['episode']['fontFamily'] == 'Haike Six Video'
    assert props['episode'].get('materialClips') or props['episode'].get('materialSlots') or props['episode'].get('videoSlots')
    assert result['render_profile']['silent'] is True
    assert not result['queue']['supported']


@pytest.mark.parametrize('payload', [
    {'action_ids':[]}, {'action_ids':'wrong'}, {'action_ids':[None]},
    {'profile':None}, {'profile':True}, {'profile':'hd'},
    {'text':'new wording'}, {'episode':{}}, {'durationInFrames':900},
    {'semantic_anchors':{'answer':123}}, {'audio':'new.wav'}, {'width':1080},
    {'inputs':{'caption':'new'}},
])
def test_unsupported_input_and_capability_rejected(payload):
    with pytest.raises(replay.ReplayError):
        replay.prepare('chromatic-06', '1.1.0', payload)


def test_action_subsets_and_order_rejected_for_every_template():
    for template in TEMPLATES:
        actions = [a['id'] for a in template['actions']]
        for requested in [actions[1:], actions[::-1], actions+[actions[0]], ['unknown']]:
            with pytest.raises(replay.ReplayError):
                replay.prepare(template['template_id'], '1.1.0', {'action_ids':requested})


def test_version_and_identity_drift_rejected():
    for version in ['latest','1.1.1','1.1.0-candidate.1']:
        with pytest.raises(replay.ReplayError):
            replay.prepare('chromatic-06', version)
    with pytest.raises(replay.ReplayError):
        replay.prepare('chromatic-06', '1.1.0', {'template_id':'chromatic-07'})


def test_source_drift_rejected_before_input_preparation(tmp_path):
    template = deepcopy(TEMPLATES[0])
    source = template['sources'][0]
    target = tmp_path / source['path']
    target.parent.mkdir(parents=True)
    target.write_text('deliberate source drift', encoding='utf-8')
    with pytest.raises(replay.ReplayError, match='来源已变化'):
        direct_prepare(template, {'profile':'historical_preview'}, workspace=tmp_path)


def test_missing_private_media_never_claims_prepared(tmp_path):
    template = TEMPLATES[0]
    for source in template['sources']:
        dest = tmp_path / source['path']; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source['path'], dest)
    with pytest.raises(replay.ReplayError):
        direct_prepare(template, {'profile':'historical_preview'}, workspace=tmp_path)


def test_adapter_rejects_contract_action_binding_tamper():
    template = deepcopy(TEMPLATES[0])
    template['actions'][0]['id'] = 'forged'
    with pytest.raises(replay.ReplayError, match='合同与可调用包装不一致'):
        direct_prepare(template, {}, workspace=ROOT)


def controlled_inputs(template):
    number = int(template['template_id'].split('-')[-1])
    window = 'a' if number<8 else 'b' if number<10 else 'c'
    manifest = json.loads((ROOT/'.local/chromatic-six-video-batch/assets-manifest.json').read_text('utf-8'))
    assets = [dict(path=a['path'],sha256=a['sha256'],
                   kind='font' if a['path'].endswith('.ttf') else 'video',
                   provenance='Reuse original authorized local reference assets, original ancestry retained')
              for a in manifest if a['path'].startswith(f'assets/{window}/')]
    baseline = json.loads((ROOT/template['local_reference']['episode_path']).read_text('utf-8'))
    captions = deepcopy(baseline['captions'])
    captions[0]['text']='本期字幕测试'
    captions[0]['lines']=['本期字幕测试']
    key = 'materialClips' if number<8 else 'materialSlots' if number<10 else 'videoSlots'
    material=deepcopy(baseline[key])
    # Each source component actually consumes the changed video slot. 07's
    # separate tracked annotation shot stays locked; another sticker can change.
    if number<8:
        material[1 if number==6 else 0]['src']=f'/assets/{window}/dog.mp4'
    elif number==8:
        material['08-intro-0']['src']='/assets/b/dog.mp4'
    elif number==9:
        material['09-desk-b']['src']='/assets/b/robot.mp4'
    elif number==10:
        material['impact'][0]['src']='/assets/c/robot.mp4'
    else:
        material['route-0'][0]['src']='/assets/c/robot.mp4'
    return {'episode':{key:material,'captions':captions},'assets':assets,
            'public_root':'.local/chromatic-six-video-batch'}


@pytest.mark.parametrize('template', TEMPLATES, ids=lambda t:t['template_id'])
def test_existing_consumed_slots_remain_replaceable(template):
    inputs=controlled_inputs(template)
    result = replay.prepare(template['template_id'],'1.1.0',
        {'profile':'controlled_preview','inputs':inputs})
    assert result['status']=='prepared'
    assert result['input_props']['episode']['captions'][0]['text']=='本期字幕测试'
    for key,value in inputs['episode'].items():
        assert result['input_props']['episode'][key]==value
    assert result['assets']['verified_assets']
    assert result['output_validation']['status']=='pending'
    assert result['render_profile']['durationInFrames']==720


@pytest.mark.parametrize('mutate', [
    lambda v:v['episode'].update({'segments':[]}),
    lambda v:v['episode']['captions'][0].update({'to':721}),
    lambda v:v['episode']['captions'][0].update({'text':'x'*31}),
    lambda v:v['episode']['materialClips'][0].update({'starts':[0,0,0,1000]}),
    lambda v:v['episode']['materialClips'][0].update({'src':'https://external/video.mp4'}),
    lambda v:v['episode']['materialClips'][2].update({'objectPosition':'20% 20%'}),
    lambda v:v['assets'][0].update({'sha256':'0'*64}),
    lambda v:v['assets'][0].update({'kind':'image'}),
    lambda v:v.update({'public_root':'../escape'}),
])
def test_replacement_rejects_unsupported_fields_ranges_identity_and_tracking(mutate):
    template=TEMPLATES[1]
    inputs=controlled_inputs(template);mutate(inputs)
    with pytest.raises(replay.ReplayError):
        replay.prepare(template['template_id'],'1.1.0',
                       {'profile':'controlled_preview','inputs':inputs})
