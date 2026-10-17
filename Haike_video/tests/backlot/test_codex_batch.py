"""Offline integration boundaries for the thin Codex batch CLI."""
import copy
import json
from pathlib import Path

import pytest

from backlot.codex_batch import BatchError, CodexBatch, deterministic_draft_id, validate_spec


def test_pending_publish_interval_is_waiting_with_beijing_earliest_time():
    item = {"publishing": {"targets": [{"platform": "douyin", "account_id": 3}]}}
    task = {"facts": {"execution": {"publish_plan_id": "same-plan"}}}
    work = {"attempts": [{"plan_id": "same-plan", "platform": "douyin", "account_id": 3,
                          "task_id": 7, "status": "pending", "next_allowed_at": "2026-10-16T16:50:38Z"}]}
    status, stage, receipts = CodexBatch._publication_progress(item, task, work)
    assert status == "queued" and "发布间隔" in stage
    assert receipts[0]["task_id"] == 7 and receipts[0]["state"] == "queued"
    assert "10/17 00:50" in receipts[0]["label"] and "最早" in receipts[0]["label"]
    assert "登录" not in receipts[0]["label"]


class API:
    def __init__(self, root):
        self.root = root
        self.calls, self.tasks, self.drafts, self.jobs = [], {}, {}, {}
        self.quotes, self.uploads, self.submissions = 0, 0, 0
        self.lose_submit_response = False
        self.conflict_once = False
        self.events, self.acks = [], []
        self.accounts = [{"id": 3, "platform": "douyin", "status": "active", "has_creator": True}]
        self.works = {}

    def call(self, path, data=None, *, method=None, raw=None, content_type=None):
        method = method or ("POST" if data is not None or raw is not None else "GET")
        self.calls.append((method, path, copy.deepcopy(data)))
        if path == "/api/health":
            return {"workspace": str(self.root), "edition": "haike-workflow-2"}
        if path == "/api/studio/audio-center":
            return {"items": [{"id": "clone-yy3", "model": "haike/internal-tts", "name": "yy3"}]}
        if path == "/api/studio/publishing":
            return {"available": True, "accounts": copy.deepcopy(self.accounts)}
        if path.startswith("/api/task-center/summary"):
            return {"changes": copy.deepcopy(list(self.tasks.values())), "next_cursor": len(self.tasks), "has_more": False}
        if path == "/api/task-center/tasks":
            old = next((t for t in self.tasks.values() if t["client_id"] == data["client_id"]), None)
            if old:
                return copy.deepcopy(old)
            value = {**copy.deepcopy(data), "id": "TC-" + str(len(self.tasks) + 1), "revision": 1, "sources": {}, "commands": []}
            self.tasks[value["id"]] = value
            return copy.deepcopy(value)
        if path.startswith("/api/task-center/tasks/"):
            if path.endswith("/events"):
                self.events.append(copy.deepcopy(data))
                return {"id": len(self.events), **copy.deepcopy(data)}
            key = path.rsplit("/", 1)[-1]
            if key not in self.tasks:
                raise AssertionError(path)
            task = self.tasks[key]
            if method == "PATCH":
                if self.conflict_once:
                    self.conflict_once = False
                    task["revision"] += 1
                    task["facts"]["parallel_report"] = "preserved"
                    raise BatchError("CAS conflict", status=409)
                assert data["expected_revision"] == task["revision"]
                task.update({k: copy.deepcopy(v) for k, v in data.items() if k != "expected_revision"})
                task["revision"] += 1
            return copy.deepcopy(task)
        if path.startswith("/api/task-center/commands/") and path.endswith("/ack"):
            self.acks.append((path, copy.deepcopy(data)))
            return copy.deepcopy(data)
        if path == "/api/studio/drafts":
            old = self.drafts.get(data["id"])
            assert old is None or old["revision"] == data["revision"]
            value = {**copy.deepcopy(data), "revision": 1 if old is None else old["revision"] + 1}
            self.drafts[value["id"]] = value
            return copy.deepcopy(value)
        if path.startswith("/api/studio/assets?"):
            assert raw == b"private portrait fixture"
            self.uploads += 1
            return {"id": f"asset-{self.uploads}", "name": "portrait.png", "kind": "image"}
        if path.startswith("/api/studio/drafts/"):
            parts = path.split("/")
            key = parts[4]
            if len(parts) == 5:
                if key not in self.drafts:
                    raise BatchError("not found", status=404)
                return copy.deepcopy(self.drafts[key])
            if parts[-1] == "quote":
                self.quotes += 1
                return {"id": f"quote-{self.quotes}", "known_max_micros": 20, "items": []}
            if parts[-1] == "avatar-job":
                return {"job": copy.deepcopy(next((j for j in self.jobs.values() if j["project_id"] == key), None))}
            if parts[-1] == "generate":
                self.submissions += 1
                assert data["revision"] == self.drafts[key]["revision"]
                job = {"job_id": "PQ-1", "project_id": key, "kind": "studio_avatar", "parent_job_id": f"studio-{data['revision']}",
                       "status": "queued", "stage": "排队", "result": {}}
                self.jobs[job["job_id"]] = job
                if self.lose_submit_response:
                    self.lose_submit_response = False
                    raise BatchError("unknown transport result", unknown=True)
                return copy.deepcopy(job)
        if path.startswith("/api/production-queue/jobs/"):
            parts = path.split("/")
            job = self.jobs[parts[4]]
            if parts[-1] == "retry":
                assert job["status"] == "failed"
                job["status"] = "queued"
            return copy.deepcopy(job)
        if path == "/api/works":
            return copy.deepcopy(list(self.works.values()))
        if path.startswith("/api/works/"):
            key = path.split("/")[3]
            return copy.deepcopy(self.works.get(key, {"work_id": key,
                "project_id": next(iter(self.jobs.values()))["project_id"], "attempts": []}))
        raise AssertionError((method, path))


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "haike-workflow-2"
    (root / "Haike_video/projects").mkdir(parents=True)
    portrait = tmp_path / "private-portrait.png"
    portrait.write_bytes(b"private portrait fixture")
    spec = {"batch_id": "night-fixture", "limit_micros": 100,
        "items": [{"slot_id": "n1", "topic_key": "official-event-2026-10-16", "sources": [
            {"url": "https://example.com/announcement", "publisher": "official", "published": "2026-10-16", "verified": True}],
            "title": "本期主题", "text": "本期已核实的口播稿。", "template_id": "avatar-deepblue-n1-v1",
            "portrait_path": str(portrait), "voice_id": "clone-yy3", "model_id": "haike/internal-tts", "speech_rate": 1.15,
            "target_duration_seconds": 25, "max_charge_micros": 100, "allow_graphic_fallback": False,
            "publishing": {"desc": "本期详情", "topics": "科技", "source_rights_status": "confirmed",
                "targets": [{"platform": "douyin", "account_id": 3}]}}]}
    api = API(root)
    return spec, root, api


