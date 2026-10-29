"""Create a private development snapshot, including ignored local state and WIP.

This is deliberately separate from public source/portable release packaging.
The resulting archive may contain credentials and is for private transfer only.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import zipfile


EXCLUDED_NAMES = {'.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache'}
TOP_EXCLUDED = {'dist', 'deliverables'}
STORED_SUFFIXES = {
    '.mp4', '.mov', '.mkv', '.webm', '.mp3', '.m4a', '.aac', '.ogg', '.flac',
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif', '.zip', '.7z', '.gz',
    '.bz2', '.xz', '.motion', '.exe', '.dll', '.pyd', '.wasm', '.woff', '.woff2',
}
GENERATED = {'migration/PACKAGE_CONTENTS.json', 'migration/FILE_HASHES.jsonl',
             'migration/DUPLICATE_FILES.json'}
DEDUP_SUFFIXES = STORED_SUFFIXES | {'.wav', '.ttf', '.otf', '.bin', '.onnx', '.safetensors'}
DEDUP_MIN_BYTES = 16 * 1024
CHUNK = 4 * 1024 * 1024


class TransferError(RuntimeError):
    pass


def safe_relative(value):
    value = str(value).replace('\\', '/')
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or ':' in value or '\x00' in value:
        raise TransferError(f'Unsafe archive path: {value!r}')
    if any(part in {'', '.'} for part in value.split('/')):
        raise TransferError(f'Unsafe archive path: {value!r}')
    return p.as_posix()


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extended_path(path):
    """Keep existing Windows long files readable without system registry changes."""
    path = Path(path).absolute()
    if os.name != 'nt' or str(path).startswith('\\\\?\\'):
        return path
    value = str(path)
    if value.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + value[2:])
    return Path('\\\\?\\' + value)


def load_mappings(path):
    if not path:
        return []
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    mappings = data.get('mappings', []) if isinstance(data, dict) else data
    if not isinstance(mappings, list):
        raise TransferError('External map must be an array or an object with mappings array')
    result = []
    for row in mappings:
        source = extended_path(row['source'])
        if not source.exists():
            raise TransferError(f'External source missing: {source}')
        result.append({'source': str(source), 'relative': safe_relative(row['relative'])})
    return result


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def load_selection(path):
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return {key: [safe_relative(item) for item in value.get(key, [])]
            for key in ('include_roots', 'include_files', 'exclude_roots', 'restrict_roots')}


def compile_selection(selection):
    compiled = {key: {value.casefold() for value in selection.get(key, [])}
                for key in ('include_roots', 'include_files', 'exclude_roots', 'restrict_roots')}
    ancestors = set()
    for value in compiled['include_roots'] | compiled['include_files']:
        parts = value.split('/')
        ancestors.update('/'.join(parts[:index]) for index in range(1, len(parts)))
    compiled['_include_ancestors'] = ancestors
    compiled['_compiled'] = True
    return compiled


def selected(relative, directory, selection):
    """Restricted data roots use explicit coverage; all other source stays selected."""
    relative = relative.casefold()
    if not selection.get('_compiled'):
        selection = compile_selection(selection)
    parts = relative.split('/')
    prefixes = {'/'.join(parts[:index]) for index in range(1, len(parts) + 1)}
    if prefixes & selection['exclude_roots']:
        return False
    if not prefixes & selection['restrict_roots']:
        return True
    if prefixes & selection['include_roots'] or relative in selection['include_files']:
        return True
    return directory and relative in selection['_include_ancestors']


def gather(root, mappings, output, report, selection=None):
    """Resolve a complete deterministic file list without following escaping links."""
    root = extended_path(root).resolve(strict=True)
    selection = compile_selection(selection or {})
    reserved = {name.casefold() for name in GENERATED}
    destinations = {}
    entries = []
    declared_sources = [(root, True)]
    for mapping in mappings:
        source = extended_path(mapping['source']).resolve(strict=True)
        declared_sources.append((source, source.is_dir()))
    omit_files = {extended_path(output), extended_path(str(output) + '.sha256'),
                  extended_path(str(output) + '.build-report.json')}

    def visit(path, relative, ancestors, workspace):
        relative = safe_relative(relative)
        if path.absolute() in omit_files:
            report['excluded_paths'].append({'path': str(path), 'reason': 'transfer output'})
            return
        if workspace:
            parts = PurePosixPath(relative).parts
            if any(part in EXCLUDED_NAMES for part in parts):
                report['excluded_paths'].append({'path': str(path), 'reason': 'rebuildable dependency/cache'})
                return
            if parts[0] in TOP_EXCLUDED or parts[:2] == ('migration', '.staging'):
                report['excluded_paths'].append({'path': str(path), 'reason': 'old delivery/staging'})
                return
        # Decide explicit exclusions from archive path text before touching the
        # filesystem, including ACL-protected temporary trees in external maps.
        if not selected(relative, True, selection):
            report['excluded_paths'].append({'path': str(path), 'reason': 'outside declared development selection'})
            return
        resolved = path.resolve(strict=True)
        if linked(path):
            declared = any(resolved == allowed or (directory and resolved.is_relative_to(allowed))
                           for allowed, directory in declared_sources)
            if not declared:
                report['rejected_links'].append({'path': str(path), 'target': str(resolved)})
                raise TransferError(f'Link leaves declared source root: {path} -> {resolved}')
            report['internal_links'].append({'path': str(path), 'target': str(resolved)})
        if path.is_dir():
            if resolved in ancestors:
                report['rejected_links'].append({'path': str(path), 'target': str(resolved), 'reason': 'cycle'})
                raise TransferError(f'Directory link cycle: {path}')
            with os.scandir(path) as children:
                names = sorted(item.name for item in children)
            for name in names:
                visit(path / name, relative + '/' + name, ancestors | {resolved}, workspace)
            return
        if not selected(relative, False, selection):
            report['excluded_paths'].append({'path': str(path), 'reason': 'outside declared development selection'})
            return
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise TransferError(f'Unsupported non-regular file: {path}')
        key = relative.casefold()
        if key in reserved:
            report['excluded_paths'].append({'path': str(path), 'reason': 'regenerated transfer metadata'})
            return
        if key in destinations:
            prior = destinations[key]
            if prior.resolve() == resolved:
                report['deduplicated_entries'] += 1
                return
            raise TransferError(f'Duplicate archive destination: {relative} ({prior} and {path})')
        destinations[key] = path
        entries.append((path, relative, info.st_size))

    with os.scandir(root) as children:
        names = sorted(item.name for item in children)
    for name in names:
        visit(root / name, name, {root}, True)
    for row in mappings:
        source = extended_path(row['source'])
        visit(source, row['relative'], set(), False)
    report['inventory_files'] = len(entries)
    report['inventory_bytes'] = sum(row[2] for row in entries)
    return entries


def git_snapshot(root):
    result = {}
    for label, args in [('head', ['rev-parse', 'HEAD']), ('branch', ['branch', '--show-current']),
                        ('status', ['-c', 'core.quotepath=false', 'status', '--porcelain=v1', '--untracked-files=all'])]:
        try:
            run = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=60, check=True)
            result[label] = run.stdout.rstrip()
        except (OSError, subprocess.SubprocessError) as exc:
            result[label + '_error'] = type(exc).__name__
    return result


def is_sqlite(path):
    if path.suffix.lower() not in {'.sqlite', '.sqlite3', '.db'}:
        return False
    with path.open('rb') as stream:
        return stream.read(16) == b'SQLite format 3\x00'


def snapshot_database(source, target):
    resolved = str(source.resolve())
    if resolved.startswith('\\\\?\\UNC\\'):
        resolved = '\\\\' + resolved[8:]
    elif resolved.startswith('\\\\?\\'):
        resolved = resolved[4:]
    uri = Path(resolved).as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as src:
        with closing(sqlite3.connect(target)) as dest:
            src.backup(dest, pages=256, sleep=0.05)
            dest.commit()
            checks = [row[0] for row in dest.execute('PRAGMA integrity_check')]
            if checks != ['ok']:
                raise TransferError(f'SQLite integrity check failed: {source}: {checks[:3]}')


def stable_snapshot(source, target, retries=2):
    """Retry before creating a ZIP entry, so changed reads never leave duplicates."""
    for attempt in range(retries + 1):
        before = source.stat()
        digest = hashlib.sha256()
        with source.open('rb') as src, target.open('wb') as dest:
            while block := src.read(CHUNK):
                digest.update(block)
                dest.write(block)
        after = source.stat()
        identity_before = (before.st_size, before.st_mtime_ns, before.st_ino)
        identity_after = (after.st_size, after.st_mtime_ns, after.st_ino)
        if identity_before == identity_after and target.stat().st_size == after.st_size:
            return digest.hexdigest(), after
        if attempt == retries:
            raise TransferError(f'File continued changing during snapshot: {source}')
    raise AssertionError('unreachable')


def write_entry(package, source, name, info):
    when = datetime.fromtimestamp(info.st_mtime)
    stamp = (max(1980, min(2107, when.year)), when.month, when.day, when.hour, when.minute, when.second)
    zinfo = zipfile.ZipInfo(name, stamp)
    zinfo.compress_type = zipfile.ZIP_STORED if source.suffix.lower() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
    zinfo._compresslevel = 3
    zinfo.external_attr = (stat.S_IMODE(info.st_mode) | stat.S_IFREG) << 16
    zinfo.file_size = info.st_size
    with source.open('rb') as stream, package.open(zinfo, 'w', force_zip64=True) as dest:
        shutil.copyfileobj(stream, dest, CHUNK)


def required_paths(root):
    manifest_path = root / 'migration/RECOVERY_MANIFEST.json'
    if not manifest_path.exists():
        return []
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    values = [row['path'] for row in data.get('reading_records', [])]
    for item in data.get('required_files', []):
        values.append(item['path'] if isinstance(item, dict) else item)
    return [safe_relative(value) for value in values]


def validate_zip(path, prefix, required=()):
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if len({name.casefold() for name in names}) != len(names):
            raise TransferError('Archive contains duplicate names')
        logical_duplicates = set()
        duplicate_name = prefix + 'migration/DUPLICATE_FILES.json'
        if duplicate_name in names:
            duplicates = json.loads(package.read(duplicate_name))['duplicates']
            for row in duplicates:
                duplicate = safe_relative(row['path'])
                target = safe_relative(row['target'])
                if prefix + target not in names or prefix + duplicate in names:
                    raise TransferError(f'Invalid duplicate materialization map: {duplicate}')
                logical_duplicates.add(duplicate)
        for relative in required:
            if prefix + relative not in names and relative not in logical_duplicates:
                raise TransferError(f'Required recovery file missing from archive: {relative}')
        bad = package.testzip()
        if bad:
            raise TransferError(f'Archive CRC verification failed: {bad}')
    return len(names)


def build(root, output, mappings=(), inventory=False, prefix=None, selection=None,
          deduplicate_files=False):
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    prefix = safe_relative(prefix or root.name) + '/'
    report_path = Path(str(output) + '.build-report.json')
    if not inventory and output.exists():
        raise TransferError(f'Refusing to overwrite archive: {output}')
    report = {'schema': 1, 'kind': 'private-development-transfer',
              'source_root': str(root), 'archive_root': prefix.rstrip('/'),
              'created_at': datetime.now(timezone.utc).isoformat(),
              'exclusion_rules': {'directory_names': sorted(EXCLUDED_NAMES), 'root_directories': sorted(TOP_EXCLUDED)},
              'excluded_paths': [], 'rejected_links': [], 'internal_links': [],
              'deduplicated_entries': 0, 'sqlite_snapshots': [], 'sqlite_sidecars_omitted': [],
              'external_mappings': list(mappings), 'git': git_snapshot(root),
              'development_selection': selection or {},
              'content_deduplication': bool(deduplicate_files),
              'private_contents': 'May contain keys, cookies, account records and private media. Keep private.'}
    started = time.monotonic()
    try:
        entries = gather(root, mappings, output, report, selection)
        if inventory:
            report['status'] = 'inventory-only'
            return report
        output.parent.mkdir(parents=True, exist_ok=True)
        report['required_files'] = required_paths(root)
        count = byte_count = archived_count = archived_bytes = 0
        content_targets = {}
        duplicates = []
        last_progress = started
        with tempfile.TemporaryDirectory(prefix='.haike-transfer-staging-', dir=output.parent) as temp:
            temp_root = Path(temp)
            databases = {}
            for source, relative, _ in entries:
                if is_sqlite(source):
                    target = temp_root / f'db-{len(databases):06d}.sqlite3'
                    snapshot_database(source, target)
                    databases[source.absolute()] = target
                    report['sqlite_snapshots'].append({'path': relative, 'integrity_check': 'ok', 'bytes': target.stat().st_size})
            hashes = temp_root / 'hashes.jsonl'
            with hashes.open('w', encoding='utf-8', newline='\n') as hash_rows:
                with zipfile.ZipFile(output, 'x', allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=3) as package:
                    for source, relative, _ in entries:
                        if source.name.endswith(('-wal', '-shm', '-journal')):
                            suffix = next(s for s in ('-wal', '-shm', '-journal') if source.name.endswith(s))
                            primary = source.with_name(source.name[:-len(suffix)]).absolute()
                            if primary in databases:
                                report['sqlite_sidecars_omitted'].append(relative)
                                continue
                        if source.absolute() in databases:
                            copy = databases[source.absolute()]
                            digest, info = file_sha(copy), copy.stat()
                        else:
                            copy = temp_root / ('file' + source.suffix)
                            digest, info = stable_snapshot(source, copy)
                        # Preserve the original suffix for compression policy and the
                        # stable copied size/time, without rereading mutable sources.
                        dedup_key = (digest, info.st_size)
                        candidate = (deduplicate_files and source.absolute() not in databases
                                     and info.st_size >= DEDUP_MIN_BYTES
                                     and source.suffix.lower() in DEDUP_SUFFIXES)
                        duplicate_target = content_targets.get(dedup_key) if candidate else None
                        if duplicate_target:
                            duplicates.append({'path': relative, 'target': duplicate_target,
                                               'bytes': info.st_size, 'sha256': digest})
                        else:
                            write_entry(package, copy, prefix + relative, info)
                            archived_count += 1
                            archived_bytes += info.st_size
                            if candidate:
                                content_targets[dedup_key] = relative
                        row = {'path': relative, 'bytes': info.st_size, 'sha256': digest,
                               'snapshot': 'sqlite-backup' if source.absolute() in databases else 'stable-file'}
                        if duplicate_target:
                            row['duplicate_of'] = duplicate_target
                        hash_rows.write(json.dumps(row, ensure_ascii=False) + '\n')
                        count += 1
                        byte_count += info.st_size
                        now = time.monotonic()
                        if count % 1000 == 0 or now - last_progress >= 10:
                            print(json.dumps({'phase': 'writing', 'files': count, 'GiB': round(byte_count / 2**30, 3),
                                              'elapsed_seconds': round(now - started)}, ensure_ascii=False), flush=True)
                            last_progress = now
                    hash_rows.flush()
                    report.update({'payload_files': count, 'payload_bytes': byte_count,
                                   'archived_payload_files': archived_count, 'archived_payload_bytes': archived_bytes,
                                   'content_duplicate_files': len(duplicates),
                                   'content_deduplicated_bytes': byte_count - archived_bytes, 'status': 'written'})
                    if deduplicate_files:
                        package.writestr(prefix + 'migration/DUPLICATE_FILES.json',
                                         json.dumps({'schema': 1, 'duplicates': duplicates}, ensure_ascii=False))
                    package.writestr(prefix + 'migration/PACKAGE_CONTENTS.json', json.dumps(report, ensure_ascii=False, indent=2))
                    package.write(hashes, prefix + 'migration/FILE_HASHES.jsonl')
        print(json.dumps({'phase': 'crc-verification', 'files': count}, ensure_ascii=False), flush=True)
        report['archive_entries'] = validate_zip(output, prefix, report['required_files'])
        report['archive_bytes'] = output.stat().st_size
        report['archive_sha256'] = file_sha(output)
        report['status'] = 'verified'
        report['elapsed_seconds'] = round(time.monotonic() - started, 2)
        Path(str(output) + '.sha256').write_text(f"{report['archive_sha256']}  {output.name}\n", encoding='utf-8')
        json_write(report_path, report)
        return report
    except Exception as exc:
        report.update({'status': 'failed', 'error': str(exc), 'error_type': type(exc).__name__})
        json_write(report_path, report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--external-map', type=Path)
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--prefix')
    parser.add_argument('--selection-file', type=Path)
    parser.add_argument('--deduplicate-files', action='store_true',
                        help='Store repeated >=16KiB media once; restore using migration/DUPLICATE_FILES.json')
    args = parser.parse_args()
    try:
        result = build(args.root, args.output, load_mappings(args.external_map), args.inventory,
                       args.prefix, load_selection(args.selection_file), args.deduplicate_files)
        summary = {key: result[key] for key in ('status', 'inventory_files', 'inventory_bytes')}
        for key in ('payload_files', 'payload_bytes', 'archive_entries', 'archive_bytes', 'archive_sha256',
                    'elapsed_seconds', 'content_duplicate_files', 'content_deduplicated_bytes'):
            if key in result:
                summary[key] = result[key]
        summary.update({'output': str(args.output.absolute()), 'excluded_paths': len(result['excluded_paths']),
                        'sqlite_databases': len(result['sqlite_snapshots'])})
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
