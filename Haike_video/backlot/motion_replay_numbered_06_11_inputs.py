"""Validate the original components' actual replacement slots on a fixed clock."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import re
import subprocess

from backlot.motion_replay import ReplayError, source_path
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def require(ok, message):
    if not ok:
        raise ReplayError(message)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def object_keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), label + '字段缺失或包含未开放字段')


def position(value):
    require(isinstance(value, str) and re.fullmatch(r'(?:100|\d{1,2})(?:\.\d+)?% (?:100|\d{1,2})(?:\.\d+)?%', value),
            'objectPosition必须是两个0到100的百分比')
    require(all(0 <= float(v[:-1]) <= 100 for v in value.split()), '裁切焦点越界')


def apply_inputs(baseline, inputs, number, *, workspace):
    """Patch only consumed slots. Assets are local, SHA/provenance-bound and decoded.

    No metadata claims are trusted for type, fps or source duration. Return new
    inputs with a separate pending visual review, never inherit old validation.
    """
    object_keys(inputs, {'episode', 'assets', 'public_root'}, 'inputs')
    root_value = inputs['public_root']
    require(isinstance(root_value, str) and root_value.startswith('.local/'),
            '本期public_root必须位于忽略的.local目录')
    public_root = source_path(root_value, workspace)
    patch = inputs['episode']
    media_key = 'materialClips' if number < 8 else 'materialSlots' if number < 10 else 'videoSlots'
    allowed = {media_key, 'presenterClips', 'captions', 'fontFamily', 'fontSrc'}
    require(isinstance(patch, dict) and patch and set(patch) <= allowed,
            'episode只开放原视频/人物/字幕/字体槽；标题、说明、时长与动作仍锁定')
    require(isinstance(inputs['assets'], list) and inputs['assets'], '本期素材必须有来源清单')
    assets = {}
    ff_pair = resolve_ffmpeg_pair()
    require(ff_pair is not None, '缺少本机FFmpeg/FFprobe，无法核验本期视频')
    for row in inputs['assets']:
        object_keys(row, {'path', 'sha256', 'kind', 'provenance'}, 'asset')
        require(isinstance(row['provenance'], str) and 0 < len(row['provenance']) <= 2000,
                '本期素材须有授权来源说明；摘要不授予使用权')
        require(isinstance(row['path'], str) and row['path'].startswith('assets/')
                and re.fullmatch(r'[A-Za-z0-9_./-]+',row['path']),
                '素材路径须位于public_root/assets，使用普通URL路径，不含查询/片段/编码转义')
        path = source_path(root_value + '/' + row['path'], workspace)
        require(path.is_file() and path.stat().st_size <= 200*1024*1024, '素材缺失或超出本期预览预算')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(digest == row['sha256'], '本期素材摘要变化')
        url = '/' + row['path']
        require(url not in assets, '本期素材路径重复')
        info = {'sha256':digest, 'kind':row['kind']}
        if row['kind'] == 'video':
            try:
                completed = subprocess.run([ff_pair[1], '-v','error','-select_streams','v:0',
                    '-show_entries','stream=codec_type,width,height,avg_frame_rate,duration,nb_frames',
                    '-of','json',str(path)], capture_output=True, timeout=30, check=True)
                stream = json.loads(completed.stdout)['streams'][0]
                require(stream.get('codec_type') == 'video' and Fraction(stream['avg_frame_rate']) == 30,
                        '主素材必须为30fps原生视频')
                frames = int(stream.get('nb_frames', 0))
                require(0 < frames <= 3600, '本期预览只接受不超过120秒且有可核帧数的视频')
                require(0 < stream['width'] <= 1920 and 0 < stream['height'] <= 1920, '视频尺寸超出本期预览预算')
                # Full decode, without exporting another media artifact. Decoder
                # errors are not silently accepted based on container metadata.
                decoded = subprocess.run([ff_pair[0],'-v','error','-xerror','-i',str(path),
                    '-map','0:v:0','-an','-f','null','-'], capture_output=True, timeout=120)
                require(decoded.returncode == 0, '本期视频无法完整解码')
                # Count decoded frames separately; do not trust nb_frames alone.
                counted = subprocess.run([ff_pair[1],'-v','error','-count_frames','-select_streams','v:0',
                    '-show_entries','stream=nb_read_frames','-of','json',str(path)],
                    capture_output=True, timeout=120, check=True)
                actual = int(json.loads(counted.stdout)['streams'][0]['nb_read_frames'])
                require(actual == frames, '容器帧数与完整解码帧数不符')
                info.update(frames=actual, width=stream['width'], height=stream['height'])
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
                raise ReplayError('本期视频探测/解码失败，请恢复可读的本地视频') from exc
        elif row['kind'] == 'font':
            require(path.suffix.lower() == '.ttf' and path.read_bytes()[:4] in {b'\x00\x01\x00\x00',b'true'},
                    '字体必须为本地TrueType字体')
        else:
            raise ReplayError('素材类型仅支持video/font，不接受照片冒充视频')
        assets[url] = info

    value = deepcopy(baseline)
    value.update(deepcopy(patch))
    # Non-overridden slots also need assets in this public root. Supplying only
    # a subtitle change cannot accidentally point to missing original videos.
    def video(url, start, end):
        require(isinstance(url,str) and url in assets and assets[url]['kind']=='video', '视频槽未绑定本期原生素材')
        require(integer(start) and integer(end) and 0 <= start < end <= assets[url]['frames'], '源帧范围不足，禁止循环、冻尾或拉伸')

    clips = value.get('presenterClips')
    require(isinstance(clips,list) and len(clips)==1, '人物槽必须是一条连续720帧原速视频')
    require(isinstance(clips[0],dict) and set(clips[0]) == set(baseline['presenterClips'][0]), '人物槽字段变化')
    for key, expected in baseline['presenterClips'][0].items():
        if key != 'src':
            require(type(clips[0].get(key)) is type(expected) and clips[0].get(key)==expected, '人物时钟、裁切或角色元数据尚未开放')
    video(clips[0]['src'],0,720)
    cues = value.get('captions')
    require(isinstance(cues,list) and 0 < len(cues) <= 40, '字幕必须连续覆盖原720帧')
    end = 0
    for cue in cues:
        require(isinstance(cue,dict) and set(cue) <= {'from','to','text','lines'} and {'from','to','text'} <= set(cue), '字幕字段无效')
        require(integer(cue['from']) and integer(cue['to']) and cue['from']==end < cue['to'] <= 720, '字幕时钟缺口、重叠或越界')
        require(isinstance(cue['text'],str) and 0 < len(cue['text']) <= (30 if number>=10 else 24), '字幕字数超过原阅读预算')
        lines=cue.get('lines',[cue['text']])
        require(isinstance(lines,list) and 0<len(lines)<=2 and all(isinstance(x,str) and x for x in lines)
                and ''.join(lines)==cue['text'].replace('\n',''), '字幕行数、内容或分行无效')
        end=cue['to']
    require(end==720,'字幕未覆盖原24秒')
    require(isinstance(value.get('fontFamily'),str) and 0<len(value['fontFamily'])<=80, '字体family缺失')
    require(isinstance(value.get('fontSrc'),str) and value['fontSrc'] in assets and assets[value['fontSrc']]['kind']=='font', '字体没有绑定已核验本地TTF')
    if number < 8:
        material=value[media_key]
        require(isinstance(material,list) and len(material)==8, 'materialClips必须保持8槽')
        # Mount lifetimes in the actual source; visibility/opacity does not stop
        # a Video's clock. 06's unused aliases are still validated as video.
        uses = ({0:[(0,41)],1:[(0,180)],2:[(1,240)],4:[(1,240),(3,120)],6:[(2,180),(3,11)]}
                if number==6 else {0:[(0,240),(3,135)],2:[(0,240),(2,165)],4:[(0,240)],1:[(1,180)],3:[(1,180)],5:[(1,180)],7:[(3,135)]})
        for i, clip in enumerate(material):
            object_keys(clip, {'src','starts','frames','objectPosition'}, 'materialClips')
            require(isinstance(clip['starts'],list) and len(clip['starts'])==4 and all(integer(v) and v>=0 for v in clip['starts']), '素材局部入点无效')
            require(isinstance(clip['src'],str) and clip['src'] in assets and integer(clip['frames']) and clip['frames']==assets[clip['src']].get('frames'), '素材帧数须匹配实际完整解码')
            position(clip['objectPosition'])
            for phase,length in uses.get(i,[(0,1)]):
                video(clip['src'],clip['starts'][phase],clip['starts'][phase]+length)
        if number==7:
            # Existing hand/robot trajectories were measured for this shot.
            # A replacement without new tracked anchors would be misleading.
            old=baseline[media_key][2]; current=material[2]
            require(current==old and assets[current['src']]['sha256']==
                    'e7cb809335cb66e385dda51192351e06c88e3755f39ac61aa7f51d1ac1834e1d',
                    '07圈注轨迹绑定原亲子源/165帧/裁切；该槽换素材需要作者重测锚点')
    elif number < 10:
        material=value[media_key]; old=baseline[media_key]
        object_keys(material, old.keys(), 'materialSlots')
        for slot, clip in material.items():
            object_keys(clip, old[slot].keys(), 'materialSlot')
            require(isinstance(clip.get('asset'),str) and clip['asset'], '素材来源标签必须为字符串')
            for key in set(clip)-{'src','asset','sourceFrom','sourceTo','objectPosition'}:
                require(type(clip[key]) is type(old[slot][key]) and clip[key]==old[slot][key], '视频槽全局窗口/速度/fit保持原合同')
            require(integer(clip['sourceFrom']) and integer(clip['sourceTo']) and clip['sourceTo']-clip['sourceFrom']==clip['to']-clip['from'], '源范围必须与全局窗口等长')
            video(clip['src'],clip['sourceFrom'],clip['sourceTo']); position(clip['objectPosition'])
        if number==9:
            a,b=material['09-fold-left'],material['09-fold-front']
            require(all(a[k]==b[k] for k in ('src','sourceFrom','sourceTo','objectPosition')), '09翻页前页与底层须同源同帧同裁切')
    else:
        material=value[media_key]; old=baseline[media_key]
        object_keys(material, old.keys(), 'videoSlots')
        for slot, clips in material.items():
            require(isinstance(clips,list) and len(clips)==len(old[slot]), '视频槽分段拓扑保持原合同')
            for clip, prior in zip(clips,old[slot]):
                object_keys(clip,prior.keys(),'videoSlot')
                for key in set(clip)-{'src','sourceStart','sourceEnd','objectPosition'}:
                    require(type(clip[key]) is type(prior[key]) and clip[key]==prior[key], '视频槽窗口/速度/fit保持原合同')
                require(integer(clip['sourceStart']) and integer(clip['sourceEnd']) and clip['sourceEnd']-clip['sourceStart']==clip['to']-clip['from'], '视频源/全局范围必须等长')
                video(clip['src'],clip['sourceStart'],clip['sourceEnd']);position(clip['objectPosition'])
    return value, {'public_root':root_value,'font_url':value['fontSrc'],
        'font_family':value['fontFamily'],'font_load_required':True,
        'verified_assets':assets,'scope':'SHA + actual stream/fps/complete decode; new visual/caption/crop review pending'}
