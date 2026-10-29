"""Face-window calibration on owned, officially imported console frames.

This module reads only 720x1280 talk JPEGs produced by the public prepare command.
It never guesses the package's source-video transform or edits its motion code.
"""
from pathlib import Path
import math

from PIL import Image, ImageDraw

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, read_json, sha

SCHEMA = 'haike.motion-console-face-crop/1'
SIZE = (720, 1280)


def require(ok, message):
    if not ok: raise WorkError(message, 'invalid')


def binding(path):
    path = Path(path).resolve()
    require(path.is_file() and not path.is_symlink(), '人物取景文件缺失，请保留原任务重新准备')
    return {'path': str(path), 'sha256': sha(path)}


def checked(row):
    require(isinstance(row, dict), '人物取景证据无效')
    path = Path(row.get('path', ''))
    require(path.is_absolute() and path.is_file() and not path.is_symlink()
            and sha(path) == row.get('sha256'), '人物取景证据已变化，请重新准备')
    return path


def imported_frames(project):
    folder = Path(project)/'project/talk/clip_000'
    require(folder.is_dir() and not folder.is_symlink(), '官方人物导入帧不存在，请恢复原准备任务')
    files = sorted(folder.glob('f_*.jpg'))
    require(len(files) >= 7, '官方人物帧不足，不能自动校准圆窗')
    # Distributed across the whole imported talk, including both ends.
    return [files[round((len(files)-1)*i/6)] for i in range(7)]


def detector():
    import cv2
    # OpenCV's XML filename loader fails on some Windows Unicode workspaces.
    xml = Path(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml').read_text(encoding='utf8')
    storage = cv2.FileStorage(xml, cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
    cascade = cv2.CascadeClassifier()
    cascade.read(storage.getFirstTopLevelNode())
    storage.release()
    require(not cascade.empty(), '本机人脸检测模型不可用，请检查项目依赖')
    return cascade


def faces(path, cascade):
    import cv2
    import numpy as np
    with Image.open(path) as image:
        require(image.size == SIZE, '官方人物导入尺寸变化，需要重新适配，不能沿用旧坐标')
        pixels = np.asarray(image.convert('RGB'))
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    return [list(map(int, box)) for box in cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60))]


def window(boxes):
    """A circle containing measured faces plus explicit hair/chin margins."""
    require(len(boxes) >= 5, '人脸检测不足五帧，请换清晰正面形象或人工适配')
    require(all(len(b) == 4 and all(type(v) in {int, float} and math.isfinite(v) for v in b)
                and b[2] >= 60 and b[3] >= 60 and b[0] >= 0 and b[1] >= 0
                and b[0]+b[2] <= SIZE[0] and b[1]+b[3] <= SIZE[1] for b in boxes), '检测到无效人脸坐标')
    heights = sorted(b[3] for b in boxes)
    median = heights[len(heights)//2]
    centers = [(x+w/2, y+h/2) for x,y,w,h in boxes]
    require(max(heights)/min(heights) <= 1.35
            and max(x for x,y in centers)-min(x for x,y in centers) <= median*.35
            and max(y for x,y in centers)-min(y for x,y in centers) <= median*.35,
            '人物移动或检测差异过大，固定圆窗不可靠，请人工适配')
    left = min(x-.1*w for x,y,w,h in boxes)
    right = max(x+1.1*w for x,y,w,h in boxes)
    top = min(y-.35*h for x,y,w,h in boxes)
    bottom = max(y+1.15*h for x,y,w,h in boxes)
    midx, midy = (left+right)/2, (top+bottom)/2
    corners=[(left,top),(right,top),(left,bottom),(right,bottom)]
    candidates=[]
    # A face's minimal enclosing circle may cross the narrow portrait edge.
    # Recenter and recompute its radius; never shrink it to hide lost hair.
    for cx,cy in [(midx,midy),(SIZE[0]/2,midy),(midx,SIZE[1]/2),(SIZE[0]/2,SIZE[1]/2)]:
        radius=max(math.hypot(x-cx,y-cy) for x,y in corners)+1
        if radius<=min(cx,SIZE[0]-cx,cy,SIZE[1]-cy):candidates.append((radius,cx,cy))
    require(candidates,'人脸靠近画面边缘，完整圆窗会越界，请换形象或人工适配')
    radius,cx,cy=min(candidates)
    return {'cx': round(cx/SIZE[0], 6), 'cy': round(cy/SIZE[1], 6),
            'h': round(2*radius/SIZE[1], 6)}


def calibrate(project, avatar, tools, output):
    avatar_path = checked(avatar)
    inputs = imported_frames(project)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    require(not output.is_symlink(), '人物取景输出目录无效')
    cascade = detector()
    samples = []
    for path in inputs:
        found = faces(path, cascade)
        require(len(found) <= 1, '人物帧包含多张脸，不能自动选择人物圆窗')
        samples.append({'source': binding(path), 'face': found[0] if found else None})
    crop = window([s['face'] for s in samples if s['face'] is not None])
    cx, cy, radius = crop['cx']*720, crop['cy']*1280, crop['h']*1280/2
    for i, sample in enumerate(samples):
        with Image.open(checked(sample['source'])) as original:
            image = original.convert('RGB')
        draw = ImageDraw.Draw(image)
        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius), outline='#00efbc', width=4)
        if sample['face']:
            x,y,w,h = sample['face']; draw.rectangle((x,y,x+w,y+h), outline='#ffb800', width=3)
        image.thumbnail((360,640))
        target = output/f'face-{i}.png'; image.save(target)
        sample['diagnostic'] = binding(target)
    receipt = {'schema': SCHEMA, 'status': 'measured-awaiting-visual-review',
               'avatar_sha256': sha(avatar_path), 'tools': {k: tools[k] for k in ['helper','package']},
               'calibrator_sha256': sha(__file__), 'source_size': list(SIZE), 'crop': crop,
               'method': 'OpenCV Haar; 7 official frames; >=5 single faces; bounded stable circle',
               'samples': samples}
    target = output/'calibration.json'; atomic_private(target, receipt)
    return binding(target)


def validate(row, avatar, tools, crop, project=None):
    receipt = read_json(checked(row))
    require(receipt.get('schema') == SCHEMA and receipt.get('avatar_sha256') == sha(checked(avatar))
            and receipt.get('calibrator_sha256') == sha(__file__)
            and receipt.get('tools') == {k: tools[k] for k in ['helper','package']}
            and receipt.get('source_size') == list(SIZE) and receipt.get('crop') == crop,
            '新人物或工具已变化，必须重新校准圆窗')
    samples = receipt.get('samples', [])
    require(len(samples) == 7 and len({s['source']['path'] for s in samples}) == 7,
            '人物取景缺少完整分布帧证据')
    for sample in samples:
        with Image.open(checked(sample['source'])) as image:
            require(image.size == SIZE, '人物取景源尺寸变化')
        checked(sample['diagnostic'])
    require(window([s['face'] for s in samples if s['face'] is not None]) == crop, '人物取景与测量坐标不符')
    if project is not None:
        current = imported_frames(project)
        require([sha(p) for p in current] == [s['source']['sha256'] for s in samples],
                '本期官方导入像素与圆窗校准不同，请重新校准')
    return receipt
