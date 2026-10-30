"""Frame owned presenter footage before native import, without letterboxing.

The official animation stays unchanged. Measurements use full-source review
frames; the resulting 9:16 talk is then independently measured after import.
"""
import math
from pathlib import Path

from PIL import Image

from backlot.studio import atomic_private
from backlot.work_catalog import read_json, sha
from backlot.studio_motion_face_crop import binding, checked, detector, require

SCHEMA='haike.motion-presenter-framing/1'


def geometry(size, boxes):
    w,h=size
    require(type(w) is int and type(h) is int and w==720 and 320<=h<=4096,
            '人物取景代表帧尺寸变化，请重新提取')
    require(len(boxes)>=5, '人物取景至少需要五幅清晰单人脸，请更换清晰形象')
    require(all(len(b)==4 and all(type(v) in {int,float} and math.isfinite(v) for v in b)
                and min(b[2:])>=44 and b[0]>=0 and b[1]>=0
                and b[0]+b[2]<=w and b[1]+b[3]<=h for b in boxes),'人物取景检测坐标无效')
    left=min(x-.10*fw for x,y,fw,fh in boxes);right=max(x+1.10*fw for x,y,fw,fh in boxes)
    top=min(y-.35*fh for x,y,fw,fh in boxes);bottom=max(y+1.10*fh for x,y,fw,fh in boxes)
    if w/h>=9/16:
        cw=math.floor(h*9/16/2)*2;ch=h
        x=max(0,min(w-cw,(left+right-cw)/2));y=0;axis='horizontal'
    else:
        cw=w;ch=math.floor(w*16/9/2)*2
        x=0;y=max(0,min(h-ch,(top+bottom)/2-ch*.36));axis='vertical'
    x=math.floor(x/2)*2;y=math.floor(y/2)*2
    if not (x<=left and right<=x+cw and y<=top and bottom<=y+ch):
        # A legitimate closeup may not fit a 9:16 cover crop. Keep its entire
        # original frame over a softened copy, sized for the native circle's
        # hair/chin envelope. Do not invent missing head pixels or pick a face.
        bottom=max(y+1.15*fh for x,y,fw,fh in boxes)
        centers=[(x+fw/2,y+fh/2) for x,y,fw,fh in boxes]
        heights=sorted(b[3] for b in boxes);median=heights[len(heights)//2]
        require(0<=left<right<=w and 0<=top<bottom<=h
                and max(heights)/min(heights)<=1.35
                and max(x for x,y in centers)-min(x for x,y in centers)<=median*.35
                and max(y for x,y in centers)-min(y for x,y in centers)<=median*.35,
                '人物头部已超出原片或移动过大，请更换构图或人工适配')
        scale=min(640/math.hypot(right-left,bottom-top),720/w,1280/h)
        fw=max(2,math.floor(w*scale/2)*2);fh=max(2,math.floor(h*scale/2)*2)
        ox=round(max(0,min(720-fw,360-(left+right)/2*fw/w))/2)*2
        oy=round(max(0,min(1280-fh,512-(top+bottom)/2*fh/h))/2)*2
        return {'source_size':[w,h],'rect':[0,0,w,h],'axis':'contain',
                'foreground_size':[fw,fh],'foreground_offset':[ox,oy],'output':[720,1280]}
    return {'source_size':[w,h],'rect':[x,y,cw,ch],'axis':axis,
            'left_ratio':round(x/w,9),'top_ratio':round(y/h,9),'output':[720,1280]}


def filtergraph(g):
    # Expressions use the auto-rotated original video's dimensions; measurements
    # were made on its 720-wide review frame, not on a guessed encoded width.
    if g['axis']=='contain':
        w,h=g['foreground_size'];x,y=g['foreground_offset']
        return ('split=2[background][foreground];'
                '[background]crop=iw:ih/8:0:0,scale=720:1280,'
                'gblur=sigma=30[soft];'
                f'[foreground]scale={w}:{h}:flags=lanczos,setsar=1[person];'
                f'[soft][person]overlay={x}:{y},setsar=1')
    if g['axis']=='horizontal':
        crop=f"crop=trunc(ih*9/16/2)*2:ih:'max(0,min(iw-ow,round(iw*{g['left_ratio']}/2)*2))':0"
    else:
        crop=f"crop=iw:trunc(iw*16/9/2)*2:0:'max(0,min(ih-oh,round(ih*{g['top_ratio']}/2)*2))'"
    return crop+',scale=720:1280:flags=lanczos,setsar=1'


def prepare(samples, avatar, ffmpeg, output, run):
    import cv2
    import numpy as np
    require(len(samples)==6 and len({s['image']['path'] for s in samples})==6,
            '人物满幅取景需要全时段六个不同代表帧')
    source=checked(avatar);ff=checked(ffmpeg)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    require(not output.is_symlink(),'人物取景输出目录无效')
    cascade=detector();rows=[];size=None
    for sample in samples:
        with Image.open(checked(sample['image'])) as im:
            current=im.size;pixels=np.asarray(im.convert('RGB'))
        require(size is None or current==size,'人物代表帧尺寸不一致')
        size=current
        # Validate frame dimensions before running the local detector.
        require(size[0]==720 and 320<=size[1]<=4096,'人物代表帧须按原画面提取为720宽')
        found=cascade.detectMultiScale(cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY),
                                      scaleFactor=1.1,minNeighbors=6,minSize=(44,44))
        require(len(found)<=1,'人物取景检测到多张脸，不能自动选择')
        rows.append({'image':sample['image'],'at':sample['at'],
                     'face':list(map(int,found[0])) if len(found) else None})
    g=geometry(size,[s['face'] for s in rows if s['face'] is not None]);vf=filtergraph(g)
    for i,row in enumerate(rows):
        path=output/f'framed-{i}.jpg'
        run([str(ff),'-nostdin','-v','error','-y','-ss',str(row['at']),'-i',str(source),
             '-frames:v','1','-vf',vf,'-q:v','2',str(path)],90)
        with Image.open(path) as im:require(im.size==(720,1280),'满幅人物预览尺寸不正确')
        row['diagnostic']=binding(path)
    receipt={'schema':SCHEMA,'status':'measured-awaiting-source-review','avatar_sha256':sha(source),
             'ffmpeg':ffmpeg,'adapter_sha256':sha(__file__),'geometry':g,'samples':rows,
             'scope':'owned presenter reframing only; native face-circle calibration follows official import'}
    path=output/'framing.json';atomic_private(path,receipt)
    return binding(path)


def validate(row,avatar,ffmpeg):
    p=read_json(checked(row));samples=p.get('samples',[])
    require(p.get('schema')==SCHEMA and p.get('adapter_sha256')==sha(__file__)
            and p.get('avatar_sha256')==sha(checked(avatar)) and p.get('ffmpeg')==ffmpeg,
            '人物或取景适配已变化，请重新提取审核')
    require(len(samples)==6 and len({s['image']['path'] for s in samples})==6,'人物取景证据不完整')
    for s in samples:
        with Image.open(checked(s['image'])) as im:
            require(list(im.size)==p['geometry']['source_size'],'人物取景源尺寸变化')
        with Image.open(checked(s['diagnostic'])) as im:
            require(im.size==(720,1280),'人物取景预览尺寸变化')
    require(geometry(p['geometry']['source_size'],[s['face'] for s in samples if s['face'] is not None])
            ==p['geometry'],'人物取景与测量不符')
    return p
