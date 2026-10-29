"""Project-owned presenter composition applied before preview and freezing.

The official package and prepared scene files stay unchanged. A separate layer
uses the same imported talk frames and output clock; audio is never touched.
"""
import json
from pathlib import Path

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, read_json, sha

SCRIPT = Path(__file__).resolve().parents[1] / 'templates/motiongit-console-v1/presenter.js'
MODES = {'auto', 'opening', 'closing', 'hidden'}


def policy(console, frames):
    mode = console.get('presenterMode', 'auto')
    if mode not in MODES:
        raise WorkError('控制台人物出镜方式无效')
    if mode != 'auto' and console.get('layout') != 'portrait':
        raise WorkError('开场、结尾和隐藏人物当前只支持4:5')
    segments = console.get('segments', [])
    if mode == 'opening':
        start, end = 0, min(segments[0]['durationFrames'], 300)
    elif mode == 'closing':
        start, end = frames - min(segments[-1]['durationFrames'], 300), frames
    else:
        start, end = 0, 0
    return {'schema': 'haike.console-presenter/1', 'mode': mode, 'startFrame': start,
            'endFrame': end, 'fps': 60, 'diameter': 440, 'left': 320, 'top': 952,
            'fadeFrames': 15}


def install(project, console, frames):
    settings = policy(console, frames)
    if settings['mode'] == 'auto':
        return
    folder = Path(project) / 'project'
    index = folder / 'index.html'
    receipt = Path(project) / 'haike-presenter.json'
    source = SCRIPT.read_bytes()
    config = ('window.HAIKE_PRESENTER=' + json.dumps(settings, separators=(',', ':')) + ';\n').encode()
    expected = {'policy': settings, 'script_sha256': sha(SCRIPT)}
    if receipt.exists():
        old = read_json(receipt)
        if (old.get('policy') != settings or old.get('script_sha256') != sha(SCRIPT)
                or old.get('index_sha256') != sha(index)
                or (folder / 'haike-presenter.js').read_bytes() != source
                or (folder / 'haike-presenter-config.js').read_bytes() != config):
            raise WorkError('出镜方案已变化，请另建本期预览版本')
        return
    if (Path(project) / 'preview.json').exists() or (folder / 'preview.json').exists():
        raise WorkError('已有预览的工程不能更换出镜层，请重新准备')
    text = index.read_text(encoding='utf-8')
    if text.count('</body>') != 1 or 'haike-presenter.js' in text:
        raise WorkError('原生工程入口与受支持版本不一致')
    expected['original_index_sha256'] = sha(index)
    (folder / 'haike-presenter.js').write_bytes(source)
    (folder / 'haike-presenter-config.js').write_bytes(config)
    index.write_bytes(text.replace('</body>', '<script src="haike-presenter-config.js"></script>'
                                  '<script src="haike-presenter.js"></script></body>').encode())
    expected['index_sha256'] = sha(index)
    atomic_private(receipt, expected)
