"""One narration, one paid mouth-sync task, admitted by the production queue.

Remote task IDs survive restarts. A lost submit response is ambiguous and must
never cause another submission. Local download/import retries reuse that task.
"""
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from backlot import commentary_audio as audio, commentary_presenter as presenter
from backlot.commentary_common import (
    CommentaryConflict, CommentaryError, RATE, atomic, digest, identifier,
    immutable, media_tools, number, probe, read_json, run as media_run, verified,
)
from backlot.avatar_roles import get_avatar_role, role_front_reference, avatar_role_asset_file
from backlot.daily_pipeline import PRODUCTION_WORKFLOW_ID, PRODUCTION_WORKFLOW_PROFILE

RATE_CNY_PER_HOUR = 6.0
POLL_SECONDS = 10


class PresenterOutputError(CommentaryError):
    """A settled cloud output needs a new human decision, not another payment."""


def directory(project, generation_id):
    identifier(generation_id, "PG-")
    return Path(project) / "artifacts/commentary/presenter-jobs" / generation_id[:27]


def quote(project, payload):
    from tools.avatar.runninghub_avatar import runninghub_configuration
    from tools.tool_registry import registry
    registry.get("runninghub_longcat_avatar")  # initialize configured provider environment
    config = runninghub_configuration()
    if not config["configured"] or config["workflow_id"] != PRODUCTION_WORKFLOW_ID or config["workflow_profile"] != PRODUCTION_WORKFLOW_PROFILE:
        raise CommentaryError("RunningHub 精确帧生产路由未配置，请核对现有数字人配置")
    take = audio.read(project, payload.get("audio_id"))
    if take["kind"] != "narration":
        raise CommentaryError("数字人生成须绑定实际旁白")
    role = get_avatar_role(payload.get("role_id"))
    reference = role_front_reference(role)
    reference_path = avatar_role_asset_file(role["role_id"], reference["path"])
    verified(reference_path, reference["sha256"])
    limit = number(payload.get("budget_limit_cny"), "累计费用上限（元）", .1, 5)
    prior = number(payload.get("prior_cost_cny"), "本轮已用或预留配音费用（元）", 0, limit)
    runtime = number(payload.get("max_runtime_seconds", 900), "单次云任务时间上限", 120, 1800)
    # Reserve for all wall time since submission, including queueing, plus a
    # two-minute cancellation/network margin. No warm-instance retention.
    reservation = round((runtime + 120)*RATE_CNY_PER_HOUR/3600, 4)
    if prior + reservation > limit:
        raise CommentaryError("数字人预留费用与已用配音费用超过本轮预算，请缩短任务时间上限")
    frames = math.ceil(take["samples"] / RATE * 25 - 1e-8) + 1
    request = {"audio": take, "role_id": role["role_id"], "name": role["name"],
        "reference": {"path": str(reference_path), "sha256": reference["sha256"]},
        "workflow_id": config["workflow_id"], "workflow_profile": config["workflow_profile"],
        "template_sha256": config["template_sha256"], "base_url": config["base_url"],
        "exact_total_frames": frames, "instance_type": "plus", "budget_limit_cny": limit,
        "prior_cost_cny": prior, "max_runtime_seconds": runtime, "reserved_cost_cny": reservation}
    generation_id = "PG-" + digest({key: request[key] for key in
        ("audio", "role_id", "reference", "workflow_id", "workflow_profile", "template_sha256", "base_url", "exact_total_frames")})
    committed = 0.0
    for path in (Path(project)/"artifacts/commentary/presenter-jobs").glob("PG-*/request.json"):
        previous = read_json(path)
        if previous["generation_id"] == generation_id:
            continue  # a retry recovers this exact operation, never reserves twice
        ledger_path = path.parent / "ledger.json"
        ledger = read_json(ledger_path) if ledger_path.is_file() else {}
        committed += float(ledger.get("result", {}).get("actual_cost_cny", previous["reserved_cost_cny"]))
    if committed + prior + reservation > limit:
        raise CommentaryError("本项目其他数字人任务的已用或预留费用计入后超过本轮预算")
    if committed:
        request["other_avatar_commitments_cny"] = round(committed, 4)
    return {**request, "generation_id": generation_id, "signature": digest(request),
        "billing_note": "Plus 48GB 按运行秒数计费，6元/小时；预留不是账单，超时请求取消，不自动补发。"}


