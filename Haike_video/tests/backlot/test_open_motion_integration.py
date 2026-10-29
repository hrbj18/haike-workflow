"""Frame-window and source safety for the upstream-effect extension."""
from copy import deepcopy
import pytest
from backlot import studio_hum_production as hum
from backlot.work_catalog import WorkError
from test_studio_hum_production import sample

def open_value(sample):
    value=deepcopy(sample['value'])
    value['props']['visualStyle']='carnival'
    value['shotPlan']=[{'id':f'f{i}','module':'focus','title':'真实体验','mediaId':f'm{i}','weight':1,'motion':'gl-circle'} for i in range(4)]
    return value

@pytest.mark.parametrize('style',['darkroom','carnival'])
def test_open_styles_preserve_voice_clock_and_every_source(sample,style):
    value=open_value(sample);value['props']['visualStyle']=style
    checked=hum.preflight(value)
    assert checked['props']['durationFrames']==608
    assert {s['mediaId'] for s in checked['props']['scenes']}=={'m0','m1','m2','m3'}

def test_old_wall_cannot_hide_unreviewed_full_playback(sample):
    sample['value']['props']['visualStyle']='carnival'
    with pytest.raises(WorkError,match='旧wall'):
        hum.preflight(sample['value'])

def test_minimum_effect_window_keeps_readable_hold():
    plan=[{'module':'focus','motion':'mondrian','weight':1},{'module':'focus','motion':'gl-circle','weight':1}]
    scenes=hum.plan_scenes(plan,134)
    assert [s['frames'] for s in scenes]==[80,54]
    with pytest.raises(WorkError,match='口播太短'):
        hum.plan_scenes(plan,133)

def test_pixel_effect_requires_decoded_media(sample):
    value=open_value(sample);value['shotPlan'].append({'id':'invalid','module':'statement','title':'你好','motion':'pixi-shock','weight':1})
    with pytest.raises(WorkError,match='GL/Pixi'):
        hum.preflight(value)
