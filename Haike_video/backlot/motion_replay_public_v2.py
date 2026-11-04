"""Read-only semantic contract for the five fixed public /2 implementations."""
from copy import deepcopy
from pathlib import Path

from backlot.motion_replay import ReplayError
from backlot.motion_public_io_v1 import WorkError

WORKSPACE = Path(__file__).resolve().parents[2]
VERSION = '1.0.0-public.2'
BINDINGS = {
    'template-01-integrated': ('observed-controls/2', 'observed-light', 'motion-package-mg-2150f84a4202e3ebd36a47fc'),
    'template-02-expanded': ('observed-controls/2', 'observed-paper', 'motion-package-mg-8c9df3f72e3cca9713485c4c'),
    'template-04-dark-console': ('observed-controls/2', 'observed-console', 'motion-package-mg-54f75c890e652d190cbfc8ec'),
    'vibrant-poster': ('observed-controls/2', 'observed-poster', 'motion-package-mg-bcf4d5995342cdffe345d140'),
    'template-03-native': ('dark-remotion/2', 'owned-dark-cobalt', 'motion-package-mg-0073456d9aef950f7548ca3e'),
}


def require(condition, message):
    if not condition:
        raise ReplayError(message)


def prepare(template, request, *, workspace):
    """Validate actual consumed actions; never creates a project, job or media."""
    require(Path(workspace).resolve() == WORKSPACE.resolve(), '请从同一海客源码副本调用动效准备入口')
    identity = template.get('template_id')
    require(identity in BINDINGS and template.get('version') == VERSION, '此公开组件精确版本尚未适配')
    engine, pack, gallery = BINDINGS[identity]
    require(template.get('gallery_id') == gallery, '公开组件须保持原canonical模板卡片身份')
    require(isinstance(request, dict) and not set(request) - {'workflow', 'input', 'action_ids', 'template_id', 'version'},
            '请按本版本input合同填写，不接受任意模块、命令或未开放参数')
    require(request.get('workflow', 'public-components-v2') == 'public-components-v2', '制作路线与精确公开组件版本不符')
    value = request.get('input')
    require(isinstance(value, dict) and value.get('reference_id') == identity
            and value.get('engine') == engine and value.get('pack_key') == pack,
            '模板、执行引擎与实际控件配方不匹配')
    require(isinstance(value.get('title'), str) and 0 < len(value['title'].strip()) <= 160, '制作输入须有明确的本期视频标题')
    try:
        work = Path(value.get('work_root', WORKSPACE/'.local/motion-public-work-v2')).resolve()
        require(work.is_relative_to((WORKSPACE/'.local').resolve()) and not work.is_symlink(),
                '作业缓存须位于本海客副本的私有目录内')
        from backlot.motion_public_production_v2 import preflight
        normalized = preflight(deepcopy(value))
    except WorkError as exc:
        raise ReplayError(str(exc)) from exc
    except (OSError, KeyError, TypeError) as exc:
        raise ReplayError('本期输入或固定运行组件不可读取，请核对原素材、ASR和对应组件后继续') from exc
    require(normalized.get('input_engine') == engine, '实际执行层返回了其他引擎，不能替代原效果')
    spec = normalized['spec']
    if engine == 'observed-controls/2':
        events = [{'id': row['id'], 'action_id': row['action_id'], 'runtime_action_version': row['action_version'],
                   'from_seconds': row['t0'], 'to_seconds': row['t1'], 'cues_seconds': row['cues']}
                  for row in spec['segments']]
        profile = {key: spec[key] for key in ('width', 'height', 'fps')}
    else:
        props = spec['props']
        events = [{'id': row['id'], 'action_id': 'haike.public-dark.'+row['group'],
                   'from_frame': row['from'], 'frames': row['frames'], 'cue_times_seconds': row.get('cueTimes', {})}
                  for row in props['scenes']]
        profile = {key: props[key] for key in ('width', 'height', 'fps')}
    known = {row['id']: row for row in template['actions']}
    used = {row['action_id'] for row in events}
    require(events and used <= set(known), '实际场景调用了本精确契约未登记的动作')
    if 'action_ids' in request:
        selected = request['action_ids']
        require(isinstance(selected, list) and all(isinstance(item, str) for item in selected)
                and len(selected) == len(set(selected)) and set(selected) == used,
                '动作编号须与实际场景控件完全对应，不能声明未消费动作或忽略既有动作')
    return {'status': 'prepared', 'implementation': 'haike.motion-public-execution/2',
        'gallery_id': gallery, 'production_contract': 'haike.motion-public-production/2',
        'action_bindings': [deepcopy(known[key]) for key in known if key in used],
        'resolved_events': events, 'render_profile': {**profile, 'frames': normalized['frames']},
        'contract_consumption': 'Actual preflight resolves control/variant or dark group into these action IDs. Composition/ASR owns order and timing; action_ids must match the consumed set.',
        'queue_admission': 'Fixed producer.prepare(queue,input), then common submit_frozen(preview) and explicit execute; render requires current concrete approval.',
        'consumer': {'entrypoint': 'backlot.motion_public_production_v2.prepare', 'input': deepcopy(value),
                     'requires_existing_queue': True, 'category': '动效模板'},
        'capability_boundaries': {'personal_motion_required': False, 'original_package_equivalence': False,
            'actual_public_v2_media_acceptance': 'pending per-version output evidence',
            'unchanged_renderers': 'Original HTML and Remotion implementations, with declared candidate repairs'},
        'submitted': False}
