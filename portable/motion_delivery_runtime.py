"""Selected18 complete-application closure and target-only, non-media probes.

The manifest pins data; it never chooses executable modules. Fixed hooks below
are the existing source/component identity functions, not another producer.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import struct

try:
    from . import app_update as core
except ImportError:
    spec = importlib.util.spec_from_file_location('haike_delivery_core', Path(__file__).with_name('app_update.py'))
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

PATH = 'Haike_video/templates/motion-presets/upgrade-closure.json'
PREFERRED = 'Haike_video/config/motion-preferred-production.json'
SCHEMA = 'haike.motion-upgrade-closure/1'
DELIVERY_SCHEMA = 'haike.motion-replay-delivery/2'
TRANSPORT = ['portable/motion_delivery_runtime.py', 'portable/motion_replay_capability.py',
             'portable/template_capability.py', PREFERRED, PATH]
REGISTRY_PREFIX = 'Haike_video/config/motion-replay/'
REGISTRY_NAMES = {
    'contract.schema.json', 'numbered-02-05.json', 'numbered-02-05-production.json', 'numbered-06-11.json',
    'imported.json', 'imported-native-full.json', 'imported-knowledge-full.json',
    'imported-knowledge-reference-public.json', 'imported-knowledge-reference-public-v2.json',
    'imported-knowledge-reference-public-v3.json', 'imported-promo-reference.json',
    'imported-promo-phase-v2.json', 'imported-promo-phase-v3.json', 'imported-public-v2.json',
    'imported-public-v2-bound.json', 'imported-public-poster-v3-bound.json',
    'imported-public-quote-v3-bound.json', 'imported-public-paper-v3-bound.json',
}
LOCKS = {'Haike_video/remotion-composer/package.json', 'Haike_video/remotion-composer/package-lock.json',
         'Haike_video/motion-components/snapcn/package.json', 'Haike_video/motion-components/snapcn/package-lock.json',
         'Haike_video/requirements.txt'}
PUBLIC_SOURCE_EXCEPTIONS = {
    'Haike_video/THIRD_PARTY_NOTICES.md',
    'Haike_video/motion-components/snapcn/upstream/content/docs/getting-started/license.mdx',
    'Haike_video/schemas/__init__.py', 'Haike_video/schemas/artifacts/__init__.py',
    'Haike_video/styles/playbook_loader.py',
    *{'Haike_video/templates/motiongit-public-components-v1/upstream/'+name for name in
      ['package.json','package-lock.json','scripts/face_track.sh','scripts/face_track.swift','scripts/pipeline.sh']},
}
HOOKS = {
    **{name: ('backlot.motion_replay_numbered_02_05_production', 'source_identity')
       for name in ['kinetic-field-v1', 'nana-mint-explainer-v1', 'field-notes-v1']},
    'field-notes-v2': ('backlot.motion_replay_field_notes_video', '_sources'),
    'chromatic-06': ('backlot.motion_replay_chromatic_production', 'sources_runtime'),
    **{name: ('backlot.motion_replay_chromatic_suite_production', 'sources_runtime')
       for name in ['chromatic-07', 'chromatic-08', 'chromatic-09', 'chromatic-six-10', 'chromatic-six-11']},
    **{name: ('backlot.motion_knowledge_public_execution_v3', 'source_identity')
       for name in ['knowledge-explainer-sketchnote', 'knowledge-explainer-chalkboard']},
    'motiongit-promo-user': ('backlot.studio_promo_phase_v3', 'runtime'),
    **{name: ('backlot.motion_public_execution_v2', 'component')
       for name in ['template-01-integrated', 'template-02-expanded', 'template-03-native', 'template-04-dark-console']},
    'vibrant-poster': ('backlot.motion_public_poster_execution_v3', 'component'),
}
FONT_EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2'}
SNAPCN_RUNTIME_PREFIXES = tuple('Haike_video/motion-components/snapcn/node_modules/'+name+'/' for name in
    ['@paper-design/shaders','@paper-design/shaders-react','class-variance-authority','clsx','culori','tailwind-merge'])
PUBLIC_COVERS = {'Haike_video/templates/library-covers/'+name+'.png' for name in
                 ['motion-package-mg-178e6870ae932019c6bf2fe9','motion-package-mg-5b31b7dd6e6709861dc6ac88']}
RUNTIME_PREFIXES = {
    'runtime/', 'runtime/python/', 'runtime/node/', 'runtime/browser/', 'runtime/ffmpeg/',
    'runtime/motion-public/dark/', 'runtime/motion-public/html/', 'runtime/motion-public/ffmpeg9/',
    'Haike_video/.venv/Lib/site-packages/', 'Haike_video/remotion-composer/node_modules/',
}


def require(ok, message):
    if not ok: raise core.UpdateError(message)


def declared(root):
    return core.safe_path(Path(root), PREFERRED).is_file()


def program_path(name):
    try: core._parts(name)
    except ValueError: return False
    return core.is_program_path(name) or name in LOCKS | PUBLIC_SOURCE_EXCEPTIONS or name == PREFERRED or (
        isinstance(name, str) and name.startswith(REGISTRY_PREFIX)
        and name.removeprefix(REGISTRY_PREFIX) in REGISTRY_NAMES) or (
        isinstance(name,str) and name.startswith('Haike_video/')
        and Path(name).name.upper() in {'LICENSE','NOTICE','OFL'})


def resource_path(name):
    try: parts = core._parts(name)
    except ValueError: return False
    if any(part.casefold() in {'.local', '.backlot', 'projects', 'browser_data', '.git', '__pycache__'}
           or part.casefold().startswith('.env') for part in parts): return False
    public_cover = re.fullmatch(r'Haike_video/templates/public-covers/[a-z0-9][a-z0-9-]{3,79}\.(?:png|jpe?g|webp)', name) is not None
    return public_cover or name.startswith(SNAPCN_RUNTIME_PREFIXES) or name in PUBLIC_COVERS or name.startswith(('runtime/', 'Haike_video/.venv/Lib/site-packages/',
                            'Haike_video/remotion-composer/node_modules/',
                            'Haike_video/backlot/ui/avatar-generator/',
                            'prototypes/haike-avatar-generator/dist/')) or (
        name.startswith(('Haike_video/templates/', 'Haike_video/remotion-composer/'))
        and Path(name).suffix.lower() in FONT_EXTENSIONS)


def read(root):
    path = core.safe_path(Path(root), PATH)
    require(path.is_file() and path.stat().st_size <= core.MAX_MANIFEST_BYTES, '18套必需组件闭包清单缺失或过大')
    return validate(core._json(path.read_bytes()))


def validate(value):
    require(isinstance(value, dict) and value.get('schema') == SCHEMA
            and value.get('distribution_scope') == 'complete-haike-application'
            and value.get('style_count') == 18 and isinstance(value.get('routes'), list)
            and len(value['routes']) == 18, '18套制作组件闭包格式无效')
    seen = set()
    for row in value['routes']:
        identity = row.get('template_id')
        require(identity in HOOKS and identity not in seen and isinstance(row.get('version'), str)
                and row.get('hook') == dict(zip(('module', 'function'), HOOKS[identity]))
                and row.get('private_original_required') is False, '18套固定调用身份不符或错误要求私人原包')
        require(program_path(row.get('registry', '')) and row['registry'].startswith(REGISTRY_PREFIX), '制作合同路径无效')
        seen.add(identity)
    require(seen == set(HOOKS), '18套样式不完整；历史版本不能充当额外样式')
    for key, predicate, limit in [('files', program_path, core.MAX_FILES), ('resources', resource_path, 100000)]:
        rows = value.get(key)
        require(isinstance(rows, dict) and 0 < len(rows) <= limit, '组件源或资源清单为空或过大')
        folded = set()
        for name, row in rows.items():
            require(predicate(name) and name.casefold() not in folded and isinstance(row, dict)
                    and isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256'])
                    and type(row.get('size')) is int and row['size'] >= 0, '组件路径、摘要或大小无效：' + str(name))
            folded.add(name.casefold())
    require(PREFERRED in value['files'] and all(row['registry'] in value['files'] for row in value['routes']),
            '组件闭包未绑定preferred或实际registry')
    required = {'Haike_video/'+module.replace('.', '/')+'.py' for module, _ in HOOKS.values()}
    required.update('Haike_video/templates/hum-production-v1/dynamic/vendor/'+name for name in
                    ['layouts.ts','NOTICE.md','REACT-BITS-LICENSE.md'])
    require(required <= set(value['files']), '实际生产模块或完整应用必需布局/原许可未闭包')
    return value


def validate_expectation(value):
    require(isinstance(value, dict) and value.get('schema') == DELIVERY_SCHEMA
            and isinstance(value.get('closure_sha256'), str) and re.fullmatch('[0-9a-f]{64}', value['closure_sha256'])
            and isinstance(value.get('preferred_sha256'), str) and re.fullmatch('[0-9a-f]{64}', value['preferred_sha256'])
            and isinstance(value.get('templates'), list) and len(value['templates']) == 18
            and {row.get('template_id') for row in value['templates']} == set(HOOKS), '当前18套发行身份无效')
    return value


def inventory(root):
    root = Path(root).resolve(); value = read(root)
    preferred = core._read(core.safe_path(root, PREFERRED))
    require(preferred.get('schema') == 'haike.motion-preferred-production/1'
            and isinstance(preferred.get('templates'), list) and len(preferred['templates']) == 18,
            '当前制作首选清单无效')
    identities = {(row['template_id'], row['version']) for row in preferred['templates']}
    require(identities == {(row['template_id'], row['version']) for row in value['routes']}, '组件闭包与当前18套preferred不一致')
    issues = inspect_files(root, value['files'])
    require(not issues, '18套必需公共源缺失或改变：' + (issues[0]['path'] if issues else ''))
    rows = []
    for row in value['routes']:
        registry = core._read(core.safe_path(root, row['registry']))
        matches = [item for item in registry.get('templates', [])
                   if (item.get('template_id'), item.get('version')) == (row['template_id'], row['version'])]
        require(len(matches) == 1 and matches[0].get('renderer') == row['renderer']
                and row['renderer'].get('kind') == 'project' and row['renderer'].get('execution') == 'supported',
                '首选实际制作合同不符：' + row['template_id'])
        for source in matches[0].get('sources', []):
            declared_source = value['files'].get(source['path']) or value['resources'].get(source['path'])
            require(declared_source is not None and declared_source['sha256'] == source['sha256'], '实际调用源未闭包：' + source['path'])
        rows.append(matches[0])
    expected = {'schema': DELIVERY_SCHEMA, 'closure_sha256': core.digest(core.safe_path(root, PATH)),
                'preferred_sha256': core.digest(core.safe_path(root, PREFERRED)),
                'templates': [{'template_id': row['template_id'], 'version': row['version'],
                    'registry': row['registry'], 'execution': 'supported'} for row in value['routes']]}
    validate_expectation(expected)
    return expected, set(value['files']) | set(TRANSPORT), rows


def checked_bindings(value=None):
    if value is None: return {'schema': 'haike.motion-runtime-bindings/1', 'prefixes': {}}
    require(isinstance(value, dict) and value.get('schema') == 'haike.motion-runtime-bindings/1'
            and isinstance(value.get('prefixes'), dict) and set(value['prefixes']) <= RUNTIME_PREFIXES,
            '只接受明确声明的系统或只读运行时映射；不能映射业务源码')
    for prefix, path in value['prefixes'].items():
        require(isinstance(path, str) and Path(path).is_absolute() and Path(path).is_dir(), '声明的运行时位置不存在：' + prefix)
    return value


def resource_location(root, name, row=None, bindings=None):
    bindings = checked_bindings(bindings)
    if not row or row.get('group') != 'font':
        for prefix in sorted(bindings['prefixes'], key=len, reverse=True):
            if name.startswith(prefix) or name == prefix.rstrip('/'):
                base = Path(bindings['prefixes'][prefix]).resolve()
                relative = name[len(prefix):] if name.startswith(prefix) else ''
                path = (base/relative).resolve()
                require(path.is_relative_to(base), '运行时映射越界')
                return path
    return core.safe_path(root, name)


def inspect_files(root, rows, *, bindings=None):
    def check(item):
        name, expected = item
        try:
            path = resource_location(root, name, expected, bindings) if bindings is not None else core.safe_path(root, name)
            if not path.is_file(): return {'path': name, 'status': 'missing', 'expected_sha256': expected['sha256']}
            if path.stat().st_size != expected['size'] or core.digest(path) != expected['sha256']:
                return {'path': name, 'status': 'changed', 'expected_sha256': expected['sha256']}
        except (OSError, ValueError) as exc: return {'path': name, 'status': 'invalid', 'reason': str(exc)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [row for row in pool.map(check, rows.items()) if row is not None]


def report(root, expected=None, *, runtime_bindings=None):
    root = Path(root).resolve(); actual, names, rows = inventory(root)
    require(expected is None or actual == expected, '安装内18套组件与本次发行身份不一致')
    value = read(root); bindings = checked_bindings(runtime_bindings)
    issues = inspect_files(root, value['resources'], bindings=bindings)
    # History is informational. Its package/media gates do not apply to these
    # selected public-source project routes.
    versions = set()
    for name in value['files']:
        if name.startswith(REGISTRY_PREFIX) and name.endswith('.json'):
            for item in core._read(core.safe_path(root, name)).get('templates', []):
                versions.add((item['template_id'], item['version']))
    templates = [{'template_id': row['template_id'], 'version': row['version'], 'contract': 'verified',
        'execution': 'supported', 'original_package': 'not_required', 'native_helper': 'not_required',
        'private_components': 'not_required', 'episode_inputs': 'user-provided',
        'production_ready': False, 'component_readiness': 'blocked' if issues else 'verified'} for row in rows]
    return {'status': 'blocked' if issues else 'verified', 'scope': 'selected18-complete-application-components',
        'template_count': 18, 'version_count': len(versions), 'preferred_count': 18, 'templates': templates,
        'public_files': len(names), 'resource_files': len(value['resources']), 'resource_issues': issues,
        'private_originals_distributed': False, 'render_selftest': 'not-performed', 'episode_review': False,
        'source_identity': actual, 'declared_external_runtimes': bindings['prefixes']}


def diagnostic_plan(root, *, runtime_bindings=None):
    root = Path(root).resolve(); bindings = checked_bindings(runtime_bindings)
    status = report(root, runtime_bindings=bindings)
    require(status['status'] == 'verified', '目标缺少必需资源，先恢复：' + (status['resource_issues'][0]['path'] if status['resource_issues'] else ''))
    value = read(root)
    return {'schema': 'haike.motion-target-diagnostic-plan/1', 'root': str(root), 'style_count': 18,
        'source_identity': status['source_identity'],
        'runtime_bindings': {key: str(resource_location(root, path, bindings=bindings)) for key, path in value['runtime_bindings'].items()},
        'declared_external_runtimes': bindings['prefixes'],
        'routes': [{**row, 'source_root': str(root), 'fallback_allowed': False} for row in value['routes']],
        'scope': 'D may use installed fixed hooks and original private inputs for short key-frame diagnostics; no full18 rerender implied',
        'media_executed': False}


def _environment(root, bindings=None):
    env = {key: val for key, val in os.environ.items() if key.casefold() in {'systemroot','windir','comspec','pathext'}}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
        PIP_NO_INDEX='1', UV_OFFLINE='1', NPM_CONFIG_OFFLINE='true', NODE_PATH='')
    env['PATH'] = os.pathsep.join(str(resource_location(root,path,bindings=bindings)) for path in
        ['runtime/python','runtime/node','runtime/ffmpeg/bin'])
    env['REMOTION_BROWSER_EXECUTABLE'] = str(resource_location(root,'runtime/browser/chrome-headless-shell.exe',bindings=bindings))
    env['FFMPEG_BINARY'] = str(resource_location(root,'runtime/ffmpeg/bin/ffmpeg.exe',bindings=bindings))
    return env


def font_probe(path):
    """Read declared public SFNT cmap bytes, without another font dependency."""
    data = Path(path).read_bytes()
    require(data[:4] in {b'\x00\x01\x00\x00', b'OTTO'}, '声明字体不是有效SFNT文件')
    count = struct.unpack_from('>H', data, 4)[0]
    tables = {data[12+i*16:16+i*16]: struct.unpack_from('>II', data, 20+i*16) for i in range(count)}
    require(b'cmap' in tables, '声明字体缺少cmap')
    offset, length = tables[b'cmap']; cmap = memoryview(data)[offset:offset+length]
    found = set()
    for i in range(struct.unpack_from('>H', cmap, 2)[0]):
        start = struct.unpack_from('>I', cmap, 8+i*8)[0]; fmt = struct.unpack_from('>H', cmap, start)[0]
        if fmt == 12:
            for j in range(struct.unpack_from('>I', cmap, start+12)[0]):
                left,right,glyph = struct.unpack_from('>III',cmap,start+16+j*12)
                for char in '检AI':
                    if left <= ord(char) <= right and glyph+ord(char)-left: found.add(char)
        elif fmt == 4:
            segments = struct.unpack_from('>H',cmap,start+6)[0]//2
            ends=start+14; starts=ends+segments*2+2; deltas=starts+segments*2; ranges=deltas+segments*2
            for char in '检AI':
                code=ord(char)
                for j in range(segments):
                    first=struct.unpack_from('>H',cmap,starts+j*2)[0];last=struct.unpack_from('>H',cmap,ends+j*2)[0]
                    if not first <= code <= last:continue
                    delta=struct.unpack_from('>h',cmap,deltas+j*2)[0];relative=struct.unpack_from('>H',cmap,ranges+j*2)[0]
                    glyph=(code+delta)&65535 if relative==0 else struct.unpack_from('>H',cmap,ranges+j*2+relative+2*(code-first))[0]
                    if glyph:found.add(char)
                    break
    require(found == set('检AI'), '声明公共字体缺少自检所需中英文字形')
    return {'status':'passed','cmap':'检AI','tables':count,'sha256':core.digest(Path(path))}


def component_selftest(root, *, runtime_bindings=None, execute=None):
    root = Path(root).resolve(); bindings = checked_bindings(runtime_bindings)
    plan = diagnostic_plan(root, runtime_bindings=bindings)
    python = resource_location(root, 'runtime/python/python.exe', bindings=bindings)
    node = resource_location(root, 'runtime/node/node.exe', bindings=bindings)
    require(python.is_file() and node.is_file(), '目标缺少已声明且核SHA的Python/Node')
    execute = execute or subprocess.run
    script = r'''
import importlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
bindings=json.loads(sys.argv[2]);allowed=[root]+[Path(path).resolve() for path in bindings['prefixes'].values()]
assert any(Path(sys.executable).resolve().is_relative_to(path) for path in allowed), 'undeclared python'
assert any(Path(sys.base_prefix).resolve().is_relative_to(path) for path in allowed), 'undeclared Python base'
site=bindings['prefixes'].get('Haike_video/.venv/Lib/site-packages/',str(root/'Haike_video/.venv/Lib/site-packages'))
sys.path[:0]=[str(root/'Haike_video'),str(root),site]
from portable import motion_delivery_runtime as checker
value=checker.read(root);rows=[];seen={}
for route in value['routes']:
 module,function=checker.HOOKS[route['template_id']]
 key=(module,function)
 if key not in seen:
  loaded=importlib.import_module(module)
  assert Path(loaded.__file__).resolve().is_relative_to(root), 'outside target component'
  result=getattr(loaded,function)()
  assert isinstance(result,dict) and result, 'empty actual source/component hook'
  seen[key]=len(result)
 rows.append({'template_id':route['template_id'],'module':module,'function':function,'actual_hook_items':seen[key]})
import numpy as np
from PIL import Image
assert np.dot([2,3],[4,5])==23
font=next(name for name in value['resources'] if name.endswith('NotoSansSC.ttf'))
font_result=checker.font_probe(root/font)
declared_runtime_files={str(checker.resource_location(root,logical,row,bindings))
    for logical,row in value['resources'].items() if row.get('group') in {'python-package','base-runtime'}}
for name,loaded in list(sys.modules.items()):
 if getattr(loaded,'__file__',None):
  origin=Path(loaded.__file__).resolve()
  if name.split('.')[0] in {'backlot','lib','portable','tools'}: assert origin.is_relative_to(root), 'outside target business source: '+name
  if name.split('.')[0] in {'numpy','scipy','PIL','fontTools','jsonschema'}: assert any(origin.is_relative_to(path) for path in allowed), 'undeclared runtime import: '+name
  if not origin.is_relative_to(root) and name.split('.')[0] not in sys.stdlib_module_names and name not in {'__main__'}:
   assert str(origin) in declared_runtime_files, 'undeclared third-party module: '+name+' '+str(origin)
print(json.dumps({'status':'passed','styles':rows,'actual_hooks':len(seen),'numpy':'passed','font':font_result}))
'''
    result = execute([str(python), '-I', '-B', '-c', script, str(root), json.dumps(bindings)], cwd=root, env=_environment(root,bindings),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, '目标实际组件import/计算未通过：' + result.stderr[-2000:])
    probe = json.loads(result.stdout.strip().splitlines()[-1])
    deps = resource_location(root, 'Haike_video/remotion-composer/node_modules', bindings=bindings)
    js = r"const p=require('path'),d=process.argv[1];const q=require('module').createRequire(p.join(d,'..','__haike_runtime_probe.cjs'));for(const n of ['react','remotion','@remotion/bundler','@remotion/renderer']){if(!q.resolve(n).startsWith(d+p.sep))throw Error('undeclared runtime '+n);q(n)}if(q('remotion').interpolate(.5,[0,1],[0,10])!==5)throw Error('actual Remotion compute');console.log(JSON.stringify({status:'passed',remotion:'actual interpolate',scope:'no bundle/browser/render'}))"
    js_result = execute([str(node), '-e', js, str(deps)], cwd=root, env=_environment(root,bindings),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(js_result.returncode == 0, '目标实际Remotion依赖计算未通过：' + js_result.stderr[-1600:])
    return {'status': 'passed', 'scope': 'installed-actual-components-import-font-and-computation-only',
        'template_count': 18, 'python': probe, 'node': json.loads(js_result.stdout.strip().splitlines()[-1]),
        'source_identity': plan['source_identity'], 'declared_external_runtimes': bindings['prefixes'],
        'tool_identities': {name: {'path': str(path), 'sha256': core.digest(path)} for name, path in [('python',python),('node',node)]},
        'media_executed': False, 'render_selftest': 'not-performed',
        'continuous_listening': 'not-performed', 'paid_calls': 0}
