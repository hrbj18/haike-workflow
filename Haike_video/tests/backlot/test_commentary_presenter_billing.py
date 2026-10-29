"""Consumer billing must not spend through the shared wallet or duplicate jobs."""
import json
import os
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backlot import commentary_presenter_job as jobs
from backlot.commentary_common import file_sha256
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from tools.avatar.runninghub_avatar import RunningHubLongCatClient as RealRunningHubClient


@pytest.fixture
def consumer_project(tmp_path, monkeypatch):
    from backlot import ai_text
    from tools.avatar import runninghub_avatar as provider
    from tools.tool_registry import registry

    projects = tmp_path / "projects"
    project = projects / "consumer-test"
    project.mkdir(parents=True)
    (project / "project.json").write_text('{"title":"消费级账单测试"}', encoding="utf-8")
    source = tmp_path / "source.bin"
    source.write_bytes(b"local-fixture")
    take = {"id": "AU-test", "kind": "narration", "samples": 48000,
        "path": str(source), "sha256": file_sha256(source)}
    monkeypatch.setattr(jobs.audio, "read", lambda *_: take)
    monkeypatch.setattr(jobs, "get_avatar_role", lambda _: {"role_id": "AR-test", "name": "测试角色"})
    monkeypatch.setattr(jobs, "role_front_reference", lambda _: {"path": str(source), "sha256": file_sha256(source)})
    monkeypatch.setattr(jobs, "avatar_role_asset_file", lambda *_: source)
    monkeypatch.setattr(registry, "get", lambda _: None)
    config = {"configured": True, "workflow_id": jobs.PRODUCTION_WORKFLOW_ID,
        "workflow_profile": jobs.PRODUCTION_WORKFLOW_PROFILE, "template_sha256": "test-template",
        "base_url": "https://provider.invalid", "issues": []}
    monkeypatch.setattr(provider, "runninghub_configuration", lambda: config)
    secrets = tmp_path / ".env.secrets.local"
    secrets.write_text('RUNNINGHUB_CONSUMER_API_KEY="consumer-from-file"\n', encoding="utf-8")
    monkeypatch.setattr(ai_text, "_secrets_path", lambda: secrets)
    monkeypatch.setenv("RUNNINGHUB_API_KEY", "shared-stays-unchanged")
    monkeypatch.setenv("RUNNINGHUB_CONSUMER_API_KEY", "wrong-process-consumer")
    monkeypatch.setattr(jobs, "media_run", lambda *_: None)
    monkeypatch.setattr(jobs, "media_tools", lambda: ("unused-ffmpeg", "unused-ffprobe"))
    credentials, submissions = [], []

    class Provider:
        def __init__(self, **kwargs):
            self.api_key = kwargs.get("api_key")
            credentials.append(kwargs)

        def upload_file(self, path, *, file_type):
            return file_type + ".uploaded"

        def submit(self, **kwargs):
            submissions.append(kwargs)
            return {"task_id": "one-provider-task"}

        def poll(self, task_id):
            assert task_id == "one-provider-task"
            return {"status": "FAILED", "raw": {"usage": {"consumeCoins": 38,
                "consumeMoney": 0, "thirdPartyConsumeMoney": 0, "taskCostTime": 95}}}

    monkeypatch.setattr(provider, "RunningHubLongCatClient", Provider)
    queue = ProductionQueue(tmp_path / "queue.sqlite3", projects)
    payload = {"audio_id": take["id"], "role_id": "AR-test", "billing_mode": "rh_coins",
        "budget_limit_cny": 5, "prior_cost_cny": .01, "max_runtime_seconds": 1800}
    return SimpleNamespace(project=project, projects=projects, queue=queue, payload=payload,
        secrets=secrets, credentials=credentials, submissions=submissions, config=config)


