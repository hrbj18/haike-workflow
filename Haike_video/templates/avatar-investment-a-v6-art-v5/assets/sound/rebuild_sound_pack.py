#!/usr/bin/env python3
"""Portable local entry point for the unchanged Template 6 original sound DSP.

Requires an explicit output directory. Optional canonical installation verifies
all seven registered SHA256 values before writing any ignored local WAV.
No provider, download, narration, render, queue, quality or publication action.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

CANONICAL_IDS = {'main-118', 'red-124', 'documentary-100', 'dong', 'impact', 'whoosh', 'tick'}
SOURCE_SHA256 = 'e2477be1613aa6b6095ca2c10e7bd4305cab14df31f747582b685fd3a9354ee4'

def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): result.update(block)
    return result.hexdigest()

def project_root():
    """Locate repository/package by a stable existing module, not task depth."""
    for parent in Path(__file__).resolve().parents:
        if (parent / 'Haike_video/lib/ffmpeg_locator.py').is_file(): return parent
    raise RuntimeError('需在完整Haike Workflow源码或便携包内运行此入口，未找到Haike_video/lib/ffmpeg_locator.py')

def canonical_sources(output):
    return {**{theme: output / 'music' / theme / 'master.wav' for theme in ('main-118', 'red-124', 'documentary-100')}, **{role: output / 'sfx' / (role + '.wav') for role in ('dong', 'impact', 'whoosh', 'tick')}}

def verify_and_install(output, sound_dir, provenance, install):
    expected = {a['id']: a for a in provenance['assets']}
    if set(expected) != CANONICAL_IDS: raise RuntimeError('来源清单必须恰有七个已登记canonical声音')
    sources, observed, missing = canonical_sources(output), [], []
    for ident in sorted(CANONICAL_IDS):
        source, registered = sources[ident], expected[ident]
        destination = sound_dir / registered['relative_path']
        if destination.parent.resolve() != sound_dir.resolve() or destination.suffix.lower() != '.wav': raise RuntimeError('canonical安装目标必须是sound目录直属WAV')
        if not source.is_file():
            missing.append(ident); continue
        digest = sha(source)
        observed.append({'id': ident, 'source': str(source), 'sha256': digest, 'expected_sha256': registered['sha256'], 'match': digest == registered['sha256'], 'destination': str(destination)})
    mismatch = [a['id'] for a in observed if not a['match']]
    if install:
        if missing or mismatch: raise RuntimeError('七文件SHA门槛未通过，不安装。missing=' + ','.join(missing) + '; mismatch=' + ','.join(mismatch))
        # Check all destinations before any mutation; preserve unknown local WAVs.
        for row in observed:
            destination = Path(row['destination'])
            if destination.exists() and sha(destination) != row['expected_sha256']: raise RuntimeError('保留已有不同canonical文件，不覆盖：' + str(destination))
        for row in observed:
            destination = Path(row['destination'])
            if not destination.exists():
                temporary = destination.with_name(destination.name + '.rebuild-tmp')
                shutil.copy2(row['source'], temporary)
                if sha(temporary) != row['expected_sha256']: raise RuntimeError('安装临时副本SHA不符')
                temporary.replace(destination)
            if sha(destination) != row['expected_sha256']: raise RuntimeError('安装后canonical SHA不符')
    return observed, missing, mismatch

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='必填绝对本地目录；不得写模板源码目录')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--theme', choices=['main-118', 'red-124', 'documentary-100'])
    modes.add_argument('--sfx-only', action='store_true')
    parser.add_argument('--install-canonical', action='store_true', help='先核对全部七个既定SHA，再安装ignored WAV；未知SHA不装')
    args = parser.parse_args(argv)
    root = project_root()
    if not args.output_dir.is_absolute(): raise RuntimeError('--output-dir需绝对本地路径')
    output = args.output_dir.resolve()
    templates = (root / 'Haike_video/templates').resolve()
    if output.is_relative_to(templates) or output in {root.resolve(), (root / 'Haike_video').resolve()}: raise RuntimeError('输出不能覆盖模板源码或项目根目录；请使用显式忽略目录或外部本地目录')
    if output.exists() and not output.is_dir(): raise RuntimeError('输出路径不是目录')
    sound_dir = templates / 'avatar-investment-a-v6-art-v5/assets/sound'
    provenance_path = sound_dir / 'PROVENANCE.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8-sig'))
    source = Path(__file__).resolve().with_name('generate_sound_pack.py')
    if sha(source) != SOURCE_SHA256 or provenance.get('generator_sha256') != SOURCE_SHA256: raise RuntimeError('原始DSP脚本SHA已变化，不静默改造本期声音')
    sys.path.insert(0, str(root / 'Haike_video'))
    module_spec = importlib.util.spec_from_file_location('template6_unchanged_sound_dsp', source)
    generator = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(generator)
    generator.ROOT, generator.OUT = root, output
    forwarded = [str(source)]
    if args.theme: forwarded += ['--theme', args.theme]
    if args.sfx_only: forwarded += ['--sfx-only']
    prior_args = sys.argv
    try:
        sys.argv = forwarded
        generator.main()
    finally:
        sys.argv = prior_args
    observed, missing, mismatch = verify_and_install(output, sound_dir, provenance, args.install_canonical)
    receipt = {'schema': 'haike.template6_sound_rebuild.v1', 'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'pass_for_generated_registered_assets' if not mismatch else 'hash_mismatch_preserved_not_installed', 'project_root': str(root), 'generator': str(source), 'generator_sha256': sha(source), 'wrapper_sha256': sha(Path(__file__)), 'provenance': str(provenance_path), 'provenance_sha256': sha(provenance_path), 'output_dir': str(output), 'theme': args.theme, 'sfx_only': args.sfx_only, 'seed': generator.SEED, 'canonical_observations': observed, 'canonical_not_generated_in_this_directory': missing, 'canonical_installed_or_same_hash_present': args.install_canonical, 'cloud_calls': 0, 'downloads': 0, 'voice_or_video_inputs': [], 'scope': 'Only this machine and generated assets; not cross-machine bit-exact reproduction, subjective listening, whole-video QA, approval or publication.'}
    (output / 'rebuild-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': receipt['status'], 'canonical_matches': len(observed) - len(mismatch), 'canonical_missing': missing, 'canonical_mismatch': mismatch, 'installed': args.install_canonical, 'receipt': str(output / 'rebuild-receipt.json')}, ensure_ascii=False))
    return 2 if mismatch else 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(json.dumps({'ok': False, 'error': str(error), 'preserved': '原始DSP、来源JSON、已有canonical与所有人物/视频/队列状态'}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from None
