"""Select an owned platform adapter without changing canonical frozen sources."""
from functools import lru_cache
from importlib import import_module
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'Haike_video/config/motion-native-v1.json'
NATIVE_MODULES = {
    'backlot.' + name: 'backlot.motion_native_' + name.removeprefix('motion_')
    for name in (
        'motion_public_execution_v2', 'motion_public_observed_v2', 'motion_public_dark_v2',
        'motion_public_dark_remotion_v2', 'motion_public_production_v2',
        'motion_public_poster_execution_v3', 'motion_public_poster_observed_v3', 'motion_public_poster_production_v3',
        'motion_replay_public_v2', 'motion_replay_public_v2_bound', 'motion_replay_public_poster_v3_bound',
        'motion_public_paper_execution_v3', 'motion_public_paper_observed_v3', 'motion_public_paper_production_v3',
        'motion_replay_public_paper_v3_bound',
        'motion_public_quote_execution_v3', 'motion_public_quote_observed_v3', 'motion_public_quote_production_v3',
        'motion_replay_public_quote_v3_bound',
    )
}


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify():
    document = json.loads(MANIFEST.read_text('utf8'))
    if document.get('schema') != 'haike.motion-native-adapter/1' or document.get('platform') != 'darwin':
        raise ValueError('Mac动效适配清单身份无效')
    rows = document.get('modules', [])
    if len(rows) != len(NATIVE_MODULES) or {r.get('canonical_module') for r in rows} != set(NATIVE_MODULES):
        raise ValueError('Mac动效固定模块清单不完整')
    for row in rows:
        canonical = row['canonical_module']
        native = NATIVE_MODULES[canonical]
        expected = {'native_module': native, 'source': 'Haike_video/' + canonical.replace('.', '/') + '.py',
                    'derived': 'Haike_video/' + native.replace('.', '/') + '.py'}
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError('Mac动效JSON只记录来源，不能选择执行模块或路径')
    for field, relative in [('generator_sha256', 'scripts/build-native-motion.py'),
                            ('runtime_sha256', 'Haike_video/backlot/motion_native_runtime.py')]:
        if _sha(ROOT / relative) != document[field]:
            raise ValueError('Mac动效适配实现改变，请为新任务重新冻结身份')
    for row in rows:
        for key in ('source', 'derived'):
            path = ROOT / row[key]
            if not path.resolve().is_relative_to(ROOT) or path.is_symlink() or _sha(path) != row[key + '_sha256']:
                raise ValueError('Mac动效原始/派生源码摘要改变')
    return document


def owned_module(name):
    """The name is selected by existing code registries, never caller JSON."""
    if sys.platform == 'darwin':
        if name in NATIVE_MODULES:
            verify()
            return import_module(NATIVE_MODULES[name])
    return import_module(name)
