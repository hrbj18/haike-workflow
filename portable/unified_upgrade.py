"""Fixed upgrade dispatch; installations and dirty Git checkouts remain distinct.

The existing online/bootstrap/API transactions own portable writes. Source or
unrecognized historical layouts get a separate pinned official source candidate;
their original tree, index, configuration and user data are never overwritten.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = 'https://github.com/hrbj18/haike-workflow'
COMMIT = re.compile(r'[0-9a-f]{40}')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def online():
    spec = importlib.util.spec_from_file_location('haike_fixed_online_upgrade', ROOT/'scripts/update-from-github.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root, *args, optional=False):
    env = os.environ.copy()
    env['GIT_OPTIONAL_LOCKS'] = '0'
    # Inherited shell Git selectors must not redirect a command to another index.
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        env.pop(key, None)
    command = ['git', '-c', 'core.longpaths=true']
    if root is not None:
        command.extend(['-C', str(root)])
    result = subprocess.run([*command, *args], env=env, capture_output=True, timeout=600,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(optional or result.returncode == 0, 'Git隔离升级未完成；原目录保持原样。请核对原仓库和官方提交。')
    return result.stdout if not optional or result.returncode == 0 else b''


def official_origin(value):
    return value in {OFFICIAL, OFFICIAL+'.git', 'git@github.com:hrbj18/haike-workflow.git',
                    'ssh://git@github.com/hrbj18/haike-workflow.git'}


def identify(target):
    """Bounded layout search: explicit root and two known Haike wrapper levels."""
    raw = Path(target)
    require(not raw.is_symlink() and not (hasattr(raw, 'is_junction') and raw.is_junction()), '目标不能经过目录链接')
    target = raw.resolve(strict=True)
    require(target.is_dir() and not target.is_symlink(), '目标必须是实际目录')
    candidates, pending = [], [(target, 0)]
    u = online()
    while pending:
        root, depth = pending.pop(0)
        if (root/'.git').exists():
            top = _git(root, 'rev-parse', '--show-toplevel', optional=True).decode('utf8').strip()
            if top and Path(top).resolve() == root:
                candidates.append({'root': str(root), 'family': 'git-checkout'})
                continue
        release_path = root/'RELEASE.json'
        if release_path.is_file() and (root/'PACKAGE-MANIFEST.json').is_file():
            release = u.read(release_path)
            if release.get('edition') == 'haike-workflow-2':
                candidates.append({'root': str(root), 'family': 'portable', 'release': release,
                    'runtime_present': (root/'runtime/python/python.exe').is_file()})
                continue
        if (root/'Haike_video/backlot/server.py').is_file():
            candidates.append({'root': str(root), 'family': 'historical-layout'})
            continue
        if depth < 2:
            children = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                        and not (hasattr(p, 'is_junction') and p.is_junction())
                        and re.fullmatch(r'haike[-_ a-z0-9.]*', p.name, re.I)]
            require(len(children) <= 16, '海客目录候选过多，请明确目标安装根')
            pending.extend((p, depth+1) for p in children)
    require(len(candidates) <= 1, '发现多个海客副本，请明确本次目标；未改任何副本')
    return candidates[0] if candidates else {'root': str(target), 'family': 'unrecognized-source'}


def load_feed(url):
    u = online()
    with u.remote(u.feed_url(url)) as response:
        raw = response.read(1_000_001)
    require(len(raw) <= 1_000_000, '发行清单过大')
    feed = json.loads(raw)
    require(feed.get('schema') == 1 and feed.get('edition') == 'haike-workflow-2'
            and feed.get('channel') == 'stable', '不是官方稳定更新清单')
    u.version(feed['version'])
    if 'bootstrap' in feed:
        u.validate_feed(feed)
    return feed


def plan(target, url=OFFICIAL, *, feed=None, destination=None):
    u = online()
    u.feed_url(url)  # Reject foreign repositories even for an offline layout plan.
    installation = identify(target)
    family = installation['family']
    release = installation.get('release', {})
    route = 'isolated-source'
    if family == 'git-checkout':
        route = 'git-worktree'
    elif family == 'portable':
        bootstrap = (feed or {}).get('bootstrap', {})
        if bootstrap.get('project_compatibility'):
            route = 'project-transaction'
        elif release.get('source_commit') == u.BASE_SOURCE and not release.get('version'):
            route = '1027-transaction'
        elif feed and any(b.get('version') == release.get('version') and b.get('source_commit') == release.get('source_commit')
                          for b in bootstrap.get('modern_bases', [])):
            route = 'migration-transaction'
        elif release.get('version'):
            try:
                if u.version(release['version']) >= (1, 2, 0):
                    route = 'application-api'
            except ValueError:
                pass  # Historical labels get an isolated candidate, not a weaker version parser.
    return {'schema': 'haike.unified-upgrade-plan/1', 'target': installation['root'], 'family': family,
        'route': route, 'github_url': url, 'current_version': release.get('version'),
        'target_version': (feed or {}).get('version'), 'destination': str(Path(destination).resolve()) if destination else None,
        'preservation': 'original configuration, works, private media and Git index remain in original tree',
        'checks': ['official source and SHA', 'existing transaction preflight', 'no local program overwrite',
                   'source route is independent and does not activate or restart existing installation']}


def git_snapshot(root):
    index = _git(root, 'rev-parse', '--git-path', 'index').decode('utf8').strip()
    index = Path(index) if Path(index).is_absolute() else root/index
    digest = lambda data: hashlib.sha256(data).hexdigest()
    untracked = {}
    for raw in _git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
        if raw:
            name = os.fsdecode(raw)
            p = root/name
            if p.is_symlink():
                untracked[name] = digest(os.fsencode(os.readlink(p)))
            elif p.is_file():
                untracked[name] = online().sha(p)
    return {'head': _git(root, 'rev-parse', 'HEAD').decode().strip(),
        'branch': _git(root, 'symbolic-ref', '-q', 'HEAD', optional=True).decode().strip(),
        'index_sha256': online().sha(index) if index.is_file() else None,
        'status_sha256': digest(_git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')),
        'working_diff_sha256': digest(_git(root, 'diff', '--binary')),
        'cached_diff_sha256': digest(_git(root, 'diff', '--cached', '--binary')), 'untracked': untracked}


def _destination(root, commit, destination):
    raw = Path(destination).absolute() if destination else root.parent/(root.name+'-upgrade-'+commit[:12])
    for p in [raw, *raw.parents]:
        require(not p.is_symlink() and not (hasattr(p, 'is_junction') and p.is_junction()), '隔离路径不能经过链接')
    target = raw.resolve()
    require(target != root and not target.is_relative_to(root) and not root.is_relative_to(target)
            and not target.is_symlink(), '隔离目标必须位于原目录之外，不能覆盖或包住原目录')
    # Refuse junction parents; ordinary Windows paths use Git core.longpaths.
    for p in [target, *target.parents]:
        require(not p.is_symlink() and not (hasattr(p, 'is_junction') and p.is_junction()), '隔离路径不能经过链接')
    return target


def source_candidate(info, feed, destination=None):
    root = Path(info['target'])
    commit = feed.get('source_commit')
    if not commit and feed.get('bootstrap', {}).get('program'):
        # Older official feeds identify source inside the SHA-verified program
        # bundle. Read metadata without executing it, outside the dirty tree.
        u = online()
        cache = root.parent/(root.name+'.upgrade-downloads')
        archive = u.fetch_asset(cache, feed['bootstrap']['program'])
        bundle = u.extract_program(cache, archive)
        metadata = u.read(bundle/'UPGRADE.json')['release']
        require(metadata.get('version') == feed['version'], '源码元数据与官方发行版本不符')
        commit = metadata.get('source_commit')
    require(isinstance(commit, str) and COMMIT.fullmatch(commit), '官方发行缺少精确源码提交；保留原安装，需补齐官方发布元数据')
    target = _destination(root, commit, destination)
    receipt_path = target.parent/(target.name+'.haike-upgrade.json')
    before = git_snapshot(root) if info['family'] == 'git-checkout' else None
    use_worktree = before is not None
    if before is not None:
        origin = _git(root, 'config', '--get', 'remote.origin.url').decode('utf8').strip()
        use_worktree = official_origin(origin)
    if target.exists():
        require(receipt_path.is_file(), '隔离目标已存在，保留现场并显式选择新目录')
        receipt = json.loads(receipt_path.read_text('utf8'))
        require(receipt.get('original_root') == str(root) and receipt.get('source_commit') == commit
                and receipt.get('status') == 'source-ready', '隔离现场与本次官方提交不符，请保留并核对')
        require(_git(target, 'rev-parse', 'HEAD').decode().strip() == commit, '隔离候选提交已有变化，保留现场')
        require(not _git(target, 'status', '--porcelain', '--untracked-files=normal'), '隔离候选有用户修改，保留并使用新目录')
        return {**receipt, 'ok': True, 'already_current_candidate': True, 'original_git_unchanged': before is None or before == git_snapshot(root)}
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = {'schema': 'haike.unified-upgrade-source/1', 'original_root': str(root), 'destination': str(target),
        'source_commit': commit, 'version': feed['version'], 'status': 'preparing',
        'user_data_root': str(root), 'activated': False, 'runtime_acceptance': 'pending isolated setup/diagnosis',
        'original_git_snapshot': before}
    u = online()
    # The private receipt is a sibling of the candidate, outside the dirty tree.
    u.native_path(receipt_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', 'utf8')
    try:
        if use_worktree:
            _git(root, 'fetch', '--no-tags', '--no-write-fetch-head', 'origin', commit)
            _git(root, 'worktree', 'add', '--detach', str(target), commit)
        else:
            _git(None, 'clone', '--no-checkout', '--origin', 'origin', OFFICIAL+'.git', str(target))
            _git(target, 'fetch', '--no-tags', '--no-write-fetch-head', 'origin', commit)
            _git(target, 'checkout', '--detach', commit)
        require(_git(target, 'rev-parse', 'HEAD').decode().strip() == commit, '隔离检出的提交与官方清单不符')
        if before is not None:
            require(before == git_snapshot(root), '原Git状态有并发变化，保留两个现场并核对，未重置原目录')
        # Snapshot only small local settings/identity; media and works remain at
        # the original absolute location and are not copied into public source.
        backup = target.parent/(target.name+'.private-backup')
        saved = []
        for name in ['RELEASE.json', 'PACKAGE-MANIFEST.json', 'VERSION.json', 'Haike_video/config.yaml',
                     'Haike_video/config.local.yaml', 'Haike_video/.env', 'creatorhub/config.yaml']:
            p = u.safe(root, name)
            if u.native_path(p).is_file():
                q = u.safe(backup, name)
                u.native_path(q.parent).mkdir(parents=True, exist_ok=True)
                require(not u.native_path(q).exists(), '私有备份路径已有现场，保留并核对')
                with u.native_path(q).open('xb') as stream:
                    stream.write(u.native_path(p).read_bytes())
                saved.append({'path': name, 'sha256': u.sha(q)})
        receipt.update(status='source-ready', private_backup=str(backup), saved_settings=saved,
            original_git_unchanged=before is None or before == git_snapshot(root),
            next='在隔离副本按README/setup与对应便携迁移规则完成运行依赖和数据绑定；通过诊断后才切换。原配置/作品/私材继续保留原目录。')
    except BaseException as exc:
        receipt.update(status='preparation-failed', error_type=type(exc).__name__)
        raise
    finally:
        u.native_path(receipt_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', 'utf8')
    return {**receipt, 'ok': True}


def execute(target, url=OFFICIAL, *, destination=None, check=False, start=True):
    feed = load_feed(url)
    info = plan(target, url, feed=feed, destination=destination)
    if check:
        return {'ok': True, 'check_only': True, **info}
    if info['route'] in {'1027-transaction', 'migration-transaction', 'project-transaction', 'application-api'}:
        try:
            result = online().run(url, Path(info['target']), start=start)
            return production_inputs({**result, 'unified_route': info['route']},feed)
        except ValueError as exc:
            # User program/dependency conflicts get a concrete, separate source
            # candidate rather than weakening the original transaction checks.
            message = str(exc)
            if any(marker in message for marker in ['用户修改', '本地修改', '依赖不匹配', '基线', '当前构建', '已被修改']):
                result = source_runtime_candidate({**info, 'route': 'isolated-source'}, feed, destination)
                return {**result, 'portable_transaction': 'not_applied', 'isolation_reason': '原文件/依赖需保留，已建立隔离官方源码候选'}
            raise
    return source_runtime_candidate(info, feed, destination)


def production_inputs(result,feed):
    """Current18 and optional historical native presets are separate scopes."""
    cap=feed.get('template_capability',{})
    current=cap.get('motion_upgrade',{})
    if current.get('schema')!='haike.motion-replay-delivery/2':
        return result
    component=result.get('component_check') or result.get('template_delivery',{}).get('component_selftest',{})
    if not component and result.get('backup'):
        path=Path(result['backup'])/'receipt.json'
        if path.is_file():
            component=online().read(path).get('probe',{}).get('template_delivery',{}).get('component_selftest',{})
    verified=component.get('status')=='passed' and component.get('template_count')==18
    output={k:v for k,v in result.items() if k!='templates'}
    return {**output,'templates':[{**row,'input_status':'awaiting-episode-inputs'} for row in current.get('templates',[])],
      'production_input_preparation':{
        'current18':{'template_count':len(current.get('templates',[])),
            'component_status':'passed' if verified else 'not-rechecked-in-this-result',
            'status':'awaiting-episode-inputs','episode_inputs_supplied':False,'preparation_called':False,
            'entrypoint':'Haike_video/scripts/motion_replay.py prepare',
            'templates':current.get('templates',[]),
            'legacy_native_setup_blocks_current18':False,'media_acceptance':'separate-root-D-validation'},
        'legacy_native_presets':{'scope':'optional-original-presets','affects_current18':False,
            'presets':cap.get('presets',[]),'catalog':result.get('templates',[])}}}


def source_runtime_candidate(info,feed,destination=None,*,online_module=None):
    from .source_upgrade import complete
    result=complete(info,feed,destination,online_module=online_module or online(),snapshot_git=git_snapshot)
    return production_inputs(result,feed)


def apply_candidate(target, feed_path, *, test_release_base=None, health_check=None, rollback=None,destination=None):
    """Real isolated release acceptance, separate from the official apply path.

    Candidate provenance is explicit and cannot pretend to be a published build.
    The only HTTP exception is an explicit loopback test server for this sandbox.
    The verified bundle's original transaction still owns all program writes.
    """
    u = online()
    root = Path(target).resolve(strict=True)
    marker = root/'UNIFIED-UPGRADE-SANDBOX.json'
    require(marker.is_file() and u.read(marker) == {'schema': 1, 'isolated_target': str(root)},
            '候选验收只允许显式标记的独立测试目录，不能更新日常安装')
    feed = u.validate_feed(u.read(feed_path))
    provenance = feed.get('candidate_provenance', {})
    require(feed.get('candidate_only') is True and re.fullmatch('[0-9a-f]{64}', provenance.get('tree_sha256', ''))
            and COMMIT.fullmatch(provenance.get('base_git_commit', '')), '候选须绑定真实树SHA和Git来源，不能冒充正式发行')
    if test_release_base:
        base = parse.urlsplit(test_release_base)
        require(base.scheme == 'http' and base.hostname in {'127.0.0.1', '::1'} and base.port
                and not base.username and not base.password and not base.query and not base.fragment,
                '候选测试服务只能是明确的本机回环HTTP地址')
        def local_asset(url, authentication=None):
            require(authentication is None, '隔离测试不传递GitHub凭据')
            u.https(url)
            return request.build_opener(request.ProxyHandler({})).open(
                test_release_base.rstrip('/')+parse.urlsplit(url).path, timeout=45)
        u.remote = local_asset
    info=plan(root,feed=feed,destination=destination)
    if info['family'] in {'git-checkout','historical-layout'} or info['family']=='unrecognized-source' and (
            'source_recovery' in feed or not (root/'PACKAGE-MANIFEST.json').is_file()):
        require(health_check is None and rollback is None,'源码候选接线只允许真实默认恢复探针，不能注入伪健康/便携回退')
        result=source_runtime_candidate(info,feed,destination,online_module=u)
        return {**result,'candidate_only':True,'published':False,'candidate_provenance':provenance}
    program = u.fetch_asset(root, feed['bootstrap']['program'])
    resources = u.fetch_asset(root, feed['bootstrap']['resources'])
    bundle = u.extract_program(root, program)
    manifest = u.read(bundle/'UPGRADE.json')
    require(manifest.get('release', {}).get('version') == feed['version']
            and manifest['resources']['sha256'] == feed['bootstrap']['resources']['sha256'], '候选清单与已校验附件不一致')
    require(manifest['release'].get('template_capability') == feed.get('template_capability'), '候选模板能力身份不一致')
    # Load only the SHA-verified bundle, with its own fixed core/dependency guards.
    previous = list(sys.path)
    previous_core = sys.modules.pop('release_core', None)
    try:
        sys.path.insert(0, str(bundle))
        spec = importlib.util.spec_from_file_location('haike_verified_candidate_installer', bundle/'legacy_upgrade.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        u.verify_installed_program(root, manifest)
        installer.stopped(root)
        with installer.lock(root):
            if rollback is not None:
                result = installer.restore(root, Path(rollback).resolve(strict=True))
            else:
                result = installer.apply(bundle, root, resources, health_check=health_check or installer.probe)
        return production_inputs({**result, 'candidate_only': True, 'published': False, 'candidate_provenance': provenance,
                'verified_program_sha256': u.sha(program), 'verified_resources_sha256': u.sha(resources),
                'installer': str(bundle/'legacy_upgrade.py')},feed)
    finally:
        sys.path[:] = previous
        sys.modules.pop('release_core', None)
        if previous_core is not None:
            sys.modules['release_core'] = previous_core