@pytest.fixture
def preset_setup(setup):
    from io import BytesIO
    from PIL import Image
    from backlot.studio_avatar_defaults import AvatarDefaults
    spec, root, api = setup
    class Center:
        account = 'test-account'
        directory = root / '.local/test-account'
        def voices(self):
            return {'items': [{'id': 'clone-yy3', 'name': '雅雅', 'model': 'haike/internal-tts', 'preferences': {}},
                              {'id': 'clone-mm14', 'name': '檬檬', 'model': 'haike/internal-tts', 'preferences': {}}]}
        def media(self, identity):
            assert identity == 'owned-image'
            return b'owned', 'image/png'
    preset = AvatarDefaults(Center())
    values = {'portrait_file_id': 'owned-image', 'voice_id': 'clone-yy3', 'speech_rate': 1.15,
              'template_id': 'avatar-deepblue-n1-v1', 'target_duration_seconds': 25,
              'max_charge_micros': 100, 'allow_graphic_fallback': True}
    preset.save({'expected_revision': 0, 'expected_scope_id': preset.scope_id, 'values': values})
    original = api.call
    def call(path, data=None, **kw):
        if path == '/api/studio/audio-center/avatar-defaults/resolve':
            api.calls.append(('POST', path, copy.deepcopy(data)))
            return preset.resolve(data)
        return original(path, data, **kw)
    api.call = call
    image = BytesIO();Image.new('RGB', (256, 320), 'blue').save(image, format='PNG')
    api.portrait = lambda identity: image.getvalue()
    return spec, root, api, preset


