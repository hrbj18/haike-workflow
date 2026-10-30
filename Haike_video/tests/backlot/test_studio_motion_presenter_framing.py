import subprocess
from copy import deepcopy

import pytest
from PIL import Image,ImageDraw

from backlot import studio_motion_presenter_framing as f
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


@pytest.mark.parametrize('size,box',[
    ((720,900),[243,212,224,224]),
    ((720,404),[85,100,65,65]),
    ((720,1800),[250,550,200,200]),
])
def test_maximal_portrait_roi_follows_measured_person(size,box):
    g=f.geometry(size,[box]*6);x,y,w,h=g['rect'];bx,by,bw,bh=box
    assert x<=bx-.1*bw and bx+1.1*bw<=x+w
    assert y<=by-.35*bh and by+1.1*bh<=y+h
    assert abs(w/h-9/16)<.004 and (w==size[0] or h==size[1])


@pytest.mark.parametrize('boxes',[
    [[50,200,150,150]]*3+[[530,200,150,150]]*3,
    [[250,200,150,150]]*4,
    [[0,10,200,200]]*6,
])
def test_unsafe_roi_cannot_silently_cut_or_select_people(boxes):
    with pytest.raises(WorkError):f.geometry((720,900),boxes)


def test_closeup_keeps_whole_head_with_a_measured_contain_layout():
    # Measured six-frame closeup: a 506-wide cover crop cannot hold the head.
    boxes=[[112,253,478,478],[108,239,475,475],[113,233,493,493],
           [95,250,490,490],[115,279,495,495],[89,224,475,475]]
    g=f.geometry((720,900),boxes)
    assert g['axis']=='contain'
    width,height=g['foreground_size'];ox,oy=g['foreground_offset']
    assert 0<=ox and ox+width<=720 and 0<=oy and oy+height<=1280
    corners=[]
    for x,y,w,h in boxes:
        for px,py in [(x-.1*w,y-.35*h),(x+1.1*w,y+1.15*h)]:
            corners.append((ox+px*width/720,oy+py*height/900))
    left=min(x for x,y in corners);right=max(x for x,y in corners)
    top=min(y for x,y in corners);bottom=max(y for x,y in corners)
    import math
    assert math.hypot(right-left,bottom-top)<=642


@pytest.mark.parametrize('size,box',[
    ((720,900),[243,212,224,224]),
    ((720,1800),[250,550,200,200]),
])
def test_real_ffmpeg_reframes_without_black_padding(tmp_path,size,box):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ff,_=resolve_ffmpeg_pair();source=tmp_path/'full.png';output=tmp_path/'portrait.png'
    image=Image.new('RGB',size,'#3a759c');draw=ImageDraw.Draw(image)
    draw.rectangle((box[0],box[1],box[0]+box[2],box[1]+box[3]),fill='#f5bc82');image.save(source)
    vf=f.filtergraph(f.geometry(size,[box]*6))
    p=subprocess.run([ff,'-nostdin','-v','error','-y','-i',str(source),'-vf',vf,
                      '-frames:v','1',str(output)],capture_output=True)
    assert p.returncode==0,p.stderr.decode(errors='replace')
    with Image.open(output) as im:
        assert im.size==(720,1280)
        for point in [(0,0),(719,0),(0,1279),(719,1279)]:assert im.getpixel(point)[:3]==(58,117,156)


def test_framing_receipt_rejects_another_person_or_changed_roi(tmp_path):
    avatar=tmp_path/'avatar.mp4';avatar.write_bytes(b'owned identity fixture')
    ff=tmp_path/'ffmpeg';ff.write_bytes(b'fixture tool identity')
    rows=[]
    for i in range(6):
        path=tmp_path/f'{i}.jpg';Image.new('RGB',(720,900),'#456789').save(path)
        diag=tmp_path/f'{i}-framed.jpg';Image.new('RGB',(720,1280),'#456789').save(diag)
        rows.append({'at':i,'image':f.binding(path),'diagnostic':f.binding(diag),'face':[243,212,224,224]})
    p={'schema':f.SCHEMA,'adapter_sha256':f.sha(f.__file__),'avatar_sha256':f.sha(avatar),
       'ffmpeg':f.binding(ff),'geometry':f.geometry((720,900),[s['face'] for s in rows]),'samples':rows}
    target=tmp_path/'framing.json';atomic_private(target,p)
    f.validate(f.binding(target),f.binding(avatar),f.binding(ff))
    other=tmp_path/'other.mp4';other.write_bytes(b'other person')
    with pytest.raises(WorkError,match='重新提取'):f.validate(f.binding(target),f.binding(other),f.binding(ff))
    p['geometry']['left_ratio']=.5;atomic_private(target,p)
    with pytest.raises(WorkError,match='测量不符'):f.validate(f.binding(target),f.binding(avatar),f.binding(ff))
