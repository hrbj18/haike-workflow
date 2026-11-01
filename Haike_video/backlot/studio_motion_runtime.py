"""Resolve public installation-owned dependencies, independent of user envelopes."""
from functools import lru_cache
import importlib.util
from pathlib import Path

from backlot.work_catalog import WorkError, read_json


@lru_cache(maxsize=4)
def _module(root):
    path = Path(root) / 'portable/motion_runtime.py'
    spec = importlib.util.spec_from_file_location('haike_motion_runtime_' + str(abs(hash(root))), path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def profile(package, workflow):
    from backlot import studio_motiongit as motion
    root = motion.ROOT.resolve()
    manifest = root / 'Haike_video/templates/motion-presets/runtime.json'
    declared = read_json(root / 'Haike_video/templates/motion-presets/delivery.json')
    if not manifest.exists():
        if 'Haike_video/templates/motion-presets/runtime.json' in declared.get('files', {}):
            raise WorkError('正式模板运行依赖清单缺失，请修复本次更新')
        return None
    try:
        return _module(str(root)).resolve(root, package, workflow)
    except (ValueError, OSError) as exc:
        raise WorkError('模板运行依赖尚未就绪：' + str(exc)) from exc
