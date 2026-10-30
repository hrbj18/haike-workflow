"""Inspect a private development snapshot and relocate only approved defaults.

The migration manifest is private package metadata, not a release manifest.
Historical task databases and frozen requests remain read-only: their source
hashes, paid intents and review evidence must survive the move unchanged.
Deduplicated ZIPs require hydrate after extraction to recreate all logical
snapshot files as independent copies before development continues.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
import uuid


MAX_TEXT_BYTES = 64 * 1024 * 1024
# Duplicate indexes cover every logical media/cache copy in a private snapshot.
# Keep their bounded metadata budget separate from individual history/config text.
MAX_DUPLICATE_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_HISTORY_FILES = 5000
REPORT_ROOT = '.local/development-recovery'
CONFIG_ALLOWLIST = frozenset({
    '.local/motion-native-story/defaults.json',
    '.local/motion-console/defaults.json',
    '.local/motion-poster/defaults.json',
    '.local/motion-template-studio/defaults.json',
    '.local/runninghub-workflow/default.json',
    'creatorhub/config.yaml',
})
HISTORY_DATABASES = (
    '.local/motiongit/registry.sqlite3',
    'Haike_video/.backlot/motion-template-sessions.sqlite3',
    'Haike_video/.backlot/production-queue.sqlite3',
    'Haike_video/.backlot/studio.sqlite3',
    'Haike_video/.backlot/task-center.sqlite3',
    'Haike_video/.backlot/works.sqlite3',
)
HISTORY_JSON_ROOTS = (
    '.local/motiongit/drafts',
    '.local/motiongit-three-20261029',
    '.local/motion-console',
    '.local/motion-poster',
    '.local/motion-native-story',
    '.local/motion-template-studio',
)
TEXT_SUFFIXES = frozenset({'.json', '.jsonl', '.yaml', '.yml'})


def standard_path(path: Path | str) -> Path:
    """Keep Windows implementation prefixes out of stored business paths."""
    value = str(path)
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)


def filesystem_path(path: Path | str) -> Path:
    """Use extended Windows filenames for all actual filesystem operations."""
    value = str(path)
    if os.name != 'nt' or value.startswith('\\\\?\\'):
        return Path(value)
    value = str(Path(value).absolute())
    if value.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + value[2:])
    return Path('\\\\?\\' + value)


def safe(root: Path, name: str, *, allow_root: bool = False) -> Path:
    """Resolve an archive-relative path without traversing links or junctions."""
    if not isinstance(name, str):
        raise ValueError('Package-relative path must be a string')
    rel = PurePosixPath(name)
    if (not name or rel.is_absolute()
            or PureWindowsPath(name).is_absolute() or '..' in rel.parts
            or '\\' in name or ':' in name or '\0' in name
            or (str(rel) == '.' and not allow_root)):
        raise ValueError('Unsafe package-relative path: ' + str(name))
    root = filesystem_path(root)
    if root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise ValueError('Target root must not be a link: ' + str(root))
    root = root.resolve()
    cursor = root.joinpath(*rel.parts)
    # resolve() follows every existing ancestor, including when the final file
    # is absent. A changed spelling signals a link even if it stays inside root.
    # Path equality retains platform case rules and extended Windows prefixes.
    # Avoid rechecking each shared ancestor for every file in large indexes.
    resolved = cursor.resolve()
    if resolved != cursor:
        raise ValueError('Package path traverses a link: ' + name)
    if not resolved.is_relative_to(root):
        raise ValueError('Package path escapes target: ' + name)
    return cursor


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def atomic_bytes(path: Path, data: bytes) -> None:
    path = filesystem_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.recovery-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sha256(path: Path) -> str:
    with filesystem_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_manifest(root: Path) -> dict:
    path = safe(root, 'migration/RECOVERY_MANIFEST.json')
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(manifest, dict) or manifest.get('schema') != 1:
        raise ValueError('Expected recovery manifest schema 1')
    if not isinstance(manifest.get('source_root'), str):
        raise ValueError('Missing source_root')
    source_root = manifest['source_root']
    if not (PureWindowsPath(source_root).is_absolute() or Path(source_root).is_absolute()):
        raise ValueError('source_root must be absolute')
    records = manifest.get('reading_records')
    if not isinstance(records, list) or not records:
        raise ValueError('Manifest reading_records must be a non-empty array')
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid reading record')
        name = record.get('path')
        safe(root, name)
        if name in seen:
            raise ValueError('Duplicate reading record: ' + name)
        seen.add(name)
        if not re.fullmatch('[0-9a-fA-F]{64}', str(record.get('sha256', ''))):
            raise ValueError('Invalid reading record SHA256: ' + name)
    mappings = manifest.get('path_mappings', [])
    if not isinstance(mappings, list):
        raise ValueError('path_mappings must be an array')
    for mapping in mappings:
        if not isinstance(mapping, dict) or not isinstance(mapping.get('old'), str):
            raise ValueError('Invalid path mapping')
        old = mapping['old']
        if not (PureWindowsPath(old).is_absolute() or Path(old).is_absolute()):
            raise ValueError('Mapping old path must be absolute')
        safe(root, mapping.get('new_relative'), allow_root=True)
    configs = manifest.get('relocation_configs', [])
    if not isinstance(configs, list) or not all(isinstance(name, str) for name in configs):
        raise ValueError('relocation_configs must be an array of relative paths')
    invalid = set(configs) - CONFIG_ALLOWLIST
    if invalid:
        raise ValueError('Relocation config is outside the defaults allowlist: ' + ', '.join(sorted(invalid)))
    for name in configs:
        safe(root, name)
    return manifest


def normal_path(value: str) -> str:
    return str(standard_path(value)).replace('\\', '/').rstrip('/').casefold()


class PathRewriter:
    def __init__(self, root: Path, manifest: dict):
        mappings = list(manifest.get('path_mappings', []))
        if not any(normal_path(item['old']) == normal_path(manifest['source_root']) for item in mappings):
            mappings.append({'old': manifest['source_root'], 'new_relative': '.'})
        self.mappings = []
        self.rules = []
        seen = set()
        for mapping in sorted(mappings, key=lambda item: len(item['old']), reverse=True):
            old = mapping['old'].rstrip('/\\')
            destination = safe(root, mapping['new_relative'], allow_root=True)
            normalized = normal_path(old)
            if normalized in seen:
                raise ValueError('Duplicate source path mapping: ' + old)
            seen.add(normalized)
            self.mappings.append((old, destination, mapping['new_relative']))
            if normalized == normal_path(str(destination)):
                continue
            self.rules.append((self.path_expression(old), standard_path(destination).as_posix()))
        protected = [self.path_expression(str(standard_path(destination)))
                     for _old, destination, _relative in self.mappings]
        alternatives = ['(?P<protected>' + '|'.join(protected) + ')']
        alternatives.extend('(?P<old' + str(index) + '>' + expression + ')'
                            for index, (expression, _replacement) in enumerate(self.rules))
        self.matcher = re.compile('|'.join(alternatives), re.IGNORECASE)

    @staticmethod
    def path_expression(value: str) -> str:
        parts = value.replace('\\', '/').rstrip('/').split('/')
        # Each separator can be native, slash, or JSON-escaped backslash.
        expression = r'(?:\\\\|\\|/)'.join(re.escape(part) for part in parts)
        return r'(?<!\w)' + expression + r'(?=$|[\\/"\s\x27,\]}])'

    def replace(self, value: str) -> tuple[str, int]:
        count = 0

        def replacement(match):
            nonlocal count
            if match.lastgroup == 'protected':
                return match.group()
            count += 1
            return self.rules[int(match.lastgroup[3:])][1]

        return self.matcher.sub(replacement, value), count


def verify(root: Path, manifest: dict) -> dict:
    results = []
    for record in manifest['reading_records']:
        path = safe(root, record['path'])
        exists = path.is_file()
        actual = sha256(path) if exists else None
        results.append({'path': record['path'], 'exists': exists,
                        'sha256_matches': actual == record['sha256'].lower()})
    report = {
        'ok': all(item['sha256_matches'] for item in results),
        'mode': 'verify', 'snapshot_id': manifest.get('snapshot_id'),
        'focus': manifest.get('focus'), 'integrity_only': True,
        'agent_reading_or_understanding': 'not_attested',
        'records_checked': len(results), 'records': results,
    }
    destination = safe(root, REPORT_ROOT + '/verification.json')
    atomic_json(destination, report)
    report['report_path'] = str(standard_path(destination))
    return report


def hydration_plan(root: Path, *, verify_hashes: bool = True) -> tuple[list[dict], bool]:
    """Preflight duplicate materialization; target files must physically exist."""
    root = filesystem_path(root).resolve()
    manifest_path = safe(root, 'migration/DUPLICATE_FILES.json')
    if not manifest_path.exists():
        return [], False
    if manifest_path.stat().st_size > MAX_DUPLICATE_MANIFEST_BYTES:
        raise ValueError('Duplicate file manifest exceeds 256 MiB')
    data = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('duplicates'), list):
        raise ValueError('Expected duplicate file manifest schema 1 with duplicates array')
    plan = []
    seen = set()
    digests = {}

    def matches(path, expected_size, expected_hash):
        metadata = path.stat()
        if metadata.st_size != expected_size:
            return False
        if not verify_hashes:
            return True
        key = (str(path), metadata.st_size, metadata.st_mtime_ns)
        if key not in digests:
            digests[key] = sha256(path)
        return digests[key] == expected_hash

    for entry in data['duplicates']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid duplicate file entry')
        name, target_name = entry.get('path'), entry.get('target')
        destination = safe(root, name)
        source = safe(root, target_name)
        if name in seen or destination == source:
            raise ValueError('Duplicate destination or self-reference: ' + str(name))
        seen.add(name)
        size, digest = entry.get('bytes'), str(entry.get('sha256', '')).lower()
        if type(size) is not int or size < 0 or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid duplicate file size or SHA256: ' + name)
        if not source.is_file():
            raise ValueError('Duplicate target must physically exist in the extracted package: ' + target_name)
        if not matches(source, size, digest):
            raise ValueError('Duplicate target failed size/SHA256 validation: ' + target_name)
        exists = destination.exists()
        if exists and (not destination.is_file() or not matches(destination, size, digest)):
            raise ValueError('Hydrate refuses to overwrite an existing different file: ' + name)
        plan.append({'path': name, 'target': target_name, 'bytes': size,
                     'sha256': digest, 'already_present': exists})
    return plan, True


def copy_independently(root: Path, item: dict) -> None:
    """Copy and verify bytes, then atomically replace only our own reservation."""
    source, destination = safe(root, item['target']), safe(root, item['path'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.hydrate-', dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    reserved_identity = None
    try:
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != item['bytes'] or sha256(temporary) != item['sha256']:
            raise ValueError('Duplicate source changed during copying: ' + item['target'])
        # O_EXCL prevents replacing a user file that appeared after preflight.
        reservation = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            reserved = os.fstat(reservation)
            reserved_identity = (reserved.st_dev, reserved.st_ino)
        finally:
            os.close(reservation)
        for attempt in range(4):
            safe(root, item['path'])
            current = destination.stat()
            if (current.st_dev, current.st_ino) != reserved_identity or current.st_size:
                raise ValueError('Hydration destination changed after reservation: ' + item['path'])
            try:
                os.replace(temporary, destination)
            except PermissionError as error:
                # Windows scanners can briefly hold the newly created files.
                # Retry only this owned reservation, with a finite time budget.
                if os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 3:
                    raise
                time.sleep(0.05 * 2**attempt)
            else:
                reserved_identity = None
                break
    finally:
        temporary.unlink(missing_ok=True)
        if reserved_identity is not None and destination.exists():
            current = destination.stat()
            if (current.st_dev, current.st_ino) == reserved_identity and not current.st_size:
                destination.unlink()


def hydrate(root: Path, *, dry_run: bool = False) -> dict:
    """Recreate ZIP-deduplicated paths using independent verified copies."""
    root = filesystem_path(root).resolve()
    plan, present = hydration_plan(root)
    pending = [item for item in plan if not item['already_present']]
    required = sum(item['bytes'] for item in pending)
    free = shutil.disk_usage(root).free
    if not dry_run and free < required:
        raise ValueError('Insufficient free space for hydrate: need ' + str(required) + ' bytes; available ' + str(free))
    report_path = safe(root, REPORT_ROOT + '/hydration.json')
    records = []
    report = {'schema': 1, 'mode': 'hydrate', 'dry_run': dry_run,
              'duplicate_manifest_present': present, 'files_total': len(plan),
              'bytes_to_copy': required, 'free_bytes_before': free, 'records': records,
              'independent_copies': True}
    try:
        for item in plan:
            if item['already_present']:
                state = 'already_present'
            elif dry_run:
                state = 'pending'
            else:
                copy_independently(root, item)
                state = 'copied'
            records.append({'path': item['path'], 'target': item['target'],
                            'bytes': item['bytes'], 'sha256': item['sha256'], 'status': state})
        report['ok'] = True
    except (OSError, ValueError) as error:
        report.update(ok=False, error_type=type(error).__name__)
        if not dry_run:
            atomic_json(report_path, report)
        raise
    if not dry_run:
        atomic_json(report_path, report)
    copied = [item for item in records if item['status'] == 'copied']
    # Keep per-file records in the local receipt; stdout contains only counts.
    return {'ok': True, 'mode': 'hydrate', 'dry_run': dry_run,
            'duplicate_manifest_present': present, 'files_total': len(plan),
            'files_copied': len(copied),
            'files_already_present': len(plan) - len(pending),
            'files_pending': len(pending) if dry_run else 0,
            'bytes_to_copy': required, 'bytes_copied': sum(item['bytes'] for item in copied),
            'free_bytes_before': free,
            'logical_snapshot_complete': not dry_run or not pending,
            'report_path': None if dry_run else str(standard_path(report_path))}


def executable_version(name: str, arguments: list[str]) -> dict:
    executable = shutil.which(name)
    if executable is None:
        return {'available': False}
    try:
        result = subprocess.run([executable, *arguments], capture_output=True,
                                text=True, timeout=15, check=False)
        value = (result.stdout or result.stderr).strip().splitlines()
        return {'available': result.returncode == 0, 'version': value[0] if value else '',
                'exit_code': result.returncode}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'available': False, 'error_type': type(error).__name__}


def doctor(root: Path, manifest: dict) -> dict:
    tools = {name: executable_version(name, ['--version']) for name in ('node', 'git', 'uv')}
    node_match = re.match(r'v?(\d+)', tools['node'].get('version', ''))
    node_ok = bool(tools['node'].get('available') and node_match and int(node_match[1]) >= 22)
    python_ok = sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32
    rewriter = PathRewriter(root, manifest)
    mapped_paths = [{'source': old, 'new_relative': relative,
                     'destination_exists': destination.exists(),
                     'source_available_here': Path(old).is_absolute() and filesystem_path(old).exists()}
                    for old, destination, relative in rewriter.mappings]
    checks = {'python_312_x64': python_ok, 'node_22_or_newer': node_ok,
              'git': tools['git']['available'], 'uv': tools['uv']['available']}
    duplicates, duplicate_manifest = hydration_plan(root, verify_hashes=False)
    pending = [item for item in duplicates if not item['already_present']]
    hydration_bytes = sum(item['bytes'] for item in pending)
    free_bytes = shutil.disk_usage(root).free
    return {
        'ok': (all(checks.values()) and all(item['destination_exists'] for item in mapped_paths)
               and not pending),
        'mode': 'doctor', 'read_only': True,
        'platform': platform.platform(), 'python': platform.python_version(),
        'checks': checks, 'tools': tools, 'mapped_paths': mapped_paths,
        'missing_package_paths': [item['new_relative'] for item in mapped_paths
                                  if not item['destination_exists']],
        'hydration': {'duplicate_manifest_present': duplicate_manifest,
                      'files_pending': len(pending), 'bytes_needed': hydration_bytes,
                      'free_bytes': free_bytes, 'space_sufficient': free_bytes >= hydration_bytes,
                      'content_hashes_verified': False},
        'history_policy': 'preserved_read_only',
        'next_steps': [
            'Run hydrate after extracting a deduplicated ZIP to complete the logical snapshot with independent file copies.',
            'Read every reading_records entry in manifest order; integrity verification is not a reading receipt.',
            'Rebuild source-checkout dependencies with scripts/setup.ps1 on Windows after confirming prerequisites.',
            'Use relocate to inspect approved defaults, then relocate --apply to back up and update only those defaults.',
            'Retain frozen historical requests, hashes and paid intents. Prepare a new local project revision and review paths before continuing.',
            'Validate the new workspace identity and original job status before any authorized paid or publish action.',
        ],
    }


def quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sqlite_references(path: Path, rewriter: PathRewriter) -> dict:
    """Count old path strings without changing task history or opening writable DBs."""
    count = 0
    fields = []
    # Immutable mode avoids creating or updating SQLite -shm sidecars. Callers
    # reject databases with live WAL data instead of silently ignoring that WAL.
    filename = quote(str(filesystem_path(path).resolve()), safe='/')
    with closing(sqlite3.connect('file:' + filename + '?mode=ro&immutable=1',
                                 uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        tables = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        excluded_tables = {row[1] for row in connection.execute('PRAGMA table_list')
                           if row[2] in ('virtual', 'shadow')}
        for table, definition in tables:
            if (table in excluded_tables or not definition
                    or re.match(r'\s*CREATE\s+VIRTUAL\s+TABLE\b', definition, re.IGNORECASE)):
                continue
            # table_info excludes generated/hidden columns and avoids virtual-table inputs.
            columns = connection.execute('PRAGMA table_info(' + quoted_identifier(table) + ')').fetchall()
            for _cid, column, declared_type, *_tail in columns:
                # SQLite may store text in loosely typed columns, so inspect actual TEXT values.
                query = ('SELECT ' + quoted_identifier(column) + ' FROM ' + quoted_identifier(table)
                         + ' WHERE typeof(' + quoted_identifier(column) + ")='text'")
                occurrences = 0
                for (value,) in connection.execute(query):
                    occurrences += rewriter.replace(value)[1]
                if occurrences:
                    fields.append({'table': table, 'column': column, 'references': occurrences})
                    count += occurrences
    return {'kind': 'sqlite', 'references': count, 'fields': fields, 'modified': False}


def history_candidates(root: Path, configs: set[str]) -> tuple[list[tuple[str, Path]], list[dict]]:
    root = filesystem_path(root).resolve()
    candidates = []
    skipped = []
    for name in HISTORY_DATABASES:
        path = safe(root, name)
        if path.is_file():
            candidates.append((name, path))
    for relative in HISTORY_JSON_ROOTS:
        start = safe(root, relative)
        if not start.exists():
            continue
        for directory, subdirs, files in os.walk(start, followlinks=False):
            subdirs[:] = sorted(subdirs)
            for name in subdirs:
                safe(root, (Path(directory) / name).relative_to(root).as_posix())
            for name in sorted(files):
                path = Path(directory) / name
                relative_name = path.relative_to(root).as_posix()
                # Validate links even when the suffix would otherwise be ignored.
                path = safe(root, relative_name)
                if relative_name not in configs and path.suffix.lower() in TEXT_SUFFIXES:
                    if len(candidates) >= MAX_HISTORY_FILES:
                        skipped.append({'path': relative, 'reason': 'history_scan_limit',
                                        'limit': MAX_HISTORY_FILES})
                        return candidates, skipped
                    candidates.append((relative_name, path))
    return candidates, skipped


def read_text_state(path: Path) -> tuple[str | None, str | None, bool]:
    path = filesystem_path(path)
    if path.stat().st_size > MAX_TEXT_BYTES:
        return None, 'text_exceeds_64_mib', False
    raw = path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    try:
        return raw.decode('utf-8-sig'), None, bom
    except UnicodeDecodeError:
        return None, 'text_is_not_utf8', bom


def relocate(root: Path, manifest: dict, *, apply: bool = False) -> dict:
    root = filesystem_path(root).resolve()
    rewriter = PathRewriter(root, manifest)
    configs = set(manifest.get('relocation_configs', []))
    plan = []
    skipped = []
    # Complete path and decode preflight before the first mutation.
    for name in sorted(configs):
        path = safe(root, name)
        if not path.is_file():
            skipped.append({'path': name, 'reason': 'config_not_present'})
            continue
        text, reason, bom = read_text_state(path)
        if reason:
            skipped.append({'path': name, 'reason': reason})
            continue
        replacement, changes = rewriter.replace(text)
        if changes:
            # Check JSON output remains valid; YAML formatting is retained bytewise.
            if path.suffix.lower() == '.json':
                json.loads(replacement)
            plan.append((name, path, replacement, changes, bom))
    candidates, history_skipped = history_candidates(root, configs)
    skipped.extend(history_skipped)
    history = []
    for name, path in candidates:
        if path.suffix.lower() in {'.db', '.sqlite', '.sqlite3'}:
            wal = safe(root, name + '-wal')
            if wal.is_file() and wal.stat().st_size:
                skipped.append({'path': name, 'reason': 'sqlite_wal_requires_consistent_snapshot'})
                continue
            try:
                record = sqlite_references(path, rewriter)
            except sqlite3.Error as error:
                skipped.append({'path': name, 'reason': 'sqlite_scan_failed',
                                'error_type': type(error).__name__})
                continue
        else:
            content, reason, _bom = read_text_state(path)
            if reason:
                skipped.append({'path': name, 'reason': reason})
                continue
            record = {'kind': 'text', 'references': rewriter.replace(content)[1], 'modified': False}
        if record['references']:
            history.append({'path': name, **record})
    backup_relative = None
    changed = []
    if apply and plan:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
        backup_relative = REPORT_ROOT + '/backups/' + stamp
        backup_root = safe(root, backup_relative)
        backup_root.mkdir(parents=True, exist_ok=False)
        # Save every original first. A failed write can be recovered from this receipt.
        originals = []
        for name, path, _replacement, changes, _bom in plan:
            backup = safe(root, backup_relative + '/files/' + name)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup)
            originals.append({'path': name, 'sha256': sha256(backup), 'replacements': changes})
        atomic_json(safe(root, backup_relative + '/receipt.json'),
                    {'schema': 1, 'status': 'backed_up', 'files': originals})
        try:
            for name, path, replacement, changes, bom in plan:
                safe(root, name)
                encoding = 'utf-8-sig' if bom else 'utf-8'
                atomic_bytes(path, replacement.encode(encoding))
                changed.append({'path': name, 'replacements': changes})
        except Exception:
            for item in originals:
                atomic_bytes(safe(root, item['path']),
                             safe(root, backup_relative + '/files/' + item['path']).read_bytes())
            atomic_json(safe(root, backup_relative + '/receipt.json'),
                        {'schema': 1, 'status': 'rolled_back', 'files': originals})
            raise
        atomic_json(safe(root, backup_relative + '/receipt.json'),
                    {'schema': 1, 'status': 'applied', 'files': originals})
    report = {
        'ok': True, 'mode': 'relocate', 'applied': apply,
        'history_policy': 'preserved_read_only', 'historical_files_modified': 0,
        'configs_to_update': [{'path': name, 'replacements': count}
                              for name, _path, _text, count, _bom in plan],
        'configs_updated': changed,
        'backup': backup_relative,
        'historical_references': history,
        'history_scan_scope': {'databases': list(HISTORY_DATABASES),
                               'json_roots': list(HISTORY_JSON_ROOTS),
                               'complete_workspace_scan': False},
        'skipped': skipped,
        'next_step': 'Keep frozen history unchanged; prepare a new local request/revision and review it before resuming production.',
    }
    if apply:
        report_path = safe(root, REPORT_ROOT + '/relocation.json')
        atomic_json(report_path, report)
        report['report_path'] = str(standard_path(report_path))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify', help='Verify required record hashes; does not attest agent reading.')
    commands.add_parser('doctor', help='Read-only environment and mapped path check; no installs or services.')
    hydration = commands.add_parser('hydrate', help='Recreate ZIP-deduplicated files as independent copies.')
    hydration.add_argument('--dry-run', action='store_true', help='Verify duplicates and report needed space without copying.')
    move = commands.add_parser('relocate', help='Inspect approved defaults and report historical references.')
    move.add_argument('--apply', action='store_true', help='Back up and update only manifest-approved defaults.')
    arguments = parser.parse_args(argv)
    try:
        root = filesystem_path(arguments.root)
        safe(root, '.', allow_root=True)
        root = root.resolve(strict=True)
        manifest = load_manifest(root)
        if arguments.command == 'verify':
            result = verify(root, manifest)
        elif arguments.command == 'doctor':
            result = doctor(root, manifest)
        elif arguments.command == 'hydrate':
            result = hydrate(root, dry_run=arguments.dry_run)
        else:
            result = relocate(root, manifest, apply=arguments.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] else 1
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__, 'error': str(error)},
                         ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
