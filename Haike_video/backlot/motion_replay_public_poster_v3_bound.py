"""Read-only exact replay binding for the fixed poster /3 implementation."""
from copy import deepcopy
from pathlib import Path

from backlot.motion_replay import ReplayError, verify_sources
from backlot.motion_public_io_v1 import WorkError

WORKSPACE = Path(__file__).resolve().parents[2]
VERSION = '1.0.0-public.3'
TEMPLATE_ID = 'vibrant-poster'
GALLERY_ID = 'motion-package-mg-bcf4d5995342cdffe345d140'
ENGINE = 'observed-controls/3'
PACK_KEY = 'observed-poster'
WORKFLOW = 'public-poster-v3'
CONTRACT = 'haike.motion-public-poster-production/3'
IMPLEMENTATION = 'haike.motion-public-poster-execution/3'
RUNTIME_ACTION_VERSION = '3-symbols-development'
ACTION_SOURCE = 'Haike_video/templates/motiongit-public-poster-symbol-v3/observed-controls-v3.js'
ACTION_CONSUMER = 'backlot.motion_public_poster_observed_v3'


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def prepare(template, request, *, workspace):
    """Verify existing sources/input/actions, add provenance, never create jobs."""
    require(Path(workspace).resolve() == WORKSPACE.resolve(), '请从同一海客源码副本准备海报/3')
    require((template.get('template_id'), template.get('version'), template.get('gallery_id')) ==
            (TEMPLATE_ID, VERSION, GALLERY_ID), '海报/3模板、精确版本或canonical卡片身份不符')
    require(isinstance(request, dict) and not set(request) - {'workflow', 'input', 'action_ids', 'template_id', 'version'},
            '海报/3只接受已声明input，不接受任意模块、命令或其他字段')
    require(request.get('template_id', TEMPLATE_ID) == TEMPLATE_ID and request.get('version', VERSION) == VERSION
            and request.get('workflow', WORKFLOW) == WORKFLOW, '海报/3请求身份或制作路线不符')
    value = request.get('input')
    require(isinstance(value, dict) and value.get('reference_id') == TEMPLATE_ID
            and value.get('engine') == ENGINE and value.get('pack_key') == PACK_KEY,
            '海报/3模板、执行引擎与实际配方不匹配')
    require(isinstance(value.get('title'), str) and 0 < len(value['title'].strip()) <= 160, '海报输入须有明确标题')
    require(isinstance(value.get('source_receipts', {}), dict), '本期来源回执须为对象')
    sources = verify_sources(template, workspace=workspace)
    try:
        work = Path(value.get('work_root', WORKSPACE/'.local/motion-public-poster-work-v3'))
        require(not work.is_symlink() and work.resolve().is_relative_to((WORKSPACE/'.local').resolve()),
                '作业缓存须位于本海客副本私有目录内')
        from backlot.motion_public_poster_production_v3 import preflight
        normalized = preflight(deepcopy(value))
    except WorkError as exc:
        raise ReplayError(str(exc)) from exc
    except (OSError, KeyError, TypeError, ImportError) as exc:
        raise ReplayError('海报/3输入或固定组件尚未齐备，请核对原素材、ASR和已冻结组件') from exc
    spec = normalized['spec']
    require(normalized.get('input_engine') == ENGINE and spec.get('style') == 'poster'
            and spec.get('reference_id') == TEMPLATE_ID, '实际执行层返回其他模板或引擎，不能替代原效果')
    known = {row['id']: row for row in template['actions']}
    require(len(known) == len(template['actions']), '精确动作编号重复')
    events = []
    for row in spec['segments']:
        action = known.get(row['action_id'])
        require(action is not None and action.get('version') == VERSION, '实际控件动作或版本未在本海报精确契约登记')
        implementation = action.get('implementation', {})
        require(isinstance(implementation, dict) and implementation.get('path') == ACTION_SOURCE
                and implementation.get('consumer') == ACTION_CONSUMER
                and implementation.get('runtime_action_version') == row['action_version'] == RUNTIME_ACTION_VERSION
                and implementation.get('actual_selector') == {'style': 'poster', 'control': row['control'], 'variant': row['variant']},
                '实际控件、运行动作版本或来源选择器与精确契约不符')
        events.append({'id': row['id'], 'action_id': row['action_id'], 'runtime_action_version': row['action_version'],
                       'from_seconds': row['t0'], 'to_seconds': row['t1'], 'cues_seconds': deepcopy(row['cues'])})
    used = {row['action_id'] for row in events}
    require(events, '缺少实际消费的完整海报动作')
    if 'action_ids' in request:
        selected = request['action_ids']
        require(isinstance(selected, list) and all(isinstance(item, str) for item in selected)
                and len(selected) == len(set(selected)) and set(selected) == used,
                '动作编号须与实际控件完全对应，不能漏报或虚报动作')
    bindings = [deepcopy(known[key]) for key in known if key in used]
    profile = {**{key: spec[key] for key in ('width', 'height', 'fps')}, 'frames': normalized['frames']}
    binding = {'schema': 'haike.motion-replay-production-binding/1', 'template_id': TEMPLATE_ID, 'version': VERSION,
        'gallery_id': GALLERY_ID, 'production_contract': CONTRACT, 'implementation': IMPLEMENTATION,
        'source_identity': deepcopy(sources), 'action_bindings': deepcopy(bindings),
        'resolved_events': deepcopy(events), 'render_profile': deepcopy(profile)}
    consumer = deepcopy(value)
    receipts = consumer.setdefault('source_receipts', {})
    require(receipts.get('motion_replay') is None or receipts['motion_replay'] == binding,
            '输入已有其他模板、版本、源码或动作绑定；请保留原请求并重新按精确契约准备')
    receipts['motion_replay'] = deepcopy(binding)
    return {'status': 'prepared', 'implementation': IMPLEMENTATION, 'gallery_id': GALLERY_ID,
        'production_contract': CONTRACT, 'action_bindings': bindings, 'resolved_events': events,
        'render_profile': profile, 'replay_binding': binding,
        'binding_consumption': 'Producer freezes source_receipts.motion_replay into the real parent; fixed preflight resolves these actual controls and measured clocks. No project/job/media is created here.',
        'queue_admission': 'Fixed poster /3 prepare then common preview submission; preclaim and concrete current approval gate actual render.',
        'consumer': {'entrypoint': 'backlot.motion_public_poster_production_v3.prepare', 'input': consumer,
                     'requires_existing_queue': True, 'category': '动效模板'},
        'capability_boundaries': {'personal_motion_required': False, 'original_package_equivalence': False,
            'actual_poster_v3_visual_acceptance': 'pending actual version-specific preview and encoded output',
            'unchanged_renderer': 'Original HTML geometry/font/audio/clock; D candidate quote symbols only'},
        'submitted': False}
