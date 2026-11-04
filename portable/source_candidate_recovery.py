"""Complete an existing isolated source candidate; no service, provider or publish.

Only a receipt-named destination is writable. Resource bodies are staged and
SHA-verified before installation. Known private data are snapshotted and rebound
inside that destination; frozen jobs/proofs and the original Git index stay intact.
This helper is independent of the currently frozen unified/legacy transaction.
"""
from __future__ import annotations

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from uuid import uuid4

try:
    from . import app_update as core
except ImportError:
    spec = importlib.util.spec_from_file_location('haike_source_recovery_core', Path(__file__).with_name('app_update.py'))
    core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

CLOSURE = 'Haike_video/templates/motion-presets/upgrade-closure.json'
DATA_TREES = ('Haike_video/projects', 'Haike_video/.backlot', 'creatorhub/data', 'creatorhub/browser_data')
CONFIG_FILES = ('Haike_video/config.yaml', 'Haike_video/config.local.yaml', 'Haike_video/.env', 'Haike_video/.env.local',
    'creatorhub/config.yaml', 'copy_skill/copy_skill-main/config/content_intelligence.local.json',
    '.local/store-manager/defaults.json', '.local/runninghub-workflow/default.json')
COVERS = {
    'Haike_video/templates/library-covers/motion-package-mg-178e6870ae932019c6bf2fe9.png':
        '2d19a4eb24160556d6960090eb85453a7345f04f9efa708a628af919ffbc9b77',
    'Haike_video/templates/library-covers/motion-package-mg-5b31b7dd6e6709861dc6ac88.png':
        '379780b6f13ba83f69f03ee3f9ccd8ee0dc8fa234e9cc5d002841cfd8ae3ff32',
}
MAX_FILES, MAX_EXPANDED = 100000, 4 * 1024**3
BASE_LOCK = '_distribution-tools/locks/Haike_video.txt'
BASE_IMPORTS = ('fastapi', 'uvicorn', 'multipart', 'yaml', 'PIL', 'cv2', 'numpy',
    'aiohttp', 'dashscope', 'httpx', 'jsonschema', 'watchfiles', 'oss2', 'docx',
    'opencc', 'google.auth', 'google.genai', 'openai')
PUBLIC_COVER = re.compile(r'Haike_video/templates/public-covers/[a-z0-9][a-z0-9-]{3,79}\.(?:png|jpg|jpeg|webp)')


class RecoveryError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise RecoveryError(message)


def read(path):
    return core._read(path)