def submit(project, payload, queue):
    root = Path(project)/"artifacts/commentary/presenter-jobs"
    root.mkdir(parents=True, exist_ok=True)
    # Serialize budget admission across browser, CLI and other local processes.
    # The long cloud job runs outside this short lock.
    with sqlite3.connect(root/"admission.sqlite3", timeout=10) as admission:
        admission.execute("BEGIN IMMEDIATE")
        return _submit(project, payload, queue)


def _submit(project, payload, queue):
    request = quote(project, payload)
    if payload.get("confirmed") is not True or payload.get("quote_signature") != request["signature"]:
        raise CommentaryConflict("请核对本次角色、实际配音和累计预算后确认生成")
    target = directory(project, request["generation_id"])
    target.mkdir(parents=True, exist_ok=True)
    path = target / "request.json"
    # A budget edit never creates a second generation for identical media.
    if path.is_file():
        request = read_json(path)
    else:
        immutable(path, request)
    return queue.submit(project_id=Path(project).name, kind="commentary_presenter", source="workbench", priority="normal",
        parent_job_id=request["generation_id"], frozen_request={"generation_id": request["generation_id"]},
        idempotency_key=f"commentary_presenter:{Path(project).name}:{request['generation_id']}", revive=True)


def inspect(project, generation_id):
    target = directory(project, generation_id)
    path = target / "ledger.json"
    if not path.is_file():
        return {"status": "queued", "stage": "等待生成一次出镜素材", "retryable": True}
    ledger = read_json(path)
    status = ledger["status"]
    if status == "completed":
        presenter.read(project, ledger["result"]["asset_id"])
        return {"status": "completed", "stage": "出镜素材已登记，可按段落启用", "result": ledger["result"]}
    if status in {"submitting", "ambiguous", "cancelling"}:
        return {"status": "ambiguous", "stage": "云端结果需核对，不自动重复付费", "retryable": False,
            "result": {"task_id": ledger.get("task_id"), "reserved_cost_cny": ledger.get("reserved_cost_cny")}}
    if status == "failed":
        return {"status": "failed", "stage": "出镜任务已终止", "error": ledger.get("error"),
            "retryable": False, "result": ledger.get("result", {})}
    return {"status": "queued", "stage": "恢复同一云任务或本地导入", "retryable": True,
        "safe_resume_point": "commentary_presenter", "result": {"task_id": ledger.get("task_id")}}


def run(project, generation_id):
    try:
        return _run(Path(project), generation_id)
    except Exception as exc:
        # Do not persist provider exception bodies: some SDK errors include
        # request credentials. The queue receives a safe, recoverable contract.
        if isinstance(exc, PresenterOutputError):
            path = directory(project, generation_id) / "ledger.json"
            ledger = read_json(path)
            ledger.update(status="failed", error={"type": "PresenterOutputError", "message": str(exc)})
            atomic(path, ledger)
        state = inspect(project, generation_id)
        if state["status"] == "queued":
            return {"status": "failed", "stage": "云任务查询或本地导入中断，重试复用原任务",
                "retryable": True, "safe_resume_point": "commentary_presenter",
                "error": {"type": "PresenterInterrupted", "message": "已保留原任务和账本，请从安全点恢复"}}
        return state


