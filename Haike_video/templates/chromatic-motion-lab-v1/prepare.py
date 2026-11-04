"""Freeze local inputs for the shared 12-second silent avatar preview recipes."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from timeline import units, require


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate(data, book=None):
    book = book or json.loads((HERE / 'recipes.json').read_text('utf-8'))
    require(data.get('schema') == 'haike.chromatic-avatar-episode/1', 'episode schema 不支持')
    require(data.get('mode') == 'visual-preview', '本入口只支持 visual-preview 静音预览')
    allowed = {'schema','mode','headline','kicker','presenterName','presenter','presenterStart','presenterCrop','font','photos','captions'}
    require(not (set(data) - allowed), '存在未支持字段，请按 episode.example.json 填写')
    for key in ['presenter', 'font']:
        require(isinstance(data.get(key), str) and data[key].strip(), f'{key} 必填')
    for key in ['presenterName', 'kicker']:
        if key == 'kicker' and key not in data:
            continue
        value = data.get(key)
        limit = book['slots'][key]['units']
        require(isinstance(value, str) and value.strip() and '\n' not in value and units(value) <= limit, f'{key} 超长/为空/含换行，上限{limit}个全角单位')
    if 'headline' in data:
        lines = data['headline'].split('\n') if isinstance(data['headline'], str) else []
        limit = book['slots']['headline']
        require(1 <= len(lines) <= limit['lines'] and all(x.strip() and units(x) <= limit['unitsPerLine'] for x in lines), f'headline 最多两行，每行{limit["unitsPerLine"]}个全角单位；使用显式换行')
    photos = data.get('photos')
    require(isinstance(photos, list) and 3 <= len(photos) <= 8 and all(isinstance(p,str) and p.strip() for p in photos), 'photos 需要3至8个本地图片路径')
    start = data.get('presenterStart', 0)
    require(type(start) in (int,float) and math.isfinite(start) and start >= 0, 'presenterStart 需为非负有限秒数')
    cues = data.get('captions')
    require(isinstance(cues, list) and len(cues) >= 1, 'captions 不能为空')
    end = 0
    for cue in cues:
        require(isinstance(cue,dict) and set(cue) == {'from','to','text'}, '字幕字段应为from/to/text')
        require(type(cue['from']) is int and type(cue['to']) is int and cue['from'] == end and end < cue['to'] <= 360, '字幕必须逐段连续覆盖[0,360)，帧号为整数')
        require(isinstance(cue['text'],str) and cue['text'].strip() and '\n' not in cue['text'] and units(cue['text']) <= book['slots']['caption']['units'], '每条字幕最多18个全角单位且为单行')
        end = cue['to']
    require(end == 360, '字幕须完整覆盖360帧')
    for recipe in book['recipes']:
        for role in ['presenterBox','mediaBox']:
            x,y,w,h = recipe[role]
            require(x >= 0 and y >= 0 and w > 0 and h > 0 and x+w <= 720 and y+h <= 990, f'{recipe["id"]} {role} 越界')
        require(recipe['mediaEffect'] in {'waterfall','parallax','reflow','click-open','spatial-gallery','orbit'}, '未知媒体动效')
    return data


def prepare(episode_path, output, check_only=False, preview_quality='standard'):
    raw=json.loads(episode_path.read_text('utf-8'))
    if raw.get('schema')=='haike.chromatic-avatar-episode/2':
        from prepare_v2 import prepare_v2
        return prepare_v2(episode_path,output,check_only,preview_quality)
    require(preview_quality=='standard','低清代理仅支持v2输入，请使用episode.v2.example.json')
    data = validate(raw)
    base = episode_path.resolve().parent
    def source(value):
        path = (base / value).resolve()
        require(path.is_file(), '缺少声明的本地素材：' + path.name)
        return path
    presenter, font = source(data['presenter']), source(data['font'])
    photos = [source(p) for p in data['photos']]
    require(font.suffix.lower() in {'.ttf','.otf'}, 'font 仅接受本地TTF/OTF字体')
    require(all(p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'} for p in photos), 'photos 仅接受JPG/PNG/WebP')
    ffmpeg, ffprobe = resolve_ffmpeg_pair()
    def probe(path):
        return json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(path)]))
    info = probe(presenter)
    video = next((s for s in info['streams'] if s['codec_type']=='video'), None)
    require(video is not None, 'presenter 没有视频流')
    require(float(info['format']['duration']) + .001 >= data.get('presenterStart',0) + 12, '人物素材不足12秒；请换连续素材或减少起点，不循环/变速补足')
    crop = data.get('presenterCrop')
    if crop is not None:
        require(isinstance(crop,list) and len(crop)==4 and all(type(v) is int for v in crop), 'presenterCrop 应为整数[x,y,w,h]')
        x,y,w,h = crop
        require(x>=0 and y>=0 and w>0 and h>0 and x+w<=video['width'] and y+h<=video['height'], '人物源裁切越界')
    for path in photos:
        require(any(s['codec_type']=='video' for s in probe(path)['streams']), '图片无法解码：' + path.name)
    if check_only:
        return {'valid':True,'recipes':6,'frames':360,'mode':data['mode']}
    require(output.resolve() != base, '输出目录应与输入目录分离')
    assets = output / 'assets'
    assets.mkdir(parents=True,exist_ok=True)
    inputs = [{'role':role,'path':str(path),'sha256':sha(path)} for role,path in [('presenter',presenter),('font',font),*[(f'photo-{i+1}',p) for i,p in enumerate(photos)]]]
    target = assets/'presenter.mp4'
    require(target.resolve() != presenter, '输出不能覆盖人物源素材')
    filters = ([f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}'] if crop else []) + ['scale=576:720:force_original_aspect_ratio=increase','crop=576:720','setsar=1']
    subprocess.run([ffmpeg,'-nostdin','-v','error','-y','-ss',str(data.get('presenterStart',0)),'-i',str(presenter),'-t','12','-map','0:v:0','-vf',','.join(filters),'-an','-r','30','-c:v','libx264','-pix_fmt','yuv420p','-crf','16','-preset','fast','-threads','2','-movflags','+faststart',str(target)],check=True,capture_output=True)
    normalized = probe(target)
    stream = next(s for s in normalized['streams'] if s['codec_type']=='video')
    require(int(stream['nb_frames']) == 360 and not any(s['codec_type']=='audio' for s in normalized['streams']), '归一化人物帧数/静音校验失败')
    shutil.copyfile(font, assets/'font.ttf')
    bindings=[]
    for i,path in enumerate(photos):
        name=f'photo-{i+1}{path.suffix.lower()}'
        shutil.copyfile(path, assets/name)
        bindings.append('/assets/'+name)
    public = {key:data[key] for key in ['schema','mode','presenterName','captions','headline','kicker'] if key in data}
    public.update(presenter='/assets/presenter.mp4',photos=bindings)
    (output/'episode.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf-8')
    files = [target,assets/'font.ttf',*[output/p.lstrip('/') for p in bindings],output/'episode.json']
    manifest={'schema':'haike.chromatic-preparation/1','sourceEpisodeSha256':sha(episode_path),'recipeSha256':sha(HERE/'recipes.json'),'inputs':inputs,'presenterStart':data.get('presenterStart',0),'presenterCrop':crop,'speed':1,'frames':360,'ffmpegVersion':subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0],'files':[{'path':p.relative_to(output).as_posix(),'sha256':sha(p)} for p in files]}
    (output/'preparation.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'valid':True,'recipes':6,'frames':360,'output':str(output),'paidCalls':0}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--preview-quality',choices=['standard','low'],default='standard',help='low仅缩小v2预览素材；动效、字幕与原声时钟保持不变')
    args=parser.parse_args()
    try:
        print(json.dumps(prepare(args.episode,args.output,args.check,args.preview_quality),ensure_ascii=False))
    except (ValueError,subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc)+'\n')
