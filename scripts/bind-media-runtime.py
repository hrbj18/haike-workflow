"""Prepare distributable fonts and bind this installation's existing media tools."""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'Haike_video')]


def bind(root=ROOT):
    target = root / '_distribution-tools/motion-html/fonts'
    target.mkdir(parents=True, exist_ok=True)
    sources = [root / 'Haike_video/remotion-composer/a2e/public/fonts/NotoSansSC.ttf',
               *(root / 'Haike_video/templates/motion-native-v1/fonts').iterdir()]
    for source in sources:
        if not source.is_file():
            continue
        destination = target / source.name
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            raise ValueError('已有字体与公开固定来源不同，请保留现场并核对：' + source.name)
        if not destination.exists():
            shutil.copyfile(source, destination)
    from backlot.motion_native_runtime import bind_installation
    print(bind_installation())


if __name__ == '__main__':
    bind()
