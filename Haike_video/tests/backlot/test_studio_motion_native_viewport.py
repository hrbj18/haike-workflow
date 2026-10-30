"""The reviewed pixels must describe exactly the exported native 4:5 window."""
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from backlot import studio_motion_native_viewport as viewport
from backlot.work_catalog import WorkError, sha


def bind(path): return {'path': str(path.resolve()), 'sha256': sha(path)}


@pytest.fixture
def images(tmp_path):
    sources=[]
    for i in range(2):
        path=tmp_path/f'{i}.png';image=Image.new('RGB',(1080,1920),'#121e2a');draw=ImageDraw.Draw(image)
        draw.rectangle((0,0,1079,249),fill='#a41e2a')
        draw.rectangle((0,250+i*20,1079,300+i*20),fill='#12ad2a');image.save(path);sources.append(bind(path))
    pairs=viewport.crop_images(sources,tmp_path/'cropped')
    review={'status':'pass','layout':deepcopy(viewport.CONSOLE_45),'source_preview_sha256':'preview-one','images':pairs}
    return sources,review


def test_reviewed_native_pixels_are_the_exact_frozen_window(images):
    sources,review=images
    assert viewport.validate_review(review,sources,'preview-one')==viewport.CONSOLE_45
    image=Image.open(review['images'][0]['image']['path'])
    assert image.size==(1080,1350) and image.getpixel((0,0))==(18,173,42)
    assert viewport.filtergraph(viewport.CONSOLE_45)=='crop=1080:1350:0:250,scale=1440:1800:flags=lanczos'


def test_other_crop_cannot_be_approved_by_merely_updating_its_sha(images):
    sources,review=images;path=review['images'][0]['image']['path']
    Image.open(sources[0]['path']).crop((0,230,1080,1580)).save(path)
    review['images'][0]['image']=bind(Path(path))
    with pytest.raises(WorkError,match='像素不一致'):viewport.validate_review(review,sources,'preview-one')


@pytest.mark.parametrize('edit',[
    lambda r:r.update(source_preview_sha256='another-preview'),
    lambda r:r['layout']['rect'].__setitem__(1,230),
    lambda r:r['layout']['rect'].__setitem__(0,False),
    lambda r:r['images'].pop(),
    lambda r:r['images'].__setitem__(1,deepcopy(r['images'][0])),
])
def test_wrong_version_geometry_and_missing_or_duplicate_states_are_rejected(images,edit):
    sources,review=images;edit(review)
    with pytest.raises(WorkError):viewport.validate_review(review,sources,'preview-one')


def test_ffmpeg_uses_the_same_window_as_the_reviewed_pillow_pixels(images,tmp_path):
    import subprocess
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff,_=resolve_ffmpeg_pair();sources,review=images;output=tmp_path/'exported.png'
    result=subprocess.run([ff,'-nostdin','-v','error','-y','-i',sources[0]['path'],
                           '-vf',viewport.filtergraph(review['layout']),'-frames:v','1',str(output)],capture_output=True)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    with Image.open(output) as encoded:
        assert encoded.size==(1440,1800)
        assert encoded.getpixel((720,25))[:3]==(18,173,42)
        assert encoded.getpixel((720,1750))[:3]==(18,30,42)