def test_consumer_queue_routes_file_key_and_preserves_bill_and_shared_key(consumer_project):
    context = consumer_project
    quote = jobs.quote(context.project, context.payload)
    assert quote["reserved_coins"] == 768
    assert quote["reserved_cost_cny"] == 2.0211
    assert quote["credential_source"] == "RUNNINGHUB_CONSUMER_API_KEY"
    assert "不等于 RH 币结算证明" in quote["billing_note"]
    assert "consumer-from-file" not in json.dumps(quote)
    confirmed = {**context.payload, "confirmed": True, "quote_signature": quote["signature"]}
    admitted = jobs.submit(context.project, confirmed, context.queue)
    assert admitted["kind"] == "commentary_presenter_consumer_v1"
    assert not context.submissions
    # Read the selected file again at execution; stale process env must not win.
    context.secrets.write_text('RUNNINGHUB_CONSUMER_API_KEY="rotated-file-key"\n', encoding="utf-8")
    outcome = ProductionQueueWorker(context.queue, context.projects).run_once()
    assert outcome["status"] == "failed"
    assert context.credentials[0]["api_key"] == "rotated-file-key"
    assert context.submissions[0]["instance_type"] == "plus"
    assert os.environ["RUNNINGHUB_API_KEY"] == "shared-stays-unchanged"
    result = jobs.inspect(context.project, quote["generation_id"])["result"]
    assert result["consume_coins"] == 38 and result["actual_cost_cny"] == .1
    assert result["total_cost_cny"] == .11
    assert result["observed_instance"] == "plus_48gb"
    assert result["observed_coins_per_second"] == .4
    assert result["provider_usage"]["consume_money"] == 0
    assert result["cost_source"] == "provider_coins"
    assert result["credential_evidence"] == "submission_snapshot"
    assert result["credential_snapshot"]["key_sha256"] == hashlib.sha256(b"rotated-file-key").hexdigest()
    assert jobs.submit(context.project, confirmed, context.queue)["job_id"] == admitted["job_id"]
    ProductionQueueWorker(context.queue, context.projects).run_once()
    assert len(context.submissions) == 1
    for path in jobs.directory(context.project, quote["generation_id"]).glob("*.json"):
        assert "rotated-file-key" not in path.read_text(encoding="utf-8")


def test_consumer_requires_local_file_key_without_shared_or_env_fallback(consumer_project):
    context = consumer_project
    context.secrets.unlink()
    with pytest.raises(jobs.CommentaryError, match="不会回退共享密钥"):
        jobs.quote(context.project, context.payload)
    assert not context.credentials and not context.submissions


def test_consumer_preflight_does_not_require_shared_wallet_key(consumer_project):
    context = consumer_project
    context.config.update(configured=False, issues=["缺少 RUNNINGHUB_API_KEY"])
    assert jobs.quote(context.project, context.payload)["billing_mode"] == "rh_coins"
    context.config["issues"].append("工作流模板不可读")
    with pytest.raises(jobs.CommentaryError, match="生产路由未配置"):
        jobs.quote(context.project, context.payload)


def test_budget_changes_keep_identity_and_billing_change_cannot_duplicate(consumer_project):
    context = consumer_project
    first = jobs.quote(context.project, context.payload)
    changed = jobs.quote(context.project, {**context.payload, "budget_limit_cny": 4})
    assert first["generation_id"] == changed["generation_id"]
    assert first["signature"] != changed["signature"]
    shared = jobs.quote(context.project, {**context.payload, "billing_mode": "cny"})
    assert shared["generation_id"] == first["generation_id"]
    assert shared["signature"] != first["signature"]
    jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": first["signature"]}, context.queue)
    with pytest.raises(jobs.CommentaryConflict, match="已有冻结任务"):
        jobs.quote(context.project, {**context.payload, "billing_mode": "cny"})
    with pytest.raises(jobs.CommentaryError, match="380"):
        jobs.quote(context.project, {**context.payload, "coins_per_cny": 400})


def test_consumer_budget_rejects_overcommit_before_provider(consumer_project):
    context = consumer_project
    with pytest.raises(jobs.CommentaryError, match="超过本轮预算"):
        jobs.quote(context.project, {**context.payload, "budget_limit_cny": 2})
    assert not context.credentials and not context.submissions


@pytest.mark.parametrize("money,third_party,expected,review", [
    (0, .2, 1.2, False), (.2, .2, 1.4, True), (.3, .2, 1.5, True),
    (None, .2, 1.2, False), (.2, None, 1.2, True),
])
def test_distinct_compute_and_third_party_cash_fields_are_each_counted_once(money, third_party, expected, review):
    request = {"billing_mode": "rh_coins", "prior_cost_cny": 0, "budget_limit_cny": 5}
    result = jobs._billing_result(request, {"task_id": "one", "submitted_at": 0}, {
        "billing": {"provider_usage": {"consume_coins": 380, "consume_money": money,
            "third_party_consume_money": third_party}}})
    assert result["actual_cost_cny"] == expected
    assert result["billing_review_required"] is review
    assert result["provider_usage"]["consume_money"] == money
    assert result["provider_usage"]["third_party_consume_money"] == third_party


