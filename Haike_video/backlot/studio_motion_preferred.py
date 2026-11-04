"""Gallery preferences are separate from frozen renderer/registry identities."""
from copy import deepcopy
import json
from functools import lru_cache
from pathlib import Path

from backlot import motion_replay as replay

CONFIG = Path(__file__).resolve().parents[1]/'config/motion-preferred-production.json'


def preferences():
    document = json.loads(CONFIG.read_text('utf-8'))
    if document.get('schema') != 'haike.motion-preferred-production/1':
        raise replay.ReplayError('模板生产选择配置需要恢复')
    rows = document['templates']
    if len(rows) != 18 or len({r['template_id'] for r in rows}) != 18 or len({r['gallery_id'] for r in rows}) != 18:
        raise replay.ReplayError('模板生产选择须为18个唯一样式')
    return rows


def production_map():
    paths = [CONFIG, replay.SCHEMA_PATH, *(replay.REGISTRY_DIR/name for name in replay.REGISTRIES)]
    signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file())
    return deepcopy(_production_map(signature))


@lru_cache(maxsize=2)
def _production_map(signature):
    registered = replay.load_registry()
    result = {}
    for row in preferences():
        matches = [r for r in registered if (r['template_id'], r['version']) == (row['template_id'], row['version'])]
        if len(matches) != 1 or matches[0]['renderer']['execution'] != 'supported':
            raise replay.ReplayError('首选生产精确版本缺失，请恢复对应组件')
        template = deepcopy(matches[0]); template.pop('_registry', None)
        # Catalogs expose metadata only. Full source/runtime checks happen in prepare.
        catalog = {k: deepcopy(template[k]) for k in ('template_id', 'version', 'gallery_id', 'renderer', 'capabilities', 'validation') if k in template}
        result[row['gallery_id']] = {**deepcopy(row), 'status': 'requires_input', 'sources_verified': False,
            'prepare_endpoint': f"/api/studio/template-library/{row['gallery_id']}/prepare",
            'replay': catalog,
            'historical_versions': [r['version'] for r in registered if r['template_id'] == row['template_id']]}
    return result


def selection(value):
    if value is None:
        return None
    if (not isinstance(value, dict) or not {'gallery_id', 'template_id', 'version'} <= set(value)
            or set(value) - {'gallery_id', 'template_id', 'version', 'production_contract'}):
        raise replay.ReplayError('动效选择只保存模板与精确版本')
    row = next((r for r in preferences() if r['gallery_id'] == value['gallery_id']), None)
    if not row or row['template_id'] != value['template_id']:
        raise replay.ReplayError('动效样式身份不符')
    template = replay.resolve(value['template_id'], value['version'])
    if template.get('gallery_id', template['template_id']) != value['gallery_id']:
        raise replay.ReplayError('动效精确版本与样式不符')
    contract = value.get('production_contract', row['production_contract'])
    if value['version'] == row['version'] and contract != row['production_contract']:
        raise replay.ReplayError('动效生产合同与精确选择不符')
    from backlot.motion_replay_production import PRODUCERS
    if contract not in PRODUCERS:
        raise replay.ReplayError('动效生产合同未登记')
    return {**deepcopy(value), 'production_contract': contract}


def prepare(gallery_id, request):
    row = next((r for r in preferences() if r['gallery_id'] == gallery_id), None)
    if row is None:
        raise replay.ReplayError('此卡片没有登记生产入口')
    if not isinstance(request, dict):
        raise replay.ReplayError('本期制作输入须为JSON对象')
    if not request:
        return {'status': 'blocked', 'submitted': False, 'template_id': row['template_id'], 'version': row['version'],
            'required_inputs': deepcopy(row['required_inputs']),
            'blockers': ['请准备本期完整声音、真实ASR、同声源人物及所列素材/编排；已有素材可复用，不自动重新生成。']}
    try:
        result = replay.prepare(row['template_id'], row['version'], request)
        declared = result.get('production_contract') or result.get('reproduction', {}).get('contract')
        if declared and declared != row['production_contract']:
            raise replay.ReplayError('准备结果的生产合同与首选绑定不符')
        return {**result, 'preferred_selection': {k: row[k] for k in
                ('gallery_id', 'template_id', 'version', 'production_contract')},
                'source_kind': row['source_kind'], 'production_contract': row['production_contract']}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Never send an internal path or provider data through a gallery error.
        raise replay.ReplayError('本期输入未满足所选精确版本；请核对完整声音、真实ASR、素材来源、编排与组件身份。原输入保留。') from exc