def test_omitted_creation_parameters_use_account_preset_without_starting_work(preset_setup):
    from backlot.codex_batch_defaults import resolve_spec_defaults
    spec, root, api, preset = preset_setup
    raw = copy.deepcopy(spec)
    raw.pop('limit_micros')
    for field in ('voice_id', 'model_id', 'speech_rate', 'template_id', 'target_duration_seconds',
                  'max_charge_micros', 'allow_graphic_fallback', 'portrait_path'):
        raw['items'][0].pop(field)
    resolved = resolve_spec_defaults(raw, root=root, api=api)
    item = resolved['items'][0]
    assert item['speech_rate'] == 1.15 and item['voice_id'] == 'clone-yy3'
    assert item['allow_graphic_fallback'] is True and resolved['limit_micros'] == 100
    assert Path(item['portrait_path']).is_file()
    assert item['avatar_defaults_snapshot']['preset_revision'] == 1
    assert api.quotes == api.uploads == api.submissions == 0 and not api.tasks
    assert 'portrait_path' not in raw['items'][0]


def test_explicit_false_voice_speed_template_and_budget_override_without_changing_defaults(preset_setup):
    from backlot.codex_batch_defaults import resolve_spec_defaults
    spec, root, api, preset = preset_setup
    spec['items'][0].update(voice_id='clone-mm14', speech_rate=1.1, template_id='avatar-full-width-v2',
                            max_charge_micros=55, allow_graphic_fallback=False)
    resolved = resolve_spec_defaults(spec, root=root, api=api)['items'][0]
    assert resolved['voice_id'] == 'clone-mm14' and resolved['speech_rate'] == 1.1
    assert resolved['max_charge_micros'] == 55 and resolved['allow_graphic_fallback'] is False
    assert resolved['portrait_path'] == spec['items'][0]['portrait_path']
    assert preset.read()['values']['voice_id'] == 'clone-yy3'
    assert preset.read()['values']['allow_graphic_fallback'] is True
    spec['items'][0]['max_charge_micros'] = None
    with pytest.raises(BatchError, match='max_charge_micros'):
        resolve_spec_defaults(spec, root=root, api=api)


def test_preset_change_cannot_modify_resumed_frozen_batch_or_create_duplicate_tasks(preset_setup):
    from backlot.codex_batch_defaults import resolve_spec_defaults
    spec, root, api, preset = preset_setup
    raw = copy.deepcopy(spec);raw['items'][0].pop('speech_rate')
    frozen = resolve_spec_defaults(raw, root=root, api=api)
    first = CodexBatch(frozen, root=root, api=api).init()
    preset.save({'expected_revision': 1, 'expected_scope_id': preset.scope_id, 'values': {'speech_rate': 1.7}})
    second = CodexBatch(frozen, root=root, api=api).init()
    assert first['items'][0]['task_id'] == second['items'][0]['task_id']
    assert len(api.tasks) == 1 and api.uploads == api.quotes == api.submissions == 0
    assert next(iter(api.drafts.values()))['input']['avatar_defaults_snapshot']['values']['speech_rate'] == 1.15


