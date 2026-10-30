"""Pixel-bound output geometry for the official native portrait renderer.

The source composition already reflows in MotionGit. This module only defines
and verifies the reviewed 4:5 window; it never recreates a scene or its motion.
"""
from pathlib import Path

from backlot.work_catalog import WorkError, sha

CONSOLE_45 = {'profile': 'console-native-portrait-45/1', 'source': [1080, 1920],
              'rect': [0, 250, 1080, 1350], 'output': [1440, 1800]}


def require(value, message):
    if not value: raise WorkError(message)


def is_layout(value):
    return (isinstance(value,dict) and value==CONSOLE_45
            and all(isinstance(value.get(key),list) and all(type(n) is int for n in value[key])
                    for key in ['source','rect','output']))


def checked(row):
    require(isinstance(row, dict) and isinstance(row.get('path'), str), '画幅审核图片未绑定身份')
    path = Path(row['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and sha(path) == row.get('sha256'),
            '画幅审核图片已变化，请保留原版本并重新预览')
    return path


def crop_images(sources, folder):
    from PIL import Image
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    require(not folder.is_symlink(), '适配预览须保存在本期普通目录')
    x, y, w, h = CONSOLE_45['rect']; images = []
    for i, source in enumerate(sources):
        path = folder/f'{i:03d}.png'
        require(not path.is_symlink(), '适配预览不能覆盖链接文件')
        with Image.open(checked(source)) as image:
            require(list(image.size) == CONSOLE_45['source'], '原生竖屏源尺寸与已核验布局不一致')
            image.crop((x, y, x+w, y+h)).save(path)
        images.append({'source': dict(source), 'image': {'path': str(path), 'sha256': sha(path)}})
    return images


def validate_review(review, sources, preview_sha):
    from PIL import Image
    require(review.get('status') == 'pass' and is_layout(review.get('layout'))
            and review.get('source_preview_sha256') == preview_sha,
            '本期4:5尚未完成同版本视窗审核')
    rows = review.get('images'); expected = {str(checked(row).resolve()): row['sha256'] for row in sources}
    require(isinstance(rows, list) and rows and len(rows) == len(sources) == len(expected), '请实际检查本期全部4:5状态')
    seen = set(); x, y, w, h = CONSOLE_45['rect']
    for row in rows:
        source = checked(row.get('source')); image = checked(row.get('image')); key = str(source.resolve())
        require(key in expected and expected[key] == row['source']['sha256'] and key not in seen,
                '4:5审核存在重复、遗漏或其他版本的源图')
        seen.add(key)
        with Image.open(source) as raw, Image.open(image) as cropped:
            require(list(raw.size) == CONSOLE_45['source'] and cropped.size == (w, h)
                    and raw.crop((x, y, x+w, y+h)).convert('RGB').tobytes() == cropped.convert('RGB').tobytes(),
                    '预览与冻结的4:5视窗像素不一致，不能用于最终导出')
    return dict(CONSOLE_45)


def filtergraph(layout):
    require(is_layout(layout), '未核验的原生视窗适配')
    x, y, w, h = layout['rect']; width, height = layout['output']
    return f'crop={w}:{h}:{x}:{y},scale={width}:{height}:flags=lanczos'
