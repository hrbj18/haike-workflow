"""Prepare short/long episodes with continuous presenter clips and optional real audio."""
import json
import math
import shutil
import subprocess
from pathlib import Path
from timeline import compile_timeline, frames, require
from prepare import HERE, sha
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def prepare_v2(episode_path,output,check_only=False,preview_quality='standard'):
    require(preview_quality in {'standard','low'},'预览画质仅支持standard或low')
    low=preview_quality=='low';width,height=(288,360) if low else (576,720)
    data=json.loads(episode_path.read_text('utf-8'));base=episode_path.resolve().parent
    ffmpeg,ffprobe=resolve_ffmpeg_pair();sources={};metadata={}
    def source(value,role):
        require(isinstance(value,str) and bool(value.strip()),role+'需要本地文件路径')
        path=(base/value).resolve();require(path.is_file(),'缺少'+role+'文件：'+path.name)
        if str(path) not in sources:sources[str(path)]={'path':str(path),'sha256':sha(path)}
        if str(path) not in metadata:
            metadata[str(path)]=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(path)]))
        return path,metadata[str(path)]
    def start_seconds(value):
        require(type(value) in (int,float) and math.isfinite(value) and value>=0,'源起点应为非负有限秒数')
        return value
    mode=data.get('mode');audio=None;audio_start=start_seconds(data.get('audioStart',0))
    if mode=='narrated-preview':
        audio,info=source(data.get('audio'),'音轨')
        require(any(s['codec_type']=='audio' for s in info['streams']),'音轨没有可解码的音频流')
        available=float(info['format']['duration'])-audio_start
        duration=data.get('durationSeconds',available)
        total=frames(duration)
        require(duration<=available+.001,'指定时长超出原音轨，不循环/变速补足')
    else:
        require('durationSeconds' in data,'静音v2预览必须填写durationSeconds')
        total=frames(data['durationSeconds'])
    plan=compile_timeline(data,total)
    require(not (data.get('presenterClips') and data.get('presenter')),'presenter与presenterClips只能选择一个')
    clips=data.get('presenterClips')
    if clips is not None:require('presenterStart' not in data and 'presenterCrop' not in data,'分段人物请在每段填写sourceStart/crop，不能同时填写全局人物裁切/起点')
    windows=plan.get('presenterWindows',[{'from':0,'to':total}])
    if clips is None:
        clips=[{'file':data.get('presenter'),'from':w['from'],'to':w['to'],'sourceStart':data.get('presenterStart',0)+w['from']/30,'crop':data.get('presenterCrop')} for w in windows]
    require(isinstance(clips,list) and bool(clips),'人物片段不可为空')
    bound=[];window_index=0;cursor=windows[0]['from'];consumed={}
    for index,clip in enumerate(clips):
        require(isinstance(clip,dict) and not(set(clip)-{'file','from','to','sourceStart','crop'}),'人物片段字段不合法')
        a,b=clip.get('from'),clip.get('to')
        require(window_index<len(windows) and type(a) is int and type(b) is int and a==cursor and a<b<=windows[window_index]['to'],'人物片段须精确覆盖声明出镜窗口；素材中段不绑定人物，不允许缺口/越界')
        path,info=source(clip.get('file'),'人物')
        video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
        require(video is not None,'人物文件没有视频流')
        start=start_seconds(clip.get('sourceStart',0));duration=(b-a)/30
        available=float(video.get('duration',info['format']['duration']))
        require(start+duration<=available+1/30+.001,'人物片段不足所需时长；请绑定对应原速片段，不循环/冻结补足')
        identity=str(path).casefold()
        require(all(min(start+duration,stop)-max(start,begin)<=.001 for begin,stop in consumed.get(identity,[])),'人物源范围重复；请绑定未重复的对应原速片段，不用重复片段补长')
        consumed.setdefault(identity,[]).append((start,start+duration))
        crop=clip.get('crop')
        if crop is not None:
            require(isinstance(crop,list) and len(crop)==4 and all(type(v) is int for v in crop),'crop应为整数[x,y,w,h]')
            x,y,w,h=crop
            require(x>=0 and y>=0 and w>0 and h>0 and x+w<=video['width'] and y+h<=video['height'],'人物裁切越界')
        bound.append({'file':str(path),'from':a,'to':b,'sourceStart':start,'crop':crop,'output':f'presenter-{index:04}.mp4'})
        cursor=b
        if b==windows[window_index]['to']:
            window_index+=1
            cursor=windows[window_index]['from'] if window_index<len(windows) else total
    require(window_index==len(windows),'人物片段未覆盖全部声明出镜窗口')
    font=(base/data['font']).resolve()
    # Fonts are not media streams; validate them without ffprobe.
    require(font.is_file() and font.suffix.lower() in {'.ttf','.otf'},'需要有效的本地TTF/OTF字体')
    sources[str(font)]={'path':str(font),'sha256':sha(font)}
    photos=[]
    for value in data['photos']:
        path,info=source(value,'照片')
        require(path.suffix.lower() in {'.jpg','.jpeg','.png','.webp'} and any(s['codec_type']=='video' for s in info['streams']),'照片格式/解码不合法')
        photos.append(path)
    if check_only:return {'valid':True,'frames':total,'seconds':total/30,'segments':len(plan['segments']),'mode':mode,'previewQuality':preview_quality}
    output=output.resolve();require(output!=base,'输出目录必须与输入目录分离')
    assets=output/'assets';assets.mkdir(parents=True,exist_ok=True)
    outputs=[]
    def run(args):
        subprocess.run([ffmpeg,'-nostdin','-v','error','-y',*args],check=True,capture_output=True)
    public_clips=[]
    for clip in bound:
        target=assets/clip['output'];require(target.resolve()!=Path(clip['file']),'输出不能覆盖人物源文件')
        crop=clip['crop'];filters=([f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}'] if crop else [])+[f'scale={width}:{height}:force_original_aspect_ratio=increase',f'crop={width}:{height}','setsar=1']
        run(['-ss',str(clip['sourceStart']),'-i',clip['file'],'-map','0:v:0','-vf',','.join(filters),'-an','-r','30','-frames:v',str(clip['to']-clip['from']),'-c:v','libx264','-pix_fmt','yuv420p','-crf','26' if low else '16','-preset','ultrafast' if low else 'fast','-threads','2','-movflags','+faststart',str(target)])
        info=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(target)]))
        v=next(s for s in info['streams'] if s['codec_type']=='video')
        require(int(v['nb_frames'])==clip['to']-clip['from'],'人物归一化后缺帧，停止而不补循环帧')
        public_clips.append({'from':clip['from'],'to':clip['to'],'src':'/assets/'+target.name});outputs.append(target)
    audio_url=None
    if audio is not None:
        target=assets/'voice.m4a'
        run(['-ss',str(audio_start),'-i',str(audio),'-map','0:a:0','-af',f'aresample=48000,apad,atrim=end_sample={total*1600}','-c:a','aac','-b:a','160k','-ar','48000','-threads','2','-movflags','+faststart',str(target)])
        outputs.append(target);audio_url='/assets/voice.m4a'
    target=assets/'font.ttf';require(target.resolve()!=font,'字体输入与输出路径重合');shutil.copyfile(font,target);outputs.append(target)
    photo_urls=[]
    for i,path in enumerate(photos):
        target=assets/f'photo-{i+1:03}{path.suffix.lower()}'
        require(target.resolve()!=path,'照片输入与输出路径重合')
        if low:
            from PIL import Image,ImageOps
            with Image.open(path) as original:
                proxy=ImageOps.exif_transpose(original);proxy.thumbnail((640,640),Image.Resampling.LANCZOS)
                if path.suffix.lower() in {'.jpg','.jpeg'}:proxy.convert('RGB').save(target,quality=75)
                else:proxy.save(target)
        else:shutil.copyfile(path,target)
        outputs.append(target);photo_urls.append('/assets/'+target.name)
    public={k:data[k] for k in ['schema','mode','presenterName','headline','kicker'] if k in data}
    public.update(plan,presenterClips=public_clips,photos=photo_urls,audio=audio_url,captionSource=data.get('captionSource','illustrative'),previewQuality=preview_quality)
    for name,content in [('episode.json',public),('timeline.json',plan),('render-props.json',{'variant':plan.get('pilotVariant','01'),'episode':public})]:
        target=output/name;target.write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8');outputs.append(target)
    manifest={'schema':'haike.chromatic-preparation/1','episodeSchema':data['schema'],'previewQuality':preview_quality,'sourceEpisodeSha256':sha(episode_path),'recipeSha256':sha(HERE/'recipes.json'),'inputs':list(sources.values()),'presenterClips':bound,'audioStart':audio_start,'clock':'Audio master at original speed; <=one-frame tail silence alignment' if audio else 'Explicit silent design clock','speed':1,'frames':total,'ffmpegVersion':subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0],'files':[{'path':p.relative_to(output).as_posix(),'sha256':sha(p)} for p in outputs]}
    (output/'preparation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'valid':True,'frames':total,'seconds':total/30,'segments':len(plan['segments']),'presenterClips':len(bound),'mode':mode,'previewQuality':preview_quality,'output':str(output),'paidCalls':0}