def test_missing_coin_evidence_uses_conservative_estimate_even_if_money_zero(monkeypatch):
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 100))
    result = jobs._billing_result({"billing_mode": "rh_coins", "prior_cost_cny": 0, "budget_limit_cny": 5},
        {"task_id": "one", "submitted_at": 0}, {"raw": {"usage": {
            "consumeMoney": 0, "taskCostTime": 120, "thirdPartyConsumeMoney": .02}}})
    assert result["consume_coins"] is None
    assert result["estimated_consume_coins"] == 48
    assert result["actual_cost_cny"] == round(48 / 380 + .02, 6)
    assert result["cost_source"] == "conservative_elapsed_estimate"
    assert result["billing_review_required"] is True


@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_terminal_cash_bill_does_not_report_estimated_coins_as_paid(status, monkeypatch):
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 381))
    result = jobs._billing_result({"billing_mode": "rh_coins", "prior_cost_cny": .01, "budget_limit_cny": 5},
        {"task_id": "one", "submitted_at": 0}, {"status": status, "raw": {"usage": {
            "consumeMoney": .636, "consumeCoins": None, "taskCostTime": 381,
            "thirdPartyConsumeMoney": 0}}})
    assert result["actual_cost_cny"] == result["confirmed_cost_cny"] == .636
    assert result["total_cost_cny"] == .646
    assert result["consume_coins"] is None
    assert result["estimated_consume_coins"] == 152.4
    assert result["estimated_cost_cny"] == round(.636 + 152.4 / 380, 6)
    assert result["cost_source"] == "provider_cash_coin_usage_unreported"
    assert result["billing_review_required"] is True


def test_consumer_inflight_status_reports_latest_cumulative_usage(consumer_project, monkeypatch):
    context = consumer_project
    quoted = jobs.quote(context.project, context.payload)
    jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": quoted["signature"]}, context.queue)
    path = jobs.directory(context.project, quoted["generation_id"]) / "ledger.json"
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 100))
    path.write_text(json.dumps({"status": "submitted", "task_id": "one", "submitted_at": 0,
        "credential_snapshot": {"contract_version": 1, "source": "RUNNINGHUB_CONSUMER_API_KEY",
            "storage": ".env.secrets.local", "key_sha256": hashlib.sha256(b"consumer-from-file").hexdigest()},
        "reserved_cost_cny": quoted["reserved_cost_cny"], "result": {"provider_usage": {
            "consume_coins": 20, "consume_money": 0, "task_cost_seconds": 50}}}), encoding="utf-8")
    first = jobs.inspect(context.project, quoted["generation_id"])["result"]
    again = jobs.inspect(context.project, quoted["generation_id"])["result"]
    assert first["consume_coins"] == again["consume_coins"] == 20
    assert first["actual_cost_cny"] == again["actual_cost_cny"] == round(20 / 380, 6)
    assert first["credential_source"] == "RUNNINGHUB_CONSUMER_API_KEY"


def test_inflight_usage_does_not_release_reserved_budget_for_another_task(consumer_project, monkeypatch):
    context = consumer_project
    quote = jobs.quote(context.project, context.payload)
    jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": quote["signature"]}, context.queue)
    path = jobs.directory(context.project, quote["generation_id"]) / "ledger.json"
    path.write_text(json.dumps({"status": "submitted", "task_id": "one", "submitted_at": 0,
        "result": {"actual_cost_cny": .01}}), encoding="utf-8")
    original_reader = jobs.audio.read
    monkeypatch.setattr(jobs.audio, "read", lambda *args: {**original_reader(*args), "id": "AU-different"})
    with pytest.raises(jobs.CommentaryError, match="其他数字人任务"):
        jobs.quote(context.project, {**context.payload, "budget_limit_cny": 4})


