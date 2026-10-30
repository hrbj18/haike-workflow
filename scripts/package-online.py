"""Build a small Windows release: committed program + verified compiled UI.

Dependencies are downloaded by 01-setup.cmd. Never copy environments, caches,
runtime trees or user configuration from the build machine.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_packager', ROOT / 'scripts/package-portable.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def build(stage, destination, built_root):
    stage, destination, built_root = Path(stage).resolve(), Path(destination).resolve(), Path(built_root).resolve()
    if stage.exists() or destination.exists():
        raise ValueError('Choose new empty stage and output locations')
    if packager.git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Commit changes before packaging')
    previous = json.loads((built_root / 'RELEASE.json').read_text(encoding='utf-8'))['source_commit']
    subprocess.run(['git', 'merge-base', '--is-ancestor', previous, 'HEAD'], cwd=ROOT, check=True)
    # A previous clean build is reusable only when every frontend input matches.
    for folder in ('prototypes/haike-avatar-generator', 'creatorhub/frontend', 'creatorhub/package.json', 'creatorhub/package-lock.json'):
        if packager.git('diff', previous, 'HEAD', '--', folder).strip():
            raise ValueError('Frontend changed; rebuild the clean UI first: ' + folder)
    stage.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='haike-online-') as temporary:
        source = Path(temporary) / 'source.zip'
        subprocess.run(['git', 'archive', '-o', str(source), 'HEAD'], cwd=ROOT, check=True)
        packager.extract_archive(source, stage)
    # Verify copied UI against the previous build's immutable inventory.
    inventory = json.loads((built_root / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))['files']
    prefixes = ('Haike_video/backlot/ui/avatar-generator/', 'creatorhub/app/web/')
    for entry in inventory:
        if not entry['path'].startswith(prefixes):
            continue
        relative = packager.safe_relative(entry['path'])
        source = built_root.joinpath(*relative.parts)
        if entry.get('mutable') or packager.sha256(source) != entry['sha256']:
            raise ValueError('Compiled UI differs from clean build: ' + entry['path'])
        target = stage.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    if not (stage / 'Haike_video/backlot/ui/avatar-generator/index.html').is_file():
        raise ValueError('Compiled studio UI missing')
    packager.copy_template_sounds(stage, built_root)
    release = json.loads((stage / 'VERSION.json').read_text(encoding='utf-8'))
    release.update(source_commit=packager.git('rev-parse', 'HEAD').decode().strip(),
                   distribution='online', runtime_id='haike-windows-x64-online-v1',
                   setup='01-setup.cmd', agent_entry='START_HERE.md')
    packager.write_json(stage / 'RELEASE.json', release)
    packager.clean_delivery(stage)
    packager.manifest(stage)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for file in sorted(stage.rglob('*')):
            if file.is_file():
                package.write(file, 'Haike_Video/' + file.relative_to(stage).as_posix())
    return {'archive': str(destination), 'size': destination.stat().st_size,
            'sha256': packager.sha256(destination), 'source_commit': release['source_commit']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--built-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.stage, args.destination, args.built_root), ensure_ascii=False))
