"""Package current template sources, portable covers and their UI/API dependencies."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('Haike_video/backlot/', 'Haike_video/lib/', 'Haike_video/scripts/',
            'Haike_video/tools/', 'Haike_video/templates/', 'Haike_video/design/',
            'Haike_video/skills/', 'Haike_video/docs/', 'Haike-Videohub/agent-runbooks/',
            'prototypes/haike-avatar-generator/', 'docs/TEMPLATE_DELIVERY.md')
LOCKS = ('Haike_video/requirements.txt', 'Haike_video/remotion-composer/package-lock.json')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build_components(stage, destination, *, runtime_bindings=None, include_resources=False):
    """Local explicit program slice + resource plan for root's transaction.

    No clean Git commit or donor project is required. This is not an installer;
    the owning app updater must include/verify the declared resources.
    """
    spec = importlib.util.spec_from_file_location('target_component_inventory', stage/'portable/motion_delivery_runtime.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    expected, names, _ = checker.inventory(stage)
    closure = checker.read(stage)
    destination.mkdir(parents=True, exist_ok=False)
    selected = []
    for name in sorted(names):
        source = checker.core.safe_path(stage, name)
        if not source.is_file(): raise ValueError('组件程序缺失：'+name)
        row = {'path':name, 'size':source.stat().st_size, 'sha256':sha(source)}
        target = destination/'payload'/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target);selected.append(row)
    resources = []
    for name, row in sorted(closure['resources'].items()):
        item = {'path':name,'size':row['size'],'sha256':row['sha256'],'group':row['group']}
        if include_resources:
            source = checker.resource_location(stage,name,row,runtime_bindings)
            if not source.is_file() or source.stat().st_size != row['size'] or sha(source) != row['sha256']:
                raise ValueError('必需资源尚未恢复或SHA不符：'+name)
            target = destination/'resources/files'/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target);item['blob']='files/'+name
        resources.append(item)
    value = {'schema':'haike.template-component-candidate/1',
        'id':'motion18-'+expected['closure_sha256'][:16],
        'style_count':18,'covered_template_ids':[r['template_id'] for r in closure['routes']],
        'motion_upgrade':expected,'files':selected,'resources_included':include_resources,
        'resource_manifest':'RESOURCES.json','resource_files':len(resources),
        'status':'component-payload-ready-for-transaction' if include_resources else 'program-slice-and-resource-plan-only',
        'installed_or_published':False}
    (destination/'UPDATE-MANIFEST.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
    (destination/'RESOURCES.json').write_text(json.dumps({'schema':1,'id':value['id'],
        'files':resources,'packages':[],'restoration':closure.get('restoration',{}),
        'component_manifest_sha256':expected['closure_sha256']},ensure_ascii=False,indent=2)+'\n','utf-8')
    (destination/'使用说明.txt').write_text(
        '18样式组件程序与固定资源清单；历史版本数不是样式数。\n'
        '由根应用更新事务整合、校验、备份并回退；不使用旧40封面模板安装器。\n'
        '资源未包含时仅为可审查程序切片，不得报告已安装或已可制作。\n'
        '不得把本轮用户素材/账号/私有人像声音/旧项目运行源混入包。\n','utf-8-sig')
    return value


def build(stage, baseline, destination, *, runtime_bindings=None, include_resources=False):
    stage, destination = Path(stage).resolve(), Path(destination).resolve()
    if (stage/'Haike_video/config/motion-preferred-production.json').is_file():
        return build_components(stage,destination,runtime_bindings=runtime_bindings,include_resources=include_resources)
    if baseline is None: raise ValueError('旧格式模板更新必须指定baseline；当前18组件方案不需要它')
    destination.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((stage / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
    release = json.loads((stage / 'RELEASE.json').read_text(encoding='utf-8'))
    current = {e['path']: e for e in manifest['files']}
    with zipfile.ZipFile(baseline) as archive:
        roots = [n for n in archive.namelist() if n.endswith('/PACKAGE-MANIFEST.json') and n.count('/') == 1]
        if len(roots) != 1:
            raise ValueError('Baseline must have exactly one root package manifest')
        previous = {e['path']: e for e in json.loads(archive.read(roots[0]))['files']}
    for path in LOCKS:
        if current[path]['sha256'] != previous[path]['sha256']:
            raise ValueError('Template update requires unchanged runtime dependencies: ' + path)
    spec = importlib.util.spec_from_file_location('template_installer', ROOT / 'scripts/install-template-update.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    selected = []
    for path, entry in current.items():
        if not path.startswith(PREFIXES):
            continue
        if any(p in installer.FORBIDDEN for p in Path(path).parts):
            continue
        # Full template/code assets are included; shared engine/UI files are a
        # delta against the supported baseline, not an unrelated module upgrade.
        complete = path.startswith(('Haike_video/templates/', 'Haike_video/backlot/ui/avatar-generator/'))
        if not complete and path in previous and entry['sha256'] == previous[path]['sha256']:
            continue
        source = stage / path
        if sha(source) != entry['sha256']:
            raise ValueError('Stage changed after manifest: ' + path)
        target = destination / 'payload' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        selected.append({k: entry[k] for k in ('path', 'size', 'sha256')})
    covers = sorted(p.stem for p in (stage / 'Haike_video/templates/library-covers').glob('*.jpg'))
    if not covers or len(covers) != len(set(covers)):
        raise ValueError('模板封面清单为空或身份重复')
    catalog = json.loads((stage/'Haike_video/templates/library.json').read_text('utf-8'))
    if not set(covers) <= {row['id'] for row in catalog['templates']}:
        raise ValueError('模板封面未绑定实际目录版本')
    value = {'schema': 1, 'id': 'template-gallery-20261027',
             'source_snapshot': release['source_commit'], 'covered_template_ids': covers,
             'required_locks': [{'path': p, 'sha256': current[p]['sha256']} for p in LOCKS],
             'files': selected}
    (destination / 'UPDATE-MANIFEST.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(ROOT / 'scripts/install-template-update.py', destination / 'install-template-update.py')
    script = (ROOT / 'scripts/install-template-update.ps1').read_text(encoding='utf-8-sig')
    (destination / 'install-template-update.ps1').write_text(script, encoding='utf-8-sig')
    (destination / '更新模板.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-template-update.ps1" %*\r\npause\r\n', encoding='ascii')
    (destination / '使用说明.txt').write_text(
        '海客模板组件更新包\n\n'
        '1. 将整个更新包完整解压到一个新文件夹。不要仅复制 templates 文件夹。\n'
        '2. 关闭旧副本工作台和它的后台服务，保留其他副本。\n'
        '3. 双击 更新模板.cmd，输入旧版项目根目录（里面有 Haike_video、creatorhub 等目录）。\n'
        '4. 看到 ok: true 后，用旧目录原有启动器重新启动。浏览器按 Ctrl+F5，进入数字人口播 → 选择模板 → 视觉模板库。\n\n'
        f'本包包含{len(covers)}个目录版本的既有截图、模板源码与手册、相应API和已编译前端。\n'
        '目录版本数不是独立样式数，保留原有制作及开发入口。\n'
        '完整样片和生产用人物/素材/音频不随包迁移；原机的有效私有预览绑定继续优先使用。封面可脱离原机路径显示。\n'
        '无需安装npm，不修改Key、Cookie、数据库、作品、素材或其他模块。首次制作使用自己的素材和已开通服务。\n'
        '依赖锁须与2026-10-21安装版兼容；不兼容时脚本会在写入前停止，请改用完整新版ZIP。\n'
        '自动备份位于目标根目录 .local/template-updates/，成功回执会显示具体路径。\n'
        '只检查不更新：powershell -ExecutionPolicy Bypass -File .\\install-template-update.ps1 -Target "旧根目录" -Check\n'
        '回退（先关闭目标服务）：用目标 runtime/python/python.exe 调用 install-template-update.py --target "旧根目录" --rollback "回执中的备份路径"。\n', encoding='utf-8-sig')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--runtime-bindings', type=Path, help='显式已核SHA的系统或只读运行时映射')
    parser.add_argument('--include-resources', action='store_true', help='将固定资源正文一起物化；否则只生成机器资源计划')
    args = parser.parse_args()
    bindings = json.loads(args.runtime_bindings.read_text('utf-8-sig')) if args.runtime_bindings else None
    result = build(args.stage, args.baseline, args.destination,runtime_bindings=bindings,include_resources=args.include_resources)
    print(json.dumps({'ok': True, 'files': len(result['files']), 'covers': len(result['covered_template_ids'])}))


if __name__ == '__main__':
    main()