def test_network_default_flows_into_frozen_input_and_explicit_off_is_preserved(preset_setup):
    from backlot.codex_batch_defaults import resolve_spec_defaults
    spec, root, api, preset = preset_setup
    preset.save({'expected_revision': 1, 'expected_scope_id': preset.scope_id,
                 'values': {'network_materials_enabled': True}})
    frozen = resolve_spec_defaults(spec, root=root, api=api)
    assert frozen['items'][0]['network_materials_enabled'] is True
    batch = CodexBatch(frozen, root=root, api=api)
    batch.init()
    assert next(iter(api.drafts.values()))['input']['network_materials_enabled'] is True
    preset.save({'expected_revision': 2, 'expected_scope_id': preset.scope_id,
                 'values': {'network_materials_enabled': False}})
    assert resolve_spec_defaults(frozen, root=root, api=api) == frozen
    spec['items'][0]['network_materials_enabled'] = False
    assert resolve_spec_defaults(spec, root=root, api=api)['items'][0]['network_materials_enabled'] is False
    assert api.uploads == api.quotes == api.submissions == 0


def test_legacy_batch_does_not_gain_new_network_field_and_invalid_switch_is_rejected(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    assert 'network_materials_enabled' not in next(iter(api.drafts.values()))['input']
    spec['items'][0]['network_materials_enabled'] = 'true'
    with pytest.raises(BatchError, match='联网素材'):
        validate_spec(spec)


def test_invalid_or_foreign_preset_cannot_silently_start_work(preset_setup):
    from backlot.codex_batch_defaults import resolve_spec_defaults
    spec, root, api, preset = preset_setup
    spec['items'][0]['api_key'] = 'do-not-use'
    with pytest.raises(BatchError, match='规格不得'):
        resolve_spec_defaults(spec, root=root, api=api)
    assert not api.calls
    spec['items'][0].pop('api_key')
    with pytest.raises(BatchError, match='不是当前新版'):
        resolve_spec_defaults(spec, root=root / 'other', api=api)
    assert api.submissions == 0


def test_budget_and_secret_validation_precedes_any_http(setup):
    spec, _, api = setup
    spec["limit_micros"] = 99
    with pytest.raises(BatchError):
        validate_spec(spec)
    spec["limit_micros"] = 100
    spec["items"][0]["api_key"] = "do-not-store-this"
    with pytest.raises(BatchError):
        validate_spec(spec)
    assert api.calls == []


def test_init_is_deterministic_and_public_facts_exclude_private_path(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    first = batch.init()
    second = CodexBatch(spec, root=root, api=api).init()
    assert first["items"][0]["task_id"] == second["items"][0]["task_id"]
    assert len(api.tasks) == len(api.drafts) == 1
    draft_id = deterministic_draft_id("night-fixture", "n1")
    assert draft_id in api.drafts
    assert str(Path(spec["items"][0]["portrait_path"]).parent) not in json.dumps(list(api.tasks.values()))
    assert api.uploads == api.quotes == api.submissions == 0
    assert first["budget"]["actual_micros"] is None


def test_spec_is_immutable_under_same_batch_and_slot(setup):
    spec, root, api = setup
    CodexBatch(spec, root=root, api=api).init()
    changed = copy.deepcopy(spec)
    changed["items"][0]["text"] = "changed after init"
    with pytest.raises(BatchError, match="规格|spec"):
        CodexBatch(changed, root=root, api=api).init()
    assert api.submissions == api.quotes == 0


def test_prepare_once_preserves_quote_portrait_and_rate_across_processes(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    batch.prepare()
    CodexBatch(spec, root=root, api=api).prepare()
    assert api.uploads == api.quotes == 1
    draft = next(iter(api.drafts.values()))
    assert draft["input"]["rate"] == 1.15
    assert draft["input"]["modelId"] == "haike/internal-tts"
    assert draft["input"]["portrait"]["id"] == "asset-1"
    assert api.submissions == 0


def test_submit_and_resume_keep_original_queue_job(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare(); batch.submit(); batch.submit(); batch.resume()
    assert api.submissions == 1
    api.jobs["PQ-1"].update(status="failed", retryable=True)
    batch.resume()
    assert api.jobs["PQ-1"]["status"] == "queued"
    assert api.submissions == 1
    retries = [c for c in api.calls if c[1].endswith("/retry")]
    assert len(retries) == 1


def test_lost_submit_response_is_reconciled_without_resubmitting(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    api.lose_submit_response = True
    with pytest.raises(BatchError):
        batch.submit()
    result = CodexBatch(spec, root=root, api=api).resume()
    assert result["items"][0]["queue"]["job_id"] == "PQ-1"
    assert api.submissions == 1


def test_unknown_without_a_job_never_creates_another_submission(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    task = next(iter(api.tasks.values()))
    task["facts"]["execution"]["submission_state"] = "unknown"
    result = batch.resume()
    assert result["items"][0]["submission_state"] == "unknown"
    assert api.submissions == 0


def test_cas_retry_preserves_other_reporter_facts(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    api.conflict_once = True
    batch.prepare()
    assert next(iter(api.tasks.values()))["facts"]["parallel_report"] == "preserved"


def test_duplicate_completed_topic_blocks_a_new_slot(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    task = next(iter(api.tasks.values()))
    task["status"] = "completed"
    other = copy.deepcopy(spec)
    other["batch_id"] = "other-night"
    other["items"][0]["topic_key"] = "OFFICIAL EVENT 2026 10 16"
    with pytest.raises(BatchError, match="重复|已完成"):
        CodexBatch(other, root=root, api=api).init()
    assert api.submissions == api.quotes == 0


def test_completed_job_is_only_observed_and_actual_cost_stays_unknown(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare(); batch.submit()
    api.jobs["PQ-1"].update(status="completed", result={"work_id": "W-1"})
    result = batch.resume()
    assert result["budget"]["actual_micros"] is None
    assert api.submissions == 1
    assert not any(c[1].endswith("/retry") for c in api.calls)


def test_status_survives_archived_original_portrait_after_preparation(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    Path(spec["items"][0]["portrait_path"]).unlink()
    result = CodexBatch(spec, root=root, api=api).status()
    assert result["items"][0]["quote_id"] == "quote-1"
    assert api.submissions == 0


def test_report_uses_real_queue_and_only_acknowledges_report_command(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare(); batch.submit()
    api.jobs["PQ-1"].update(status="completed", stage="合成完成待核验", result={"work_id": "W-1"})
    task = next(iter(api.tasks.values()))
    task["commands"] = [{"id": "C-report", "kind": "report_now", "status": "requested"},
                        {"id": "C-pause", "kind": "pause_requested", "status": "requested"}]
    batch.report()
    task = next(iter(api.tasks.values()))
    assert task["status"] == "running" and task["links"]["work_id"] == "W-1"
    assert "等待Codex质量检查" in task["summary"]
    assert len(api.events) == len(api.acks) == 1
    assert api.events[0]["kind"] == "report"
    assert api.acks[0][0].endswith("/C-report/ack")
    assert task["budget"]["actual_micros"] is None


def test_publish_never_uses_unreviewed_or_foreign_batch_evidence(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    before = api.submissions
    with pytest.raises(BatchError):
        batch.publish({"batch_id": "other", "spec_sha256": batch.spec_hash, "items": []})
    with pytest.raises(BatchError):
        batch.publish({"batch_id": spec["batch_id"], "spec_sha256": batch.spec_hash,
                       "items": [{"slot_id": "n1", "technical_checks_passed": True}]})
    assert api.submissions == before
    assert not any(c[1].startswith("/api/works/publish/") for c in api.calls)


def test_invalid_platform_account_warns_but_does_not_block_init_or_preparation(setup):
    spec, root, api = setup
    api.accounts[0]["status"] = "invalid"
    batch = CodexBatch(spec, root=root, api=api)
    resolved = batch.resolve()
    assert resolved["items"][0]["targets"][0]["needs_recovery"] is True
    batch.init(); batch.prepare()
    assert api.quotes == 1 and api.submissions == 0


def test_wrong_platform_account_is_rejected_before_task_creation(setup):
    spec, root, api = setup
    api.accounts[0]["platform"] = "kuaishou"
    with pytest.raises(BatchError):
        CodexBatch(spec, root=root, api=api).init()
    assert not api.tasks and not api.drafts


@pytest.mark.parametrize("status,acceptance,expected,label", [
    ("done", "not_checked", "running", "已提交，待核验"),
    ("done", "verified", "completed", "完整核验"),
    ("under_review", "not_checked", "running", "审核中"),
    ("blocked", "not_checked", "running", "登录阻塞"),
    ("uncertain", "not_checked", "uncertain", "结果未知"),
])
def test_report_tracks_platform_receipts_without_reverting_to_video_qa(setup, status, acceptance, expected, label):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare(); batch.submit()
    api.jobs["PQ-1"].update(status="completed", result={"work_id": "W-1"})
    api.works["W-1"] = {"work_id": "W-1", "project_id": deterministic_draft_id(spec["batch_id"], "n1"),
        "attempts": [{"platform": "douyin", "account_id": 3, "task_id": 81, "status": status,
            "acceptance_status": acceptance, "identity_verified": True, "error": "logged_out" if status == "blocked" else ""}]}
    batch.report(); batch.report()
    task = next(iter(api.tasks.values()))
    assert task["status"] == expected and label in task["summary"]
    assert "等待Codex质量检查" not in task["stage"]
    assert task["budget"]["actual_micros"] is None
    assert api.events == []  # PATCH already owns stage snapshots; no report spam.
    assert any(c[1] == "/api/works/W-1/sync" for c in api.calls)


def test_only_all_three_target_receipts_can_finish_the_overall_task(setup):
    spec, root, api = setup
    targets = [{"platform": "douyin", "account_id": 3}, {"platform": "kuaishou", "account_id": 2}, {"platform": "shipinhao", "account_id": 1}]
    spec["items"][0]["publishing"]["targets"] = targets
    api.accounts = [{"id": t["account_id"], "platform": t["platform"], "status": "active"} for t in targets]
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare(); batch.submit()
    api.jobs["PQ-1"].update(status="completed", result={"work_id": "W-1"})
    attempts = [{**t, "status": "done", "acceptance_status": "verified", "identity_verified": True} for t in targets]
    attempts[-1]["acceptance_status"] = "not_checked"
    api.works["W-1"] = {"work_id": "W-1", "project_id": deterministic_draft_id(spec["batch_id"], "n1"), "attempts": attempts}
    batch.report()
    assert next(iter(api.tasks.values()))["status"] == "running"
    attempts[-1]["acceptance_status"] = "verified"
    batch.report()
    assert next(iter(api.tasks.values()))["status"] == "completed"


def test_status_preserves_a_known_actual_cost_instead_of_replacing_it_with_zero_or_null(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init()
    next(iter(api.tasks.values()))["budget"]["actual_micros"] = 2160
    assert batch.status()["budget"]["actual_micros"] == 2160


def _gateway_state(batch, stages, slot="n1"):
    project = deterministic_draft_id(batch.spec["batch_id"], slot)
    path = batch.projects / project / "renders/studio-2/gateway-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stages": stages, "prepared": {"audio_base64": "private-audio-sentinel"}}), encoding="utf-8")
    return path


def test_report_adds_original_stage_quotes_once_and_does_not_invent_unknown_actual_cost(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    _gateway_state(batch, {
        "tts": {"quote": {"id": "q-tts", "max_charge_micros": "2"}, "intent": "call-tts",
                "job": {"status": "succeeded", "charged_micros": None, "actual_cost_status": "unconfirmed"}},
        "asr_bailian": {"quote": {"id": "q-asr", "max_charge_micros": "11"}, "intent": "call-asr",
                        "job": {"status": "processing", "charged_micros": "0"}},
        "avatar": {"quote": {"id": "q-avatar", "max_charge_micros": "70"}, "intent": "call-avatar",
                   "job": {"status": "submission_unknown", "charged_micros": "0", "result": {"video_url": "private-url-sentinel"}}},
        "avatar_alias": {"quote": {"id": "q-avatar-alias", "max_charge_micros": "68"}, "intent": "call-avatar"},
    })
    result = batch.report()
    assert result["budget"]["estimated_micros"] == 83
    assert result["budget"]["reserved_micros"] == 83
    assert result["budget"]["actual_micros"] is None
    assert not any(s in json.dumps([result, api.tasks]) for s in ("private-audio-sentinel", "private-url-sentinel"))
    assert api.submissions == 0


def test_report_only_totals_actual_when_every_original_stage_has_a_settled_receipt(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    stages = {
        "tts": {"quote": {"id": "q-tts", "max_charge_micros": "2"},
                "job": {"id": "j-tts", "status": "succeeded", "funds_status": "settled", "charged_micros": "2"}},
        "asr_bailian": {"quote": {"id": "q-asr", "max_charge_micros": "11"},
                        "job": {"id": "j-asr", "status": "failed", "funds_status": "released", "charged_micros": "0"}},
        "avatar": {"quote": {"id": "q-avatar", "max_charge_micros": "70"},
                   "job": {"id": "j-avatar", "status": "succeeded", "funds_status": "settled", "charged_micros": "61"}},
    }
    _gateway_state(batch, stages)
    first = batch.report()
    assert first["budget"]["actual_micros"] is None
    assert first["budget"]["reserved_micros"] == 11  # Failed/released is not inferred to be a free call.
    stages["asr_bailian"]["job"].update(status="succeeded", funds_status="settled", charged_micros="9")
    _gateway_state(batch, stages)
    second = batch.report()
    assert second["budget"]["actual_micros"] == 72
    assert second["budget"]["estimated_micros"] == 83
    assert second["budget"]["reserved_micros"] == 11  # Previously known reservation never silently shrinks.


def test_report_keeps_larger_existing_budget_across_partial_state_and_cas_retry(setup):
    spec, root, api = setup
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    task = next(iter(api.tasks.values()))
    task["budget"].update(actual_micros=7, reserved_micros=90, estimated_micros=95)
    path = _gateway_state(batch, {"tts": {"quote": {"id": "q-tts", "max_charge_micros": "8"}}})
    original = api.call
    conflicted = False
    def concurrent_budget(path, data=None, **kwargs):
        nonlocal conflicted
        if kwargs.get("method") == "PATCH" and not conflicted:
            conflicted = True
            task["revision"] += 1
            task["budget"]["reserved_micros"] = 99
            raise BatchError("CAS conflict", status=409)
        return original(path, data, **kwargs)
    api.call = concurrent_budget
    assert batch.report()["budget"] == {"limit_micros": 100, "allocated_micros": 100,
        "actual_micros": 7, "reserved_micros": 99, "estimated_micros": 95}
    path.write_text("{partial atomic record", encoding="utf-8")
    assert batch.report()["budget"]["reserved_micros"] == 99
    path.unlink()
    assert batch.report()["budget"]["actual_micros"] == 7


def test_report_never_borrows_a_foreign_slot_state_or_traverses_a_revision(setup):
    spec, root, api = setup
    second = copy.deepcopy(spec["items"][0])
    second.update(slot_id="template2", topic_key="a-different-official-event", title="另一个主题")
    spec["items"].append(second)
    spec["limit_micros"] = 200
    batch = CodexBatch(spec, root=root, api=api)
    batch.init(); batch.prepare()
    _gateway_state(batch, {"avatar": {"quote": {"id": "foreign-quote", "max_charge_micros": "99"}}}, slot="template2")
    task = next(t for t in api.tasks.values() if t["links"]["draft_id"] == deterministic_draft_id(spec["batch_id"], "n1"))
    task["facts"]["execution"]["state_path"] = "../template2/gateway-state.json"
    result = batch.report(slot="n1")
    assert result["items"][0]["budget"] == {"actual_micros": None, "reserved_micros": None, "estimated_micros": None}
    task["facts"]["execution"]["draft_revision"] = "../../other-slot"
    with pytest.raises(BatchError, match="版本|路径"):
        batch.report(slot="n1")
    task["facts"]["execution"]["draft_revision"] = 2
    _gateway_state(batch, {"avatar": {"quote": {"id": "foreign-quote", "max_charge_micros": "99",
        "project_ref": deterministic_draft_id(spec["batch_id"], "template2")}}})
    with pytest.raises(BatchError, match="项目|槽位"):
        batch.report(slot="n1")
    assert task["budget"]["reserved_micros"] is None
    assert not api.submissions
