"""Reproduce a frozen store-manager film through the native queue and archive it."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.work_catalog import read_json, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--fresh', action='store_true', help='Freeze current runtime and the same original inputs for a new local render')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    r = read_json(args.request)
    if r.get('contract') == 'store-opening-v1':
        from backlot import studio_store_opening as adapter
    elif r.get('contract') == 'store-footage-contrast-v1':
        from backlot import studio_store_footage as adapter
    elif r.get('contract') == 'store-manager-lab-v1':
        from backlot import studio_store_manager_lab as adapter
    elif r.get('contract') == 'store-manager-contrast-v1':
        from backlot import studio_store_manager as adapter
    else:
        parser.error('Unsupported store-manager request contract')
    q = ProductionQueue(ROOT / '.backlot/production-queue.sqlite3', projects_root=ROOT / 'projects')
    # A new opening-contract render may re-freeze unchanged source assets with
    # the current implementation; all source and request checks still run.
    project = (adapter.validate(q, r, check_runtime=False)
               if args.fresh and r.get('contract') == 'store-opening-v1'
               else adapter.validate(q, r))
    if args.check:
        print(json.dumps({'valid': True, 'project_id': r['project_id'], 'style': r['props']['style'], 'source_count': len(r['origins'])}))
        return
    if args.fresh:
        sources = {name: project / 'assets/store-manager' / name for name in r['origins']}
        r = adapter.prepare(q, r['props'], sources, r['title'])
    job = adapter.submit(q, r)
    if job['status'] != 'completed':
        job = ProductionQueueWorker(q, ROOT / 'projects', worker_id='store-manager-template-cli', lease_seconds=7200).run_local_recompose(job['job_id'])
    if job['status'] != 'completed':
        raise RuntimeError(json.dumps(job.get('error') or {'status': job['status']}, ensure_ascii=False))
    project = adapter.validate(q, r)
    source = project / 'renders' / r['render_id'] / 'avatar-preview.mp4'
    quality = read_json(source.parent / 'quality.json')
    if int(quality['video_stream'].get('bit_rate', 0)) < 20000000:
        raise RuntimeError('Measured video bitrate is below 20 Mbps')
    defaults = read_json(ROOT.parent / '.local/store-manager/defaults.json')
    destination = args.output_dir or (Path(defaults['output_dir']) if defaults.get('output_dir') else None)
    if destination is None:
        raise RuntimeError('Set --output-dir or local store-manager defaults.json')
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (r['render_id'] + '.mp4')
    if target.exists() and sha(target) != sha(source):
        raise RuntimeError('Refusing to overwrite a different existing film')
    if not target.exists():
        shutil.copy2(source, target)
    assert sha(target) == sha(source)
    print(json.dumps({'output': str(target), 'sha256': sha(target), 'video_bitrate': quality['video_stream']['bit_rate'], 'cloud_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
