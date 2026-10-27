"""Private MotionGit intake and versioned editing; package documents are data.

Import never executes package code. Only an independently pinned official helper
can verify/read a personal envelope. Unknown runtimes stay inspectable, not runnable.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import urllib.request
import zipfile

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / '.local/motiongit'
MAX_PACKAGE = 386 * 1024 * 1024
MAX_DOCUMENT = 2 * 1024 * 1024
HELPER_VERSION = '1.0.0-rc.50'
HELPER_SHA = '7004609ddbc0ccf6451beeb477aff0d3c85bda74f902e5922465c85cd347f6f3'
HELPER_BYTES = 836994
METADATA_URL = 'https://motiongit.com/assets/motion-runtimes/1.0.0-rc.50.json'


def require(condition, message):
    if not condition:
        raise WorkError(message)


def _db():
    STORE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STORE / 'registry.sqlite3', timeout=30)
    db.execute('CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS assets(draft_id TEXT, slot TEXT, data TEXT NOT NULL, PRIMARY KEY(draft_id,slot))')
    db.execute('CREATE TABLE IF NOT EXISTS productions(draft_id TEXT, render_id TEXT, data TEXT NOT NULL, PRIMARY KEY(draft_id,render_id))')
    return db


def _id(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-z0-9-]{4,80}', value), '编号无效')
    return value


def _get(table, identity):
    _id(identity)
    with _db() as db:
        row = db.execute(f'SELECT data FROM {table} WHERE id=?', (identity,)).fetchone()
    require(row is not None, '模板包或草稿不存在')
    value = json.loads(row[0])
    if table == 'packages':
        _hum_workflow(value)
    return value


def _put_package(value):
    with _db() as db:
        db.execute('INSERT OR REPLACE INTO packages VALUES(?,?)', (value['id'], json.dumps(value, ensure_ascii=False)))


def _json_entry(archive, name):
    info = archive.getinfo(name)
    require(info.file_size <= MAX_DOCUMENT, '模板说明文件过大')
    value = json.loads(archive.read(info).decode('utf-8-sig'))
    require(isinstance(value, dict), '模板说明须为JSON对象')
    return value


def inspect_package(path):
    """Bounded, read-only ZIP inspection. No extraction, keys, imports or shell."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_PACKAGE, '请选择386MiB以内的.motion包')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            require(len(entries) <= 5000, '模板包文件数过多')
            names = [i.filename for i in entries]
            require(len(set(n.casefold() for n in names)) == len(names), '模板包包含重复或大小写冲突路径')
            for item in entries:
                n = item.filename
                require('\\' not in n and not n.startswith('/') and ':' not in n
                        and '..' not in PurePosixPath(n).parts
                        and ((item.external_attr >> 16) & 0o170000) != 0o120000, '模板包包含不安全路径或链接')
            require('motion.json' in names, '模板包缺少motion.json')
            manifest = _json_entry(archive, 'motion.json')
            require(manifest.get('format') == 'motiongit-template', '不是MotionGit模板包')
            guide = _json_entry(archive, 'assistant/guide.json') if 'assistant/guide.json' in names else {}
            personal = manifest.get('packageProfile') == 'personal-download-v1'
            known = (personal and manifest.get('specVersion') == '1.0.0-rc.1'
                     and manifest.get('runtime', {}).get('profile') == 'motiongit-host/1')
            template = guide.get('template') or manifest.get('template') or {}
            result = {'filename': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path),
                      'name': str(template.get('name') or path.stem)[:200],
                      'version': str(template.get('version') or '未声明')[:80],
                      'template_id': str(template.get('id') or 'unknown')[:120],
                      'runtime': manifest.get('runtime', {}).get('profile'), 'spec_version': manifest.get('specVersion'),
                      'personal': personal, 'protection': manifest.get('content', {}).get('protection'),
                      'verification': 'pending', 'runnable': False,
                      'support': 'official-helper' if known else 'inspection-only',
                      'workflows': {}, 'entry_count': len(entries)}
            if known:
                require('assistant/motion.mjs' in names, '个人包缺少随包入口')
                info = archive.getinfo('assistant/motion.mjs')
                if info.file_size != HELPER_BYTES or hashlib.sha256(archive.read(info)).hexdigest() != HELPER_SHA:
                    result['support']='inspection-only'
                    result['support_note']='随包入口不在已核验版本内；已保留原包，只读分析，不执行。'
            # An open format is inspectable without becoming an executable plugin.
            if not personal:
                for key, fallback in [('parameters', 'params.schema.json')]:
                    name = manifest.get(key, {}).get('schema', fallback)
                    if name in names:
                        result['workflows']['native'] = {'schema': _json_entry(archive, name), 'controls': {}}
            return result
    except (zipfile.BadZipFile, KeyError, UnicodeError, ValueError, TypeError) as exc:
        raise WorkError('模板包结构或JSON无效，请保留原文件重新核对') from exc


