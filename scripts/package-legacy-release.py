"""Create the local 1027/1.1 -> 1.2 bootstrap and offline template resources.

The original ZIP remains untouched. Inputs must be the audited 1027 manifest,
an accepted portable stage, and an independently committed source snapshot.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_core', ROOT / 'portable/app_update.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
ID = '1027-to-1.2'
PACKAGES = ['mg-54f75c890e652d190cbfc8ec', 'mg-0073456d9aef950f7548ca3e', 'mg-bcf4d5995342cdffe345d140']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').strip()


def build(args):
    before = {e['path']: e for e in read(args.baseline_manifest)['files']}
    accepted = {e['path']: e for e in read(args.stage / 'PACKAGE-MANIFEST.json')['files']}
    modern_bases = []
    modern_entries = {}
    for directory in getattr(args, 'modern_baseline', []):
        release = read(directory / 'RELEASE.json')
        identity = 'base-' + release['version'].replace('.', '-') + '-' + release['source_commit'][:12]
        if identity in modern_entries:
            raise ValueError('Duplicate migration baseline')
        modern_entries[identity] = {e['path']: e for e in read(directory / 'PACKAGE-MANIFEST.json')['files']}
        modern_bases.append({'id': identity, 'version': release['version'], 'source_commit': release['source_commit']})
    if git(args.source, 'status', '--porcelain'):
        raise ValueError('Source snapshot must be clean and committed')
    commit = git(args.source, 'rev-parse', 'HEAD')
    version = read(args.source / 'VERSION.json')
    if not version['version'].startswith('1.2.'):
        raise ValueError('Source must belong to the 1.2 release series')
    args.output.mkdir(parents=True, exist_ok=False)
    bundle = args.output / 'haike-update-1.2'
    bundle.mkdir()
    rows = []
    tracked = set(subprocess.check_output(['git', '-C', str(args.source), 'ls-files', '-z'])
                  .decode('utf-8').split('\0')) - {''}
    # The frontend was built from this exact tracked frontend source. Compare
    # it with the accepted stage's source rather than copying a working build.
    accepted_commit = read(args.stage / 'RELEASE.json')['source_commit']
    frontend_diff = subprocess.run(['git', '-C', str(args.source), 'diff', '--quiet', accepted_commit,
                                    'HEAD', '--', 'prototypes/haike-avatar-generator'], check=False)
    if frontend_diff.returncode:
        raise ValueError('Frontend changed or accepted source is unavailable; rebuild an audited stage first')
    candidates = {n: args.source / n for n in tracked if core.is_program_path(n)}
    candidates.update({n: args.source / n for n in [
        'Haike_video/remotion-composer/package.json', 'Haike_video/remotion-composer/package-lock.json']})
    for name in accepted:
        if name.startswith('Haike_video/backlot/ui/avatar-generator/') and core.is_program_path(name):
            file = args.stage / name
            if core.digest(file) != accepted[name]['sha256']:
                raise ValueError('Accepted frontend bytes changed: ' + name)
            candidates[name] = file
    capability_file = args.source / 'portable/template_capability.py'
    template_capability = None
    runtime_sources = []
    runtime_value = None
    if (args.source / 'Haike_video/templates/motion-presets/manifest.json').is_file():
        spec = importlib.util.spec_from_file_location('haike_release_motion_runtime', args.source / 'portable/motion_runtime.py')
        runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        profiles = []
        for identity, option in [('paper-rc54-v1', 'paper_cache'), ('knowledge-rc54-v1', 'knowledge_cache')]:
            origin = getattr(args, option, None) or args.donor / runtime.PROFILES[identity]['cache']
            profile, files = runtime.build_profile(identity, origin)
            profiles.append(profile); runtime_sources.extend(files)
        runtime_value = runtime.validate({'schema': runtime.SCHEMA, 'profiles': profiles})
        generated_runtime = bundle / 'template-runtime.json'
        generated_runtime.write_bytes(core.json_bytes(runtime_value))
        candidates[runtime.PATH] = generated_runtime
        spec = importlib.util.spec_from_file_location('haike_release_template_capability', capability_file)
        capability = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(capability)
        value = capability.build(args.source, frontend_root=args.stage,
                                 generated_files={runtime.PATH: generated_runtime})
        content = core.json_bytes(value)
        generated = bundle / 'template-delivery.json'
        generated.write_bytes(content)
        candidates[capability.PATH] = generated
        template_capability = capability.expectation(value, hashlib.sha256(content).hexdigest())
    for name, source in sorted(candidates.items()):
        digest = core.digest(source)
        old = before.get(name)
        if old and old['sha256'] == digest and all(base.get(name, {}).get('sha256') == digest for base in modern_entries.values()):
            continue
        target = bundle / 'payload' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        rows.append({'path': name, 'payload': 'payload/' + name, 'size': source.stat().st_size,
                     'sha256': digest, 'before_sha256': old['sha256'] if old else None,
                     'before_by_base': {identity: base.get(name, {}).get('sha256') for identity, base in modern_entries.items()}})
    # Public resources contain execution dependencies. Personalized originals
    # are an explicit local-only option and must never enter public releases.
    # A content address can reuse an identical file anywhere in the old install.
    by_sha = {}
    for name, row in before.items():
        if not row.get('mutable') and name.startswith(('runtime/', 'Haike_video/.venv/',
                                                     'Haike_video/remotion-composer/node_modules/')):
            if all(base.get(name, {}).get('sha256') == row['sha256'] for base in modern_entries.values()):
                by_sha.setdefault(row['sha256'], name)
    sources = []
    for name, entry in accepted.items():
        if not name.startswith('Haike_video/remotion-composer/node_modules/'):
            continue
        if '/.cache/' in name or '/__pycache__/' in name or name.endswith(('.pyc', '.pyo')):
            continue
        if name in before and before[name]['sha256'] == entry['sha256'] and all(
                base.get(name, {}).get('sha256') == entry['sha256'] for base in modern_entries.values()):
            continue
        sources.append((name, args.stage / name))
    cache = args.donor / '.local/md/console-v1'
    if not cache.is_dir():
        cache = args.donor / '.local/md/shared-1.2'
    if not cache.is_dir():
        raise ValueError('Donor lacks the previously verified shared runtime')
    for file in cache.rglob('*'):
        if not file.is_file():
            continue
        rel = file.relative_to(cache).as_posix()
        if '__pycache__' in file.parts or file.suffix in {'.pyc', '.pyo'} or rel == '.venv/pyvenv.cfg':
            continue
        sources.append(('.local/md/shared-1.2/' + rel, file))
    sources.extend(runtime_sources)
    package_ids = PACKAGES if args.include_personal_motion else []
    for identity in package_ids:
        name = '.local/motiongit/packages/' + identity + '/original.motion'
        sources.append((name, args.donor / name))
    helper_versions = {'1.0.0-rc.50'}
    if template_capability:
        helper_versions.add('1.0.0-rc.54')
    for helper_version in sorted(helper_versions):
        helper = '.local/motiongit/tools/' + helper_version + '/motion.mjs'
        original = (getattr(args, 'helper_54', None) or args.donor / helper) if helper_version == '1.0.0-rc.54' else args.donor / helper
        if helper_version == '1.0.0-rc.54' and (original.stat().st_size != runtime.HELPER_BYTES or core.digest(original) != runtime.HELPER_SHA):
            raise ValueError('rc.54 helper differs from the independent release pin')
        sources.append((helper, original))
    def info(item):
        name, file = item
        return name, file, core.digest(file), file.stat().st_size
    with ThreadPoolExecutor(max_workers=8) as pool:
        verified = list(pool.map(info, sources))
    resource_rows, written = [], set()
    resource_zip = args.output / 'haike-templates-1.2.zip'
    with zipfile.ZipFile(resource_zip, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, file, sha, size in sorted(verified):
            old = before.get(name)
            row = {'path': name, 'sha256': sha, 'size': size,
                   'before_sha256': old['sha256'] if old else None,
                   'before_by_base': {identity: base.get(name, {}).get('sha256') for identity, base in modern_entries.items()}}
            if sha in by_sha:
                row['reuse_from'] = by_sha[sha]
            else:
                blob = ('templates/' + name.split('/')[3] + '.motion' if name.endswith('original.motion')
                        else 'blobs/' + sha)
                row['blob'] = blob
                if blob not in written:
                    archive.write(file, blob)
                    written.add(blob)
            resource_rows.append(row)
        packages = []
        if package_ids:
            with sqlite3.connect((args.donor / '.local/motiongit/registry.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
                for identity in package_ids:
                    original = json.loads(db.execute('SELECT data FROM packages WHERE id=?', (identity,)).fetchone()[0])
                    # Do not distribute absolute paths, private render history or local config.
                    keys = {'id', 'filename', 'bytes', 'sha256', 'name', 'version', 'template_id', 'runtime',
                            'spec_version', 'personal', 'protection', 'verification', 'runnable', 'support',
                            'support_note', 'workflows', 'entry_count', 'helper_version'}
                    value = {k: v for k, v in original.items() if k in keys}
                    actual = next(r for r in resource_rows if r['path'].endswith(identity + '/original.motion'))
                    if actual['sha256'] != value['sha256'] or value.get('verification') != 'verified':
                        raise ValueError('Original package identity/verification differs: ' + identity)
                    packages.append(value)
        resource_plan = {'schema': 1, 'id': ID, 'files': resource_rows, 'packages': packages,
                         'shared_cache': '.local/md/shared-1.2',
                         'dependency_locks': read(cache / 'dependencies.json'),
                         'template_package_policy': 'local-personal' if package_ids else 'user-provided',
                         'personal_credentials_included': bool(package_ids),
                         'private_media_included': False}
        if runtime_value:
            resource_plan['runtime_manifest_sha256'] = core.digest(generated_runtime)
        archive.writestr('RESOURCES.json', core.json_bytes(resource_plan))
    release = {**version, 'source_commit': commit, 'date': datetime.now(timezone.utc).date().isoformat(),
               'setup': '01-setup.cmd', 'agent_entry': 'START_HERE.md',
               'runtime_origin': 'original 20261027 portable installation; runtime binaries unchanged'}
    if template_capability:
        release['template_capability'] = template_capability
    # Old Python requirements are unchanged. Verify shipped ABI/runtime binaries
    # and all declared lockfiles; overwritten files and reuse inputs are separately checked.
    required = [row for name, row in before.items() if name in {
        'Haike_video/requirements.txt', 'creatorhub/requirements.txt',
        'Haike_video/remotion-composer/package-lock.json',
        'runtime/python/python.exe', 'runtime/python/python312.dll', 'runtime/node/node.exe',
        'runtime/ffmpeg/bin/ffmpeg.exe', 'runtime/ffmpeg/bin/ffprobe.exe',
        'runtime/browser/chrome-headless-shell.exe'}]
    for baseline in modern_bases:
        entries = modern_entries[baseline['id']]
        baseline['required_files'] = [{'path': row['path'], 'sha256': entries[row['path']]['sha256']} for row in required]
    plan = {'schema': 1, 'id': ID, 'base_label': '1.1 / 20261027',
            'base_source_commit': '21d1ff23bd1debdb53a9e651a590895c755a8c03',
            'base_manifest_sha256': core.digest(args.baseline_manifest),
            'resources': {'filename': resource_zip.name, 'sha256': core.digest(resource_zip)},
            'release': release, 'files': rows,
            'required_files': [{k: r[k] for k in ('path', 'sha256')} for r in required]}
    if modern_bases:
        plan['modern_bases'] = modern_bases
    (bundle / 'UPGRADE.json').write_bytes(core.json_bytes(plan))
    for source, name in [('portable/legacy_upgrade.py', 'legacy_upgrade.py'),
                         ('portable/app_update.py', 'release_core.py'),
                         ('portable/upgrade-1027.ps1', 'upgrade-1027.ps1')]:
        shutil.copyfile(args.source / source, bundle / name)
    if runtime_value:
        shutil.copyfile(args.source / 'portable/motion_runtime.py', bundle / 'motion_runtime.py')
    shutil.copyfile(args.source / 'docs/releases/1.2-使用说明.txt', bundle / '使用说明.txt')
    (bundle / 'upgrade.cmd').write_text('@echo off\ncd /d "%~dp0"\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0upgrade-1027.ps1" %*\npause\n', encoding='ascii')
    update_zip = args.output / 'haike-update-1.2.zip'
    with zipfile.ZipFile(update_zip, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(bundle.rglob('*')):
            if file.is_file():
                archive.write(file, file.relative_to(args.output).as_posix())
    if update_zip.stat().st_size + resource_zip.stat().st_size > 200_000_000:
        raise ValueError('Bootstrap program and resource download exceeds the combined 200MB contract')
    result = {'ok': True, 'version': '1.2', 'base_version': '1.1 / 1027', 'source_commit': commit,
              'program_files': len(rows), 'resource_files': len(resource_rows),
              'reused_resource_files': sum('reuse_from' in r for r in resource_rows),
              'resource_expanded_bytes': sum(r['size'] for r in resource_rows),
              'artifacts': [{'name': f.name, 'size': f.stat().st_size, 'sha256': core.digest(f)}
                            for f in (update_zip, resource_zip)]}
    (args.output / 'BUILD.json').write_bytes(core.json_bytes(result))
    (args.output / 'SHA256SUMS.txt').write_text(''.join(r['sha256'] + '  ' + r['name'] + '\n'
        for r in result['artifacts']), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-manifest', 'stage', 'donor', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--include-personal-motion', action='store_true',
                        help='Local private delivery only; includes signed personal credentials. Never upload publicly.')
    parser.add_argument('--paper-cache', type=Path, help='Verified rc.54 component dependency directory')
    parser.add_argument('--knowledge-cache', type=Path, help='Verified rc.54 knowledge dependency directory')
    parser.add_argument('--helper-54', type=Path, help='Independently pinned rc.54 helper bytes')
    parser.add_argument('--modern-baseline', action='append', type=Path, default=[], help='Exact, audited 1.2 runtime-migration baseline')
    args = parser.parse_args()
    print(json.dumps(build(args), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
