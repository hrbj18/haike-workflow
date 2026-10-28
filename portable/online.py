"""Hydrate a small online distribution using pinned, China-direct dependencies.

Only runtime, virtual environments and node_modules are installer-owned. User
configuration is initialized afterwards by the existing portable entry point.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import portable


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(name, spec):
    expected = spec['sha256']
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('Invalid pinned checksum: ' + name)
    cached = portable.local_path('.portable/downloads/' + expected + '.zip')
    cached.parent.mkdir(parents=True, exist_ok=True)
    if cached.is_file() and digest(cached) == expected:
        print('Using verified download: ' + name, flush=True)
        return cached
    failures = []
    for url in spec['urls']:
        if not url.startswith('https://'):
            raise ValueError('Downloads require HTTPS')
        print('Downloading ' + name + ': ' + url, flush=True)
        partial = cached.with_suffix('.part')
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as output:
                if not response.geturl().startswith('https://'):
                    raise ValueError('Insecure redirect')
                shutil.copyfileobj(response, output, 1024 * 1024)
            if digest(partial) != expected:
                raise ValueError('Checksum mismatch; file rejected')
            os.replace(partial, cached)
            return cached
        except (OSError, ValueError) as error:
            failures.append(type(error).__name__)
        finally:
            partial.unlink(missing_ok=True)
    raise RuntimeError('Cannot download ' + name + '; retry setup. Sources: ' + ', '.join(failures))


def extract(archive, target, prefix='', flatten=False, select=None):
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            name = entry.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name
                    or ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('Unsafe dependency archive')
            if entry.is_dir() or not name.startswith(prefix) or (select and not select(name)):
                continue
            relative = Path(path.name if flatten else name[len(prefix):])
            output = target / relative
            if not output.resolve().is_relative_to(target.resolve()):
                raise ValueError('Dependency path escapes staging')
            output.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as source, output.open('wb') as stream:
                shutil.copyfileobj(source, stream)


def install_component(name, spec):
    target = portable.local_path('runtime/' + name)
    receipt = portable.read_json('.portable/components/' + name + '.json', {})
    if receipt.get('archive_sha256') == spec['sha256'] and receipt.get('files'):
        if all(portable.local_path('runtime/' + name + '/' + p).is_file()
               and digest(portable.local_path('runtime/' + name + '/' + p)) == h
               for p, h in receipt['files'].items()):
            print('Installed component verified: ' + name, flush=True)
            return
    archive = download(name, spec)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='install-' + name + '-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'payload'
        staged.mkdir()
        options = {'prefix': spec.get('prefix', '')}
        if name == 'uv':
            options.update(flatten=True, select=lambda p: p.endswith(('uv.exe', 'LICENSE-MIT', 'LICENSE-APACHE')))
        elif name == 'msvc':
            options.update(flatten=True, select=lambda p: (p.endswith('.dll') and '/Scripts/' in p) or 'licenses/' in p)
        elif name == 'ffmpeg':
            with zipfile.ZipFile(archive) as package:
                options['prefix'] = package.namelist()[0].split('/')[0] + '/'
        extract(archive, staged, **options)
        if not any(staged.rglob('*.exe')) and name != 'msvc':
            raise ValueError('Dependency archive has no executables: ' + name)
        files = {p.relative_to(staged).as_posix(): digest(p) for p in staged.rglob('*') if p.is_file()}
        # Keep a recoverable old dependency tree; never touch user configuration.
        backup = portable.local_path('.portable/dependency-backups/' + name)
        if target.exists():
            if backup.exists():
                raise RuntimeError('Previous dependency backup exists; inspect ' + str(backup))
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup.exists():
                backup.rename(target)
            raise
    portable.write_json('.portable/components/' + name + '.json', {'archive_sha256': spec['sha256'], 'files': files})


def install_environment(spec):
    env = portable.environment()
    for key in ('PIP_NO_INDEX', 'UV_OFFLINE', 'NPM_CONFIG_OFFLINE'):
        env.pop(key, None)
    env.update(UV_PYTHON_DOWNLOADS='never', NPM_CONFIG_REGISTRY=spec['npm'],
               NPM_CONFIG_REPLACE_REGISTRY_HOST='always', UV_LINK_MODE='copy')
    return env


def command(arguments, env, cwd=None):
    log = portable.local_path('.portable/logs/online-install.log')
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Installing: ' + str(cwd or 'Python dependencies'), flush=True)
    with log.open('ab') as output:
        result = subprocess.run(list(map(str, arguments)), cwd=cwd or portable.ROOT, env=env,
                                stdout=output, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Dependency command failed; see .portable/logs/online-install.log')


def install_hyperframes(spec, env, npm):
    hyperframes = portable.local_path('runtime/hyperframes')
    hyperframes.mkdir(parents=True, exist_ok=True)
    # npm otherwise searches ancestor folders for a project. Establish an
    # explicit package boundary before running any install command.
    portable.write_json('runtime/hyperframes/package.json', {
        'name': 'haike-hyperframes-runtime', 'private': True,
        'dependencies': {'hyperframes': spec['hyperframes']},
    })
    installed = portable.read_json('runtime/hyperframes/node_modules/hyperframes/package.json', {})
    if installed.get('version') != spec['hyperframes']:
        command([npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund',
                 '--save-exact', 'hyperframes@' + spec['hyperframes']], env, hyperframes)


def hydrate():
    if (portable.ROOT / '.git').exists() or portable.read_json('RELEASE.json', {}).get('distribution') != 'online':
        raise RuntimeError('Use 01-setup.cmd inside an extracted online release')
    spec = portable.read_json('config/online-downloads.json')
    for name in ('uv', 'node', 'msvc', 'ffmpeg', 'browser'):
        install_component(name, spec[name])
    env = install_environment(spec)
    uv = portable.local_path('runtime/uv/uv.exe')
    base = portable.local_path('runtime/python/python.exe')
    modules = [('Haike_video', 'Haike_video'), ('creatorhub', 'creatorhub'),
               ('copy_skill/copy_skill-main', 'copy_skill')]
    for module, lock in modules:
        folder = portable.local_path(module)
        venv = portable.local_path(module + '/.venv')
        python = venv / 'Scripts/python.exe'
        if not python.is_file():
            command([uv, 'venv', '--python', base, venv], env)
        lockfile = portable.local_path('_distribution-tools/locks/' + lock + '.txt')
        stamp = '.portable/python-' + lock + '.json'
        if portable.read_json(stamp, {}).get('lock_sha256') != digest(lockfile):
            for index in spec['pypi']:
                try:
                    command([uv, 'pip', 'sync', '--python', python, '--index-url', index, lockfile], env)
                    break
                except RuntimeError:
                    if index == spec['pypi'][-1]:
                        raise
            portable.write_json(stamp, {'lock_sha256': digest(lockfile)})
    # Editable source is local to this copy, without embedding installation paths.
    portable.write_text('copy_skill/copy_skill-main/.venv/Lib/site-packages/haike-source.pth', '../../../src\n')
    command([base, '-s', portable.local_path('_distribution-tools/setup_msvc.py'),
             '--source-dir', portable.local_path('runtime/msvc')], env)
    composer = portable.local_path('Haike_video/remotion-composer')
    npm = portable.local_path('runtime/node/npm.cmd')
    lock = composer / 'package-lock.json'
    if portable.read_json('.portable/npm-composer.json', {}).get('lock_sha256') != digest(lock):
        command([npm, 'ci', '--no-audit', '--no-fund'], env, composer)
        portable.write_json('.portable/npm-composer.json', {'lock_sha256': digest(lock)})
    install_hyperframes(spec, env, npm)
    portable.prepare()
    result = portable.diagnose(full=True)
    portable.write_json('.portable/online-ready.json', {'ok': True, 'distribution': 'online'})
    return result


if __name__ == '__main__':
    try:
        with portable.bundle_lock():
            print(json.dumps(hydrate(), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError) as error:
        print('Setup stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