def import_package(path, *, filename=None):
    value = inspect_package(path)
    if filename:
        value['filename']=Path(filename).name[:200]
    identity = 'mg-' + value['sha256'][:24]
    with _db() as db:
        row = db.execute('SELECT data FROM packages WHERE id=?', (identity,)).fetchone()
    if row:
        previous = json.loads(row[0])
        require(Path(previous['path']).is_file() and sha(previous['path']) == value['sha256'], '已导入原包缺失或已改变')
        return public_package(previous)
    folder = STORE / 'packages' / identity
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'original.motion'
    if target.exists():
        require(sha(target) == value['sha256'], '原包保存位置已有不同文件')
    else:
        shutil.copyfile(path, target)
    require(sha(target) == value['sha256'], '原包复制校验失败')
    value.update(id=identity, path=str(target.resolve()))
    _put_package(value)
    return public_package(value)


def public_package(value):
    _hum_workflow(value)
    fields={'id','filename','bytes','sha256','name','version','template_id','runtime','spec_version','personal',
            'protection','verification','runnable','support','support_note','workflows','entry_count'}
    result={k: v for k, v in value.items() if k in fields}
    if 'project-wall' in result.get('workflows',{}):
        result['workflows']['project-wall']['schema']=_project_schema()
    return result


def _hum_workflow(value):
    """Expose the independently authored adapter on already-verified originals."""
    if value.get('verification') == 'verified' and value.get('template_id') == 'motiongit-promo-user':
        value.setdefault('workflows', {})['hum-production'] = {
            'schema': _hum_schema(), 'controls': {}, 'description': '完整口播可复用模板 · Hum / Coral',
            'implementation': 'hum-production-v1',
            'scope': '4:5 / 30fps；完整口播自动时长；素材墙/聚焦/大窗/小窗/不出镜；本地配乐音效'}


def packages():
    with _db() as db:
        values = db.execute('SELECT data FROM packages ORDER BY rowid DESC').fetchall()
    return {'packages': [public_package(json.loads(row[0])) for row in values]}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def verified_helper(value):
    require(value['support'] == 'official-helper', '此版本目前支持只读分析，尚未适配运行')
    package = Path(value['path'])
    require(package.is_file() and sha(package) == value['sha256'], '原包身份已变化')
    # Fixed official origin + independent digest; never a URL or trust root from a package.
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(METADATA_URL, timeout=30) as response:
        require(response.geturl() == METADATA_URL, '官方工具元数据发生跳转')
        raw = response.read(16385)
    require(len(raw) <= 16384, '官方工具元数据过大')
    metadata = json.loads(raw)
    require(metadata.get('sha256') == HELPER_SHA and metadata.get('bytes') == HELPER_BYTES
            and metadata.get('helperVersion') == HELPER_VERSION, '官方工具身份与已支持版本不一致')
    target = STORE / 'tools' / HELPER_VERSION / 'motion.mjs'
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with zipfile.ZipFile(package) as archive:
            content = archive.read('assistant/motion.mjs')
        require(len(content) == HELPER_BYTES and hashlib.sha256(content).hexdigest() == HELPER_SHA, '随包工具身份不符')
        with target.open('xb') as output:
            output.write(content)
    require(sha(target) == HELPER_SHA, '本地官方工具身份已变化')
    return target


