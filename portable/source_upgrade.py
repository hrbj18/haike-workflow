"""Continue a trusted release into a new usable source/runtime snapshot.

The official program ZIP owns source bytes; the same feed's full resource ZIP
owns runtime bytes. Original Git/index/data are read only. No checkout or invented
commit is needed for an explicitly identified working-source candidate.
"""
from pathlib import Path
import importlib.util
import json
import re

from . import app_update as core
from . import source_candidate_recovery as recovery

REQUIRED_PROGRAM = {
    'portable/source_upgrade.py','portable/source_candidate_recovery.py','scripts/recover-upgrade-source.py',
    'portable/unified_upgrade.py','scripts/upgrade-haike.py','scripts/update-from-github.py',
    'portable/app_update.py','portable/update_dependencies.py','portable/dependency-downloads.json',
    'portable/queue_update_guard.py','portable/audio_update_guard.py','portable/template_capability.py',
    'portable/motion_delivery_runtime.py',recovery.BASE_LOCK,
}


def need(ok,message):
    recovery.need(ok,message)


def write(path,value):
    recovery.write(path,value)


def load_installer(target):
    # Only after every public program byte was checked against this same feed.
    path=core.safe_path(target,'portable/source_candidate_recovery.py')
    spec=importlib.util.spec_from_file_location('haike_verified_source_recovery',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def program_rows(bundle,feed,descriptor):
    plan=core._read(bundle/'UPGRADE.json');release=plan.get('release',{})
    need(release.get('version')==feed['version'] and release.get('source_commit')==feed.get('source_commit')
         and release.get('template_capability')==feed.get('template_capability'), '源码程序与同次feed发行身份不一致')
    rows=plan.get('files');need(isinstance(rows,list) and 0<len(rows)<=20000,'源码程序清单数量无效')
    names=set();frozen=[]
    for row in rows:
        name=row['path'];need(core.is_program_path(name) and name.casefold() not in names
            and row.get('payload')=='payload/'+name and type(row.get('size')) is int and 0<=row['size']<256*1024**2
            and re.fullmatch('[0-9a-f]{64}',row.get('sha256','')), '源码程序路径、摘要或数量无效：'+name)
        names.add(name.casefold())
        p=core.safe_path(bundle,row['payload'])
        need(core.native_path(p).is_file() and core.native_path(p).stat().st_size==row['size'] and core.digest(p)==row['sha256'],
            '源码程序正文SHA不符：'+name)
        core.validate_public_route(name,core.native_path(p).read_bytes())
        frozen.append({k:row[k] for k in ('path','size','sha256')})
    need(sum(r['size'] for r in frozen)<256*1024**2,'源码程序展开超限')
    frozen.sort(key=lambda r:r['path'])
    need(recovery.identity(frozen)==descriptor['program_tree_sha256'],'源码程序完整树SHA不符')
    actual={r['path']:r for r in frozen}
    need(REQUIRED_PROGRAM<=set(actual),'源码程序未交付必需恢复器/CLI/基础锁：'+','.join(sorted(REQUIRED_PROGRAM-set(actual))))
    for key in ('base_lock','implementation'):
        expected=descriptor[key]
        need(actual[expected['path']]['sha256']==expected['sha256'],'源码恢复基础锁/helper与feed身份不符')
    need(actual.get(recovery.CLOSURE,{}).get('sha256')==descriptor['closure_sha256'],'源码程序没有绑定本次精确闭包')
    return plan,rows,frozen


def complete(info,feed,destination,*,online_module,snapshot_git):
    """Called by normal apply and marked candidate apply; no probe injection."""
    descriptor=online_module.validate_source_recovery(feed)
    need(re.fullmatch('[0-9a-f]{40}',feed.get('source_commit','')),'源码恢复缺真实Git来源身份')
    source=Path(info['target']).resolve(strict=True)
    # Use the exact snapshot identity, not the base Git provenance, for its name.
    from .unified_upgrade import _destination
    target=_destination(source,descriptor['program_tree_sha256'][:40],destination)
    original=snapshot_git(source) if info['family']=='git-checkout' else None
    guards=recovery._guard_source(source)
    source_receipt=target.parent/(target.name+'.haike-upgrade.json')
    if target.exists():
        need(source_receipt.is_file(),'隔离目标已存在且不属于本次恢复，保留现场')
        receipt=core._read(source_receipt)
        need(receipt.get('schema')=='haike.unified-upgrade-source/1'
            and receipt.get('original_root')==str(source) and receipt.get('destination')==str(target)
            and receipt.get('source_tree_sha256')==descriptor['program_tree_sha256']
            and receipt.get('source_commit')==feed['source_commit'] and receipt.get('activated') is False,
            '隔离候选的来源/目标/树身份不一致，保留现场')
    else:
        core.native_path(target).mkdir(parents=True,exist_ok=False)
        receipt={'schema':'haike.unified-upgrade-source/1','status':'preparing','original_root':str(source),
            'destination':str(target),'source_commit':feed['source_commit'],'source_tree_sha256':descriptor['program_tree_sha256'],
            'source_kind':'verified-program-snapshot','git_commit_role':'provenance-only','version':feed['version'],
            'activated':False,'original_git_snapshot':original,'user_data_root':str(source)}
        write(source_receipt,receipt)
    continuation=core.safe_path(target,'.local/source-upgrade/continuation.json')
    state={'schema':'haike.unified-source-continuation/1','status':'downloading','target':str(target),
        'feed_sha256':recovery.identity(feed),'source_tree_sha256':descriptor['program_tree_sha256'],
        'original_git_unchanged':True,'activated':False,'services_started':False,'provider_calls':0}
    write(continuation,state)
    try:
        program=online_module.fetch_asset(target,feed['bootstrap']['program'])
        resource=online_module.fetch_asset(target,descriptor['resources'])
        cache=core.safe_path(target,'.local/source-upgrade/program-extraction.json')
        prior=core._read(cache) if core.native_path(cache).is_file() else {}
        if prior.get('program_sha256')==feed['bootstrap']['program']['sha256']:
            name=prior.get('bundle_relative','')
            need(name.startswith('.local/gu/b/') and name.endswith('/haike-update-1.2'),'源码解包缓存路径无效')
            bundle=core.safe_path(target,name)
        else:
            bundle=online_module.extract_program(target,program)
            write(cache,{'program_sha256':feed['bootstrap']['program']['sha256'],'bundle_relative':bundle.relative_to(target).as_posix()})
        plan,rows,frozen=program_rows(bundle,feed,descriptor)
        # Preflight every destination before copying any application code.
        for row in frozen:
            p=core.safe_path(target,row['path'])
            need(not core.native_path(p).exists() or core.native_path(p).is_file() and core.digest(p)==row['sha256'],
                '隔离源码已有用户修改，保留：'+row['path'])
        state['status']='installing-source';write(continuation,state)
        for row in rows:
            with core.native_path(core.safe_path(bundle,row['payload'])).open('rb') as stream:
                recovery.copy_new(core.safe_path(target,row['path']),stream,row['sha256'],row['size'])
        # Runtime/asset paths are declared now; the recovery helper verifies their
        # actual bytes before any factory/health check uses this inventory.
        closure=core._read(target/recovery.CLOSURE)
        inventory={r['path']:r for r in frozen}
        inventory.update({name:{'path':name,**row} for name,row in closure['resources'].items()})
        for name,value in [('RELEASE.json',plan['release']),('PACKAGE-MANIFEST.json',{'schema':1,'files':list(inventory.values())})]:
            p=core.safe_path(target,name)
            content=core.json_bytes(value)
            need(not core.native_path(p).exists() or core.native_path(p).read_bytes()==content,'隔离发行元数据已被修改，保留：'+name)
            if not core.native_path(p).exists():core._atomic_write(p,content)
        if receipt['status']!='source-ready':
            receipt.update(status='source-ready',original_git_unchanged=original is None or snapshot_git(source)==original,
                runtime_acceptance='automatic same-feed recovery in progress')
            write(source_receipt,receipt)
        state['status']='recovering-runtime-and-data';write(continuation,state)
        runner=load_installer(target)
        donor=source if (source/'PACKAGE-MANIFEST.json').is_file() and (source/'Haike_video/.venv/Lib/site-packages').is_dir() else None
        result=runner.recover(source_receipt,resource,archive_sha256=descriptor['resources']['sha256'],
            archive_size=descriptor['resources']['size'],closure_sha256=descriptor['closure_sha256'],
            program_tree_sha256=descriptor['program_tree_sha256'],runtime_source=donor,
            runtime_manifest_sha256=core.digest(donor/'PACKAGE-MANIFEST.json') if donor else None,online=True)
        need(original is None or snapshot_git(source)==original,'原Git/index有并发变化；保留两个现场')
        need(recovery._guard_source(source)==guards,'原冻结队列/音色记录有并发变化；保留两个现场')
        ready=result.get('status')=='ready' and result.get('runtime_ready') is True and result.get('data_binding_complete') is True
        state.update(status=result['status'],runtime_ready=result.get('runtime_ready',False),
            data_binding_complete=result.get('data_binding_complete',False),production_acceptance=result.get('production_acceptance',False),
            recovery=result,original_git_unchanged=True,source_program_sha256=core.digest(program),
            resource_sha256=core.digest(resource),next='隔离副本运行与已支持数据绑定完成；按本期输入准备制作。'
                if ready else '隔离副本保留；按恢复回执unknown条目核对未支持的数据绑定，不重试原云任务。')
        write(continuation,state)
        output={k:v for k,v in state.items() if k!='recovery'}
        component=result.get('probe',{}).get('component',{})
        return {**output,'ok':ready,'source_commit':feed['source_commit'],'source_kind':receipt['source_kind'],
            'source_tree_sha256':descriptor['program_tree_sha256'],'runtime_receipt':str(continuation),
            'unified_route':info['route'],'already_current_candidate':bool(result.get('already_recovered')),
            'component_check':{k:component[k] for k in ('status','template_count','scope') if k in component},
            'data_visibility':result.get('probe',{}).get('health',{}),
            'unknown_data_items':len(result.get('data',{}).get('unknown',[])),
            'media_rendered':False,'published':False}
    except BaseException as error:
        state.update(status='blocked',runtime_ready=False,error_type=type(error).__name__,
            next='读取本隔离副本continuation及source-recovery回执恢复；原目录/队列不变，无需重置Git或重复云调用。')
        write(continuation,state)
        raise
