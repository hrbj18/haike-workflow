"""Freeze, reproduce and deliver editable speech-free store films via the queue."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import studio_store_motion_showcase as adapter
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.work_catalog import read_json, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=Path, help='Local JSON: title, props, sources; freezes a new request')
    group.add_argument('--request', type=Path, help='Existing immutable request')
    parser.add_argument('--check', action='store_true', help='Validate without submitting/rendering')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    queue = ProductionQueue(ROOT / '.backlot/production-queue.sqlite3', ROOT / 'projects')
    if args.input:
        value = read_json(args.input)
        if args.check:
            adapter.validate_props(value['props'])
            print(json.dumps({'props_valid': True, 'note': 'Full source/receipt validation occurs during freeze'}, ensure_ascii=False))
            return
        request = adapter.prepare(queue, value['props'], value['sources'], value['title'])
    else:
        request = read_json(args.request)
    project = adapter.validate(queue, request)
    request_path = project / 'artifacts/store-motion-request.json'
    print(json.dumps({'request': str(request_path), 'project_id': request['project_id'], 'valid': True}, ensure_ascii=False), flush=True)
    if args.check:
        return
    job = adapter.submit(queue, request)
    if job['status'] != 'completed':
        job = ProductionQueueWorker(queue, queue.projects_root, worker_id='store-motion-showcase-cli', lease_seconds=7200).run_local_recompose(job['job_id'])
    if job['status'] != 'completed':
        raise RuntimeError(json.dumps(job.get('error') or {'status': job['status']}, ensure_ascii=False))
    # Public queue results redact local paths. Resolve the verified artifact
    # from its frozen project instead of treating that display value as a path.
    source = project / 'renders' / request['render_id'] / 'showcase.mp4'
    defaults = read_json(ROOT.parent / '.local/store-manager/defaults.json')
    destination = args.output_dir or (Path(defaults['output_dir']) if defaults.get('output_dir') else source.parent)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (request['render_id'] + '.mp4')
    if target.exists() and sha(target) != sha(source):
        raise RuntimeError('Refusing to overwrite a different existing film')
    if not target.exists():
        shutil.copy2(source, target)
    assert sha(target) == sha(source)
    delivery = {'output': str(target), 'source': str(source), 'sha256': sha(target), 'job_id': job['job_id'],
                'work_id': job['result'].get('work_id'), 'version_id': job['result'].get('version_id'), 'request': str(request_path), 'cloud_calls': 0, 'published': False}
    from backlot.studio import atomic_private
    atomic_private(source.parent / 'delivery.json', delivery)
    print(json.dumps(delivery, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