def helper_command(value, *args, timeout=180):
    helper = Path(value['helper'])
    require(helper.is_file() and sha(helper) == HELPER_SHA, '官方工具未核验或已变化')
    require(sha(value['path']) == value['sha256'], '原包已变化')
    node = shutil.which('node')
    require(node is not None, '需要Node.js 22或更新版本')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    try:
        result = subprocess.run([node, str(helper), args[0], value['path'], *map(str, args[1:])],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                                env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise WorkError('模板步骤超时，原工程保留；请恢复原步骤') from exc
    # Output stays private. Do not expose upstream errors with local paths/tokens over HTTP.
    log = STORE / 'packages' / value['id'] / 'last-operation.log'
    log.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    require(result.returncode == 0, '模板步骤未通过，请检查本机操作记录并从原工程恢复')
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except ValueError:
        # Dependency installers may precede their JSON result with progress lines.
        for line in reversed(result.stdout.splitlines()):
            if line.startswith('{'):
                try: return json.loads(line)
                except ValueError: continue
        return {'output_recorded_privately': True}


def _read_public(value, name):
    require(isinstance(name, str) and not name.startswith(('personal/', 'content/')) and '..' not in name
            and name.endswith(('.json', '.md')), '仅允许声明的公开说明文档')
    document = helper_command(value, 'read', name)
    require(len(json.dumps(document)) <= 8 * MAX_DOCUMENT, '公开说明过大')
    return document.get('content', document)


def verify_package(identity):
    value = _get('packages', identity)
    value['helper'] = str(verified_helper(value))
    started = helper_command(value, 'start', '--summary')
    require(started.get('verified') is True, '模板个人封套验签未通过')
    entry = started.get('productionEntry') or {}
    guide = _read_public(value, entry.get('guide', 'guide.json'))
    schema = _read_public(value, entry.get('parameterSchema', 'params.schema.json'))
    workflows = {'native': {'schema': schema, 'controls': {}, 'description': '原生参数路线'}}
    component = guide.get('componentMode') or {}
    if component.get('timelineSchema') and component.get('guide'):
        component_guide = _read_public(value, component['guide'])
        component_schema = _read_public(value, component['timelineSchema'])
        control_path = component_guide.get('controlContract')
        spec = _read_public(value, control_path) if control_path else {}
        workflows['poster-kit'] = {'schema': component_schema, 'controls': spec.get('controls', {}),
                                   'description': component_guide.get('fit', {}).get('style', '组件时间线'),
                                   'guide': component_guide, 'transitions': spec.get('transitions', [])}
    if value['template_id'] == 'motiongit-promo-user':
        workflows['project-wall'] = {'schema': _project_schema(), 'controls': {},
            'description': '项目内可编辑素材墙', 'implementation': 'motiongit-narrated-pilot-v1',
            'scope': '1440×1800/30fps/20秒；自有动效实现；保持原包独立'}
    value.update(verification='verified', runnable=True, workflows=workflows)
    value['documents'] = {'guide': guide}
    _put_package(value)
    return public_package(value)


def validate_parameters(package, workflow, parameters):
    import jsonschema
    require(workflow in package['workflows'], '模板未声明此工作流')
    require(isinstance(parameters, dict), '参数须为JSON对象')
    if workflow == 'project-wall':
        from backlot.studio_motiongit_narrated_pilot import validate_props
        validate_props(parameters)
        return {'valid': True, 'scope': 'project-template-structure', 'runtime_validation': 'pending-source-receipts'}
    if workflow == 'hum-production':
        require(not set(parameters) - {'props', 'audio', 'provenance', 'shotPlan'}
                and isinstance(parameters.get('props'), dict) and isinstance(parameters.get('audio'), dict)
                and isinstance(parameters.get('provenance'), dict), '完整口播模板须有props、audio、provenance')
        require(('scenes' in parameters['props']) != ('shotPlan' in parameters), '固定场景和自动shotPlan须选一种')
        from backlot.studio_hum_production import _name
        require(_name(parameters['audio'].get('voice')) and parameters['props'].get('visualStyle') in {'hum', 'coral'}, '口播绑定名或视觉风格无效')
        return {'valid': True, 'scope': 'speech-clock-draft-structure', 'runtime_validation': 'pending-bound-source-preflight'}
    schema = package['workflows'][workflow]['schema']
    # Remote references are not implicit network permission. Real local refs remain available.
    def check_refs(obj):
        if isinstance(obj, dict):
            require(not ('$ref' in obj and not str(obj['$ref']).startswith('#')), '此schema的外部引用尚未接入')
            for v in obj.values(): check_refs(v)
        elif isinstance(obj, list):
            for v in obj: check_refs(v)
    check_refs(schema)
    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = sorted(validator.iter_errors(parameters), key=lambda e: str(list(e.path)))
    require(not errors, '参数不符合模板契约：' + ('/'.join(map(str, errors[0].path)) + ' ' + errors[0].message[:350] if errors else ''))
    if workflow == 'poster-kit':
        controls = package['workflows'][workflow]['controls']
        previous = 0
        for segment in parameters['segments']:
            require(segment['control'] in controls, '控件尚未在此包声明')
            control = controls[segment['control']]
            require(previous <= segment['t0'] < segment['t1'] <= parameters['duration'], '场景重叠或超出时间线')
            require(segment['t1'] - segment['t0'] + .001 >= control.get('minDur', 0), '场景短于控件最短时长')
            require(not segment.get('variant') or segment['variant'] in control.get('variants', []), '控件变体未声明')
            for key, field in control.get('props', {}).items():
                require(not field.get('required') or key in segment['props'], '控件缺少字段：' + key)
            previous = segment['t1']
    return {'valid': True, 'scope': 'schema-and-control-structure', 'runtime_validation': 'pending'}


def save_draft(identity, workflow, parameters, *, draft_id=None, revision=0, title='新视频', output_profile='native', art_direction=None):
    package = _get('packages', identity)
    require(workflow in package['workflows'], '请先核验模板并选择已声明工作流')
    require(isinstance(parameters, dict) and isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0,
            '草稿参数或版本无效')
    require(output_profile in {'native','4:5'}, '输出画幅无效')
    require(len(json.dumps(parameters, ensure_ascii=False).encode()) <= MAX_DOCUMENT, '草稿参数过大')
    from uuid import uuid4
    draft_id = _id(draft_id or 'mgd-' + uuid4().hex)
    value = {'id': draft_id, 'package_id': identity, 'package_sha256': package['sha256'], 'workflow': workflow,
             'parameters': parameters, 'revision': revision + 1, 'title': str(title)[:160], 'output_profile':output_profile}
    if art_direction is not None:
        from backlot.studio_art_direction import normalize_selection
        value['art_direction'] = normalize_selection(art_direction)
    with _db() as db:
        if revision == 0:
            try:
                db.execute('INSERT INTO drafts VALUES(?,?,?)', (draft_id, 1, json.dumps(value, ensure_ascii=False)))
            except sqlite3.IntegrityError as exc:
                raise WorkError('草稿已存在，请读取当前版本') from exc
        else:
            old = db.execute('SELECT data FROM drafts WHERE id=? AND revision=?', (draft_id, revision)).fetchone()
            require(old and json.loads(old[0])['package_id'] == identity, '草稿已更新或模板身份不同，请重新读取')
            if art_direction is None and 'art_direction' in json.loads(old[0]):
                value['art_direction'] = json.loads(old[0])['art_direction']
            count = db.execute('UPDATE drafts SET revision=?,data=? WHERE id=? AND revision=?',
                               (revision + 1, json.dumps(value, ensure_ascii=False), draft_id, revision)).rowcount
            require(count == 1, '草稿已更新，请重新读取')
    return value


def draft(identity):
    return _get('drafts', identity)


def draft_list():
    with _db() as db:
        rows = db.execute('SELECT data FROM drafts ORDER BY rowid DESC').fetchall()
    return {'drafts': [json.loads(row[0]) for row in rows]}


def clone_draft(identity):
    """Reuse a complete film layout while preserving the original draft/version."""
    old=draft(identity)
    new=save_draft(old['package_id'],old['workflow'],old['parameters'],title=old['title']+' · 副本',
                   output_profile=old.get('output_profile','native'),art_direction=old.get('art_direction'))
    folder=STORE/'drafts'/new['id']/'inputs';folder.mkdir(parents=True,exist_ok=True)
    for asset in asset_list(identity)['assets']:
        source=STORE/'drafts'/identity/'inputs'/asset['name']
        require(source.is_file() and sha(source)==asset['sha256'],'原草稿素材已变化')
        target=folder/asset['name']
        if not target.exists():
            try: os.link(source,target)
            except OSError: shutil.copyfile(source,target)
        require(sha(target)==asset['sha256'],'复制草稿素材校验失败')
        with _db() as db:
            db.execute('INSERT INTO assets VALUES(?,?,?)',(new['id'],asset['slot'],json.dumps(asset,ensure_ascii=False)))
    return new


def validate_draft(identity):
    value = draft(identity)
    package = _get('packages', value['package_id'])
    require(value['package_sha256'] == package['sha256'], '草稿模板身份不一致')
    return validate_parameters(package, value['workflow'], value['parameters'])


def save_asset(draft_id, filename, content):
    draft(draft_id)
    require(0 < len(content) <= MAX_PACKAGE, '素材为空或超过386MiB')
    suffix = Path(filename).suffix.lower()
    require(suffix in {'.mp4', '.mov', '.m4v', '.webm', '.jpg', '.jpeg', '.png', '.webp', '.wav', '.mp3', '.m4a', '.srt', '.json', '.ttf', '.otf'}, '不支持此素材类型')
    name = hashlib.sha256(content).hexdigest() + suffix
    folder = STORE / 'drafts' / draft_id / 'inputs'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if not target.exists():
        with target.open('xb') as output: output.write(content)
    require(sha(target) == hashlib.sha256(content).hexdigest(), '素材身份不一致')
    original = Path(filename).name[:160]
    result = {'name': name, 'slot': original, 'original_name': original, 'bytes': len(content), 'sha256': sha(target)}
    with _db() as db:
        db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?)', (draft_id, original, json.dumps(result, ensure_ascii=False)))
    return result