def write(path, value):
    core._atomic_write(path, core.json_bytes(value))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_git(root):
    if not core.native_path(root/'.git').exists():
        return None
    env = os.environ.copy()
    env['GIT_OPTIONAL_LOCKS'] = '0'
    for name in ('GIT_DIR', 'GIT_INDEX_FILE', 'GIT_WORK_TREE', 'GIT_COMMON_DIR'):
        env.pop(name, None)
    def run(*args, optional=False):
        r = subprocess.run(['git', '-C', str(root), *args], capture_output=True, env=env, timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        need(optional or r.returncode == 0, '原Git状态无法只读核对')
        return r.stdout if r.returncode == 0 else b''
    raw = run('rev-parse', '--git-path', 'index').decode().strip()
    index = Path(raw) if Path(raw).is_absolute() else root/raw
    return {'head': run('rev-parse', '--verify', 'HEAD', optional=True).decode().strip(),
        'branch': run('symbolic-ref', '-q', 'HEAD', optional=True).decode().strip(),
        'index_sha256': core.digest(index) if core.native_path(index).is_file() else None,
        'working_diff_sha256': hashlib.sha256(run('diff', '--binary')).hexdigest(),
        'cached_diff_sha256': hashlib.sha256(run('diff', '--cached', '--binary')).hexdigest(),
        'status_sha256': hashlib.sha256(run('status', '--porcelain=v1', '-z', '--untracked-files=all')).hexdigest()}


def context(receipt_path, closure_sha256):
    receipt_path = Path(receipt_path).resolve(strict=True)
    receipt = read(receipt_path)
    need(receipt.get('schema') == 'haike.unified-upgrade-source/1' and receipt.get('status') == 'source-ready'
         and receipt.get('activated') is False, '只接受原统一入口的未启用source-ready回执')
    source = Path(receipt['original_root']).resolve(strict=True)
    target = Path(receipt['destination']).resolve(strict=True)
    need(receipt_path == target.parent/(target.name+'.haike-upgrade.json'), '回执名字与隔离目标不匹配')
    need(source != target and not target.is_relative_to(source) and not source.is_relative_to(target), '原目录与隔离目标必须分离')
    for root in (source, target):
        for path in [root, *root.parents]:
            need(not path.is_symlink() and not (hasattr(path, 'is_junction') and path.is_junction()), '恢复根不能经过目录链接')
    path = core.safe_path(target, CLOSURE)
    need(core.native_path(path).is_file() and core.digest(path) == closure_sha256, '目标源码的精确组件闭包SHA不符')
    closure = read(path)
    need(closure.get('schema') == 'haike.motion-upgrade-closure/1'
         and isinstance(closure.get('files'), dict) and isinstance(closure.get('resources'), dict), '恢复闭包格式无效')
    verify_program(target, closure)
    target_git = source_git(target)
    if target_git and target_git['head']:
        need(target_git['head'] == receipt['source_commit'], '隔离源码Git提交已改变')
    return source, target, receipt, closure


def verify_program(target, closure):
    for name, row in closure['files'].items():
        p = core.safe_path(target, name)
        need(core.native_path(p).is_file() and core.native_path(p).stat().st_size == row['size'] and core.digest(p) == row['sha256'],
             '目标新源码缺失或改变：'+name)


def resource_path(name):
    parts = core._parts(name)
    lower = [p.casefold() for p in parts]
    if any(p in {'.git', '.backlot', '.local', 'projects', 'browser_data', 'profiles', '__pycache__'} or p.startswith('.env') for p in lower):
        return False
    if lower[-1] in {'cookies', 'storage_state.json', 'credentials.json'} or '.private.' in lower[-1]:
        return False
    if name.startswith('Haike_video/motion-components/snapcn/node_modules/'):
        return not any(p in {'profile','user_data'} for p in lower) and not lower[-1].endswith(('.pem','.key'))
    if PUBLIC_COVER.fullmatch(name):
        return True
    return name in COVERS or name.startswith(('runtime/python/', 'runtime/node/', 'runtime/browser/',
        'runtime/ffmpeg/', 'runtime/motion-public/', 'Haike_video/.venv/Lib/site-packages/',
        'Haike_video/remotion-composer/node_modules/', 'Haike_video/backlot/ui/avatar-generator/',
        'prototypes/haike-avatar-generator/dist/')) or (
        name.startswith(('Haike_video/templates/', 'Haike_video/remotion-composer/'))
        and Path(name).suffix.lower() in {'.ttf', '.otf', '.woff', '.woff2'})


def manifest(archive, closure, closure_sha, program_tree_sha):
    infos = archive.infolist()
    need(len(infos) <= MAX_FILES+1 and len({i.filename.casefold() for i in infos}) == len(infos), '完整资源ZIP条目重复或超限')
    for item in infos:
        core._parts(item.filename)
        need(not item.is_dir() and ((item.external_attr>>16)&0o170000) != 0o120000, '资源ZIP含链接或目录')
    need(archive.getinfo('RESOURCES.json').file_size <= core.MAX_MANIFEST_BYTES, '完整资源清单过大')
    value = core._json(archive.read('RESOURCES.json'))
    need(value.get('schema') == 'haike.complete-resource-recovery/1'
         and value.get('kind') == 'content-addressed-resource-bodies'
         and value.get('baseline_dependency') is None and value.get('reuse_from_required') is False
         and value.get('target_transaction_plan_required') is True, '需要不依赖旧安装的完整正文资源包')
    need(value.get('component_manifest_sha256') == closure_sha
         and value.get('preferred_sha256') == closure['preferred_sha256']
         and value.get('program_source_tree_sha256') == program_tree_sha, '资源包与本期源码/闭包身份不一致')
    rows = value.get('files')
    need(isinstance(rows, list) and 0 < len(rows) <= MAX_FILES, '完整资源条目数量无效')
    seen, objects = set(), {}
    for row in rows:
        name = row['path']
        need(resource_path(name) and name.casefold() not in seen, '资源路径越界、重复或属于用户私有配置：'+name)
        seen.add(name.casefold())
        expected = closure['resources'].get(name)
        need((name in COVERS and row['sha256'] == COVERS[name]) or (
            isinstance(expected, dict) and row['sha256'] == expected['sha256'] and row['size'] == expected['size']),
            '资源不属于本期SHA绑定闭包：'+name)
        need(type(row['size']) is int and 0 <= row['size'] < 512*1024**2
             and core._SHA.fullmatch(row['sha256']) and row.get('blob') == 'objects/'+row['sha256'], '资源正文身份无效')
        need(archive.getinfo(row['blob']).file_size == row['size'], '资源正文大小改变')
        if row['blob'] in objects:
            need(objects[row['blob']] == row['size'], '相同SHA资源大小冲突')
        objects[row['blob']] = row['size']
    need(set(closure['resources']) <= {r['path'] for r in rows}, '完整包缺少本期运行资源')
    need(sum(r['size'] for r in rows) <= MAX_EXPANDED and set(archive.namelist()) == {*objects, 'RESOURCES.json'}, '资源展开超限或含未声明正文')
    return value, rows, objects


def copy_new(path, source, expected_sha, expected_size):
    """Atomic no-clobber publication; no hardlinks to original/cache contents."""
    if core.native_path(path).is_file():
        need(core.native_path(path).stat().st_size == expected_size and core.digest(path) == expected_sha, '隔离目标已有不同文件，保留：'+path.name)
        return
    core.native_path(path.parent).mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.haike-source-recovery-', dir=core.native_path(path.parent))
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as output:
            while block := source.read(1024*1024):
                count += len(block); need(count <= expected_size, '资源正文超过声明大小')
                digest.update(block); output.write(block)
            output.flush(); os.fsync(output.fileno())
        need(count == expected_size and digest.hexdigest() == expected_sha, '恢复正文SHA不符')
        os.link(temporary, core.native_path(path))
    finally:
        core.native_path(Path(temporary)).unlink(missing_ok=True)


def _guard_source(source):
    # Existing read-only held-job/audio guards. No reconciliation/provider calls.
    result={}
    for file, argument in [('queue_update_guard.py', source/'Haike_video/.backlot/production-queue.sqlite3'),
                           ('audio_update_guard.py', source)]:
        spec = importlib.util.spec_from_file_location('haike_source_'+file[:-3], Path(__file__).with_name(file))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        result[file]=module.require_idle(argument)
    return result


def snapshot_data(source, target, folder):
    entries = []
    for relative in DATA_TREES:
        root = core.safe_path(source, relative)
        if not core.native_path(root).exists():
            continue
        for current, dirs, files in os.walk(core.native_path(root), followlinks=False):
            current=core.logical_path(Path(current))
            for name in [*dirs, *files]:
                core.safe_path(source, (Path(current)/name).relative_to(source).as_posix())
            entries.extend((Path(current)/name).relative_to(source).as_posix() for name in files
                           if not name.endswith(('-wal', '-shm', '-journal')))
    entries += [name for name in CONFIG_FILES if core.native_path(core.safe_path(source, name)).is_file()]
    need(shutil.disk_usage(target).free > 3*sum(core.native_path(core.safe_path(source,n)).stat().st_size for n in set(entries))+32*1024**2,
         '资料快照、导入与回退备份空间不足；原资料保留')
    result = []
    for name in sorted(set(entries)):
        src, staged = core.safe_path(source, name), core.safe_path(folder/'data', name)
        before = core.native_path(src).stat()
        with core.native_path(src).open('rb') as stream:
            sqlite = stream.read(16) == b'SQLite format 3\x00'
        if sqlite:
            core.native_path(staged.parent).mkdir(parents=True, exist_ok=True)
            need(not core.native_path(staged).exists(), '数据快照已有现场，请保留并恢复本次回执')
            with closing(sqlite3.connect(src.resolve().as_uri()+'?mode=ro', uri=True)) as db:
                version = db.execute('PRAGMA data_version').fetchone()[0]
                with closing(sqlite3.connect(str(core.native_path(staged)))) as dst:
                    db.backup(dst)
                    need(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', '原数据库快照不完整')
                need(db.execute('PRAGMA data_version').fetchone()[0] == version, '原数据库在快照中变化，保留原数据并重试')
        else:
            with core.native_path(src).open('rb') as stream:
                copy_new(staged, stream, core.digest(src), before.st_size)
            after = core.native_path(src).stat()
            need((after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns), '原文件在快照中变化')
        result.append({'path':name, 'sha256':core.digest(staged), 'size':core.native_path(staged).stat().st_size, 'sqlite_snapshot':sqlite})
    return result


def _mapped(raw, source, target, data_root, unknown, expected_sha=None):
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        return raw
    path = Path(raw)
    try:
        name = path.resolve().relative_to(source).as_posix()
        need(any(name.startswith(prefix+'/') for prefix in DATA_TREES), '路径不属于可迁移的用户资料目录')
        copied = core.safe_path(data_root, name)
        need(core.native_path(copied).is_file() and (expected_sha is None or core.digest(copied) == expected_sha), '资料副本缺失或SHA改变')
        return str(core.safe_path(target, name))
    except (ValueError, OSError):
        unknown.append({'kind':'unresolved_ui_path', 'path_sha256':hashlib.sha256(raw.encode()).hexdigest()})
        return raw


def rebind_models(source, target, folder):
    """Only presentation/asset locator fields; never frozen requests/proofs."""
    data_root = folder/'data'; unknown = []; expected = {'works':[], 'drafts':[], 'assets':[]}
    studio = core.safe_path(data_root, 'Haike_video/.backlot/studio.sqlite3')
    if core.native_path(studio).is_file():
        with closing(sqlite3.connect(str(core.native_path(studio)))) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'studio_drafts' in tables:
                expected['drafts'] = [r[0] for r in db.execute('SELECT id FROM studio_drafts')]
            if 'studio_assets' in tables:
                for asset_id, path in db.execute('SELECT id,path FROM studio_assets').fetchall():
                    mapped = _mapped(path, source, target, data_root, unknown)
                    db.execute('UPDATE studio_assets SET path=? WHERE id=?', (mapped, asset_id)); expected['assets'].append(asset_id)
            unknown += [{'kind':'unrecognized_studio_table','table':t} for t in tables-
                {'studio_drafts','studio_assets','studio_calendar','studio_quotes','studio_audio_operations','sqlite_sequence'}]
            db.commit()
    works = core.safe_path(data_root, 'Haike_video/.backlot/works.sqlite3')
    if core.native_path(works).is_file():
        with closing(sqlite3.connect(str(core.native_path(works)))) as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            unknown += [{'kind':'unrecognized_works_table','table':t} for t in tables-
                {'works','work_events','work_plans','work_activity','sqlite_sequence'}]
            for work_id, raw in db.execute('SELECT id,data FROM works').fetchall():
                value = json.loads(raw)
                if value.get('final_version_id'):
                    expected['works'].append(work_id)
                for version in value.get('versions', []):
                    old = version.get('paths', [])
                    mapped = [_mapped(p, source, target, data_root, unknown, version.get('sha256')) for p in old]
                    version['paths'] = list(dict.fromkeys([*mapped, *old]))
                for item in value.get('assets', []):
                    if 'path' in item:
                        item['path'] = _mapped(item['path'], source, target, data_root, unknown, item.get('sha256'))
                for item in value.get('materials', []):
                    for key in ('cover_path','cover_proof_path'):
                        data = item.get('data', {})
                        if data.get(key): data[key] = _mapped(data[key], source, target, data_root, unknown, data.get(key+'_sha256'))
                db.execute('UPDATE works SET data=? WHERE id=?', (json.dumps(value,ensure_ascii=False),work_id))
            db.commit()
    return expected, unknown


def plan_data(source, target, folder, entries, closure):
    expected, unknown = rebind_models(source, target, folder)
    changes, after = [], []
    for row in entries:
        name = row['path']; src = core.safe_path(folder/'data', name); dst = core.safe_path(target, name)
        desired = core.digest(src)
        # A tracked configuration is still new source. Retain its exact bytes,
        # archive the old settings and explicitly require a semantic merge.
        if name in closure['files']:
            need(name in CONFIG_FILES, '不能用用户资料覆盖新程序源码：'+name)
            if desired != closure['files'][name]['sha256']:
                unknown.append({'kind':'tracked_config_merge_pending','path':name})
            continue
        before = core.digest(dst) if core.native_path(dst).is_file() else None
        need(not core.native_path(dst).exists() or core.native_path(dst).is_file(), '资料目标不是普通文件：'+name)
        if before is not None and before != desired:
            if name not in CONFIG_FILES:
                # Fresh create_app may have initialized an empty database only.
                empty = False
                if row['sqlite_snapshot']:
                    with closing(sqlite3.connect(dst.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                        empty = all(db.execute('SELECT 1 FROM "'+t.replace('"','""')+'" LIMIT 1').fetchone() is None for t in tables)
                need(empty, '隔离目标已有用户数据，保留且不覆盖：'+name)
            backup = core.safe_path(folder/'before-data', name)
            with core.native_path(dst).open('rb') as stream: copy_new(backup,stream,core.digest(dst),core.native_path(dst).stat().st_size)
        if before != desired:
            changes.append({'path':name,'before_sha256':before,'after_sha256':desired})
        after.append({'path':name,'sha256':desired})
        if name.startswith(('creatorhub/data/', 'creatorhub/browser_data/')):
            unknown.append({'kind':'publisher_binding_not_exercised','path':name})
        elif name.startswith('Haike_video/.backlot/') and row['sqlite_snapshot'] and Path(name).name not in {
            'studio.sqlite3','works.sqlite3','production-queue.sqlite3'}:
            unknown.append({'kind':'unrecognized_database_preserved','path':name})
    return {'expected_visible':expected,'unknown':unknown,'changes':changes,'after':after,
            'snapshot':str(folder), 'all_source_snapshots':entries}


def apply_data(target, plan):
    folder = Path(plan['snapshot'])
    for row in plan['changes']:
        dst = core.safe_path(target,row['path'])
        before = core.digest(dst) if core.native_path(dst).is_file() else None
        need(before == row['before_sha256'], '隔离资料在准备后变化；未覆盖：'+row['path'])
        staged = core.safe_path(folder/'data',row['path'])
        need(core.digest(staged) == row['after_sha256'], '资料暂存SHA改变')
        core._atomic_write(dst,core.native_path(staged).read_bytes())


def rollback_data(target, plan):
    """Restore only our exact writes; concurrent target edits are never erased."""
    result = []
    folder = Path(plan['snapshot'])
    for row in reversed(plan['changes']):
        dst = core.safe_path(target,row['path'])
        current = core.digest(dst) if core.native_path(dst).is_file() else None
        if current == row['before_sha256']:
            continue
        if current != row['after_sha256']:
            result.append({'path':row['path'],'status':'concurrent-change-preserved'})
            continue
        if row['before_sha256'] is None:
            core.native_path(dst).unlink()
        else:
            backup = core.safe_path(folder/'before-data',row['path'])
            need(core.digest(backup) == row['before_sha256'], '资料回退备份SHA不符')
            core._atomic_write(dst,core.native_path(backup).read_bytes())
        result.append({'path':row['path'],'status':'restored'})
    return result


def runtime_inventory(source, manifest_sha256):
    """Explicit legal donor, immutable file identity; never use donor data/code."""
    source = Path(source).resolve(strict=True)
    inventory = core.safe_path(source,'PACKAGE-MANIFEST.json')
    need(core.digest(inventory) == manifest_sha256, '运行时来源清单SHA不符')
    value = read(inventory)
    need(value.get('schema') == 1 and isinstance(value.get('files'),list), '运行时来源清单格式不支持')
    rows, seen = [], set()
    for row in value['files']:
        name = row['path']
        selected = name.startswith(('Haike_video/.venv/Lib/site-packages/', 'Haike_video/.venv/msvc/', 'runtime/msvc/'))
        if not selected or '__pycache__' in core._parts(name) or name.endswith(('.pyc','.pth','/sitecustomize.py','/usercustomize.py')):
            continue
        # OpenAI SDK's public package namespace happens to be named projects;
        # it is not Haike's private project tree. Limit this exception to code.
        sdk_projects=name.startswith(('Haike_video/.venv/Lib/site-packages/openai/resources/admin/organization/projects/',
            'Haike_video/.venv/Lib/site-packages/openai/types/admin/organization/projects/')) and Path(name).suffix in {'.py','.pyi'}
        need(resource_path(name) or sdk_projects or re.fullmatch(r'(?:runtime/msvc|Haike_video/\.venv/msvc)/(?:msvcp140|vcruntime140|vcruntime140_1)\.dll',name), '运行时来源越界')
        need(name.casefold() not in seen and type(row['size']) is int and row['size'] >= 0
             and core._SHA.fullmatch(row['sha256']), '运行时来源条目重复或无效')
        seen.add(name.casefold()); rows.append(row)
    need(rows and len(rows)<50000 and sum(r['size'] for r in rows)<3*1024**3, '运行时来源数量/大小无效')
    return source, rows


def supplement_runtime(target, source, manifest_sha256, folder):
    source, rows = runtime_inventory(source,manifest_sha256)
    need(source != target and not source.is_relative_to(target) and not target.is_relative_to(source), '运行时来源必须独立')
    def inspect_row(row):
        name = row['path']; src = core.safe_path(source,name); dst = core.safe_path(target,name)
        need(core.native_path(src).is_file() and core.native_path(src).stat().st_size == row['size'] and core.digest(src)==row['sha256'], '运行时来源文件摘要不符：'+name)
        current = core.digest(dst) if core.native_path(dst).is_file() else None
        if current != row['sha256'] and current is not None:
            # RECORD is an installation manifest, not executable runtime. C's
            # bound subset owns its own RECORD; every other shared byte matches.
            need(name.endswith('.dist-info/RECORD'), '基础依赖与18组件版本冲突：'+name)
            return None
        if current is None:
            return row
        return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        plan=[row for row in pool.map(inspect_row,rows) if row is not None]
    write(folder/'base-runtime-plan.json',{'schema':1,'source':str(source),'manifest_sha256':manifest_sha256,
        'target':str(target),'files':plan,'source_files_verified':len(rows)})
    need(shutil.disk_usage(target).free > 2*sum(r['size'] for r in plan)+32*1024**2, '基础依赖恢复空间不足')
    # Verify all selected bytes before any runtime destination is published.
    def stage(row):
        with core.native_path(core.safe_path(source,row['path'])).open('rb') as stream:
            copy_new(core.safe_path(folder/'base-runtime',row['path']),stream,row['sha256'],row['size'])
    def install(row):
        with core.native_path(core.safe_path(folder/'base-runtime',row['path'])).open('rb') as stream:
            copy_new(core.safe_path(target,row['path']),stream,row['sha256'],row['size'])
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(stage,plan))
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(install,plan))
    need(core.digest(source/'PACKAGE-MANIFEST.json')==manifest_sha256,'运行时来源清单有并发变化')
    return {'status':'restored-awaiting-abi-probe','method':'sha-bound-inventory-copy','copied':len(plan),
        'source_files_verified':len(rows),'manifest_sha256':manifest_sha256,
        'files':[{'path':r['path'],'sha256':r['sha256']} for r in rows if not r['path'].endswith('.dist-info/RECORD')]}


def verified_base_cache(target, source, manifest_sha256, record):
    if record.get('method')!='sha-bound-inventory-copy' or record.get('manifest_sha256')!=manifest_sha256:
        return False
    _,rows=runtime_inventory(source,manifest_sha256)
    expected={r['path']:r['sha256'] for r in rows if not r['path'].endswith('.dist-info/RECORD')}
    if {r['path']:r['sha256'] for r in record.get('files',[])} != expected:
        return False
    def check(item):return core.digest(core.safe_path(target,item[0]))==item[1]
    with ThreadPoolExecutor(max_workers=8) as pool:return all(pool.map(check,expected.items()))


def probe_environment(target):
    env = {k:v for k,v in os.environ.items() if k.casefold() in {'systemroot','windir','comspec','pathext','temp','tmp'}}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        PIP_NO_INDEX='1',UV_OFFLINE='1',NPM_CONFIG_OFFLINE='true',HAIKE_PORTABLE_OFFLINE='1',
        OPENMONTAGE_PROJECTS_DIR=str(target/'Haike_video/projects'),BACKLOT_NO_BROWSER='1',BACKLOT_DETACHED='1',
        FFMPEG_BINARY=str(target/'runtime/ffmpeg/bin/ffmpeg.exe'))
    env['PATH'] = os.pathsep.join(str(target/p) for p in ('runtime/python','runtime/node','runtime/ffmpeg/bin',
        'runtime/msvc','Haike_video/.venv/msvc'))
    env['PYTHONPATH'] = os.pathsep.join(str(target/p) for p in ('','Haike_video','Haike_video/.venv/Lib/site-packages'))
    profile=target/'.local/source-recovery/probe-profile'
    env.update(USERPROFILE=str(profile),APPDATA=str(profile/'AppData/Roaming'),LOCALAPPDATA=str(profile/'AppData/Local'),
        TEMP=str(profile/'Temp'),TMP=str(profile/'Temp'),UV_CACHE_DIR=str(profile/'uv-cache'))
    return env


def _execute(target, args):
    env=probe_environment(target)
    for key in ('USERPROFILE','APPDATA','LOCALAPPDATA','TEMP'):
        core.native_path(Path(env[key])).mkdir(parents=True,exist_ok=True)
    result = subprocess.run([str(a) for a in args],cwd=target,env=env,capture_output=True,
        encoding='utf8',errors='replace',timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode != 0:
        error=RecoveryError('目标内固定准备/组件/健康检查失败；原目录保留，未标就绪')
        missing=re.findall(r"ModuleNotFoundError: No module named ['\"]([A-Za-z0-9_.-]+)['\"]",result.stderr)
        error.execution={'returncode':result.returncode,'missing_modules':missing,
            'operation':Path(str(args[2])).name if len(args)>2 and str(args[2])!='-c' else 'fixed-inline-probe'}
        raise error
    return result.stdout


def prepare_runtime(target):
    python = core.safe_path(target,'runtime/python/python.exe')
    need(core.native_path(python).is_file(), '完整包缺少已声明Python，不能转交用户setup代替恢复')
    _execute(target,[python,'-s','-m','venv','--without-pip','--copies',target/'Haike_video/.venv'])
    return {'status':'passed','method':'restored Python stdlib venv; no pip/network'}


def probe_base(target):
    """Locked distributions and real native ABI, entirely within the target."""
    script = r'''
import importlib,importlib.metadata as meta,json,os,re,struct,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve(); names=json.loads(sys.argv[2]); dll_handles=[]
for p in [root/'runtime/msvc',root/'Haike_video/.venv/msvc']:
 if p.is_dir() and hasattr(os,'add_dll_directory'):dll_handles.append(os.add_dll_directory(str(p)))
assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Python ABI'
sys.path[:0]=[str(root/'Haike_video/.venv/Lib/site-packages')]
lock=root/'_distribution-tools/locks/Haike_video.txt'
assert lock.is_file(), 'target base lock missing'
missing=[];locked=0
for line in lock.read_text(encoding='utf-8-sig').splitlines():
 line=line.strip()
 if not line or line.startswith('#'):continue
 match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^ ;]+)',line)
 assert match, 'unsupported lock syntax'
 name,version=match.groups();locked+=1
 try:
  dist=meta.distribution(name)
  assert Path(dist.locate_file('')).resolve().is_relative_to(root), 'external distribution'
  if dist.version != version:missing.append(name+':version')
 except meta.PackageNotFoundError:missing.append(name+':missing')
origins={}
for name in names:
 try:
  module=importlib.import_module(name);origin=Path(module.__file__).resolve()
  assert origin.is_relative_to(root), 'external module'
  origins[name]=str(origin.relative_to(root))
 except (ImportError,OSError,AssertionError):missing.append(name+':import')
if not missing:
 import numpy as np,cv2
 assert cv2.cvtColor(np.zeros((2,2,3),dtype=np.uint8),cv2.COLOR_BGR2GRAY).shape==(2,2)
 from PIL import Image
 assert Image.new('RGB',(2,2)).resize((1,1)).size==(1,1)
print(json.dumps({'status':'blocked' if missing else 'passed','missing':missing,'locked_distributions':locked,'origins':origins,'abi':'cp312-win_amd64','native_compute':not missing}))
'''
    value=json.loads(_execute(target,[target/'runtime/python/python.exe','-s','-c',script,target,json.dumps(BASE_IMPORTS)]).strip().splitlines()[-1])
    return value


def restore_base_online(target, folder, closure):
    """Reuse the existing resolver, with the recipient's exact base lock."""
    spec=importlib.util.spec_from_file_location('haike_source_dependency_recovery',Path(__file__).with_name('update_dependencies.py'))
    dependencies=importlib.util.module_from_spec(spec);spec.loader.exec_module(dependencies)
    existing_environment=dependencies.environment
    def isolated_environment(root,staged=None):
        original=existing_environment(root,staged)
        return {**original,**probe_environment(Path(root)),'PYTHONPATH':original['PYTHONPATH']}
    dependencies.environment=isolated_environment
    lock=core.safe_path(target,BASE_LOCK)
    need(core.native_path(lock).is_file(),'目标缺少基础依赖锁')
    bundle=folder/'base-dependency-bundle';core.native_path(bundle).mkdir(exist_ok=True)
    core._atomic_write(bundle/'video-dependencies.txt',core.native_path(lock).read_bytes())
    core._atomic_write(bundle/'dependency-downloads.json',Path(__file__).with_name('dependency-downloads.json').read_bytes())
    plan=dependencies.prepare(target,bundle,{'missing':['python_packages'],'components':{},'download_required':True})
    rows=dependencies.rows(target,plan)
    selected=[]
    for row in rows:
        name=row['path']
        # Keep the stdlib-created venv and C's exact component resources.
        if name.startswith('Haike_video/.venv/Scripts/') or name=='Haike_video/.venv/pyvenv.cfg':continue
        need(resource_path(name) or dependencies.allowed(name),'基础依赖恢复越界')
        dst=core.safe_path(target,name);current=core.digest(dst) if core.native_path(dst).is_file() else None
        if current is not None and current!=row['sha256']:
            need(name.endswith('.dist-info/RECORD'),'基础依赖与冻结组件冲突：'+name)
            continue
        selected.append(row)
    write(folder/'online-base-plan.json',{'lock_sha256':core.digest(lock),'files':selected})
    for row in selected:
        with core.native_path(Path(row['prepared'])).open('rb') as stream:
            copy_new(core.safe_path(target,row['path']),stream,row['sha256'],row['size'])
    return {'status':'restored-awaiting-abi-probe','method':'existing-update-dependencies-with-target-lock',
        'lock_sha256':core.digest(lock),'files':[{'path':r['path'],'sha256':r['sha256']} for r in selected]}


def probe_target(target, expected):
    python = target/'runtime/python/python.exe'
    text = _execute(target,[python,'-s',target/'portable/template_capability.py','--root',target,'--component-selftest'])
    component = json.loads(text.strip().splitlines()[-1])
    need(component.get('status') == 'passed' and component.get('template_count') == 18, '实际18组件调用未通过')
    health=probe_health(target,expected)
    return {'status':'passed','component':component,'health':health,'media_rendered':False}


def probe_health(target, expected):
    """Real recipient create_app/GETs, without lifespan, external sockets or workers."""
    python=target/'runtime/python/python.exe'
    script = r'''
import hashlib,json,sys,os,socket,threading
from pathlib import Path
root=Path(sys.argv[1]).resolve();expected=json.loads(sys.argv[2])
sys.path[:0]=[str(root/'Haike_video'),str(root),str(root/'Haike_video/.venv/Lib/site-packages')]
dll_handles=[os.add_dll_directory(str(p)) for p in [root/'runtime/msvc',root/'Haike_video/.venv/msvc'] if p.is_dir() and hasattr(os,'add_dll_directory')]
original_connect=socket.socket.connect;original_pair=socket.socketpair;ipc=threading.local()
def no_network(sock,address):
 if getattr(ipc,'socketpair',False) and isinstance(address,tuple) and address[0] in {'127.0.0.1','::1'}:
  return original_connect(sock,address)
 raise AssertionError('external network forbidden in recovery probe')
def pair(*a,**k):
 ipc.socketpair=True
 try:return original_pair(*a,**k)
 finally:ipc.socketpair=False
def no_connection(*a,**k):raise AssertionError('external network forbidden in recovery probe')
socket.socket.connect=no_network;socket.create_connection=no_connection;socket.socketpair=pair
from fastapi.testclient import TestClient
from backlot.server import create_app
from backlot.studio import Studio
app=create_app();client=TestClient(app)
health=client.get('/api/health');assert health.status_code==200 and Path(health.json()['workspace']).resolve()==root
assert client.get('/avatar').status_code==200, 'new frontend missing'
works=client.get('/api/works');drafts=client.get('/api/studio/drafts')
assert works.status_code==drafts.status_code==200
assert set(expected['works']) <= {w['work_id'] for w in works.json()}
assert set(expected['drafts']) <= {d['id'] for d in drafts.json()}
for work in expected['works']:
 response=client.get('/api/works/'+work+'/media');assert response.status_code==200
studio=Studio(root/'Haike_video/projects')
for asset in expected['assets']:
 p=studio.asset(asset);assert p.resolve().is_relative_to(root/'Haike_video/projects')
print(json.dumps({'status':'passed','workspace':str(root),'frontend':'passed','works_visible':len(works.json()),'drafts_visible':len(drafts.json()),'assets_openable':len(expected['assets']),'service_started':False,'provider_calls':0}))
client.close()
'''
    text = _execute(target,[python,'-s','-c',script,target,json.dumps(expected)])
    health = json.loads(text.strip().splitlines()[-1])
    need(health.get('status') == 'passed', '目标健康或新前端数据可见性未通过')
    return health


def recover(receipt_path, archive_path, *, archive_sha256, archive_size, closure_sha256, program_tree_sha256,
            runtime_source=None, runtime_manifest_sha256=None, online=False, prepare=None, probe=None, base_probe=None):
    fixture_seams=[name for name,value in [('prepare',prepare),('probe',probe),('base_probe',base_probe)] if value is not None]
    source,target,source_receipt,closure = context(receipt_path,closure_sha256)
    original_git = source_git(source)
    source_guards=_guard_source(source)
    archive_path = Path(archive_path).resolve(strict=True)
    need(core.native_path(archive_path).stat().st_size == archive_size and core.digest(archive_path) == archive_sha256, '完整资源包大小或SHA不符')
    material = {'source_receipt_sha256':core.digest(receipt_path),'closure_sha256':closure_sha256,
        'archive_sha256':archive_sha256,'program_tree_sha256':program_tree_sha256,'destination':str(target),
        'recovery_implementation_sha256':core.digest(Path(__file__)),
        'runtime_source':str(Path(runtime_source).resolve()) if runtime_source else None,
        'runtime_manifest_sha256':runtime_manifest_sha256,'online':bool(online),'fixture_seams':fixture_seams}
    folder = core.safe_path(target,'.local/source-recovery/'+identity(material)[:24]); core.native_path(folder).mkdir(parents=True,exist_ok=True)
    state_path = folder/'receipt.json'; state = read(state_path) if core.native_path(state_path).is_file() else {}
    if state:
        need(state.get('material') == material, '原恢复回执绑定改变')
        if state.get('status') in {'ready','runtime-ready-data-review','fixture-passed','fixture-passed-data-review'}:
            verify_program(target,closure)
            need(all(core.digest(core.safe_path(target,r['path']))==r['sha256'] for r in state['data']['after']), '恢复后用户数据已有修改，保留原目标')
            for name,row in closure['resources'].items():
                need(core.digest(core.safe_path(target,name))==row['sha256'],'恢复后runtime资源改变')
            for row in state.get('base_restoration',{}).get('files',[]):
                need(core.digest(core.safe_path(target,row['path']))==row['sha256'],'恢复后基础依赖改变')
            need((base_probe or probe_base)(target).get('status')=='passed','重复基础依赖/ABI核对未通过')
            result = (probe or probe_target)(target,state['data']['expected_visible'])
            need(result.get('status')=='passed','重复核对未通过')
            need(source_git(source)==original_git,'原Git有并发变化')
            need(_guard_source(source)==source_guards,'原暂挂任务/音色操作有并发变化')
            return {**state,'already_recovered':True}
        if state.get('data'):
            state['data_rollback']=rollback_data(target,state['data'])
            need(not any(r['status']=='concurrent-change-preserved' for r in state['data_rollback']), '上次资料目标有并发修改，保留待核对')
            state.pop('data')
    state = {**state,'schema':'haike.source-candidate-recovery/1','material':material,'status':'preparing',
        'source':str(source),'target':str(target),'original_git':original_git,'runtime_ready':False,
        'services_started':False,'provider_calls':0,'published':False}
    for name in ('error_type','execution_error','data_rollback_error'):
        state.pop(name,None)
    write(state_path,state)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            declaration,rows,objects = manifest(archive,closure,closure_sha256,program_tree_sha256)
            plan = {'schema':'haike.source-target-recovery-plan/1','material':material,
                'program_source_tree_sha256':declaration['program_source_tree_sha256'],'resources':[]}
            def inspect_resource(row):
                dst = core.safe_path(target,row['path']); before = core.digest(dst) if core.native_path(dst).is_file() else None
                need(before in {None,row['sha256']},'隔离目标已有不同runtime资源，保留：'+row['path'])
                return {'path':row['path'],'before_sha256':before,'after_sha256':row['sha256'],'size':row['size']}
            with ThreadPoolExecutor(max_workers=8) as pool:plan['resources']=list(pool.map(inspect_resource,rows))
            write(folder/'target-plan.json',plan)
            needed={r['path'] for r in plan['resources'] if r['before_sha256'] is None}
            install_rows=[r for r in rows if r['path'] in needed]
            object_names={r['blob'] for r in install_rows}
            install_objects={b:size for b,size in objects.items() if b in object_names}
            state['resources']={'verified_existing_files':len(rows)-len(install_rows),'restore_files':len(install_rows),
                'needed_blobs':len(install_objects),'archive_sha256_verified':True}
            need(shutil.disk_usage(target).free > sum(install_objects.values())+sum(r['size'] for r in install_rows)+32*1024**2,'隔离目标空间不足')
            # Existing destinations were individually SHA-checked above. Every
            # body needed for a new write is verified before publishing any of it.
            def stage_object(item):
                blob,size=item
                staged = core.safe_path(folder,blob)
                with archive.open(blob) as stream: copy_new(staged,stream,blob.split('/')[1],size)
            with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(stage_object,install_objects.items()))
            state['status']='installing-runtime';write(state_path,state)
            def install_resource(row):
                with core.native_path(core.safe_path(folder,row['blob'])).open('rb') as stream:
                    copy_new(core.safe_path(target,row['path']),stream,row['sha256'],row['size'])
            with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(install_resource,install_rows))
        state['runtime_prepare']=(prepare or prepare_runtime)(target)
        need(state['runtime_prepare'].get('status')=='passed','目标Python准备未通过')
        if runtime_source:
            state['status']='restoring-base-runtime';write(state_path,state)
            need(runtime_manifest_sha256 is not None,'运行时来源必须提供精确清单SHA')
            try:
                if not verified_base_cache(target,runtime_source,runtime_manifest_sha256,state.get('base_restoration',{})):
                    state['base_restoration']=supplement_runtime(target,runtime_source,runtime_manifest_sha256,folder)
            except (OSError,ValueError) as error:
                if not online:raise
                # A partial/older donor is optional, never a reason to modify
                # the original or give up on the target's fixed base lock.
                state['runtime_donor_rejected']={'error_type':type(error).__name__,'original_modified':False}
                write(state_path,state)
        state['base_probe']=(base_probe or probe_base)(target)
        if state['base_probe'].get('status')!='passed' and online:
            state['base_restoration']=restore_base_online(target,folder,closure)
            state['base_probe']=(base_probe or probe_base)(target)
        need(state['base_probe'].get('status')=='passed','目标基础依赖/锁版本/原生ABI缺失；回执保留明确missing，不标就绪')
        state['status']='binding-data';write(state_path,state)
        attempt=folder/('snapshot-'+uuid4().hex)
        entries = snapshot_data(source,target,attempt)
        state['data']=plan_data(source,target,attempt,entries,closure)
        write(state_path,state)
        apply_data(target,state['data'])
        verify_program(target,closure)
        result = (probe or probe_target)(target,state['data']['expected_visible'])
        need(result.get('status')=='passed','实际组件/健康/资料可见性未通过')
        need(source_git(source)==original_git,'原Git/暂存区有并发变化，保留两个现场')
        need(_guard_source(source)==source_guards,'原暂挂任务/音色操作有并发变化，保留两侧现场')
        status=('fixture-passed-data-review' if state['data']['unknown'] else 'fixture-passed') if fixture_seams else (
            'runtime-ready-data-review' if state['data']['unknown'] else 'ready')
        state.update(status=status,runtime_ready=not fixture_seams,probe=result,original_git_unchanged=True,
            recorded_source_sha256=source_receipt.get('source_commit'),production_acceptance=not fixture_seams,
            data_binding_complete=not bool(state['data']['unknown']),
            data_binding_scope='Studio drafts/assets and WorkCatalog media; frozen jobs/proofs preserved, not reexecuted',
            runtime_scope='injected-fixture-no-production-acceptance' if fixture_seams else 'workbench-and-18-components-no-media-render')
        write(state_path,state)
        return state
    except BaseException as exc:
        state.update(status='blocked',runtime_ready=False,error_type=type(exc).__name__)
        if hasattr(exc,'execution'):state['execution_error']=exc.execution
        if state.get('data'):
            try:state['data_rollback']=rollback_data(target,state['data'])
            except (OSError,ValueError):state['data_rollback_error']=True
        write(state_path,state)
        raise