@pytest.mark.parametrize("status", ["generated", "completed", "failed"])
def test_terminal_cash_bill_keeps_reservation_until_coin_evidence_reconciled(consumer_project, monkeypatch, status):
    context = consumer_project
    quote = jobs.quote(context.project, context.payload)
    jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": quote["signature"]}, context.queue)
    path = jobs.directory(context.project, quote["generation_id"]) / "ledger.json"
    ledger = {"status": status, "task_id": "one", "submitted_at": 0, "result": {
        "actual_cost_cny": .636, "confirmed_cost_cny": .636, "consume_coins": None,
        "estimated_cost_cny": 1.044, "billing_review_required": True}}
    path.write_text(json.dumps(ledger), encoding="utf-8")
    original_reader = jobs.audio.read
    monkeypatch.setattr(jobs.audio, "read", lambda *args: {**original_reader(*args), "id": "AU-different"})
    with pytest.raises(jobs.CommentaryError, match="其他数字人任务"):
        jobs.quote(context.project, {**context.payload, "budget_limit_cny": 4})
    # An explicit reconciliation can release the unused reservation; it does
    # not turn the old estimate into another paid amount.
    ledger["result"].update(consume_coins=0, billing_review_required=False)
    path.write_text(json.dumps(ledger), encoding="utf-8")
    next_quote = jobs.quote(context.project, {**context.payload, "budget_limit_cny": 4})
    assert next_quote["other_avatar_commitments_cny"] == .636


def test_legacy_wallet_uses_existing_bill_without_coin_conversion(monkeypatch):
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: 100))
    result = jobs._billing_result({"prior_cost_cny": .01, "budget_limit_cny": 5},
        {"task_id": "one", "submitted_at": 0}, {"consume_money_cny": .07, "consume_coins": 380})
    assert result["actual_cost_cny"] == .07 and result["cost_source"] == "provider"
    assert result["billing_mode"] == "cny"


def test_missing_runtime_consumer_key_never_falls_back_or_submits(consumer_project):
    context = consumer_project
    quote = jobs.quote(context.project, context.payload)
    jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": quote["signature"]}, context.queue)
    context.secrets.unlink()
    outcome = ProductionQueueWorker(context.queue, context.projects).run_once()
    assert outcome["status"] == "failed" and outcome["retryable"] is True
    assert not context.credentials and not context.submissions
    assert not (jobs.directory(context.project, quote["generation_id"]) / "ledger.json").exists()


def _admit(context):
    quote = jobs.quote(context.project, context.payload)
    job = jobs.submit(context.project, {**context.payload, "confirmed": True,
        "quote_signature": quote["signature"]}, context.queue)
    return quote, job


def test_legacy_handler_cannot_execute_versioned_consumer_job(consumer_project):
    context = consumer_project
    quote, job = _admit(context)
    called = []
    old_worker = ProductionQueueWorker(context.queue, context.projects,
        handlers={"commentary_presenter": lambda job: called.append(job)})
    result = old_worker.run_once()
    assert result["status"] == "failed" and "没有注册执行器" in result["error"]["message"]
    assert not called and not context.submissions and not context.credentials
    assert not (jobs.directory(context.project, quote["generation_id"]) / "ledger.json").exists()
    # A new worker can safely retry the same admitted identity after this
    # no-side-effect failure; the old worker never entered the paid handler.
    assert _admit(context)[1]["job_id"] == job["job_id"]
    ProductionQueueWorker(context.queue, context.projects).run_once()
    assert len(context.submissions) == 1


def test_existing_legacy_job_keeps_kind_identity_and_is_not_revived(consumer_project):
    context = consumer_project
    quote = jobs.quote(context.project, context.payload)
    legacy = context.queue.submit(project_id=context.project.name, kind="commentary_presenter",
        source="workbench", priority="normal", parent_job_id=quote["generation_id"],
        frozen_request={"generation_id": quote["generation_id"]},
        idempotency_key=f"commentary_presenter:{context.project.name}:{quote['generation_id']}")
    claimed = context.queue.claim_next("legacy-test-worker")
    assert claimed["job_id"] == legacy["job_id"]
    context.queue.finish(legacy["job_id"], "legacy-test-worker", status="failed", stage="旧任务已终止")
    preserved = _admit(context)[1]
    assert preserved["job_id"] == legacy["job_id"]
    assert preserved["kind"] == "commentary_presenter" and preserved["status"] == "failed"
    assert len(context.queue.list()["tasks"]) == 1
    assert ProductionQueueWorker(context.queue, context.projects).run_once() is None
    assert not context.submissions


