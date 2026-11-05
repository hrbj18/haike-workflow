"""Apply an explicitly supplied local colleague profile; never fetch or print keys.

Public source contains this importer, not its optional private-profile payload.
It does not transfer browser sessions, queued jobs or billing databases.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def profile_files(root):
    directory = Path(root).resolve() / 'private-profile'
    if not directory.exists():
        return None
    manifest = directory / 'PROFILE-MANIFEST.json'
    value = json.loads(manifest.read_text(encoding='utf-8-sig'))
    if value.get('schema') != 'haike.private-colleague-profile/1' or not isinstance(value.get('files'), list):
        raise ValueError('私有配置清单无效')
    seen = set()
    for row in value['files']:
        name = row.get('path')
        if not isinstance(name, str) or '\\' in name or ':' in name or name in seen:
            raise ValueError('私有配置文件路径无效或重复')
        path = directory / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('私有配置路径越界')
        if not path.is_file() or path.stat().st_size != row['size']:
            raise ValueError('私有配置文件缺失或大小改变')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                raise ValueError('私有配置文件校验失败')
        seen.add(name)
    if 'config.private.md' not in seen:
        raise ValueError('缺少私有配置导入文档')
    return directory


def install(root, python, env=None):
    root = Path(root).resolve()
    directory = profile_files(root)
    if directory is None:
        return {'profile_present': False, 'paid_calls': 0}
    command = [str(python), '-s', str(root / 'scripts/install-private-profile.py'), '--root', str(root), '--worker']
    result = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=180)
    if result.returncode:
        # Provider/configuration payloads must never escape through subprocess errors.
        raise ValueError('私有配置导入失败；请在本机检查 private-profile 清单、音色或形象文件')
    value = json.loads(result.stdout)
    print(json.dumps(value, ensure_ascii=False))
    return value


def worker(root):
    root = Path(root).resolve()
    directory = profile_files(root)
    spec = importlib.util.spec_from_file_location('haike_profile_configuration', root / 'scripts/configure-user.py')
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    config.ROOT = root
    data = config.read_document(directory / 'config.private.md')
    plan = config.prepare(root, data, directory)
    config.apply(plan)
    sys.path.insert(0, str(root / 'Haike_video'))
    with config.offline_environment(plan['environment']):
        from backlot.studio_audio_internal import InternalAudioCenter, LegacyAudioBackend
        audio_dir = root / config.AUDIO_PATH
        backend = LegacyAudioBackend(audio_dir)
        backend.center.read_audio_center = lambda: {}
        center = InternalAudioCenter(SimpleNamespace(private=root / 'Haike_video/.backlot'), backend=backend)
        assets_path = directory / 'assets.json'
        assets = json.loads(assets_path.read_text(encoding='utf8')) if assets_path.is_file() else {}
        record_path = root / 'Haike_video/.backlot/private-profile-import.json'
        old = json.loads(record_path.read_text(encoding='utf8')) if record_path.is_file() else {}
        imported = old.get('portraits', {})
        profiles = backend.catalog()
        for row in assets.get('portraits', []):
            path = directory / row['path']
            if not path.resolve().is_relative_to(directory) or path.is_symlink():
                raise ValueError('人物图路径越界')
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            file_id = imported.get(checksum)
            if not file_id:
                file_id = center.upload(content, 'image', path.name)['id']
                imported[checksum] = file_id
            alias = row.get('voice_alias')
            voice = next((v for v in data.get('voices', []) if v['alias'] == alias), None) if alias else None
            if voice:
                matches = [p for p in profiles if p.get('provider_id') == voice['provider'] and p.get('provider_voice_id') == voice['voice_id']]
                if len(matches) == 1 and not center._preferences().get('voices', {}).get(matches[0]['id'], {}).get('image_file_id'):
                    center.preferences({'image_file_id': file_id}, matches[0]['id'])
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps({'schema': 1, 'portraits': imported}) + '\n', encoding='utf8')
    return {'profile_present': True, 'voice_count': len(data.get('voices', [])), 'portrait_count': len(imported),
            'keys_imported': True, 'paid_calls': 0, 'provider_execution_verified': False, 'browser_sessions_imported': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--python', type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    try:
        if args.worker:
            print(json.dumps(worker(args.root), ensure_ascii=False))
        else:
            py = args.python or args.root / ('Haike_video/.venv/Scripts/python.exe' if os.name == 'nt' else 'Haike_video/.venv/bin/python')
            install(args.root, py)
    except Exception:
        print('私有配置导入失败，原设置保留；请在本机核对文件与清单。', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
