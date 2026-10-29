"""One narration, one paid mouth-sync task, admitted by the production queue.

Remote task IDs survive restarts. A lost submit response is ambiguous and must
never cause another submission. Local download/import retries reuse that task.
"""
import hashlib
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
COINS_PER_CNY = 380.0
MAX_COINS_PER_SECOND = 0.4
CONSUMER_KEY_SOURCE = "RUNNINGHUB_CONSUMER_API_KEY"
CONSUMER_QUEUE_KIND = "commentary_presenter_consumer_v1"
POLL_SECONDS = 10


class PresenterOutputError(CommentaryError):
    """A settled cloud output needs a new human decision, not another payment."""


def directory(project, generation_id):
    identifier(generation_id, "PG-")
    return Path(project) / "artifacts/commentary/presenter-jobs" / generation_id[:27]


def _billing_contract(payload):
    mode = payload.get("billing_mode", "cny")
    if mode not in {"cny", "rh_coins"}:
        raise CommentaryError("数字人计费方式须为 cny 或 rh_coins")
    if mode == "cny":
        return {"billing_mode": mode, "credential_source": "RUNNINGHUB_API_KEY"}
    for field, expected in (("coins_per_cny", COINS_PER_CNY), ("max_coins_per_second", MAX_COINS_PER_SECOND)):
        if field in payload and payload[field] != expected:
            raise CommentaryError("本次 RH 币合同固定为 380 币/元、最高 0.4 币/秒")
    return {"billing_mode": mode, "credential_source": CONSUMER_KEY_SOURCE,
        "credential_storage": ".env.secrets.local", "coins_per_cny": COINS_PER_CNY,
        "max_coins_per_second": MAX_COINS_PER_SECOND}


def _consumer_api_key():
    from backlot.ai_text import _read_env_file, _secrets_path
    _, values = _read_env_file(_secrets_path())
    key = str(values.get(CONSUMER_KEY_SOURCE) or "").strip()
    if not key:
        raise CommentaryError("请先在本地 .env.secrets.local 配置独立 RUNNINGHUB_CONSUMER_API_KEY；不会回退共享密钥")
    return key


def _credential_provenance(request, ledger):
    """Submission evidence is distinct from the key requested for recovery."""
    requested = _billing_contract(request)
    snapshot = ledger.get("credential_snapshot") or {}
    fingerprint = str(snapshot.get("key_sha256") or "")
    valid_snapshot = snapshot.get("contract_version") == 1 and snapshot.get("source") in {
        "RUNNINGHUB_API_KEY", CONSUMER_KEY_SOURCE} and len(fingerprint) == 64 and all(c in "0123456789abcdef" for c in fingerprint)
    audit = ledger.get("credential_audit") or {}
    audited_source = audit.get("actual_source")
    valid_audit = audited_source in {"RUNNINGHUB_API_KEY", CONSUMER_KEY_SOURCE} and bool(audit.get("evidence"))
    return {"requested_credential_source": requested["credential_source"],
        "credential_source": snapshot["source"] if valid_snapshot else audited_source if valid_audit else "unknown_legacy",
        "credential_storage": snapshot.get("storage") if valid_snapshot else None,
        "credential_evidence": "submission_snapshot" if valid_snapshot else "posthoc_audit" if valid_audit else "unknown_legacy",
        "credential_snapshot": snapshot if valid_snapshot else None}


def _submission_credential_snapshot(request, client, expected_key=None):
    contract = _billing_contract(request)
    actual_key = str(getattr(client, "api_key", "") or "")
    if contract["billing_mode"] == "rh_coins" and (not expected_key or actual_key != expected_key):
        raise CommentaryError("消费级客户端凭据与冻结来源不一致，已阻止付费提交")
    if not actual_key:
        return None
    return {"contract_version": 1, "source": contract["credential_source"],
        "storage": contract.get("credential_storage"),
        "key_sha256": hashlib.sha256(actual_key.encode("utf-8")).hexdigest(),
        "evidence": "client_key_before_submit"}


