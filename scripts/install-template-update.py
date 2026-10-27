"""Apply an audited template update without touching accounts or user media."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile


SCOPES = ('Haike_video/backlot/', 'Haike_video/lib/', 'Haike_video/scripts/',
          'Haike_video/tools/', 'Haike_video/templates/', 'Haike_video/design/',
          'Haike_video/skills/', 'Haike_video/docs/', 'Haike-Videohub/agent-runbooks/',
          'prototypes/haike-avatar-generator/', 'docs/TEMPLATE_DELIVERY.md')
FORBIDDEN = {'.local', '.backlot', '.venv', 'node_modules', 'projects', 'media',
             '__pycache__', 'data', 'browser_data', 'runtime', '.git'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def safe(root, name, payload=False):
    rel = PurePosixPath(name)
    if (not name or rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name
            or '\0' in name):
        raise ValueError('Unsafe update path: ' + name)
    if payload and (not name.startswith(SCOPES) or any(p in FORBIDDEN for p in rel.parts)
                    or rel.name.startswith('.env') or rel.suffix in ('.db', '.sqlite', '.key')):
        raise ValueError('Path is outside template update scope: ' + name)
    root = root.resolve()
    result = root.joinpath(*rel.parts)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
            raise ValueError('Update cannot traverse links: ' + name)
    if not result.resolve().is_relative_to(root):
        raise ValueError('Update path escapes target: ' + name)
    return result


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.template-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def preflight(bundle, target):
    target = target.resolve(strict=True)
    if not (target / 'Haike_video/backlot/server.py').is_file():
        raise ValueError('请选择海客项目根目录（其中应有 Haike_video 文件夹）')
    plan = read(bundle / 'UPDATE-MANIFEST.json')
    if plan.get('schema') != 1 or not plan.get('files'):
        raise ValueError('Invalid update manifest')
    if len({e['path'] for e in plan['files']}) != len(plan['files']):
        raise ValueError('Duplicate update paths')
    for lock in plan['required_locks']:
        path = safe(target, lock['path'])
        if not path.is_file() or digest(path) != lock['sha256']:
            raise ValueError('旧版依赖不兼容，请使用完整新版包：' + lock['path'])
    for item in plan['files']:
        source = safe(bundle / 'payload', item['path'], payload=True)
        destination = safe(target, item['path'], payload=True)
        if not source.is_file() or digest(source) != item['sha256']:
            raise ValueError('更新包文件损坏：' + item['path'])
        if destination.exists() and not destination.is_file():
            raise ValueError('目标路径不是文件：' + item['path'])
    # Validate every portable screenshot and guide from the delivered catalog.
    catalog = read(bundle / 'payload/Haike_video/templates/library.json')['templates']
    ids = {e['id'] for e in catalog}
    if len(ids) != len(catalog) or not set(plan['covered_template_ids']).issubset(ids):
        raise ValueError('Template catalog is inconsistent')
    for identity in plan['covered_template_ids']:
        name = f'Haike_video/templates/library-covers/{identity}.jpg'
        if name not in {e['path'] for e in plan['files']}:
            raise ValueError('Missing portable cover: ' + identity)
    return plan


def apply(bundle, target, check=False):
    bundle, target = bundle.resolve(), target.resolve()
    plan = preflight(bundle, target)
    changed = [e for e in plan['files'] if not safe(target, e['path']).is_file()
               or digest(safe(target, e['path'])) != e['sha256']]
    if check:
        return {'ok': True, 'mode': 'check', 'files_to_update': len(changed),
                'covers': len(plan['covered_template_ids'])}
    if not changed:
        return {'ok': True, 'already_current': True, 'files_updated': 0}
    name = plan['id'] + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = safe(target, '.local/template-updates/' + name)
    backup.mkdir(parents=True, exist_ok=False)
    metadata = ['PACKAGE-MANIFEST.json', 'RELEASE.json']
    names = [e['path'] for e in changed] + [n for n in metadata if (target / n).is_file()]
    records = []
    for name in names:
        existing = safe(target, name)
        row = {'path': name, 'existed': existing.is_file()}
        if row['existed']:
            copy = safe(backup / 'files', name)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(existing, copy)
            row['before_sha256'] = digest(copy)
        records.append(row)
    receipt = {'schema': 1, 'update_id': plan['id'], 'files': records}
    atomic(backup / 'receipt.json', json_bytes(receipt))
    try:
        for item in changed:
            atomic(safe(target, item['path']), safe(bundle / 'payload', item['path']).read_bytes())
        manifest_path = target / 'PACKAGE-MANIFEST.json'
        if manifest_path.is_file():
            manifest = read(manifest_path)
            entries = {e['path']: e for e in manifest['files']}
            for item in plan['files']:
                entries[item['path']] = {**item, 'mutable': False}
            manifest['files'] = [entries[n] for n in sorted(entries)]
            atomic(manifest_path, json_bytes(manifest))
        release = target / 'RELEASE.json'
        if release.is_file():
            value = read(release)
            value['template_update'] = {'id': plan['id'], 'source_snapshot': plan['source_snapshot'],
                                        'covers': len(plan['covered_template_ids'])}
            atomic(release, json_bytes(value))
            if manifest_path.is_file():
                manifest = read(manifest_path)
                for item in manifest['files']:
                    if item['path'] == 'RELEASE.json':
                        item.update(size=release.stat().st_size, sha256=digest(release))
                atomic(manifest_path, json_bytes(manifest))
        for row in records:
            row['after_sha256'] = digest(safe(target, row['path']))
        receipt['status'] = 'complete'
        atomic(backup / 'receipt.json', json_bytes(receipt))
    except Exception:
        restore(target, backup, check_hashes=False)
        raise
    return {'ok': True, 'files_updated': len(changed), 'covers': len(plan['covered_template_ids']),
            'backup': str(backup), 'next': '重新启动目标副本，浏览器按 Ctrl+F5，再打开选择模板 → 视觉模板库'}


def restore(target, backup, check_hashes=True):
    target, backup = target.resolve(), backup.resolve(strict=True)
    if not backup.is_relative_to((target / '.local/template-updates').resolve()):
        raise ValueError('Backup must belong to this installation')
    receipt = read(backup / 'receipt.json')
    # Check the entire restore before changing anything, including files edited after upgrade.
    for row in receipt['files']:
        current = safe(target, row['path'])
        if check_hashes and (not current.is_file() or digest(current) != row['after_sha256']):
            raise ValueError('更新后文件又被修改，已停止回退：' + row['path'])
        if row['existed']:
            source = safe(backup / 'files', row['path'])
            if digest(source) != row['before_sha256']:
                raise ValueError('Backup checksum failed: ' + row['path'])
    for row in receipt['files']:
        destination = safe(target, row['path'])
        if row['existed']:
            atomic(destination, safe(backup / 'files', row['path']).read_bytes())
        else:
            destination.unlink(missing_ok=True)
    receipt['status'] = 'restored'
    atomic(backup / 'receipt.json', json_bytes(receipt))
    return {'ok': True, 'restored_files': len(receipt['files'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    try:
        result = (restore(args.target, args.rollback) if args.rollback else
                  apply(args.bundle, args.target, check=args.check))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
