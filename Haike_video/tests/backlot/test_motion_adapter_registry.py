"""Public slot recognition is exact, conservative and independent of execution."""
from copy import deepcopy
import json

import pytest

from backlot import motion_adapter_registry as registry
from backlot import studio_motiongit as motion


TEMPLATE = 'template-03-native'
VERSION = '2.7.18-alpha.2'


def test_exact_source_version_returns_existing_project_and_preview_links():
    value = registry.resolve_adapter(TEMPLATE, VERSION)
    assert value['status'] == 'mapped'
    assert value['adapter_id'] == 'motiongit-template-03-native-v1'
    assert value['automatic_motion_conversion'] is False
    assert value['project_template']['template_id'] == 'motiongit-dark-full-v1'
    assert value['project_template']['workbench_url'] == '/motiongit?section=dark-full'
    assert len(value['groups']) == 10
    assert value['groups'][-1]['preview_endpoint'] == '/api/studio/dark-full/catalog/review/preview'
    assert (registry.ROOT.parent / value['map_file']).is_file()


@pytest.mark.parametrize('template,version', [
    (TEMPLATE, '2.7.17-alpha.3'), (TEMPLATE, '2.7.18-alpha.3'),
    ('future-template', VERSION), (TEMPLATE, 'latest'), (None, VERSION),
])
def test_unknown_or_unreviewed_version_is_never_advertised_as_direct(template, version):
    value = registry.resolve_adapter(template, version)
    assert value['status'] == 'needs_adaptation' and value['adapter_id'] is None
    assert 'field_counts' not in value and value['automatic_motion_conversion'] is False


def test_only_the_real_public_media_slot_is_direct():
    known = registry.source_slot_support(TEMPLATE, VERSION, '03-A:s02', 'comparison.items.4.media')
    assert known['category'] == 'direct' and known['field']['kind'] == 'sequence'
    assert known['field']['source']['parameter_path'] == (
        'brief.segments[].candidates["03-A:s02"].inputs.comparison.items.4.media')
    for group, path in [('03-A:s01', 'my_new_video'), ('03-A:s08', 'artifact.media'),
                        (None, 'brief.hidePerson'), (None, 'brief.width')]:
        assert registry.source_slot_support(TEMPLATE, VERSION, group, path)['category'] == 'locked'
    assert registry.source_slot_support(TEMPLATE, '2.8.0', '03-A:s02',
                                        'comparison.items.4.media')['category'] == 'needs_adaptation'


def write_map(tmp_path, value):
    path = tmp_path / 'adapter.json'
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def test_removing_public_media_slot_cannot_leave_a_direct_claim(tmp_path):
    value = deepcopy(registry.load_registry()[0])
    del value['source_contract']['groups'][0]['slots']['evidence.wall']
    write_map(tmp_path, value)
    with pytest.raises(ValueError, match='确实公开'):
        registry.load_registry(tmp_path)
    assert registry.resolve_adapter(TEMPLATE, VERSION, directory=tmp_path)['status'] == 'needs_adaptation'


def test_misreported_media_type_and_wildcard_versions_are_rejected(tmp_path):
    value = deepcopy(registry.load_registry()[0])
    wall = next(r for r in value['fields']['direct'] if r['id'] == '03-A:s01/evidence.wall')
    wall['kind'] = 'video'
    write_map(tmp_path, value)
    with pytest.raises(ValueError, match='同类型'):
        registry.load_registry(tmp_path)
    value = deepcopy(registry.load_registry()[0]); value['source']['versions'] = ['2.7.*']
    write_map(tmp_path, value)
    with pytest.raises(ValueError, match='精确版本'):
        registry.load_registry(tmp_path)


def test_project_only_features_are_not_native_direct_fields():
    value = registry.load_registry()[0]
    direct = {r['source']['input_path'] for r in value['fields']['direct']}
    assert not direct.intersection({'brief.width', 'brief.height', 'brief.hidePerson',
                                    'brief.palette', 'brief.fontFamily'})
    adapted = {r['id']: r for r in value['fields']['project_adapter']}
    assert 'props.presenter.modes[].mode' in adapted['project-presenter']['project_paths']
    assert 'props.fontAssets.body' in adapted['project-fonts']['project_paths']
    assert len([g for g in value['groups'] if g['project_group'] == 'review']) == 1
    assert 'native-hide-person' in {r['id'] for r in value['fields']['locked']}


def test_public_package_adds_only_metadata_and_preserves_unrelated_workflow(monkeypatch):
    monkeypatch.setattr(motion.subprocess, 'run', lambda *a, **k: pytest.fail('metadata executed code'))
    value = {'id': 'mg-test', 'template_id': TEMPLATE, 'version': VERSION,
             'verification': 'pending', 'runnable': False, 'path': 'private.motion',
             'personal_key': 'not-public', 'workflows': {'native': {'schema': {'type': 'object'}}}}
    previous = deepcopy(value['workflows'])
    public = motion.public_package(value)
    assert public['motion_adapter']['status'] == 'mapped'
    assert public['runnable'] is False and public['verification'] == 'pending'
    assert public['workflows'] == previous == value['workflows']
    assert 'private.motion' not in json.dumps(public) and 'not-public' not in json.dumps(public)
    unknown = motion.public_package({**value, 'template_id': 'other-template'})
    assert unknown['motion_adapter']['status'] == 'needs_adaptation'
    assert unknown['workflows'] == previous


def test_s02_cost_bindings_use_public_slots_and_keep_curve_controls_project_only():
    value = registry.load_registry()[0]
    row = next(r for r in value['fields']['project_adapter'] if r['id'] == 'project-content-s02')
    pairs = {p: b['project_path'] for b in row['bindings'] for p in b['source_input_paths']}
    for source, target in [('metrics.unitCost', 'unitCost'), ('metrics.costLabel', 'costLabel'),
                           ('metrics.alertThreshold', 'alertThreshold')]:
        assert pairs[source] == f'props.scenes[group="s02"].content.{target}'
        assert registry.source_slot_support(TEMPLATE, VERSION, '03-A:s02', source)['category'] == 'direct'
    assert 'props.scenes[group="s02"].content.countPower' in row['project_only_controls']
    assert registry.source_slot_support(TEMPLATE, VERSION, '03-A:s02',
                                        'metrics.countPower')['category'] == 'locked'
