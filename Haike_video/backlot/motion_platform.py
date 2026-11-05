"""Select an owned platform adapter without changing canonical frozen sources."""
from functools import lru_cache
from importlib import import_module
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'Haike_video/config/motion-native-v1.json'


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify():
    document = json.loads(MANIFEST.read_text('utf8'))
    if document.get('schema') != 'haike.motion-native-adapter/1' or document.get('platform') != 'darwin':
        raise ValueError('Mac动效适配清单身份无效')
    for field, relative in [('generator_sha256', 'scripts/build-native-motion.py'),
                            ('runtime_sha256', 'Haike_video/backlot/motion_native_runtime.py')]:
        if _sha(ROOT / relative) != document[field]:
            raise ValueError('Mac动效适配实现改变，请为新任务重新冻结身份')
    for row in document['modules']:
        for key in ('source', 'derived'):
            path = ROOT / row[key]
            if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or _sha(path) != row[key + '_sha256']:
                raise ValueError('Mac动效原始/派生源码摘要改变')
    return document


def owned_module(name):
    """The name is selected by existing code registries, never caller JSON."""
    if sys.platform == 'darwin':
        document = verify()
        row = next((r for r in document['modules'] if r['canonical_module'] == name), None)
        if row:
            return import_module(row['native_module'])
    return import_module(name)
