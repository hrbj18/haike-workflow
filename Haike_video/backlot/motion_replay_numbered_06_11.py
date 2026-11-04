"""Read-only preparation of six real-video compositions and their original slots.

Formal 1.1.0 is a design release. Explicit preview profiles retain the authored
clock and support only original source-consumed slots; no queue submission occurs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backlot.motion_replay import ReplayError, source_path, verify_sources

BASE = 'Haike_video/templates/motion-replay-numbered-06-11'
PREVIEW = '.local/chromatic-six-video-batch'
IDS = {f'chromatic-{n:02}' if n < 10 else f'chromatic-six-{n}': n for n in range(6, 12)}


def _require(condition, message):
    if not condition:
        raise ReplayError(message)


def _json(path):
    try:
        _require(path.is_file() and path.stat().st_size < 4 * 1024 * 1024,
                 '缺少本机已验视频输入或清单，请恢复原预览资产')
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ReplayError('视频输入或身份清单不可读，请恢复原预览资产') from exc


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _checked_file(workspace, value, expected, *, base=None):
    # Old private manifests contain absolute paths. Constrain them to this
    # workspace; public contracts themselves always use repository-relative paths.
    root = workspace.resolve()
    candidate = Path(value)
    path = candidate if candidate.is_absolute() else (base or root) / candidate
    _require(not path.is_symlink() and path.resolve().is_relative_to(root),
             '本机视频身份路径越界，请恢复本副本的原始清单')
    _require(path.is_file() and _digest(path) == expected,
             '视频预览来源或素材已变化，必须定向重验后重新绑定')
    return path


def _asset_urls(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'src', 'fontSrc'} and isinstance(child, str):
                yield child
            else:
                yield from _asset_urls(child)
    elif isinstance(value, list):
        for child in value:
            yield from _asset_urls(child)


def prepare(template, request, *, workspace):
    """Return an actual ReplayNumbered component + original {episode, replay} props.

    Request fields: template_id/version/action_ids/profile/inputs. Only actual
    source-consumed content slots are accepted. Omitting profile preserves the formal HD/audio default
    and returns blockers, never a silent low-resolution fallback.
    """
    if template.get('template_id') == 'chromatic-06' and template.get('version') == '1.2.0-candidate.1':
        from backlot.motion_replay_chromatic_production import prepare_contract
        return prepare_contract(template, request, workspace=workspace)
    _require(isinstance(request, dict), '复刻输入必须是JSON对象')
    _require(set(request) <= {'template_id', 'version', 'action_ids', 'profile', 'inputs'},
             '该版本未开放该输入字段，请按受控episode槽传入')
    identity = template.get('template_id')
    _require(identity in IDS and template.get('version') == '1.1.0',
             '模板编号或版本未适配')
    _require(request.get('template_id', identity) == identity
             and request.get('version', '1.1.0') == '1.1.0', '复刻输入身份不一致')
    verify_sources(template, workspace=workspace)
    binding = _json(source_path(BASE + '/bindings.json', workspace))[identity]
    actions = request.get('action_ids', binding['actionIds'])
    _require(isinstance(actions, list) and all(isinstance(v, str) for v in actions)
             and len(actions) == len(set(actions)), '动作编号必须是无重复的字符串数组')
    _require(actions == binding['actionIds'],
             '本固定编排仅支持原动作全集及原顺序；删减、增添或重排动作待适配')
    _require([a['id'] for a in template['actions']] == binding['actionIds'],
             '动作合同与可调用包装不一致，请恢复同一适配版本')
    profile = request.get('profile', 'formal')
    _require(isinstance(profile, str) and profile in {'formal', 'historical_preview', 'controlled_preview'},
             'profile仅支持formal/historical_preview/controlled_preview')
    _require(profile == 'controlled_preview' or 'inputs' not in request,
             '本期替换输入必须显式使用controlled_preview')
    _require(profile != 'controlled_preview' or 'inputs' in request,
             'controlled_preview需要本期episode槽、素材来源清单与public_root')
    result = {
        'status': 'blocked', 'profile': profile,
        'entrypoint': BASE + '/Replay.tsx#ReplayNumbered',
        'action_bindings': [{**a['implementation'], 'id': a['id']} for a in template['actions']],
        'blockers': [], 'input_props': None,
        'reproduction': '见 ' + BASE + '/README.md；此接口只准备，不自动渲染或入队',
        'queue': {'supported': False, 'reason': '六套尚无注册生产处理器，不生成伪队列payload'},
    }
    if profile == 'formal':
        result['render_profile'] = _json(source_path(
            f'Haike_video/templates/chromatic-six-video-batch-v1/formal/{IDS[identity]:02}.json',
            workspace))['render_profile']
        result['blockers'] = [
            '正式1080p有声配置已冻结；高清原片绑定、完整音轨及真实ASR/同源人物适配尚未完成',
            '完整高清有声输出、混音、口型及生产队列尚未验收；不能执行历史静音入口冒充正式输出',
            '换稿、改时长和内部语义事件重排均待实现，不接受外层窗口等比缩放',
        ]
        return result

    preview = source_path(PREVIEW, workspace)
    manifest_path = _checked_file(workspace, str(preview / 'build-manifest.json'),
                                  template['local_reference']['manifest_sha256'])
    manifest = _json(manifest_path)
    _require(manifest.get('schema') == 'haike.six-real-video-build/1', '原预览构建身份无效')
    count = 0
    for group in ('sources', 'inputs', 'assets', 'outputs'):
        for row in manifest[group]:
            _checked_file(workspace, row['path'], row['sha256'], base=preview)
            count += 1
    _require(count == 301, '原预览301项身份数量不符')
    ep_path = _checked_file(workspace, str(preview / f'episodes/{IDS[identity]:02}.json'),
                            template['local_reference']['episode_sha256'])
    episode = _json(ep_path)
    _require(episode.get('durationInFrames') == 720 and episode.get('fps') == 30,
             '仅支持原24秒720帧参考输入')
    assets = {('/' + r['path']): r['sha256'] for r in manifest['assets']}
    for url in _asset_urls(episode):
        _require(url in assets, '输入含未绑定素材或外部地址')
    # Use the exact same family as the original aggregate Preview boot().
    episode['fontFamily'] = 'Haike Six Video'
    asset_info = {'public_root': PREVIEW, 'font_url': episode['fontSrc'],
                  'font_family': 'Haike Six Video', 'font_load_required': True}
    if profile == 'controlled_preview':
        from backlot.motion_replay_numbered_06_11_inputs import apply_inputs
        episode, asset_info = apply_inputs(episode, request['inputs'], IDS[identity], workspace=workspace)
    result.update(status='prepared', blockers=[], input_props={
        'episode': episode,
        'replay': {'templateId': identity, 'version': '1.1.0', 'actionIds': actions},
    }, render_profile={'width': 720, 'height': 1280, 'fps': 30,
                       'durationInFrames': 720, 'silent': True},
        assets=asset_info,
        local_verification={'historical_manifest_entries': count,
                            'episode_sha256': _digest(ep_path)},
        validation_scope=('本期已开放槽预览，需重新检查字幕、裁切及内容运动；未做视觉验收'
                          if profile == 'controlled_preview' else '历史低清静音参考复现；不代表高清有声或生产就绪'),
        output_validation={'status':'pending' if profile=='controlled_preview' else 'reference_only',
                           'scope':'任何本期输入变更不继承历史视觉/听审验收'})
    return result