def _numeric(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _billing_result(request, ledger, result):
    """Account cumulative usage once; never add a fresh poll to the last poll."""
    from tools.avatar.runninghub_avatar import billing_evidence
    billing = result.get("billing") or billing_evidence(result.get("raw", {}))
    usage = billing.get("provider_usage") or {}
    coins = _numeric(usage.get("consume_coins"))
    if coins is None:
        coins = _numeric(result.get("consume_coins"))
    money = _numeric(usage.get("consume_money"))
    if money is None:
        money = _numeric(result.get("consume_money_cny"))
    third_party = _numeric(usage.get("third_party_consume_money"))
    seconds = _numeric(usage.get("task_cost_seconds"))
    elapsed = max(0.0, time.time() - ledger["submitted_at"], seconds or 0)
    contract = _billing_contract(request)
    summary = {**contract, "task_id": ledger.get("task_id"), "consume_coins": coins,
        "consume_money_cny": money, "third_party_consume_money_cny": third_party,
        "provider_usage": {"consume_coins": coins, "consume_money": money,
            "third_party_consume_money": third_party, "task_cost_seconds": seconds},
        "prior_cost_cny": request["prior_cost_cny"], "budget_limit_cny": request["budget_limit_cny"]}
    if contract["billing_mode"] == "cny":
        cost = money if money is not None else round(elapsed * RATE_CNY_PER_HOUR / 3600, 4)
        summary["cost_source"] = "provider" if money is not None else "conservative_elapsed_estimate"
    else:
        estimated_coins = elapsed * contract["max_coins_per_second"] if coins is None else None
        # RunningHub documents these separately: consumeMoney is compute
        # wallet spend, thirdPartyConsumeMoney is third-party API spend.
        # Both are cumulative totals, not amounts to add again on each poll.
        cash = (money or 0) + (third_party or 0)
        wallet_used = money is not None and money > 0
        cost = (coins if coins is not None else estimated_coins) / contract["coins_per_cny"] + cash
        confirmed = (coins or 0) / contract["coins_per_cny"] + cash
        estimated_cost = cost if coins is None else None
        terminal_cash_only = result.get("status") in {"SUCCEEDED", "FAILED"} and coins is None and cash > 0
        if terminal_cash_only:
            # Missing coin usage is not evidence of another payment. Keep
            # the conservative estimate separate from the confirmed bill.
            cost = confirmed
        coin_rate = coins / seconds if coins is not None and seconds else None
        plus_observed = coin_rate is not None and abs(coin_rate - MAX_COINS_PER_SECOND) <= MAX_COINS_PER_SECOND * .03
        summary.update(estimated_consume_coins=round(estimated_coins, 4) if estimated_coins is not None else None,
            confirmed_cost_cny=round(confirmed, 6),
            estimated_cost_cny=round(estimated_cost, 6) if estimated_cost is not None else None,
            coin_cost_source="provider" if coins is not None else "conservative_elapsed_estimate",
            cash_cost_cny=cash,
            requested_instance=request.get("instance_type", "plus"),
            observed_instance="plus_48gb" if plus_observed else "unverified",
            observed_coins_per_second=round(coin_rate, 6) if coin_rate is not None else None,
            instance_evidence="provider_usage_rate" if plus_observed else "provider_did_not_report_resolvable_rate",
            cash_cost_source="provider_compute_and_third_party",
            wallet_compute_spend_detected=wallet_used,
            cost_source="provider_cash_coin_usage_unreported" if terminal_cash_only else "conservative_elapsed_estimate" if coins is None else (
                "provider_coins_wallet_review_required" if wallet_used else "provider_coins"),
            billing_review_required=coins is None or wallet_used)
    summary["actual_cost_cny"] = round(cost, 6) if contract["billing_mode"] == "rh_coins" else cost
    summary["total_cost_cny"] = round(cost + request["prior_cost_cny"], 6)
    summary.update(_credential_provenance(request, ledger))
    return summary


def quote(project, payload):
    from tools.avatar.runninghub_avatar import runninghub_configuration
    from tools.tool_registry import registry
    registry.get("runninghub_longcat_avatar")  # initialize configured provider environment
    config = runninghub_configuration()
    billing = _billing_contract(payload)
    ready = config["configured"]
    if billing["billing_mode"] == "rh_coins":
        _consumer_api_key()
        # Workflow validation is shared; the shared wallet key is unnecessary
        # for this explicitly isolated consumer credential route.
        ready = ready or config.get("issues") == ["缺少 RUNNINGHUB_API_KEY"]
    if not ready or config["workflow_id"] != PRODUCTION_WORKFLOW_ID or config["workflow_profile"] != PRODUCTION_WORKFLOW_PROFILE:
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
    rate = MAX_COINS_PER_SECOND / COINS_PER_CNY if billing["billing_mode"] == "rh_coins" else RATE_CNY_PER_HOUR / 3600
    reservation = round((runtime + 120) * rate, 4)
    if prior + reservation > limit:
        raise CommentaryError("数字人预留费用与已用配音费用超过本轮预算，请缩短任务时间上限")
    frames = math.ceil(take["samples"] / RATE * 25 - 1e-8) + 1
    request = {"audio": take, "role_id": role["role_id"], "name": role["name"],
        "reference": {"path": str(reference_path), "sha256": reference["sha256"]},
        "workflow_id": config["workflow_id"], "workflow_profile": config["workflow_profile"],
        "template_sha256": config["template_sha256"], "base_url": config["base_url"],
        "exact_total_frames": frames, "instance_type": "plus", "budget_limit_cny": limit,
        "prior_cost_cny": prior, "max_runtime_seconds": runtime, "reserved_cost_cny": reservation, **billing}
    if billing["billing_mode"] == "rh_coins":
        request["reserved_coins"] = round((runtime + 120) * MAX_COINS_PER_SECOND, 4)
    # The paid identity remains media-based (including legacy CNY requests).
    # Billing changes alter the quote signature, but cannot buy the same media
    # again; an admitted request freezes its original credential and price.
    generation_id = "PG-" + digest({key: request[key] for key in
        ("audio", "role_id", "reference", "workflow_id", "workflow_profile", "template_sha256", "base_url", "exact_total_frames")})
    committed = 0.0
    for path in (Path(project)/"artifacts/commentary/presenter-jobs").glob("PG-*/request.json"):
        previous = read_json(path)
        if previous["generation_id"] == generation_id:
            if _billing_contract(previous) != billing:
                raise CommentaryConflict("同一数字人输入已有冻结任务，不能切换计费方式或汇率；请查询原任务，避免重复付费")
            continue  # a retry recovers this exact operation, never reserves twice
        ledger_path = path.parent / "ledger.json"
        ledger = read_json(ledger_path) if ledger_path.is_file() else {}
        settled = ledger.get("result", {})
        actual = float(settled.get("actual_cost_cny", previous["reserved_cost_cny"]))
        unresolved_coins = previous.get("billing_mode") == "rh_coins" and settled.get("consume_coins") is None and settled.get("billing_review_required") is True
        # A running task's cumulative usage is not its final bill. Retain its
        # reservation until terminal billing is resolved, including missing
        # coin evidence. A confirmed cash charge alone cannot release it.
        committed += actual if ledger.get("status") in {"generated", "completed", "failed"} and not unresolved_coins else max(
            actual, previous["reserved_cost_cny"], _numeric(settled.get("estimated_cost_cny")) or 0)
    if committed + prior + reservation > limit:
        raise CommentaryError("本项目其他数字人任务的已用或预留费用计入后超过本轮预算")
    if committed:
        request["other_avatar_commitments_cny"] = round(committed, 4)
    note = "Plus 48GB 按运行秒数计费，6元/小时；预留不是账单，超时请求取消，不自动补发。"
    if billing["billing_mode"] == "rh_coins":
        note = "独立消费级密钥来源不等于 RH 币结算证明，扣币或扣钱包须以实际账单核验。按最高0.4币/秒、380币/元预留；实际机型以平台调度为准。预留不是账单，人民币费用单列，超时请求取消，不自动补发。"
    return {**request, "generation_id": generation_id, "signature": digest(request), "billing_note": note}


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
    identity = f"commentary_presenter:{Path(project).name}:{request['generation_id']}"
    kind = CONSUMER_QUEUE_KIND if request.get("billing_mode") == "rh_coins" else "commentary_presenter"
    existing = queue.find_by_idempotency_key(identity)
    if existing is not None and existing["kind"] != kind:
        # Keep the original paid identity and status. A new queue protocol is
        # not permission to migrate/revive an old job or pay for it again.
        return existing
    return queue.submit(project_id=Path(project).name, kind=kind, source="workbench", priority="normal",
        parent_job_id=request["generation_id"], frozen_request={"generation_id": request["generation_id"]},
        idempotency_key=identity, revive=True)


def inspect(project, generation_id):
    target = directory(project, generation_id)
    path = target / "ledger.json"
    if not path.is_file():
        return {"status": "queued", "stage": "等待生成一次出镜素材", "retryable": True}
    ledger = read_json(path)
    status = ledger["status"]
    details = {**ledger.get("result", {}), "task_id": ledger.get("task_id"),
        "reserved_cost_cny": ledger.get("reserved_cost_cny")}
    request_path = target / "request.json"
    if request_path.is_file():
        request = read_json(request_path)
        details.update(_billing_contract(request))
        details.update(_credential_provenance(request, ledger))
        if request.get("billing_mode") == "rh_coins" and status in {"submitting", "submitted", "ambiguous", "cancelling"}:
            details.update(_billing_result(request, ledger, {"billing": {
                "provider_usage": details.get("provider_usage", {})}}))
    if status == "completed":
        presenter.read(project, ledger["result"]["asset_id"])
        return {"status": "completed", "stage": "出镜素材已登记，可按段落启用", "result": details}
    if status in {"submitting", "ambiguous", "cancelling"}:
        return {"status": "ambiguous", "stage": "云端结果需核对，不自动重复付费", "retryable": False,
            "result": details}
    if status == "failed":
        return {"status": "failed", "stage": "出镜任务已终止", "error": ledger.get("error"),
            "retryable": False, "result": details}
    return {"status": "queued", "stage": "恢复同一云任务或本地导入", "retryable": True,
        "safe_resume_point": "commentary_presenter", "result": details}


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
    credential = {}
    billing = _billing_contract(request)
    if billing["billing_mode"] == "rh_coins":
        if request.get("credential_source") != CONSUMER_KEY_SOURCE or request.get("credential_storage") != ".env.secrets.local":
            raise CommentaryError("冻结的消费级密钥来源无效；不会回退共享密钥")
        credential["api_key"] = _consumer_api_key()
    client = RunningHubLongCatClient(workflow_id=request["workflow_id"], workflow_profile=request["workflow_profile"],
        base_url=request["base_url"], **credential)
    ledger_path = target / "ledger.json"
    ledger = read_json(ledger_path) if ledger_path.is_file() else None
    if ledger is None:
        _submission_credential_snapshot(request, client, credential.get("api_key"))
        driver = target / "driver.wav"
        samples = request["exact_total_frames"] * (RATE // 25)
        media_run([media_tools()[0], "-v", "error", "-nostdin", "-y", "-i", take["path"], "-ac", "1", "-ar", RATE,
            "-af", f"apad,atrim=end_sample={samples},asetpts=N/SR/TB", "-c:a", "pcm_s16le", driver])
        # Uploads are reversible/non-billed. Claim the paid boundary exclusively
        # only once both uploads have returned.
        image_remote = client.upload_file(Path(request["reference"]["path"]), file_type="image")
        audio_remote = client.upload_file(driver, file_type="audio")
        snapshot = _submission_credential_snapshot(request, client, credential.get("api_key"))
        ledger = {"status": "submitting", "reserved_cost_cny": request["reserved_cost_cny"], **billing,
            "credential_snapshot": snapshot,
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
                    ledger["result"] = _billing_result(request, ledger, result)
                    atomic(ledger_path, ledger)
                    return inspect(project, generation_id)
            else:
                result = client.poll(ledger["task_id"])
            if result["status"] in {"SUCCEEDED", "FAILED"}:
                ledger.update(status="generated" if result["status"] == "SUCCEEDED" else "failed",
                    video_url=result.get("video_url"), result=_billing_result(request, ledger, result))
                if result["status"] == "FAILED":
                    ledger["error"] = {"type": "PresenterProviderFailed", "message": "供应商任务失败，请核对原任务，不自动重发"}
                atomic(ledger_path, ledger)
                break
            if billing["billing_mode"] == "rh_coins":
                ledger["result"] = _billing_result(request, ledger, result)
                atomic(ledger_path, ledger)
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
        ledger["result"]["total_cost_cny"] = round(ledger["result"]["actual_cost_cny"] + request["prior_cost_cny"], 6)
        ledger["status"] = "completed"
        atomic(ledger_path, ledger)
    return inspect(project, generation_id)