def asset_list(draft_id):
    draft(draft_id)
    with _db() as db:
        rows = db.execute('SELECT data FROM assets WHERE draft_id=? ORDER BY slot', (draft_id,)).fetchall()
    return {'assets': [json.loads(r[0]) for r in rows]}


def _project_schema():
    """Form description; authoritative validation stays in the production adapter."""
    example = json.loads((ROOT / 'Haike_video/templates/motiongit-narrated-pilot-v1/props.example.json').read_text(encoding='utf-8'))
    for scene in example['scenes']:
        if scene['module']=='select':
            scene['module']='wall';scene.pop('secondaryMediaId',None)
            scene['wallMediaIds']=[m['id'] for m in example['media']]
    def shape(value):
        if isinstance(value, dict): return {'type':'object','properties':{k:shape(v) for k,v in value.items()}}
        if isinstance(value, list): return {'type':'array','items':shape(value[0]) if value else {}}
        if isinstance(value, bool): return {'type':'boolean'}
        if isinstance(value, (int,float)): return {'type':'number'}
        return {'type':'string'}
    schema = shape(example)
    schema['properties']['wallCategories']={'type':'array','items':{'type':'string','maxLength':8},'maxItems':6,'minItems':1}
    schema['properties']['visualStyle']={'type':'string','title':'视频视觉风格','enum':['original','hum'],
                                       'enumTitles':['原版素材墙','Hum亲子剪纸']}
    schema['default'] = example
    scene = schema['properties']['scenes']['items']['properties']
    scene['module'] = {'enum':['statement','select','focus','wall']}
    scene['theme'] = {'enum':['paper','dark']}
    scene['wallMediaIds'] = {'type':'array','items':{'type':'string'}}
    scene['secondaryMediaId']={'type':'string'}
    return schema


