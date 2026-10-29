from copy import deepcopy

import pytest
from PIL import Image

from backlot import studio_motion_face_crop as m
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


def test_circle_contains_hair_and_chin_without_using_source_video_coordinates():
    boxes=[[243,401,224,224], [245,400,224,224], [242,403,226,226]]*2
    crop=m.window(boxes)
    cx,cy,r=crop['cx']*720,crop['cy']*1280,crop['h']*1280/2
    assert .47<crop['cx']<.52 and .37<crop['cy']<.42
    for x,y,w,h in boxes:
        for px,py in [(x-.1*w,y-.35*h),(x+1.1*w,y+1.15*h)]:
            assert (px-cx)**2+(py-cy)**2<r*r


def test_wide_head_window_is_recentered_without_shrinking_its_measured_content():
    boxes=[[212,302,309,309],[194,332,339,339],[239,320,324,324],
           [206,301,336,336],[215,320,323,323],[191,296,329,329],[202,298,321,321]]
    crop=m.window(boxes);cx,cy,r=crop['cx']*720,crop['cy']*1280,crop['h']*1280/2
    assert crop['cx']==.5 and r<=min(cx,720-cx,cy,1280-cy)
    for x,y,w,h in boxes:
        for px,py in [(x-.1*w,y-.35*h),(x+1.1*w,y+1.15*h)]:
            assert (px-cx)**2+(py-cy)**2<r*r


@pytest.mark.parametrize('boxes', [
    [[250,400,200,200]]*4,
    [[250,400,200,200]]*5+[[500,500,150,150]],
    [[250,400,200,200]]*5+[[200,300,320,320]],
    [[0,10,200,200]]*7,
    [[250,400,float('nan'),200]]*7,
])
def test_unreliable_or_out_of_bounds_face_requires_adaptation(boxes):
    with pytest.raises(WorkError):m.window(boxes)


@pytest.fixture
def imported(tmp_path,monkeypatch):
    project=tmp_path/'official'; folder=project/'project/talk/clip_000';folder.mkdir(parents=True)
    for i in range(13):Image.new('RGB',m.SIZE,(i,50,100)).save(folder/f'f_{i+1:05}.jpg')
    avatar=tmp_path/'avatar.mp4';avatar.write_bytes(b'owned identity fixture')
    tools={}
    for key in ['helper','package']:
        p=tmp_path/key;p.write_bytes(key.encode());tools[key]=m.binding(p)
    monkeypatch.setattr(m,'detector',lambda:None)
    monkeypatch.setattr(m,'faces',lambda p,d:[[243,401,224,224]])
    return project,m.binding(avatar),tools,tmp_path/'calibration'


def test_whole_import_sampling_and_new_person_binding(imported):
    project,avatar,tools,output=imported
    row=m.calibrate(project,avatar,tools,output)
    proof=m.validate(row,avatar,tools,m.read_json(m.checked(row))['crop'],project)
    assert len(proof['samples'])==7
    assert proof['samples'][0]['source']['path'].endswith('f_00001.jpg')
    assert proof['samples'][-1]['source']['path'].endswith('f_00013.jpg')
    other=deepcopy(tools);other['helper']={**tools['helper'],'sha256':'changed'}
    with pytest.raises(WorkError,match='重新校准'):m.validate(row,avatar,other,proof['crop'])
    changed=deepcopy(proof['crop']);changed['cy']+=.1
    with pytest.raises(WorkError,match='重新校准'):m.validate(row,avatar,tools,changed)
    Image.new('RGB',m.SIZE,'red').save(project/'project/talk/clip_000/f_00001.jpg')
    with pytest.raises(WorkError,match='已变化'):m.validate(row,avatar,tools,proof['crop'],project)


def test_reimport_must_have_identical_pixels_even_with_same_dimensions(imported,tmp_path):
    project,avatar,tools,output=imported
    row=m.calibrate(project,avatar,tools,output);crop=m.read_json(m.checked(row))['crop']
    other=tmp_path/'different-import';folder=other/'project/talk/clip_000';folder.mkdir(parents=True)
    for i in range(13):Image.new('RGB',m.SIZE,'red').save(folder/f'f_{i+1:05}.jpg')
    with pytest.raises(WorkError,match='导入像素'):m.validate(row,avatar,tools,crop,other)


def test_no_largest_face_fallback_for_multi_person_frame(imported,monkeypatch):
    project,avatar,tools,output=imported
    monkeypatch.setattr(m,'faces',lambda p,d:[[243,401,224,224],[50,500,80,80]])
    with pytest.raises(WorkError,match='多张脸'):m.calibrate(project,avatar,tools,output)


def test_unicode_model_loader_uses_bundled_detector():
    assert not m.detector().empty()
