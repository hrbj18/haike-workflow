"""Build or verify a pinned public-source runtime, without personal MotionGit packages.

Only the fixed upstream inventory is accepted. This builds source components,
not an updater, an installation package, or proof of original-template fidelity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'templates/motiongit-public-components-v1'
COMMIT = '4a52ae2cff542cfb0bfcf6e93e5120c55d0110cf'
INVENTORY_SHA = 'e02925cedcb4b2e48fe73f7da01bc9711aad30edbf3f0f0982461c5526fa2f16'
RECORD_PINS = {'DEPENDENCIES.json': 'c30cf57bb3f2192410d99685a771fd36f69583737e0464cce9c0bd0985ec5f1f',
               'TOOLS.json': '5a2bd3c270d30fd841c89116c4eabe25ad6a15e957ee40d021f77d31c5ef26f1'}
COMPONENT_SHA = 'bf335a15f8f71c6313c2618bbbb9ded5c598350b71f0a1607b7a4d3db379968f'
SOURCE_ONLY_SHA = 'e7090f43ecdf4a00f35c2c7ceeaa905bd26dcae2d738a44fdb8c0544324ebbc2'
REPOSITORY = 'https://github.com/adunext/adu-motion-video'
PACKS = {
    'classic': 'classic-performance/1.1.1-candidate',
    'continuous': 'continuous-performance/1.1.1-candidate',
    'editorial': 'editorial-performance/1.2.1-candidate',
    'kinetic': 'kinetic-performance/1.2.1-candidate',
    'stage': 'stage-performance/1.1.1-candidate',
    'paper-balance': 'paper-balance/1.1.1-candidate',
    'paper-ball': 'paper-ball-performance/1.1.1-candidate',
    'sticker': 'vivid-sticker-performance/0.2.1-candidate',
    'dark': 'dark-3d-showcase/1.3.2-candidate',
    'console': 'doubao-console-performance/0.3.1-candidate',
    'poster': 'vibrant-color-performance/0.1.1-candidate',
}
REFERENCES = {
    'template-01-integrated': {'version': '2.7.18-alpha.4', 'package_sha256': '2150f84a4202e3ebd36a47fc93b9a32ebdfc637afada6e73385f8d0c4eca58e3', 'packs': ['classic', 'continuous', 'editorial', 'kinetic', 'stage']},
    'template-02-expanded': {'version': '2.7.21-alpha.5', 'package_sha256': '8c9df3f72e3cca9713485c4c43b9aa62dccc251ed84c23ecdd79f92218938546', 'packs': ['paper-balance', 'paper-ball', 'sticker']},
    'template-03-native': {'version': '2.7.18-alpha.2', 'package_sha256': '0073456d9aef950f7548ca3e18fd752ab2577cc9bec23258c2cfcc689ad7009f', 'packs': ['dark']},
    'template-04-dark-console': {'version': '2.7.20-alpha.3', 'package_sha256': '54f75c890e652d190cbfc8ec93e66de54deb64a27d36094e85faf5d9b183f863', 'packs': ['console']},
    'vibrant-poster': {'version': '2.7.13', 'package_sha256': 'bcf4d5995342cdffe345d1400507a18217380381c2fcf816e90b6b1bfd1aa447', 'packs': ['poster']},
}


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if not isinstance(relative, str) or '\\' in relative or ':' in relative or path.is_absolute() or '..' in path.parts:
        raise ValueError('组件路径必须在指定目录内')
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root.resolve()) or result.is_symlink():
        raise ValueError('组件路径或链接越界')
    return result


def verify(target: Path = TARGET, *, allow_unbound=False) -> dict:
    accepted = {COMPONENT_SHA, SOURCE_ONLY_SHA} if allow_unbound else {COMPONENT_SHA}
    if sha(target / 'COMPONENT.json') not in accepted:
        raise ValueError('组件清单不是已核固定摘要；不能删减清单绕过源码验证')
    manifest = json.loads((target / 'COMPONENT.json').read_bytes())
    if manifest.get('schema') != 'haike.motion-public-components/1' or manifest.get('source_commit') != COMMIT:
        raise ValueError('公开组件身份未知')
    seen = set()
    for row in manifest['files']:
        relative = row['path']
        if relative.casefold() in seen:
            raise ValueError('组件路径大小写冲突')
        seen.add(relative.casefold())
        path = checked_path(target, relative)
        if not path.is_file() or path.stat().st_size != row['size'] or sha(path) != row['sha256']:
            raise ValueError('公开组件摘要不符：' + relative)
    actual = {p.relative_to(target).as_posix() for p in (target / 'upstream').rglob('*') if p.is_file()}
    expected = {r['path'] for r in manifest['files'] if r['path'].startswith('upstream/')}
    if actual != expected:
        raise ValueError('公开执行目录出现未绑定文件或缺件')
    return manifest


def bind_records(target: Path, dependencies: Path, tools: Path) -> dict:
    manifest = verify(target, allow_unbound=True)
    for name, path in [('DEPENDENCIES.json', dependencies), ('TOOLS.json', tools)]:
        if sha(path) != RECORD_PINS[name]:
            raise ValueError('运行依赖记录不是已核固定摘要：' + name)
        destination = target / name
        if destination.exists() and sha(destination) != RECORD_PINS[name]:
            raise ValueError('不可覆盖已经改变的依赖记录')
        if not destination.exists():
            shutil.copyfile(path, destination)
        if not any(row['path'] == name for row in manifest['files']):
            manifest['files'].append({'path': name, 'sha256': sha(destination), 'size': destination.stat().st_size,
                                      'origin': 'fixed public registry/font identity or external-tool requirements; no binary included'})
    (target / 'COMPONENT.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return verify(target)


def build(source: Path, inventory: Path, target: Path = TARGET) -> dict:
    if sha(inventory) != INVENTORY_SHA:
        raise ValueError('必须使用已核官方固定提交的源文件清单')
    declared = json.loads(inventory.read_bytes())
    if declared['source_commit'] != COMMIT or target.exists():
        raise ValueError('固定来源不符或目标目录已经存在；不可覆盖已冻结组件')
    selected = []
    prefixes = ('scripts/', 'template/', 'adapters/', 'adaptation-profiles/', 'schemas/')
    for row in declared['files']:
        name = row['path']
        if name in {'LICENSE', 'THIRD_PARTY.md', 'package.json', 'package-lock.json', 'assets/fonts/sources.json'} or name.startswith(prefixes) or any(name.startswith('packs/' + value + '/') for value in PACKS.values()):
            if Path(name).name in {'AGENTS.md', 'SKILL.md'} or '__pycache__' in PurePosixPath(name).parts:
                continue
            path = checked_path(source, name)
            if not path.is_file() or sha(path) != row['sha256']:
                raise ValueError('公开源文件缺失或改变：' + name)
            selected.append(row)
    # Validate original pack file lists before creating the component directory.
    packs = {}
    available = {r['path']: r for r in selected}
    for key, relative in PACKS.items():
        pack = json.loads((source / 'packs' / relative / 'manifest.json').read_bytes())
        for name, expected in pack.get('files', {}).items():
            identity = 'packs/' + relative + '/' + name
            if '__pycache__' in PurePosixPath(name).parts or name.endswith(('.pyc', '.pyo')):
                raise ValueError('上游版本包含生成缓存，必须选择真正干净的新版本')
            if identity not in available or available[identity]['sha256'] != expected:
                raise ValueError('公开整包源闭包缺件：' + identity)
        packs[key] = {'path': 'upstream/packs/' + relative, 'upstream_id': pack['id'],
            'upstream_version': pack['version'], 'manifest_sha256': available['packs/' + relative + '/manifest.json']['sha256'],
            'actions': [{'id': s['id'], 'source': s['source'], 'source_block_sha256': s.get('sourceBlockSha256'),
                         'slots': s.get('slots', []), 'cues': s.get('cues', [])} for s in pack['scenes']]}
    target.mkdir(parents=True)
    for row in selected:
        destination = target / 'upstream' / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / row['path'], destination)
    manifest = {'schema': 'haike.motion-public-components/1', 'component_id': 'haike-public-motion-source-v1',
        'component_version': '0.1.0-development', 'source_repository': REPOSITORY, 'source_commit': COMMIT,
        'license': 'MIT for upstream-owned source; nearest licenses and third-party notices retain scope',
        'references': REFERENCES, 'packs': packs, 'original_package_equivalence': False,
        'full_original_template_closure': False,
        'files': [{**{k: row[k] for k in ('sha256', 'size', 'git_blob_sha')}, 'path': 'upstream/' + row['path'],
                   'source_path': row['path'], 'source_commit': COMMIT} for row in selected]}
    (target / 'COMPONENT.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return verify(target, allow_unbound=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--target', type=Path, default=TARGET)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--bind-records', action='store_true')
    parser.add_argument('--dependencies', type=Path)
    parser.add_argument('--tools', type=Path)
    args = parser.parse_args()
    if args.bind_records:
        if not args.dependencies or not args.tools:
            parser.error('--bind-records须提供--dependencies和--tools')
        manifest = bind_records(args.target, args.dependencies, args.tools)
    elif args.check:
        manifest = verify(args.target)
    else:
        if not args.source or not args.inventory:
            parser.error('构建须明确--source和--inventory；不会自动安装或下载个人包')
        manifest = build(args.source, args.inventory, args.target)
    print(json.dumps({'component_id': manifest['component_id'], 'files': len(manifest['files']),
        'packs': len(manifest['packs']), 'public_actions': sum(len(p['actions']) for p in manifest['packs'].values()),
        'full_original_template_closure': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
