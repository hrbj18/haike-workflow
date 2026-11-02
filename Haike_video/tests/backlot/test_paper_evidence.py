from copy import deepcopy

import pytest

from backlot import paper_evidence as paper
from backlot.studio_motiongit_render import entry_parameters
from backlot.work_catalog import WorkError


@pytest.fixture
def parameters():
    return {'workflow': 'motion-kit', 'timeline': {'layout': 'portrait', 'styleProfile': 'paper',
        'duration': 5, 'captions': [{'s': .5, 'e': 2.5, 'text': '本期真实句子'}],
        'segments': [{'shotId': 'opening', 'control': 'compare', 't0': 0, 't1': 5,
                      'area': dict(paper.TEXT_AREA), 'props': {}, 'presenter': 'hide'}]},
        'paperSupport': {'profile': paper.PROFILE, 'shots': [{'shotId': 'opening', 'cards': [
            {'src': name, 'sourceStart': 0, 'captionIndices': [0], 'meaning': '本期提供的实际体验场景'}
            for name in ['a.mp4', 'b.mp4']]}]}}


def test_legacy_drafts_do_not_gain_or_require_new_composition(parameters):
    old = deepcopy(parameters); old.pop('paperSupport')
    assert paper.validate(old) is None
    assert entry_parameters({'workflow': 'motion-kit', 'parameters': old}) == old


def test_project_support_is_not_forwarded_to_protected_native_entry(parameters):
    expected = deepcopy(parameters); expected.pop('paperSupport')
    assert entry_parameters({'workflow': 'motion-kit', 'parameters': parameters}) == expected
    assert 'paperSupport' in parameters


@pytest.mark.parametrize('change', ['missing', 'same-file', 'wrong-caption', 'bad-clock', 'collision', 'caption-position'])
def test_missing_or_unsafe_visual_binding_blocks_production(parameters, change):
    cards = parameters['paperSupport']['shots'][0]['cards']
    if change == 'missing': parameters['paperSupport']['shots'] = []
    if change == 'same-file': cards[1]['src'] = cards[0]['src']
    if change == 'wrong-caption': cards[0]['captionIndices'] = [4]
    if change == 'bad-clock': cards[0]['sourceStart'] = float('nan')
    if change == 'collision': parameters['timeline']['segments'][0]['area']['y'] = 820
    if change == 'caption-position': parameters['timeline']['captionPosition'] = 'top'
    with pytest.raises(WorkError): paper.validate(parameters)


def test_bound_sources_need_distinct_hashes_and_real_continuous_windows(parameters):
    assets = {name: {'path': name, 'sha256': name} for name in ['a.mp4', 'b.mp4']}
    good = lambda p: {'video': {'width': 1920}, 'duration': 8}
    assert paper.validate(parameters, assets, good)
    assets['b.mp4']['sha256'] = assets['a.mp4']['sha256']
    with pytest.raises(WorkError, match='改名'): paper.validate(parameters, assets, good)
    assets['b.mp4']['sha256'] = 'b'
    with pytest.raises(WorkError, match='区间不足'):
        paper.validate(parameters, assets, lambda p: {'video': {'width': 1920}, 'duration': 4.9})


def test_native_media_and_presenter_cannot_be_covered_by_cards(parameters):
    parameters['timeline']['segments'][0]['props']['src'] = 'native.mp4'
    with pytest.raises(WorkError, match='遮挡'): paper.validate(parameters)
    parameters['paperSupport']['shots'] = []
    assert paper.validate(parameters)


def test_preview_and_export_use_same_geometry_and_original_audio(parameters, tmp_path):
    assets = {name: {'path': str(tmp_path / name)} for name in ['a.mp4', 'b.mp4']}
    before = deepcopy(parameters)
    still = paper.command('ffmpeg', 'native.png', 'out.png', parameters, assets, at=0)
    movie = paper.command('ffmpeg', 'native.mp4', 'out.mp4', parameters, assets)
    for cmd in [still, movie]:
        graph = cmd[cmd.index('-filter_complex') + 1]
        assert 'scale=912:586' in graph and 'overlay=x=72' in graph and 'overlay=x=642' in graph
        assert '-stream_loop' not in cmd and '-loop' not in cmd
    assert '0:a:0' in movie and movie[movie.index('-c:a') + 1] == 'copy'
    assert parameters == before


def test_measured_captions_must_stay_clear_of_actual_card_motion():
    receipt = {'renderer': {'captionSamples': [{'items': [{'left': 170, 'right': 910, 'top': 1478, 'bottom': 1555}]}]}}
    paper.check_preview(receipt)
    receipt['renderer']['captionSamples'][0]['items'][0]['top'] = 1360
    with pytest.raises(WorkError, match='冲突'): paper.check_preview(receipt)


def test_display_orientation_uses_rotation_matrix_not_encoded_width(monkeypatch):
    from backlot import studio_render
    monkeypatch.setattr(studio_render, 'media_probe', lambda path: {'video': {
        'width': 1920, 'height': 1080, 'sample_aspect_ratio': '1:1',
        'side_data_list': [{'side_data_type': 'Display Matrix', 'rotation': -90}]}})
    paper.display_ratio.cache_clear()
    assert paper.display_ratio('owned-clip.mp4', 'fixture-sha') == pytest.approx(9/16)
    paper.display_ratio.cache_clear()


def test_composition_uses_owned_project_copy_not_mutable_draft_input(tmp_path):
    from backlot.studio_motiongit_render import _frozen_assets
    folder = tmp_path/'project/renders/version'
    resolved = _frozen_assets(folder, {'assets': {'a.mp4': {'path': '/mutable-draft/a.mp4', 'sha256': 'owned-sha'}}})
    assert resolved['a.mp4']['path'] == str(tmp_path/'project/assets/motiongit/a.mp4')
    assert resolved['a.mp4']['sha256'] == 'owned-sha'