def _hum_schema():
    """Editable input shape; precise source/clock gates live in the new adapter."""
    example = {'props': {'brand': '海客', 'footer': '欢迎来店体验', 'visualStyle': 'hum',
        'fontAssets': {'display': 'display.ttf', 'body': 'body.ttf'},
        'media': [{'id': 'material-' + str(i), 'src': 'material-' + str(i) + '.mp4', 'thumbnail': 'material-' + str(i) + '.jpg',
                   'offset': 0, 'fit': 'contain', 'orientation': 'landscape', 'label': '门店实拍'} for i in range(1, 5)],
        'captions': [{'text': '替换为实际口播字幕', 'startMs': 0, 'endMs': 1000}]},
        'audio': {'voice': 'voice.wav', 'music': 'music.wav', 'musicGainDb': -16, 'loopMusic': False, 'tailSeconds': .25, 'sfx': []},
        'shotPlan': [{'id': 'wall', 'module': 'wall', 'theme': 'paper', 'title': '来看看现场', 'subtitle': '亲手体验，慢慢了解',
                      'mediaId': 'material-1', 'wallMediaIds': ['material-' + str(i) for i in range(1, 5)], 'weight': 2},
                     {'id': 'ending', 'module': 'statement', 'theme': 'paper', 'title': '欢迎来店体验', 'subtitle': '', 'weight': 1}],
        'provenance': {'voice': {'sha256': '', 'source': '', 'authorized': True}, 'captions': {'voice_sha256': '', 'method': ''}, 'audio': {}, 'media': [], 'presenterClips': []}}
    def shape(value):
        if isinstance(value, dict): return {'type': 'object', 'properties': {k: shape(v) for k, v in value.items()}}
        if isinstance(value, list): return {'type': 'array', 'items': shape(value[0]) if value else {}}
        if isinstance(value, bool): return {'type': 'boolean'}
        if isinstance(value, (int, float)): return {'type': 'number'}
        return {'type': 'string'}
    schema = shape(example)
    schema['default'] = example
    schema['properties']['props']['properties']['visualStyle'] = {'type': 'string', 'enum': ['hum', 'coral'], 'enumTitles': ['Hum亲子剪纸', 'Coral温暖棉纸']}
    return schema