def _run(project, generation_id):
    from tools.avatar.runninghub_avatar import RunningHubLongCatClient, runninghub_configuration
    target = directory(project, generation_id)
    request = read_json(target / "request.json")
    existing = inspect(project, generation_id)
    if existing["status"] in {"completed", "ambiguous", "failed"}:
        return existing
    config = runninghub_configuration()
    for key in ("workflow_id", "workflow_profile", "template_sha256", "base_url"):
        if config[key] != request[key]:
            raise CommentaryError("数字人配置已变化，请恢复冻结路由后继续")
    take = request["audio"]
    verified(take["path"], take["sha256"])
    verified(request["reference"]["path"], request["reference"]["sha256"])
    client = RunningHubLongCatClient(workflow_id=request["workflow_id"], workflow_profile=request["workflow_profile"], base_url=request["base_url"])
    ledger_path = target / "ledger.json"
    ledger = read_json(ledger_path) if ledger_path.is_file() else None
    if ledger is None:
        driver = target / "driver.wav"
        samples = request["exact_total_frames"] * (RATE // 25)
        media_run([media_tools()[0], "-v", "error", "-nostdin", "-y", "-i", take["path"], "-ac", "1", "-ar", RATE,
            "-af", f"apad,atrim=end_sample={samples},asetpts=N/SR/TB", "-c:a", "pcm_s16le", driver])
        # Uploads are reversible/non-billed. Claim the paid boundary exclusively
        # only once both uploads have returned.
        image_remote = client.upload_file(Path(request["reference"]["path"]), file_type="image")
        audio_remote = client.upload_file(driver, file_type="audio")
        ledger = {"status": "submitting", "reserved_cost_cny": request["reserved_cost_cny"],
            "submitted_at": datetime.now(timezone.utc).timestamp()}
        import json
        try:
            with ledger_path.open("x", encoding="utf-8") as stream:
                json.dump(ledger, stream)
        except FileExistsError:
            return inspect(project, generation_id)
        try:
            response = client.submit(presenter_filename=image_remote, audio_filename=audio_remote,
                instance_type="plus", exact_total_frames=request["exact_total_frames"])
            ledger.update(status="submitted", task_id=response["task_id"])
            atomic(ledger_path, ledger)
        except Exception:
            ledger["status"] = "ambiguous"
            atomic(ledger_path, ledger)
            return inspect(project, generation_id)
    if ledger["status"] == "submitted":
        while True:
            if time.time() - ledger["submitted_at"] >= request["max_runtime_seconds"]:
                ledger["status"] = "cancelling"; atomic(ledger_path, ledger)
                client.cancel(ledger["task_id"])
                result = client.poll(ledger["task_id"])
                if result["status"] not in {"SUCCEEDED", "FAILED"}:
                    return inspect(project, generation_id)
            else:
                result = client.poll(ledger["task_id"])
            if result["status"] in {"SUCCEEDED", "FAILED"}:
                exact = result.get("consume_money_cny")
                elapsed_cost = (time.time() - ledger["submitted_at"])*RATE_CNY_PER_HOUR/3600
                cost = float(exact) if isinstance(exact, (int, float)) else round(elapsed_cost, 4)
                ledger.update(status="generated" if result["status"] == "SUCCEEDED" else "failed",
                    video_url=result.get("video_url"), result={"task_id": ledger["task_id"], "actual_cost_cny": cost,
                        "cost_source": "provider" if isinstance(exact, (int, float)) else "conservative_elapsed_estimate",
                        "prior_cost_cny": request["prior_cost_cny"], "budget_limit_cny": request["budget_limit_cny"]})
                if result["status"] == "FAILED":
                    ledger["error"] = {"type": "PresenterProviderFailed", "message": "供应商任务失败，请核对原任务，不自动重发"}
                atomic(ledger_path, ledger)
                break
            time.sleep(POLL_SECONDS)
    if ledger["status"] == "generated":
        path = target / "presenter.mp4"
        if not path.is_file():
            client.download(ledger["video_url"], path)
        media_run([media_tools()[0], "-v", "error", "-xerror", "-nostdin", "-i", path, "-f", "null", "-"])
        info = probe(path)
        stream = next(s for s in info["streams"] if s.get("codec_type") == "video")
        output_frames = int(stream.get("nb_frames", 0))
        missing = request["exact_total_frames"] - output_frames
        if stream.get("r_frame_rate") != "25/1" or not 0 <= missing <= 5:
            raise PresenterOutputError("供应商出镜结果与精确帧时钟不一致，保留原任务供核对")
        if missing:
            import wave
            with wave.open(str(target / "driver.wav"), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != RATE or wav.getnframes() != request["exact_total_frames"]*(RATE//25):
                    raise PresenterOutputError("驱动音轨时钟已变化，无法核对出镜尾帧")
                wav.setpos(output_frames*(RATE//25))
                if any(wav.readframes(missing*(RATE//25))):
                    raise PresenterOutputError("缺失出镜尾帧包含非零语音，禁止补帧或截掉语音")
        # Retain the exact downloaded video. Only unused digital-silence tail
        # may be omitted; segment freeze still requires complete local coverage.
        ledger["result"].update(output_frames=output_frames, requested_frames=request["exact_total_frames"],
            omitted_silent_frames=missing)
        asset = presenter.import_presenter(project, {"path": str(path), "audio_id": take["id"], "name": request["name"],
            "provenance": f"RunningHub {request['workflow_profile']}，原任务 {ledger['task_id']}，使用本音轨驱动"})
        ledger["result"]["asset_id"] = asset["id"]
        ledger["result"]["total_cost_cny"] = ledger["result"]["actual_cost_cny"] + request["prior_cost_cny"]
        ledger["status"] = "completed"
        atomic(ledger_path, ledger)
    return inspect(project, generation_id)
