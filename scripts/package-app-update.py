"""Build a public, compatible application patch from two audited portable stages.

This command only creates local artifacts. Publication is a separate operation.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
METADATA = {'VERSION.json', 'RELEASE.json', 'PACKAGE-MANIFEST.json'}


def installer():
    spec = importlib.util.spec_from_file_location('haike_patch_installer', ROOT / 'portable/app_update.py')
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError('更新包下载地址必须是无账号密码的 HTTPS 地址')


def audited_stage(root, update):
    root = Path(root).resolve(strict=True)
    if (root / '.git').exists():
        raise ValueError('请提供已生成的便携 stage，不要使用源码工作区')
    release = read_json(root / 'RELEASE.json')
    if release.get('edition') != 'haike-workflow-2' or release.get('channel') != 'stable':
        raise ValueError('更新包只接受海客稳定版便携 stage')
    update.version_tuple(release.get('version', ''))
    if (release.get('platform') != 'windows-x64' or not release.get('runtime_id')
            or not isinstance(release.get('data_schema'), int)
            or isinstance(release.get('data_schema'), bool)
            or not re.fullmatch(r'[0-9a-f]{40}', release.get('source_commit', ''))):
        raise ValueError('stage 缺少有效的发布身份，请重新生成便携包')
    manifest = read_json(root / 'PACKAGE-MANIFEST.json')
    if manifest.get('schema') != 1 or not isinstance(manifest.get('files'), list):
        raise ValueError('便携包清单格式错误')
    entries, insensitive = {}, set()
    for entry in manifest['files']:
        name = entry['path']
        update._parts(name)
        if name in entries or name.casefold() in insensitive:
            raise ValueError('便携包清单含重复文件：' + name)
        entries[name] = entry
        insensitive.add(name.casefold())
    def verify(entry):
        path = update.safe_path(root, entry['path'])
        if (not path.is_file() or path.stat().st_size != entry['size']
                or update.digest(path) != entry['sha256']):
            raise ValueError('stage 文件已偏离清单：' + entry['path'])
    # Windows package trees contain tens of thousands of small dependency
    # files. Bounded concurrent reads retain full path and SHA verification.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in pool.map(verify, manifest['files']):
            pass
    if 'RELEASE.json' not in entries:
        raise ValueError('便携包清单缺少 RELEASE.json')
    return root, release, entries


def build(baseline, stage, output, package_url, notes='', published_at=None):
    """Write the ZIP, its SHA256 and the online feed only after all prechecks."""
    validate_url(package_url)
    update = installer()
    baseline, before_release, before = audited_stage(baseline, update)
    stage, release, current = audited_stage(stage, update)
    if baseline == stage:
        raise ValueError('新旧 stage 必须不同')
    if update.version_tuple(release['version']) <= update.version_tuple(before_release['version']):
        raise ValueError('新版本号必须大于基线版本号')
    for key in ('edition', 'platform', 'runtime_id', 'data_schema'):
        if release[key] != before_release[key]:
            raise ValueError('运行环境或数据结构不兼容，请交付完整新版包：' + key)
    # Portable staging records its source commit inside runtime provenance.
    # Keep the installed runtime inventory: application source provenance is
    # advanced by RELEASE.json while runtime contents remain unchanged.
    inventory_name = 'RUNTIME-INVENTORY.json'
    if inventory_name in before or inventory_name in current:
        if inventory_name not in before or inventory_name not in current:
            raise ValueError('运行环境来源记录缺失，请交付完整新版包')
        previous_inventory = read_json(baseline / inventory_name)
        next_inventory = read_json(stage / inventory_name)
        for record, identity in ((previous_inventory, before_release), (next_inventory, release)):
            if record.get('source_commit') != identity['source_commit']:
                raise ValueError('运行环境来源提交与 stage 发布身份不符')
        if ({k: v for k, v in previous_inventory.items() if k != 'source_commit'}
                != {k: v for k, v in next_inventory.items() if k != 'source_commit'}):
            raise ValueError('运行环境来源或组件发生变化，请交付完整新版包')
    # Content-hashed frontend builds remove old JS/CSS names. Keep those
    # shipped program files at the destination; this patch never deletes.
    missing_protected = sorted(name for name in set(before) - set(current)
                               if not update.is_program_path(name))
    if missing_protected:
        raise ValueError('第一版补丁不能移除依赖、运行环境或受保护资源：' + missing_protected[0])
    changed = []
    for name, entry in sorted(current.items()):
        old = before.get(name)
        if old and entry['sha256'] == old['sha256']:
            continue
        if name in METADATA or name == inventory_name:
            continue
        if not update.is_program_path(name):
            raise ValueError('更新含运行依赖、用户数据或未授权资源，请单独处理：' + name)
        changed.append({'path': name, 'size': entry['size'], 'sha256': entry['sha256'],
                        'before_sha256': old['sha256'] if old else None})
    if not changed:
        raise ValueError('没有可分发的程序变更')
    locks = [{'path': name, 'sha256': entry['sha256']} for name, entry in sorted(before.items())
             if update.is_dependency_path(name)]
    plan = {key: release[key] for key in ('edition', 'version', 'channel', 'runtime_id', 'data_schema', 'platform')}
    plan.update(schema=1, base_version=before_release['version'], source_commit=release['source_commit'],
                files=changed, required_locks=locks)
    plan_bytes = update.json_bytes(plan)
    if (len(changed) + 1 > update.MAX_FILES or len(plan_bytes) > update.MAX_MANIFEST_BYTES
            or any(item['size'] > update.MAX_FILE_BYTES for item in changed)
            or sum(item['size'] for item in changed) + len(plan_bytes) > update.MAX_EXPANDED_BYTES):
        raise ValueError('程序补丁超出安装器大小限制，请交付完整新版包')
    output = Path(output).resolve()
    feed_path = output.parent / 'haike-update.json'
    hash_path = output.with_name(output.name + '.sha256')
    for artifact in (output, feed_path, hash_path):
        if artifact.exists():
            raise ValueError('输出已存在，请使用新的发行目录：' + str(artifact))
        if artifact.is_relative_to(stage) or artifact.is_relative_to(baseline):
            raise ValueError('输出目录必须位于新旧 stage 之外')
    output.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            created.append(output)
            archive.writestr('UPDATE-MANIFEST.json', plan_bytes)
            for entry in changed:
                source = update.safe_path(stage, entry['path'])
                data = source.read_bytes()
                if len(data) != entry['size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise ValueError('stage 在打包过程中发生变化：' + entry['path'])
                archive.writestr('payload/' + entry['path'], data)
        if output.stat().st_size > update.MAX_ARCHIVE_BYTES:
            raise ValueError('程序补丁压缩包过大，请交付完整新版包')
        checksum = update.digest(output)
        feed = {key: plan[key] for key in ('schema', 'edition', 'channel', 'version', 'base_version',
                                          'runtime_id', 'data_schema', 'platform')}
        feed.update(notes=notes, published_at=published_at or datetime.now(timezone.utc).isoformat(),
                    package={'url': package_url, 'size': output.stat().st_size, 'sha256': checksum})
        if output.stat().st_size + len(update.json_bytes(feed)) > update.MAX_ARCHIVE_BYTES:
            raise ValueError('更新包与版本清单的下载总量超过300 MB')
        with feed_path.open('xb') as stream:
            created.append(feed_path)
            stream.write(update.json_bytes(feed))
        with hash_path.open('x', encoding='utf-8') as stream:
            created.append(hash_path)
            stream.write(checksum + '  ' + output.name + '\n')
    except Exception:
        for artifact in created:
            artifact.unlink(missing_ok=True)
        raise
    return {'ok': True, 'package': str(output), 'feed': str(feed_path), 'sha256': checksum,
            'version': release['version'], 'base_version': before_release['version'],
            'files': len(changed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New update ZIP outside both stages')
    parser.add_argument('--package-url', required=True, help='Final HTTPS URL for the ZIP')
    parser.add_argument('--notes-file', type=Path)
    args = parser.parse_args()
    try:
        notes = args.notes_file.read_text(encoding='utf-8-sig') if args.notes_file else ''
        result = build(args.baseline, args.stage, args.output, args.package_url, notes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
