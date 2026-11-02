"""Public versioned recipes. Episode inputs and personal envelopes stay local.

These recipes author through the existing MotionGit draft/freeze/queue contract.
They never import a developer draft or inherit a previous episode's approval.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from backlot import studio_motiongit as motion
from backlot.work_catalog import WorkError, sha

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'Haike_video/templates/motion-presets'
SCHEMA = 'haike.motion-presets/1'


def manifest():
    path = FOLDER / 'manifest.json'
    motion.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= motion.MAX_DOCUMENT,
                   '正式模板清单缺失，请修复本次程序更新')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        motion.require(isinstance(value, dict) and value.get('schema') == SCHEMA
                       and isinstance(value.get('presets'), list) and 0 < len(value['presets']) <= 100,
                       '正式模板清单格式无效')
        seen = set()
        for row in value['presets']:
            motion.require(isinstance(row, dict) and isinstance(row.get('id'), str)
                           and re.fullmatch(r'[a-z0-9-]{4,80}', row['id']) and row['id'] not in seen
                           and re.fullmatch(r'\d+\.\d+\.\d+', row.get('version', ''))
                           and re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')),
                           '正式模板清单身份重复或无效')
            seen.add(row['id'])
            recipe = row.get('recipe')
            motion.require(isinstance(recipe, str) and re.fullmatch(r'[a-z0-9-]+\.json', recipe),
                           '正式模板参数位置无效')
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise WorkError('正式模板清单无法读取，请修复本次程序更新') from exc


def load(identity):
    row = next((v for v in manifest()['presets'] if v['id'] == identity), None)
    motion.require(row is not None, '正式预设不存在，请刷新模板库')
    path = FOLDER / row['recipe']
    motion.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= motion.MAX_DOCUMENT
                   and sha(path) == row['sha256'], '正式预设文件缺失或已改变，请修复本次程序更新')
    try:
        recipe = json.loads(path.read_text(encoding='utf-8'))
        motion.require(recipe.get('schema') == 'haike.motion-preset-recipe/1'
                       and isinstance(recipe.get('parameters'), dict) and isinstance(recipe.get('binding'), dict),
                       '正式预设结构无效')
    except (ValueError, TypeError, AttributeError) as exc:
        raise WorkError('正式预设结构无效') from exc
    return deepcopy(row), recipe


def _resolve(row, package_id=None):
    """Match the current user's verified envelope, never the author's envelope ID."""
    expected = row['package']
    if not row['requires_package']:
        package = motion._get('packages', expected['template_id'])
        motion.require(package_id in {None, package['id']}, '此预设使用项目内置模板')
        return package
    with motion._db() as db:
        records = db.execute('SELECT data FROM packages ORDER BY rowid DESC').fetchall()
    for record in records:
        value = json.loads(record[0])
        if package_id is not None and value['id'] != package_id:
            continue
        if ((value.get('template_id'), value.get('version'), value.get('helper_version'))
                != (expected['template_id'], expected['version'], expected['helper_version'])):
            continue
        if value.get('verification') != 'verified' or row['workflow'] not in value.get('workflows', {}):
            continue
        value = motion._get('packages', value['id'])
        motion.require(Path(value['path']).is_file() and sha(value['path']) == value['sha256'],
                       '本机原包已改变，请重新导入并验签自己的合法原包')
        helper = Path(value.get('helper', ''))
        motion.require(helper.is_file() and sha(helper) == motion.helper_identity(value)['sha256'],
                       '原包执行工具缺失或已改变，请重新核验本机原包')
        return value
    raise WorkError('请导入并核验自己的合法原包：' + expected['template_id'] + '@' + expected['version'])


def catalog():
    rows = []
    for entry in manifest()['presets']:
        row, recipe = load(entry['id'])
        try:
            package = _resolve(row)
            row.update(can_create=True, package_id=package['id'], status='needs-inputs',
                       message='可以创建；请绑定本期声音、真实字幕、素材和时间安排')
        except WorkError as exc:
            row.update(can_create=False, status='needs-package', message=str(exc))
        row['binding'] = recipe['binding']
        rows.append(row)
    return {'schema': SCHEMA, 'manifest_sha256': sha(FOLDER / 'manifest.json'), 'presets': rows}


def _merge(base, patch):
    if isinstance(base, dict) and isinstance(patch, dict):
        return {k: _merge(base.get(k), v) for k, v in patch.items()} | {
            k: deepcopy(v) for k, v in base.items() if k not in patch}
    return deepcopy(patch)


def _mechanisms(row, p):
    """Creation retains the named preset. Subsequent editing remains explicit."""
    if row['protocol'] == 'hum-production-v1':
        props = p.get('props', {}); scenes = props.get('scenes', [])
        kinds = ['comment', 'ranking', 'world', 'media', 'path', 'path', 'clear']
        motion.require(props.get('visualStyle') == 'quest' and (props.get('width'), props.get('height')) == (1080, 1920)
                       and [s.get('quest', {}).get('kind') for s in scenes] == kinds,
                       '定稿预设需保留9:16七镜动作；其他编排请另建模板变体')
        motion.require([s.get('theme') for s in scenes] == ['paper', 'dark', 'paper', 'paper', 'paper', 'dark', 'paper']
                       and [s['quest'].get('transition') for s in scenes] == [None, 'checker', 'iris', None, None, 'checker', 'iris'],
                       '定稿预设需保留白底至深色的路径接力和原转场')
        a, b = scenes[4]['quest'], scenes[5]['quest']
        motion.require(a.get('path', {}).get('id') and a.get('path', {}).get('id') == b.get('path', {}).get('id')
                       and a.get('items') == b.get('items') and not b.get('path', {}).get('reset'),
                       '定稿路径需使用同一编号和节点，不能重置')
        motion.require(len(scenes[0]['quest'].get('comment', {}).get('photoIds', [])) == 3
                       and len(scenes[6]['quest'].get('photoIds', [])) == 5
                       and all(scenes[i].get('mediaId') for i in [2, 3, 4, 5]),
                       '定稿预设需保留提问证据、旁窗和五照片收尾')
    elif row['protocol'] == 'motion-kit':
        t = p.get('timeline', {}); segments = t.get('segments', [])
        motion.require(t.get('layout') == 'portrait' and t.get('styleProfile') == 'paper'
                       and [(s.get('control'), s.get('variant')) for s in segments] == [
                           ('compare', 'panels'), ('kinetic', 'stack'), ('device', 'phone'),
                           ('device', 'phone'), ('quote', 'reveal'), ('cta', 'button')],
                       '纸感预设需保留六段原生控件及引用揭示')
        if row['version'] != '1.0.0':
            from backlot.paper_evidence import PROFILE
            motion.require(isinstance(p.get('paperSupport'), dict) and p['paperSupport'].get('profile') == PROFILE,
                           '纸感新版需保留通用证据层；请按本期台词绑定真实素材')
    else:
        motion.require(p.get('creationProfile') == 'knowledge-story/1' and p.get('layout') == 'portrait'
                       and [s.get('family') for s in p.get('segments', [])] == [
                           'sketchnote.keyword-annotation', 'sketchnote.step-sequence'],
                       '点阵预设需保留关键词手绘与步骤接力')


def create(identity, *, parameters=None, title=None, package_id=None):
    row, recipe = load(identity)
    motion.require(parameters is None or isinstance(parameters, dict), '本期参数须为JSON对象')
    package = _resolve(row, package_id)
    p = deepcopy(recipe['parameters']) if parameters is None else _merge(recipe['parameters'], parameters)
    try:
        _mechanisms(row, p)
    except (TypeError, AttributeError, KeyError) as exc:
        raise WorkError('本期参数结构无效，请按正式预设绑定') from exc
    if parameters is not None:
        motion.validate_parameters(package, row['workflow'], p)
    source = {'id': row['id'], 'version': row['version'], 'recipe_sha256': row['sha256'],
              'schema': 'haike.motion-preset-source/1', 'manifest_sha256': sha(FOLDER / 'manifest.json')}
    return motion.save_draft(package['id'], row['workflow'], p, title=title or row['name'], preset_source=source)


def check_binding(value):
    """An editable scaffold is not a render-ready episode or a passed review."""
    p = value['parameters']
    if value['workflow'] == 'hum-production':
        props = p.get('props', {})
        scenes = props.get('scenes', [])
        motion.require(isinstance(scenes, list) and scenes and all(isinstance(s, dict)
                       and type(s.get('from')) is int and type(s.get('frames')) is int and s['frames'] > 0 for s in scenes),
                       '正式预设待绑定：请按本期真实字幕填写每镜开始帧和持续帧数')
        motion.require(props.get('captions') and p.get('provenance', {}).get('voice')
                       and p.get('provenance', {}).get('captions'),
                       '正式预设待绑定：请提供本期完整口播、真实字幕及同源证据')
    elif value['workflow'] == 'motion-kit':
        t = p.get('timeline', {})
        source = value.get('preset_source', {})
        if source.get('id') == 'paper-approved-portrait-v1' and source.get('version') != '1.0.0':
            from backlot.paper_evidence import PROFILE
            motion.require(isinstance(p.get('paperSupport'), dict) and p['paperSupport'].get('profile') == PROFILE,
                           '纸感新版需保留通用证据层；请按本期台词绑定真实素材')
        motion.require(t.get('duration') and t.get('captions') and t.get('narrationMap')
                       and all('t0' in s and 't1' in s for s in t.get('segments', [])),
                       '正式预设待绑定：请填写本期完整时长、真实字幕和逐镜口播归属')
    else:
        motion.require(p.get('durationSeconds') and p.get('script') and p.get('captions')
                       and p.get('sentenceEvidence', {}).get('audioSha256')
                       and all('start' in s and 'end' in s for s in p.get('segments', [])),
                       '正式预设待绑定：请填写本期声音时钟、真实字幕和句级证据')


def delivery_files():
    """Release tooling uses this exact set, including the transport and UI caller."""
    names = {'Haike_video/templates/motion-presets/manifest.json',
             'Haike_video/backlot/studio_motion_presets.py', 'Haike_video/backlot/studio_motiongit.py',
             'Haike_video/backlot/studio_motiongit_api.py', 'Haike_video/scripts/motiongit.py'}
    for row in manifest()['presets']:
        load(row['id'])
        names.add('Haike_video/templates/motion-presets/' + row['recipe'])
        names.update(row['engine_files'])
    result = {}
    for name in sorted(names):
        path = ROOT / name
        motion.require(path.is_file() and not path.is_symlink(), '模板执行文件缺失：' + name)
        result[name] = sha(path)
    return result


def capability_identity():
    files = delivery_files()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'schema': 'haike.motion-capability/1', 'sha256': digest, 'files': files,
            'presets': [{k: r[k] for k in ['id', 'version', 'sha256', 'protocol', 'requires_package']}
                        for r in manifest()['presets']]}