def freeze_project_draft(queue, draft_id):
    value = draft(draft_id)
    if value['workflow'] == 'hum-production':
        return freeze_hum_draft(queue, draft_id)
    require(value['workflow'] == 'project-wall', '此草稿请使用其原生适配路线')
    validate_draft(draft_id)
    from backlot import studio_motiongit_narrated_pilot as adapter
    indexed = {a['slot']:a for a in asset_list(draft_id)['assets']}
    sources = {}
    for slot in adapter._required_names(value['parameters']):
        require(slot in indexed, '素材墙缺少已绑定文件：' + slot)
        asset = indexed[slot]
        path = STORE / 'drafts' / draft_id / 'inputs' / asset['name']
        require(path.is_file() and sha(path) == asset['sha256'], '绑定素材已变化：' + slot)
        sources[slot] = str(path)
    request=adapter.prepare(queue, value['parameters'], sources, value['title'])
    track_production(value,request)
    return request


def freeze_hum_draft(queue, draft_id):
    from copy import deepcopy
    from backlot import studio_hum_production as adapter
    value = draft(draft_id)
    require(value['workflow'] == 'hum-production', '不是完整口播复用模板草稿')
    validate_draft(draft_id)
    parameters = deepcopy(value['parameters'])
    indexed = {a['slot']: a for a in asset_list(draft_id)['assets']}
    sources = {}
    for slot in adapter._required_names(parameters['props'], parameters['audio']):
        require(slot in indexed, '完整口播模板缺少绑定文件：' + slot)
        asset = indexed[slot]
        path = STORE / 'drafts' / draft_id / 'inputs' / asset['name']
        require(path.is_file() and sha(path) == asset['sha256'], '完整口播绑定文件已改变：' + slot)
        sources[slot] = str(path.resolve())
    request = adapter.prepare(queue, {**parameters, 'title': value['title'], 'sources': sources})
    track_production(value, request)
    return request


def track_production(value,request):
    record={'project_id':request['project_id'],'render_id':request['render_id'],'revision':value['revision'],
            'contract':request['contract'],'request_sha256':request['request_sha256']}
    with _db() as db:
        db.execute('INSERT OR IGNORE INTO productions VALUES(?,?,?)',(value['id'],request['render_id'],json.dumps(record)))


def productions(draft_id):
    value=draft(draft_id)
    with _db() as db:
        rows=db.execute('SELECT data FROM productions WHERE draft_id=? ORDER BY rowid DESC',(draft_id,)).fetchall()
    return {'productions':[json.loads(r[0]) for r in rows if json.loads(r[0])['revision']==value['revision']]}