@pytest.mark.parametrize("audited", [False, True])
def test_legacy_ledger_never_adopts_consumer_intent_as_submission_source(consumer_project, audited):
    context = consumer_project
    quote, _ = _admit(context)
    path = jobs.directory(context.project, quote["generation_id"]) / "ledger.json"
    ledger = {"status": "failed", "task_id": "old-task", "submitted_at": 0,
        "result": {"credential_source": "RUNNINGHUB_CONSUMER_API_KEY", "credential_storage": ".env.secrets.local"}}
    if audited:
        ledger["credential_audit"] = {"requested_source": "RUNNINGHUB_CONSUMER_API_KEY",
            "actual_source": "RUNNINGHUB_API_KEY", "evidence": "user_task_detail_screenshot_and_queue_claim_event"}
    path.write_text(json.dumps(ledger), encoding="utf-8")
    result = jobs.inspect(context.project, quote["generation_id"])["result"]
    assert result["credential_source"] == ("RUNNINGHUB_API_KEY" if audited else "unknown_legacy")
    assert result["credential_evidence"] == ("posthoc_audit" if audited else "unknown_legacy")
    assert result["requested_credential_source"] == "RUNNINGHUB_CONSUMER_API_KEY"
    assert result["credential_snapshot"] is None and result["credential_storage"] is None
    resettled = jobs._billing_result(quote, ledger, {"status": "FAILED", "consume_money_cny": .636})
    assert resettled["credential_source"] == result["credential_source"]
    assert "credential_snapshot" not in json.loads(path.read_text(encoding="utf-8"))


def _real_client_offline_transport(monkeypatch, context):
    import requests
    from tools.avatar import runninghub_avatar as provider
    session = requests.Session()
    calls = []

    class OfflineAdapter(requests.adapters.BaseAdapter):
        def send(self, request, **kwargs):
            calls.append(request)
            if request.url.endswith("/openapi/v2/media/upload/binary"):
                payload = {"code": 0, "data": {"fileName": "offline-upload"}}
            elif request.url.endswith("/task/openapi/create"):
                payload = {"code": 0, "data": {"taskId": "offline-task"}}
            elif request.url.endswith("/openapi/v2/query"):
                payload = {"code": 0, "data": {"status": "FAILED", "usage": {
                    "consumeCoins": 38, "consumeMoney": 0, "taskCostTime": 95}}}
            else:
                raise AssertionError("unexpected offline route")
            response = requests.Response()
            response.status_code = 200
            response.request = request
            response._content = json.dumps(payload).encode()
            return response

        def close(self):
            pass

    session.mount("https://", OfflineAdapter())
    session.mount("http://", OfflineAdapter())
    monkeypatch.setattr(provider.requests, "Session", lambda: session)
    monkeypatch.setattr(provider, "RunningHubLongCatClient", RealRunningHubClient)
    monkeypatch.setattr(jobs, "media_run", lambda argv: Path(argv[-1]).write_bytes(b"synthetic-driver"))
    return calls


def test_real_client_prepared_requests_use_explicit_consumer_key_not_shared_environment(consumer_project, monkeypatch):
    context = consumer_project
    calls = _real_client_offline_transport(monkeypatch, context)
    quote, _ = _admit(context)
    outcome = ProductionQueueWorker(context.queue, context.projects).run_once()
    assert outcome["status"] == "failed"
    assert len(calls) == 4  # image/audio uploads, one create, one query
    assert all(request.headers["Authorization"] == "Bearer consumer-from-file" for request in calls)
    created = [request for request in calls if request.url.endswith("/task/openapi/create")]
    assert len(created) == 1
    assert json.loads(created[0].body)["apiKey"] == "consumer-from-file"
    snapshot = jobs.inspect(context.project, quote["generation_id"])["result"]["credential_snapshot"]
    assert snapshot["key_sha256"] == hashlib.sha256(b"consumer-from-file").hexdigest()
    assert snapshot["key_sha256"] != hashlib.sha256(b"shared-stays-unchanged").hexdigest()
    assert os.environ["RUNNINGHUB_API_KEY"] == "shared-stays-unchanged"


def test_real_client_wrong_key_constructor_is_blocked_before_any_request(consumer_project, monkeypatch):
    context = consumer_project
    calls = _real_client_offline_transport(monkeypatch, context)
    original_init = RealRunningHubClient.__init__

    def stale_constructor(self, **kwargs):
        kwargs["api_key"] = os.environ["RUNNINGHUB_API_KEY"]
        original_init(self, **kwargs)

    monkeypatch.setattr(RealRunningHubClient, "__init__", stale_constructor)
    quote, _ = _admit(context)
    outcome = ProductionQueueWorker(context.queue, context.projects).run_once()
    assert outcome["status"] == "failed" and not calls
    assert not (jobs.directory(context.project, quote["generation_id"]) / "ledger.json").exists()
