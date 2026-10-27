"""Package current template sources, portable covers and their UI/API dependencies."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
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


def build(stage, baseline, destination):
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
    if len(covers) != 40:
        raise ValueError('Expected the current 40 screenshot-backed template versions')
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
        '海客现用40模板更新包 · 2026-10-27\n\n'
        '1. 将整个更新包完整解压到一个新文件夹。不要仅复制 templates 文件夹。\n'
        '2. 关闭旧副本工作台和它的后台服务，保留其他副本。\n'
        '3. 双击 更新模板.cmd，输入旧版项目根目录（里面有 Haike_video、creatorhub 等目录）。\n'
        '4. 看到 ok: true 后，用旧目录原有启动器重新启动。浏览器按 Ctrl+F5，进入数字人口播 → 选择模板 → 视觉模板库。\n\n'
        '本包包含40个现用模板版本的真实截图、模板源码与手册、相应API和已编译前端。\n'
        '页面保留原有42条目录：40条带截图，另2条为图文制作入口和访谈开发手册入口。\n'
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
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.stage, args.baseline, args.destination)
    print(json.dumps({'ok': True, 'files': len(result['files']), 'covers': len(result['covered_template_ids'])}))


if __name__ == '__main__':
    main()
