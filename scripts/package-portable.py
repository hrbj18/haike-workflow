"""Build a clean Windows portable delivery from committed source and audited runtimes.

The old archive contributes only explicitly selected dependency trees. Project
code always comes from this repository's HEAD, never from a live installation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('Haike_video', 'creatorhub', 'copy_skill/copy_skill-main')
CRAWLER = 'copy_skill/copy_skill-main/third_party/MediaCrawler'
RUNTIME_PARTS = {'python', 'node', 'ffmpeg', 'browser', 'models', 'hyperframes', 'uv', 'msvc'}
PRIVATE_PARTS = {'.git', '.local', '.backlot', '.portable', 'browser_data', 'profiles',
                 '__pycache__', '.pytest_cache', '.workbuddy'}
PRIVATE_PREVIEWS = {'presenter.png', 'template3-poster.png', 'n1-presenter.jpg',
                    'n1-cover.jpg', 'n1-material.jpg', 'n1-screenshot.jpg', 'n1-data.jpg', 'n1-sample.mp4'}
STATE_NAMES = {'cookies', 'cookies.txt', 'local state', 'login data', 'web data', 'history'}


def private_path(relative):
    parts = tuple(part.lower() for part in PurePosixPath(str(relative).replace('\\', '/')).parts)
    name = parts[-1]
    return (any(part in PRIVATE_PARTS or part.endswith('_user_data_dir') for part in parts)
            or name in STATE_NAMES or name.startswith('storage_state')
            or ('cookie' in name and name.endswith('.txt'))
            or name.endswith(('.db', '.sqlite', '.sqlite3', '.log', '.key', '.pfx', '.p12'))
            or (name.startswith('.env') and name != '.env.example')
            or (name.endswith('.pem') and parts[-2:] != ('certifi', 'cacert.pem')))


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, timeout=120)


def safe_relative(name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or chr(92) in name or chr(0) in name or ':' in name:
        raise ValueError('Unsafe archive path: ' + name)
    return relative


def extract_archive(archive, destination, select=lambda name: True, prefix=''):
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            safe_relative(entry.orig_filename)
            if entry.is_dir() or not entry.filename.startswith(prefix):
                continue
            name = entry.filename[len(prefix):]
            relative = safe_relative(name)
            if not select(name):
                continue
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive symlinks are not portable: ' + name)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def copy_environment(source_root, destination, module):
    source = source_root / module / '.venv'
    target = destination / module / '.venv'
    if not (source / 'Scripts/python.exe').is_file():
        raise ValueError('Missing prepared Python environment: ' + module)
    # Copy installed libraries, not activation scripts/launchers with old paths,
    # user caches, installer logs, editable direct URLs or running service data.
    files = [p for p in (source / 'Lib/site-packages').rglob('*') if p.is_file()]
    files += [source / 'Scripts' / name for name in ('python.exe', 'pythonw.exe')]
    if (source / 'msvc').is_dir():
        files += [p for p in (source / 'msvc').rglob('*') if p.is_file()]
    count = 0
    for file in files:
        rel = file.relative_to(source)
        if file.is_symlink() or not file.resolve().is_relative_to(source.resolve()):
            raise ValueError('Environment contains a link: ' + module + '/' + str(rel))
        if (private_path(rel) or file.suffix in {'.pyc', '.pyo'} or file.name == 'direct_url.json'
                or file.name.startswith('__editable___douyin_content_intelligence_')):
            continue
        if file.name.startswith('.env') and file.name != '.env.example':
            raise ValueError('Environment contains a credential file: ' + str(rel))
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix == '.pth' and '__editable__.douyin_content_intelligence' in file.name:
            out.write_text('../../../src\n', encoding='utf-8')
        elif file.suffix == '.pth' and (':\\' in file.read_text(encoding='utf-8') or ':/' in file.read_text(encoding='utf-8')):
            raise ValueError('Unreviewed absolute editable path: ' + str(rel))
        else:
            shutil.copyfile(file, out)
        count += 1
    (target / 'pyvenv.cfg').write_text('home = RUNTIME_PREPARE_REQUIRED\ninclude-system-site-packages = false\nversion = 3.12.8\n', encoding='utf-8')
    probe = subprocess.check_output([str(source / 'Scripts/python.exe'), '-c',
        'import importlib.metadata as m,json,sys; print(json.dumps({"python":sys.version,"packages":sorted([(d.metadata["Name"],d.version) for d in m.distributions()])}))'],
        text=True, encoding='utf-8', timeout=60)
    return {'module': module, 'copied_files': count, **json.loads(probe)}


def clean_runtime(name):
    parts = PurePosixPath(name).parts
    runtime = len(parts) > 2 and parts[0] == 'runtime' and parts[1] in RUNTIME_PARTS
    composer = name.startswith('Haike_video/remotion-composer/node_modules/')
    if not (runtime or composer):
        return False
    lower = parts[-1].lower()
    return not (private_path(name) or lower.endswith(('.pyc', '.pyo')))


def clean_delivery(root):
    errors = []
    for file in root.rglob('*'):
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
            errors.append(str(file.relative_to(root)))
            continue
        if not file.is_file():
            continue
        rel = file.relative_to(root)
        name = file.name.lower()
        if private_path(rel):
            errors.append(str(rel))
        if rel.as_posix() in {'creatorhub/config.yaml', 'copy_skill/copy_skill-main/config/content_intelligence.local.json'}:
            errors.append(str(rel))
        if file.name in PRIVATE_PREVIEWS and ('public/assets' in rel.as_posix() or 'backlot/ui' in rel.as_posix()):
            errors.append(str(rel))
    if errors:
        raise ValueError('Private/state files in delivery: ' + ', '.join(errors[:20]))


def copy_browser_tree(source, destination):
    """Copy browser application resources, excluding existing diagnostic/state files."""
    source = source.resolve()
    for file in source.rglob('*'):
        if file.is_symlink() or not file.resolve().is_relative_to(source):
            raise ValueError('Browser application contains a link')
        rel = file.relative_to(source)
        if not file.is_file() or private_path(rel) or file.name == 'First Run':
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)


def copy_template_sounds(destination, source_root=None):
    """Ship only original sounds individually authorized by the tracked provenance."""
    relative = Path('Haike_video/templates/avatar-investment-a-v6-art-v5/assets/sound')
    catalog = json.loads((destination / relative / 'PROVENANCE.json').read_text(encoding='utf-8'))
    if catalog.get('external_samples') or catalog.get('contains_user_portrait_or_voice') is not False:
        raise ValueError('Template sound provenance is not approved for clean delivery')
    # Validate the full set before copying anything; never silently ship a partial sound pack.
    approved = []
    for asset in catalog['assets']:
        name = safe_relative(asset['relative_path'])
        if len(name.parts) != 1 or not str(name).endswith('.wav'):
            raise ValueError('Invalid template sound path')
        source = (source_root or ROOT) / relative / str(name)
        if not source.is_file() or source.is_symlink() or sha256(source) != asset['sha256']:
            raise ValueError('Missing/mismatched original template sound: ' + str(name))
        approved.append(source)
    for source in approved:
        shutil.copyfile(source, destination / relative / source.name)
    return len(approved)


def stage(args):
    destination = args.stage.resolve()
    if destination.exists():
        raise ValueError('Staging directory already exists; choose a new empty path')
    if git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Commit source changes before packaging')
    subprocess.run([sys.executable, str(ROOT / 'scripts/check.py')], cwd=ROOT, check=True)
    revision = git('rev-parse', 'HEAD').decode().strip()
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='haike-source-') as tmp:
        archive = Path(tmp) / 'source.zip'
        subprocess.run(['git', 'archive', '--format=zip', '-o', str(archive), 'HEAD'], cwd=ROOT, check=True)
        extract_archive(archive, destination)
    print('Exported committed source: ' + revision, flush=True)
    dependency_root = getattr(args, 'dependency_root', None) or ROOT
    copy_template_sounds(destination, dependency_root)
    # Rendering dependencies must match the current source lock exactly.
    with zipfile.ZipFile(args.runtime_archive) as package:
        candidates = [name for name in package.namelist() if name.endswith('/Haike_video/remotion-composer/package-lock.json')]
        if len(candidates) != 1:
            raise ValueError('Runtime archive has no unique composer lock')
        prefix = candidates[0][:-len('Haike_video/remotion-composer/package-lock.json')]
        if package.read(candidates[0]) != (destination / 'Haike_video/remotion-composer/package-lock.json').read_bytes():
            raise ValueError('Composer lock differs from the approved runtime; rebuild its dependencies first')
    extract_archive(args.runtime_archive, destination, clean_runtime, prefix)
    if args.chromium:
        if not (args.chromium / 'chrome.exe').is_file():
            raise ValueError('Chromium directory has no chrome.exe')
        copy_browser_tree(args.chromium, destination / 'runtime/playwright' / args.chromium.parent.name / args.chromium.name)
        for sibling in sorted(args.chromium.parent.parent.glob('chromium_headless_shell-*')):
            copy_browser_tree(sibling, destination / 'runtime/playwright' / sibling.name)
        for sibling in sorted(args.chromium.parent.parent.glob('ffmpeg-*')):
            copy_browser_tree(sibling, destination / 'runtime/playwright' / sibling.name)
    print('Copied selected runtime dependencies; no legacy application code/configuration.', flush=True)
    environments = [copy_environment(dependency_root, destination, module) for module in MODULES]
    if args.include_crawler:
        crawler = dependency_root / CRAWLER
        if git('status', '--porcelain', '--untracked-files=no', cwd=crawler).strip():
            raise ValueError('External crawler source has modifications; export an audited commit first')
        with tempfile.TemporaryDirectory(prefix='haike-crawler-') as tmp:
            archive = Path(tmp) / 'crawler.zip'
            subprocess.run(['git', 'archive', '--format=zip', '-o', str(archive), 'HEAD'], cwd=crawler, check=True)
            extract_archive(archive, destination / CRAWLER)
        environments.append(copy_environment(dependency_root, destination, CRAWLER))
        write_json(destination / 'portable/CRAWLER-SOURCE.json', {
            'url': 'https://github.com/NanmiCoder/MediaCrawler',
            'commit': git('rev-parse', 'HEAD', cwd=crawler).decode().strip(),
            'license': CRAWLER + '/LICENSE', 'scope': 'Non-commercial learning/research; separate permission needed for commercial use',
        })
    model_spec = json.loads((ROOT / 'config/external-models.json').read_text(encoding='utf-8'))['yunet']
    model = dependency_root / model_spec['destination']
    if model.is_file():
        if sha256(model) != model_spec['sha256']:
            raise ValueError('YuNet model does not match the tracked model specification')
        target = destination / model.relative_to(dependency_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model, target)
        for license_file in model.parent.glob('*.LICENSE'):
            shutil.copyfile(license_file, target.parent / license_file.name)
    node_env = dict(os.environ)
    node_env['PATH'] = str(destination / 'runtime/node') + os.pathsep + node_env.get('PATH', '')
    node_env['HAIKE_EMBED_BASE'] = '/ui/avatar-generator/'
    npm = destination / 'runtime/node/npm.cmd'
    for module, command in [('prototypes/haike-avatar-generator', 'build'), ('creatorhub', 'build:ui')]:
        folder = destination / module
        subprocess.run([str(npm), 'ci', '--no-audit', '--no-fund'], cwd=folder, env=node_env, check=True)
        subprocess.run([str(npm), 'run', command], cwd=folder, env=node_env, check=True)
    studio = destination / 'Haike_video/backlot/ui/avatar-generator'
    shutil.copytree(destination / 'prototypes/haike-avatar-generator/dist/client', studio)
    # UI authoring dependencies are retained: agents can edit/rebuild offline.
    write_json(destination / 'RUNTIME-INVENTORY.json', {
        'source_commit': revision, 'runtime_source_sha256': sha256(args.runtime_archive),
        'runtime_source_name': args.runtime_archive.name, 'environments': environments,
        'local_tts': 'optional_not_installed', 'account_sessions': 'none', 'cloud_credentials': 'none',
    })
    write_json(destination / 'RELEASE.json', {'edition': 'haike-workflow-2', 'source_commit': revision,
               'platform': 'windows-x64', 'setup': '01-setup.cmd', 'agent_entry': 'START_HERE.md'})
    clean_delivery(destination)
    manifest(destination)
    print('Portable staging ready: ' + str(destination), flush=True)


def manifest(root):
    entries = []
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file == root / 'PACKAGE-MANIFEST.json':
            continue
        rel = file.relative_to(root).as_posix()
        if any(part in PRIVATE_PARTS for part in PurePosixPath(rel).parts):
            continue
        mutable = (rel.endswith('/.venv/pyvenv.cfg') or
                   (rel.startswith('copy_skill/copy_skill-main/.venv/Lib/site-packages/__editable__.douyin_content_intelligence-')
                    and file.suffix == '.pth'))
        entries.append({'path': rel, 'size': file.stat().st_size, 'sha256': sha256(file), 'mutable': mutable})
    write_json(root / 'PACKAGE-MANIFEST.json', {'schema': 1, 'files': entries})


def archive(args):
    root = args.stage.resolve()
    if not (root / 'RELEASE.json').is_file():
        raise ValueError('Stage the portable delivery before archiving')
    clean_delivery(root)
    out = args.destination.resolve()
    out.mkdir(parents=True, exist_ok=True)
    archive_path = out / 'Haike_videoflow.zip'
    doc = out / 'API_Key配置说明.md'
    if archive_path.exists() or doc.exists():
        raise ValueError('Delivery already exists; refusing to overwrite')
    external = getattr(args, 'config_document', None)
    if external is not None:
        external = external.resolve(strict=True)
        if external.is_relative_to(root):
            raise ValueError('Private configuration must be outside the portable stage')
        spec = importlib.util.spec_from_file_location('user_configuration', ROOT / 'scripts/configure-user.py')
        configuration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(configuration)
        configuration.read_document(external)
        document_text = external.read_text(encoding='utf-8-sig')
    else:
        document_text = (root / 'docs/API_KEY_SETUP.md').read_text(encoding='utf-8')
    files = json.loads((root / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))['files']
    expected = {entry['path'] for entry in files}
    actual = {file.relative_to(root).as_posix() for file in root.rglob('*') if file.is_file()
              and file != root / 'PACKAGE-MANIFEST.json'}
    if actual != expected:
        raise ValueError('Staging file set changed after manifest creation')
    for entry in files:
        if sha256(root / entry['path']) != entry['sha256']:
            raise ValueError('Staging file changed after manifest creation: ' + entry['path'])
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as package:
        for entry in files:
            package.write(root / entry['path'], 'Haike_videoflow/' + entry['path'])
        package.write(root / 'PACKAGE-MANIFEST.json', 'Haike_videoflow/PACKAGE-MANIFEST.json')
    digest = sha256(archive_path)
    text = document_text
    text += '\n## 本次交付校验\n\n- ZIP SHA256：`' + digest + '`\n'
    text += '- 源码提交：`' + json.loads((root / 'RELEASE.json').read_text(encoding='utf-8'))['source_commit'] + '`\n'
    doc.write_text(text, encoding='utf-8-sig')
    print(json.dumps({'zip': str(archive_path), 'bytes': archive_path.stat().st_size,
                      'sha256': digest, 'api_key_document': str(doc)}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'archive'])
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--runtime-archive', type=Path)
    parser.add_argument('--dependency-root', type=Path,
                        help='Audited installed dependency trees; application code still comes only from clean HEAD')
    parser.add_argument('--include-crawler', action='store_true')
    parser.add_argument('--chromium', type=Path, help='Clean Playwright Chromium application directory; no browser profile')
    parser.add_argument('--destination', type=Path, default=ROOT / 'dist/portable')
    parser.add_argument('--config-document', type=Path,
                        help='Optional private configuration document delivered separately; never added to the ZIP')
    args = parser.parse_args()
    if args.action == 'stage':
        if not args.runtime_archive or not args.runtime_archive.is_file():
            parser.error('stage requires --runtime-archive')
        stage(args)
    else:
        archive(args)


if __name__ == '__main__':
    main()
