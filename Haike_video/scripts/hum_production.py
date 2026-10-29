"""Freeze and render a reusable speech-clock motion video through Backlot."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backlot import studio_hum_production as adapter
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import read_json, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="New local JSON with title, props/shotPlan, sources, audio and provenance")
    group.add_argument("--request", type=Path, help="Resume the same immutable request without regenerating upstream voice/avatar")
    parser.add_argument("--check", action="store_true", help="Read-only full validation; no freeze, submission, cloud call or rendering")
    parser.add_argument("--freeze-only", action="store_true", help="Freeze a valid request without submitting it")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    queue = ProductionQueue(ROOT / ".backlot/production-queue.sqlite3", ROOT / "projects")
    if args.input:
        value = read_json(args.input)
        if args.check:
            checked = adapter.preflight(value)
            print(json.dumps({"valid": True, "durationFrames": checked["props"]["durationFrames"], "durationSeconds": checked["props"]["durationFrames"] / adapter.FPS,
                              "voiceClock": checked["audio"]["voice_clock"], "sourceFiles": len(checked["paths"]), "cloud_calls": 0}, ensure_ascii=False))
            return
        request = adapter.prepare(queue, value)
    else:
        request = read_json(args.request)
    project = adapter.validate(queue, request)
    request_path = project / "artifacts" / adapter.REQUEST_FILE
    print(json.dumps({"request": str(request_path), "project_id": request["project_id"], "durationFrames": request["props"]["durationFrames"], "valid": True}, ensure_ascii=False), flush=True)
    if args.check or args.freeze_only:
        return
    job = adapter.submit(queue, request)
    if job["status"] != "completed":
        job = ProductionQueueWorker(queue, queue.projects_root, worker_id="hum-production-cli", lease_seconds=7200).run_local_recompose(job["job_id"])
    if job["status"] != "completed":
        print(json.dumps({"job_id": job["job_id"], "status": job["status"], "request": str(request_path), "error": job.get("error"),
                          "resume": "python scripts/hum_production.py --request <request>"}, ensure_ascii=False), flush=True)
        raise RuntimeError("生产队列尚未完成；保留原请求恢复，不重新调用配音或数字人服务")
    source = project / "renders" / request["render_id"] / adapter.OUTPUT_FILE
    defaults = read_json(ROOT.parent / ".local/store-manager/defaults.json")
    destination = args.output_dir or (Path(defaults["output_dir"]) if defaults.get("output_dir") else source.parent)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (request["render_id"] + ".mp4")
    if target.exists() and sha(target) != sha(source):
        raise RuntimeError("目标文件已存在且内容不同，拒绝覆盖")
    if not target.exists():
        shutil.copy2(source, target)
    if sha(target) != sha(source):
        raise RuntimeError("交付副本SHA校验失败")
    delivery = {"output": str(target), "source": str(source), "sha256": sha(target), "job_id": job["job_id"], "work_id": job["result"].get("work_id"),
                "version_id": job["result"].get("version_id"), "request": str(request_path), "cloud_calls": 0, "published": False}
    alternative = source.parent / adapter.NOMUSIC_FILE
    if alternative.is_file():
        alternative_target = destination / (request['render_id'] + '-nomusic.mp4')
        if alternative_target.exists() and sha(alternative_target) != sha(alternative):
            raise RuntimeError('无配乐备选目标已有不同内容，拒绝覆盖')
        if not alternative_target.exists():
            shutil.copy2(alternative, alternative_target)
        if sha(alternative_target) != sha(alternative):
            raise RuntimeError('无配乐备选交付副本SHA校验失败')
        delivery.update(nomusic_output=str(alternative_target), nomusic_sha256=sha(alternative_target), nomusic_wav=str(source.parent / 'nomusic.wav'))
    atomic_private(source.parent / "delivery.json", delivery)
    print(json.dumps(delivery, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
