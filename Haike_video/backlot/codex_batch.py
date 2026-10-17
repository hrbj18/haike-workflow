"""Thin, restartable Codex orchestration over the existing local authorities.

TaskCenter owns orchestration receipts; Studio/production_queue/works own the
actual operations. This module never calls suppliers or publishes directly.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


TEMPLATES = {"avatar-safe-circle-v1", "avatar-deepblue-n1-v1", "avatar-full-width-v2", "avatar-template3-card-3x4-v001"}
PLATFORMS = {"douyin", "kuaishou", "shipinhao"}
SECRET_FIELDS = {"api_key", "apikey", "cookie", "cookies", "authorization", "secret", "secret_key", "access_token", "password", "signed_url"}
SUBMITTED = {"submitting", "pending", "publishing", "done", "uncertain", "submission_unknown"}


class BatchError(ValueError):
    def __init__(self, message, *, status=None, unknown=False):
        super().__init__(message)
        self.status, self.unknown = status, unknown


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized(value):
    return re.sub(r"[\W_]+", "", str(value).casefold())


def deterministic_draft_id(batch_id, slot_id):
    return "studio-" + fingerprint([batch_id, slot_id])[:16]


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}", value):
        raise BatchError("批次或槽位编号无效")
    return value


def _money(value):
    if type(value) is not int or not 0 < value <= 1_000_000_000:
        raise BatchError("预算须为正整数微元，最高1,000元")
    return value


def _record_micros(value):
    """Receipts use integer strings; booleans/floats/unknown are not money."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,16}", value):
        value = int(value)
    return value if type(value) is int and 0 <= value <= 10**15 else None


def _no_secrets(value):
    if isinstance(value, dict):
        if any(str(k).casefold() in SECRET_FIELDS for k in value):
            raise BatchError("规格不得包含密钥、Cookie、登录信息或签名地址")
        for v in value.values():
            _no_secrets(v)
    elif isinstance(value, list):
        for v in value:
            _no_secrets(v)
    elif isinstance(value, str) and re.search(r"\b(?:hk_[A-Za-z0-9_-]{25,}|sk-[A-Za-z0-9_-]{20,})", value):
        raise BatchError("规格不得包含供应商或海客密钥")


def validate_spec(raw):
    """Validate the complete batch before making any HTTP request."""
    _no_secrets(raw)
    if not isinstance(raw, dict) or set(raw) != {"batch_id", "limit_micros", "items"}:
        raise BatchError("批次规格需要batch_id、limit_micros、items")
    spec = copy.deepcopy(raw)
    _identifier(spec["batch_id"])
    _money(spec["limit_micros"])
    if not isinstance(spec["items"], list) or not 1 <= len(spec["items"]) <= 20:
        raise BatchError("一个批次需要1至20个明确槽位")
    required = {"slot_id", "topic_key", "sources", "title", "text", "template_id", "portrait_path",
                "target_duration_seconds", "max_charge_micros", "allow_graphic_fallback", "publishing"}
    voice_fields = {"voice_id", "model_id", "speech_rate"}
    slots, topics = set(), set()
    for item in spec["items"]:
        if not isinstance(item, dict) or not required <= set(item) or set(item) - required - voice_fields - {"audio_path", "n1", "avatar_defaults_snapshot", "network_materials_enabled"}:
            raise BatchError("制作槽位规格字段不完整或包含未知字段")
        audio_mode = "audio_path" in item
        if audio_mode:
            if not isinstance(item["audio_path"], str) or not item["audio_path"].strip():
                raise BatchError("完整音轨需要明确本机音频路径")
        elif not voice_fields <= set(item):
            raise BatchError("配音路线需要明确音色、模型和语速；完整音轨请提供audio_path")
        if "network_materials_enabled" in item and type(item["network_materials_enabled"]) is not bool:
            raise BatchError("联网素材开关须为布尔值")
        if "avatar_defaults_snapshot" in item:
            from backlot.studio_avatar_defaults import validate_snapshot
            from backlot.work_catalog import WorkError
            try:
                item["avatar_defaults_snapshot"] = validate_snapshot(item["avatar_defaults_snapshot"])
            except WorkError as exc:
                raise BatchError(str(exc)) from None
        slot, topic = _identifier(item["slot_id"]), normalized(item["topic_key"])
        if slot in slots or not topic or topic in topics:
            raise BatchError("槽位或具体事件topic_key重复/为空")
        slots.add(slot); topics.add(topic)
        if item["template_id"] not in TEMPLATES:
            raise BatchError("本入口仅支持已接入的N1和基础模板1/2/3")
        if not isinstance(item["title"], str) or not 1 <= len(item["title"].strip()) <= (120 if item["template_id"] == "avatar-deepblue-n1-v1" else 36 if item["template_id"].startswith("avatar-template3") else 16):
            raise BatchError("标题超过本模板字数限制")
        if not isinstance(item["text"], str) or not 1 <= len(item["text"].strip()) <= 5000:
            raise BatchError("口播稿需要1至5,000字")
        for key in ("voice_id", "model_id"):
            if audio_mode and key not in item:
                continue
            if not isinstance(item[key], str) or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", item[key]):
                raise BatchError("模型或音色编号无效")
        for key, lower, upper in (("speech_rate", .5, 2), ("target_duration_seconds", 1, 120)):
            if audio_mode and key not in item:
                continue
            if type(item[key]) not in {int, float} or not math.isfinite(item[key]) or not lower <= item[key] <= upper:
                raise BatchError("语速或目标时长无效")
        if type(item["allow_graphic_fallback"]) is not bool:
            raise BatchError("图文备用授权须为布尔值")
        _money(item["max_charge_micros"])
        if not isinstance(item["portrait_path"], str) or not item["portrait_path"].strip():
            raise BatchError("必须明确本机人物图片路径")
        sources = item["sources"]
        if not isinstance(sources, list) or not sources:
            raise BatchError("每条需要明确来源；可记录公开网页或用户提供的素材")
        for source in sources:
            if isinstance(source, dict) and source.get("kind") == "user_provided":
                if set(source) != {"kind", "label"} or not isinstance(source.get("label"), str) or not 1 <= len(source["label"].strip()) <= 200:
                    raise BatchError("用户提供的素材来源需要简短说明，不记录私人路径或凭据")
                continue
            if not isinstance(source, dict) or not isinstance(source.get("url"), str):
                raise BatchError("来源需要公开URL对象")
            url = urllib.parse.urlsplit(source["url"])
            if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
                raise BatchError("来源必须是无凭据的公开网页URL")
            if any(k.casefold().startswith(("x-amz-", "x-oss-")) or k.casefold() in {"token", "signature", "sig", "access_token"}
                   for k, _ in urllib.parse.parse_qsl(url.query)):
                raise BatchError("来源不能是临时签名或带认证的地址")
        pub = item["publishing"]
        if not isinstance(pub, dict) or set(pub) != {"desc", "topics", "source_rights_status", "targets"}:
            raise BatchError("发布资料字段无效")
        if not isinstance(pub["desc"], str) or not pub["desc"].strip() or not isinstance(pub["topics"], str):
            raise BatchError("发布详情/话题无效")
        if pub["source_rights_status"] not in {"owned", "confirmed", "unknown"}:
            raise BatchError("来源权利状态无效")
        targets = pub["targets"]
        if not isinstance(targets, list):
            raise BatchError("发布目标应为列表；仅制作时可明确设为空列表")
        identities = set()
        for target in targets:
            if not isinstance(target, dict) or not {"platform", "account_id"} <= set(target) or set(target) - {"platform", "account_id", "scheduled_at"} or target["platform"] not in PLATFORMS or type(target["account_id"]) is not int or target["account_id"] < 1:
                raise BatchError("发布目标必须明确平台及账号")
            if "scheduled_at" in target:
                try:
                    when = datetime.fromisoformat(target["scheduled_at"].replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        raise ValueError()
                except (ValueError, TypeError, AttributeError):
                    raise BatchError("发布时间scheduled_at必须包含时区") from None
            identity = (target["platform"], target["account_id"])
            if identity in identities:
                raise BatchError("发布目标重复")
            identities.add(identity)
        if "n1" in item:
            if item["template_id"] != "avatar-deepblue-n1-v1":
                raise BatchError("n1字段不能进入其他模板")
            from backlot.studio_n1 import settings
            settings({"title": item["title"], "input": {"n1": item["n1"]}})
    if sum(item["max_charge_micros"] for item in spec["items"]) > spec["limit_micros"]:
        raise BatchError("各条保守上限之和超过批次预算；未知/失败不释放额度")
    return spec


class LocalAPI:
    def __init__(self, base="http://127.0.0.1:14756"):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path not in {"", "/"} or parsed.username or parsed.password:
            raise BatchError("批次CLI仅连接本机工作台")
        self.base = base.rstrip("/")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, path, data=None, *, method=None, raw=None, content_type=None):
        if not path.startswith("/api/") or path.startswith("//"):
            raise BatchError("只允许本机API路径")
        body = raw if raw is not None else canonical(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(self.base + path, data=body, method=method,
            headers={"Origin": self.base, "Content-Type": content_type or "application/json"})
        try:
            with self.opener.open(req, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not echo server errors containing private paths or request data.
            raise BatchError(f"本机API拒绝请求（HTTP {exc.code}）；保留原任务后核对", status=exc.code) from None
        except (OSError, ValueError) as exc:
            raise BatchError("API响应未确认；先读取原任务，禁止换编号重发", unknown=body is not None) from None

    def portrait(self, file_id):
        if not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", file_id):
            raise BatchError("默认人物图编号无效")
        path = "/api/studio/audio-center/media/" + urllib.parse.quote(file_id, safe="")
        try:
            with self.opener.open(self.base + path, timeout=30) as response:
                data = response.read(10 * 1024 * 1024 + 1)
            if not data or len(data) > 10 * 1024 * 1024:
                raise BatchError("默认人物图为空或超过10MB")
            return data
        except OSError:
            raise BatchError("默认人物图暂不可读，保留预设后重查") from None


class CodexBatch:
    def __init__(self, spec, *, root=None, api=None):
        self.spec = validate_spec(spec)
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.projects = self.root / "Haike_video/projects"
        self.api = api or LocalAPI()
        self.spec_hash = fingerprint(self.spec)
        self._task_ids = {}

    def _guard(self):
        h = self.api.call("/api/health")
        if h.get("edition") != "haike-workflow-2" or Path(h.get("workspace", "")).resolve() != self.root:
            raise BatchError("服务不是明确指定的haike-workflow-2副本")

    def _items(self, slot=None):
        result = [i for i in self.spec["items"] if slot is None or i["slot_id"] == slot]
        if not result:
            raise BatchError("指定槽位不存在")
        return result

    def _draft_id(self, item):
        return deterministic_draft_id(self.spec["batch_id"], item["slot_id"])

    def _client_id(self, item):
        return "codex-batch:" + fingerprint([self.spec["batch_id"], item["slot_id"]])[:40]

    def _folder(self, item):
        path = self.projects / self._draft_id(item) / "artifacts/automation/codex-batch"
        for p in (path, *path.parents):
            if p == self.projects.parent:
                break
            if p.is_symlink() or (p.exists() and getattr(p.lstat(), "st_file_attributes", 0) & 0x400):
                raise BatchError("项目规格路径不能穿过链接或目录联接")
        return path

    def _public_item(self, item):
        return {k: copy.deepcopy(v) for k, v in item.items() if k not in {"portrait_path", "audio_path"}}

    def _all_tasks(self):
        cursor, tasks = 0, []
        while True:
            result = self.api.call(f"/api/task-center/summary?cursor={cursor}&limit=100")
            tasks.extend(result.get("changes", []))
            if not result.get("has_more"):
                return tasks
            after = result.get("next_cursor", cursor)
            if type(after) is not int or after <= cursor:
                raise BatchError("任务历史游标没有前进，未假定去重完成")
            cursor = after

    def _task(self, item):
        client = self._client_id(item)
        if client not in self._task_ids:
            row = next((t for t in self._all_tasks() if t.get("client_id") == client), None)
            if not row:
                raise BatchError("请先init登记本批次")
            self._task_ids[client] = row["id"]
        task = self.api.call("/api/task-center/tasks/" + self._task_ids[client])
        if task.get("facts", {}).get("spec_sha256") != self.spec_hash:
            raise BatchError("同一批次槽位规格已冻结，不能变更spec")
        return task

    def _patch(self, item, *, execution=None, links=None, budget_floor=None, **updates):
        for attempt in range(3):
            current = self._task(item)
            facts = copy.deepcopy(current.get("facts", {}))
            if execution is not None:
                facts["execution"] = {**facts.get("execution", {}), **execution}
            data = {"expected_revision": current["revision"], "facts": facts,
                    "links": {**current.get("links", {}), **(links or {})}, **updates}
            if budget_floor is not None:
                # Re-read on every CAS attempt: partial/missing receipts cannot
                # erase a larger reservation written by another reporter.
                budget = copy.deepcopy(current.get("budget", {}))
                for key, value in budget_floor.items():
                    if value is not None:
                        previous = _record_micros(budget.get(key))
                        budget[key] = max(value, previous) if previous is not None else value
                data["budget"] = budget
            try:
                return self.api.call("/api/task-center/tasks/" + current["id"], data, method="PATCH")
            except BatchError as exc:
                if exc.status != 409 or attempt == 2:
                    raise
        raise BatchError("任务并发更新尚未完成")

    def resolve(self):
        self._guard()
        voices = self.api.call("/api/studio/audio-center").get("items", []) if any("audio_path" not in i for i in self.spec["items"]) else []
        publishing = self.api.call("/api/studio/publishing") if any(i["publishing"]["targets"] for i in self.spec["items"]) else {}
        accounts = publishing.get("accounts", [])
        result = []
        for item in self.spec["items"]:
            portrait = Path(item["portrait_path"])
            if not portrait.is_file() or portrait.is_symlink():
                raise BatchError("明确指定的人物图片不存在或不是普通文件")
            voice = next((v for v in voices if v.get("id") == item.get("voice_id") and v.get("model") == item.get("model_id")), None)
            if voice is None and "audio_path" not in item:
                raise BatchError("本账号未提供规格指定的音色/模型，未换源")
            if "audio_path" in item and (not Path(item["audio_path"]).is_file() or Path(item["audio_path"]).is_symlink()):
                raise BatchError("明确指定的完整音轨不存在或不是普通文件")
            voice = voice or {}
            target_states = []
            for target in item["publishing"]["targets"]:
                account = next((a for a in accounts if a.get("id") == target["account_id"] and a.get("platform") == target["platform"]), None)
                if account is None:
                    raise BatchError("指定发布账号不存在或平台不符")
                target_states.append({**target, "status": account.get("status"),
                    "needs_recovery": account.get("status") != "active"})
            result.append({"slot_id": item["slot_id"], "draft_id": self._draft_id(item), "voice_id": voice.get("id"),
                           "voice_name": voice.get("name"), "model_id": item.get("model_id"), "template_id": item["template_id"],
                           "sound_mode": "audio" if "audio_path" in item else "voice", "speech_rate": None if "audio_path" in item else item["speech_rate"],
                           "audio_sha256": file_sha(item["audio_path"]) if "audio_path" in item else None,
                           "portrait_name": Path(item["portrait_path"]).name,
                           "portrait_source": "account_preset" if item.get("avatar_defaults_snapshot", {}).get("values", {}).get("portrait_file_id") else "explicit_local_override", "portrait_sha256": file_sha(portrait),
                           "cloud_portrait_image_id": (voice.get("preferences") or {}).get("image_file_id"), "targets": target_states})
        return {"batch_id": self.spec["batch_id"], "spec_sha256": self.spec_hash, "items": result}

    def _check_history(self):
        tasks = self._all_tasks()
        works = self.api.call("/api/works")
        if isinstance(works, dict):
            works = works.get("items", works.get("works", []))
        for item in self.spec["items"]:
            topic = normalized(item["topic_key"])
            for old in tasks:
                if old.get("client_id") == self._client_id(item):
                    continue
                detail = self.api.call("/api/task-center/tasks/" + old["id"])
                facts = detail.get("facts", {})
                attempts = facts.get("publication_attempts", [])
                has_submission = any(a.get("status") in SUBMITTED for a in attempts)
                if (detail.get("status") == "completed" or has_submission) and topic == normalized(facts.get("topic_key", "")):
                    raise BatchError("具体事件topic_key已完成/已提交，阻止重复选题")
            for work in works:
                if work.get("project_id") == self._draft_id(item):
                    continue
                if normalized(work.get("title")) == normalized(item["title"]) and any(a.get("status") in SUBMITTED for a in work.get("attempts", [])):
                    raise BatchError("同标题作品已提交，需总控先核对是否重复事件")

    def _freeze(self, item):
        from lib.bailian_speech import operation_lock, read_record, write_record
        folder = self._folder(item)
        if not Path(item["portrait_path"]).is_file() or Path(item["portrait_path"]).is_symlink():
            raise BatchError("本批人物原图已缺失，请恢复原图后准备，不换人物")
        record = {"spec_sha256": self.spec_hash, "spec": self.spec,
                  "portrait_sha256": file_sha(item["portrait_path"])}
        if "audio_path" in item:
            audio = Path(item["audio_path"])
            if not audio.is_file() or audio.is_symlink():
                raise BatchError("本批完整音轨缺失，请恢复原音频，不自动改配音")
            record["audio_sha256"] = file_sha(audio)
        path = folder / "spec.json"
        with operation_lock(folder / "spec-lock"):
            old = read_record(path)
            if old and old != record:
                raise BatchError("本项目spec或人物图片已冻结，不能覆盖")
            if not old:
                write_record(path, record)
        return path

    def _input(self, item, portrait=None, audio=None):
        value = {"soundMode": "audio" if "audio_path" in item else "voice", "subtitles": True,
                 "portrait": portrait or {}, "ai": {"enabled": False}}
        if "audio_path" in item:
            value["audio"] = audio or {}
        else:
            value.update(modelId=item["model_id"], voiceId=item["voice_id"], rate=item["speech_rate"])
        if "network_materials_enabled" in item:
            value["network_materials_enabled"] = item["network_materials_enabled"]
        if "n1" in item:
            value["n1"] = copy.deepcopy(item["n1"])
        if "avatar_defaults_snapshot" in item:
            value["avatar_defaults_snapshot"] = copy.deepcopy(item["avatar_defaults_snapshot"])
        return value

    def init(self):
        resolved = self.resolve()
        # Reject immutable-spec changes before creating or modifying anything.
        for old in self._all_tasks():
            if any(old.get("client_id") == self._client_id(i) for i in self.spec["items"]):
                detail = self.api.call("/api/task-center/tasks/" + old["id"])
                if detail.get("facts", {}).get("spec_sha256") != self.spec_hash:
                    raise BatchError("已登记规格不可变更spec")
        self._check_history()
        for item in self.spec["items"]:
            path = self._freeze(item)
            draft_id = self._draft_id(item)
            payload = {"client_id": self._client_id(item), "batch_id": self.spec["batch_id"], "kind": "production",
                "title": item["title"], "status": "planned", "stage": "代码接入/待制作",
                "links": {"project_id": draft_id, "draft_id": draft_id},
                "budget": {"limit_micros": item["max_charge_micros"], "actual_micros": None, "reserved_micros": None, "estimated_micros": None},
                "facts": {"spec_sha256": self.spec_hash, "spec_ref": path.relative_to(self.projects / draft_id).as_posix(),
                    "topic_key": item["topic_key"], "topic_key_normalized": normalized(item["topic_key"]),
                    "snapshot": self._public_item(item), "portrait": {"source": "explicit_local_override",
                        "sha256": file_sha(item["portrait_path"]), "name": Path(item["portrait_path"]).name},
                    **({"audio": {"source": "user_provided_complete_track", "sha256": file_sha(item["audio_path"])}} if "audio_path" in item else {}), "execution": {}}}
            task = self.api.call("/api/task-center/tasks", payload)
            self._task_ids[self._client_id(item)] = task["id"]
            try:
                self.api.call("/api/studio/drafts/" + draft_id)
            except BatchError as exc:
                if exc.status != 404:
                    raise
                self.api.call("/api/studio/drafts", {"id": draft_id, "template_id": item["template_id"],
                    "title": item["title"], "text": item["text"], "input": self._input(item)})
        result = self.status()
        result["resolved"] = resolved["items"]
        return result

    def prepare(self, slot=None):
        self._guard()
        for item in self._items(slot):
            self._freeze(item)
            task = self._task(item)
            execution = task["facts"].get("execution", {})
            draft = self.api.call("/api/studio/drafts/" + self._draft_id(item))
            expected = self._input(item, draft.get("input", {}).get("portrait"), draft.get("input", {}).get("audio"))
            if any(draft.get(k) != item[k] for k in ("template_id", "title", "text")) or draft.get("input") != expected:
                raise BatchError("草稿内容与冻结规格不同，不能沿用本批制作")
            if execution.get("quote_id"):
                if draft["revision"] != execution.get("draft_revision"):
                    raise BatchError("已报价草稿版本改变，不能替换原报价")
                continue
            portrait = draft["input"].get("portrait") or {}
            audio = draft["input"].get("audio") or {}
            changed = False
            if not portrait.get("id"):
                raw = Path(item["portrait_path"]).read_bytes()
                query = urllib.parse.urlencode({"draft_id": draft["id"], "kind": "image", "filename": Path(item["portrait_path"]).name})
                portrait = self.api.call("/api/studio/assets?" + query, raw=raw, content_type="application/octet-stream")
                changed = True
            if "audio_path" in item and not audio.get("id"):
                raw = Path(item["audio_path"]).read_bytes()
                query = urllib.parse.urlencode({"draft_id": draft["id"], "kind": "audio", "filename": Path(item["audio_path"]).name})
                audio = self.api.call("/api/studio/assets?" + query, raw=raw, content_type="application/octet-stream")
                changed = True
            if changed:
                draft = self.api.call("/api/studio/drafts", {"id": draft["id"], "revision": draft["revision"],
                    "template_id": item["template_id"], "title": item["title"], "text": item["text"], "input": self._input(item, portrait, audio)})
            quote = self.api.call(f"/api/studio/drafts/{draft['id']}/quote", {"revision": draft["revision"]})
            if int(quote["known_max_micros"]) > item["max_charge_micros"]:
                raise BatchError("已知报价超过本条预算，未提交生成")
            self._patch(item, execution={"quote_id": quote["id"], "draft_revision": draft["revision"],
                "portrait_asset_id": portrait["id"], "known_max_micros": int(quote["known_max_micros"])},
                status="planned", stage="报价已冻结/待制作")
        return self.status(slot)

    def _queue(self, item, task):
        job_id = task.get("links", {}).get("queue_job_id")
        job = self.api.call("/api/production-queue/jobs/" + job_id) if job_id else self.api.call(
            f"/api/studio/drafts/{self._draft_id(item)}/avatar-job").get("job")
        if job:
            execution = task["facts"].get("execution", {})
            if job.get("project_id") != self._draft_id(item) or job.get("kind") != "studio_avatar" or job.get("parent_job_id") != "studio-" + str(execution.get("draft_revision")):
                raise BatchError("现有队列不匹配冻结草稿，未创建替代任务")
            links = {"queue_job_id": job["job_id"]}
            if job.get("result", {}).get("work_id"):
                links["work_id"] = job["result"]["work_id"]
            self._patch(item, links=links, execution={"submission_state": "bound"})
        return job

    def submit(self, slot=None):
        self._guard()
        for item in self._items(slot):
            task = self._task(item)
            execution = task["facts"].get("execution", {})
            if not execution.get("quote_id"):
                raise BatchError("请先prepare并冻结报价")
            if self._queue(item, task):
                continue
            if execution.get("submission_state") in {"requesting", "unknown"}:
                raise BatchError("原提交结果未知且尚未找到队列，仅能继续核对原任务", unknown=True)
            self._patch(item, execution={"submission_state": "requesting"}, status="queued", stage="提交原制作请求")
            try:
                job = self.api.call(f"/api/studio/drafts/{self._draft_id(item)}/generate", {
                    "revision": execution["draft_revision"], "quote_id": execution["quote_id"],
                    "max_charge_micros": item["max_charge_micros"], "confirmed": True})
            except BatchError:
                self._patch(item, execution={"submission_state": "unknown"}, status="uncertain", stage="提交结果待核对/禁止换任务")
                raise
            self._patch(item, links={"queue_job_id": job["job_id"]}, execution={"submission_state": "bound"},
                        status="queued", stage=job.get("stage", "排队"))
        return self.status(slot)

    def resume(self, slot=None):
        self._guard()
        for item in self._items(slot):
            task = self._task(item)
            job = self._queue(item, task)
            if job and job.get("status") == "failed" and job.get("retryable") is True:
                self.api.call("/api/production-queue/jobs/" + job["job_id"] + "/retry", {})
            # No job, queued/running/completed/ambiguous/uncertain all remain
            # observations. Resume never creates another generation request.
        return self.status(slot)

    def material_context(self, slot=None):
        """Read observations needed by the Agent; never start or resume work."""
        if slot is None:
            raise BatchError("素材分析需要明确--slot，不能跨槽位混用素材与音频时钟")
        item = self._items(slot)[0]
        self._guard()
        task = self._task(item)
        revision = task.get("facts", {}).get("execution", {}).get("draft_revision")
        path = f"/api/studio/drafts/{self._draft_id(item)}/agent-materials"
        if revision is not None:
            if type(revision) is not int or revision < 1:
                raise BatchError("原草稿版本无效，未读取其他版本的素材分析")
            path += "?" + urllib.parse.urlencode({"revision": revision})
        context = self.api.call(path)
        if (not isinstance(context, dict) or context.get("draft_id") != self._draft_id(item)
                or type(context.get("draft_revision")) is not int or context["draft_revision"] < 1
                or revision is not None and context["draft_revision"] != revision):
            raise BatchError("素材上下文不属于本槽位的原草稿版本")
        return {**context, "batch_id": self.spec["batch_id"], "slot_id": slot, "task_id": task["id"]}

    def material_apply(self, analysis, slot=None):
        """Record Agent observations against the frozen task, without retrying it."""
        if slot is None:
            raise BatchError("提交素材分析需要明确--slot")
        _no_secrets(analysis)
        if (not isinstance(analysis, dict) or set(analysis) - {"draft_revision", "clock_sha256", "scenes", "materials", "decisions"}
                or type(analysis.get("draft_revision")) is not int or analysis["draft_revision"] < 1
                or not isinstance(analysis.get("clock_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", analysis["clock_sha256"])):
            raise BatchError("分析文件需要原draft_revision/clock_sha256及分镜或候选审核结果，不得包含路径或凭据")
        item = self._items(slot)[0]
        context = self.material_context(slot)
        task = self._task(item)
        revision = task.get("facts", {}).get("execution", {}).get("draft_revision")
        if (revision != analysis["draft_revision"] or context.get("clock_sha256") != analysis["clock_sha256"]
                or context.get("status") == "pending_audio"):
            raise BatchError("分析文件与原任务真实音频时钟或草稿版本不符，请重新读取material-context")
        result = self.api.call(f"/api/studio/drafts/{self._draft_id(item)}/agent-materials", copy.deepcopy(analysis))
        if (not isinstance(result, dict) or result.get("ok") is not True or result.get("draft_revision") != revision
                or result.get("next") != "resume_original_job" or not isinstance(result.get("analysis_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", result["analysis_sha256"])):
            raise BatchError("分析提交回执未确认，请读取原material-context核对；未恢复制作", unknown=True)
        self._patch(item, execution={"agent_analysis_sha256": result["analysis_sha256"], "agent_analysis_revision": revision},
                    stage="Agent素材分析已记录，等待明确恢复原任务")
        return {"ok": True, "batch_id": self.spec["batch_id"], "slot_id": slot, "draft_id": self._draft_id(item),
                "draft_revision": revision, "analysis_sha256": result["analysis_sha256"], "next": result["next"], "queue_resumed": False}

    def status(self, slot=None):
        self._guard()
        items = []
        for item in self._items(slot):
            task = self._task(item)
            execution = task["facts"].get("execution", {})
            job_id = task.get("links", {}).get("queue_job_id")
            job = self.api.call("/api/production-queue/jobs/" + job_id) if job_id else None
            # Return only public queue receipts, never frozen_request or state.
            queue = {k: job.get(k) for k in ("job_id", "status", "stage", "updated_at", "retryable", "error")} if job else None
            items.append({"slot_id": item["slot_id"], "task_id": task["id"], "draft_id": self._draft_id(item),
                "status": task["status"], "stage": task["stage"], "queue": queue,
                "work_id": task.get("links", {}).get("work_id") or ((job or {}).get("result") or {}).get("work_id"), "quote_id": execution.get("quote_id"),
                "submission_state": execution.get("submission_state"), "max_charge_micros": item["max_charge_micros"],
                "summary": task.get("summary", ""), "publication_receipts": copy.deepcopy(execution.get("publication_receipts", [])),
                "audio_sha256": task.get("facts", {}).get("audio", {}).get("sha256"),
                "budget": {k: task.get("budget", {}).get(k) for k in ("actual_micros", "reserved_micros", "estimated_micros")}})
        def total(key):
            values = [row["budget"][key] for row in items]
            return sum(values) if len(items) == len(self.spec["items"]) and all(type(v) is int for v in values) else None
        return {"batch_id": self.spec["batch_id"], "spec_sha256": self.spec_hash, "items": items,
            "budget": {"limit_micros": self.spec["limit_micros"], "allocated_micros": sum(i["max_charge_micros"] for i in self.spec["items"]),
                       "actual_micros": total("actual_micros"), "reserved_micros": total("reserved_micros"), "estimated_micros": total("estimated_micros")}}

    def _original_stage_budget(self, item, task):
        """Project only amounts from this slot's frozen render, never raw state.

        The quote cap is exposure, not an actual charge. Unknown, failed, or
        privately estimated calls retain that exposure until explicit receipts.
        """
        project_id = self._draft_id(item)
        if any(task.get("links", {}).get(key) != project_id for key in ("project_id", "draft_id")):
            raise BatchError("预算项目路径不属于本槽位")
        revision = task.get("facts", {}).get("execution", {}).get("draft_revision")
        if revision is None:
            return {}
        if type(revision) is not int or revision <= 0:
            raise BatchError("冻结草稿版本无效，未读取费用路径")
        path = self.projects / project_id / "renders" / f"studio-{revision}" / "gateway-state.json"
        try:
            for part in (path, *path.parents):
                if part == self.projects.parent:
                    break
                if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                    raise BatchError("费用路径不能穿过链接或目录联接")
            if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
                return {}
            with path.open("r", encoding="utf-8") as stream:
                state = json.load(stream)
        except (OSError, ValueError) as exc:
            if isinstance(exc, BatchError):
                raise
            return {}  # Atomic write absent/incomplete: preserve known totals.
        stages = state.get("stages") if isinstance(state, dict) else None
        if not isinstance(stages, dict) or not 1 <= len(stages) <= 200:
            return {}
        groups, incomplete = [], False
        for name, stage in stages.items():
            quote = stage.get("quote") if isinstance(stage, dict) else None
            if not isinstance(quote, dict):
                incomplete = True
                continue
            if quote.get("project_ref") not in (None, "", project_id):
                raise BatchError("原报价项目与本槽位不符，未借用其他项目费用")
            maximum = _record_micros(quote.get("max_charge_micros"))
            if maximum is None:
                incomplete = True
                continue
            job = stage.get("job") if isinstance(stage.get("job"), dict) else {}
            aliases = set()
            for kind, identifier in (("intent", stage.get("intent")), ("quote", quote.get("id")),
                                     ("operation", quote.get("operation_id")), ("job", job.get("id")),
                                     ("operation", job.get("operation_id"))):
                if isinstance(identifier, str) and identifier:
                    aliases.add((kind, identifier))
            if not aliases:
                aliases.add(("stage", name))
            charged = _record_micros(job.get("charged_micros"))
            settled = (job.get("status") == "succeeded" and job.get("funds_status") == "settled"
                       and isinstance(job.get("id"), str) and bool(job["id"])
                       and job.get("actual_cost_status") not in ("unconfirmed", "pending")
                       and charged is not None and charged <= maximum)
            group = {"aliases": aliases, "maximum": maximum, "charges": {charged} if settled else set(),
                     "unsettled": not settled}
            # A repeated intent/quote/job is one operation. Merge transitively;
            # conflicting caps use the larger cap, never add a repeated hold.
            for previous in groups[:]:
                if group["aliases"] & previous["aliases"]:
                    group["aliases"].update(previous["aliases"])
                    group["maximum"] = max(group["maximum"], previous["maximum"])
                    group["charges"].update(previous["charges"])
                    group["unsettled"] |= previous["unsettled"]
                    groups.remove(previous)
            groups.append(group)
        if not groups:
            return {}
        def settled(group):
            return not group["unsettled"] and len(group["charges"]) == 1
        estimated = sum(group["maximum"] for group in groups)
        reserved = sum(group["maximum"] for group in groups if not settled(group))
        actual = sum(next(iter(group["charges"])) for group in groups) if not incomplete and all(settled(g) for g in groups) else None
        if estimated > 10**15:
            return {}  # Out-of-schema receipts are not silently truncated.
        return {"estimated_micros": estimated,
                "reserved_micros": reserved if reserved or not incomplete else None,
                "actual_micros": actual}

    @staticmethod
    def _publication_progress(item, task, work):
        plan_id = task["facts"].get("execution", {}).get("publish_plan_id")
        attempts = [a for a in work.get("attempts", []) if not plan_id or a.get("plan_id") == plan_id]
        receipts = []
        for target in item["publishing"]["targets"]:
            matches = [a for a in attempts if a.get("platform") == target["platform"] and a.get("account_id") == target["account_id"]]
            attempt = matches[-1] if matches else {}
            status, evidence = attempt.get("status"), attempt.get("acceptance") or {}
            error = str(attempt.get("error") or attempt.get("blocked_reason") or "")
            if status == "done" and attempt.get("acceptance_status") == "verified" and attempt.get("identity_verified") is True:
                state, label = "verified", "已提交并核验"
            elif status == "done":
                state, label = "submitted", "已提交，待核验"
            elif status in {"uncertain", "submission_unknown"}:
                state, label = "unknown", "提交结果未知，核对原任务"
            elif status in {"reviewing", "under_review", "审核中"} or evidence.get("platform_status") in {"reviewing", "under_review", "审核中"}:
                state, label = "reviewing", "平台审核中"
            elif status == "blocked" and re.search(r"登录|logged_out|auth", error, re.I):
                state, label = "login_blocked", "登录阻塞，待恢复原账号"
            elif status == "blocked":
                state, label = "blocked", "提交阻塞，待恢复原计划"
            elif status == "publishing":
                state, label = "publishing", "正在提交"
            elif status == "pending":
                state, label = "queued", "发布排队"
                if attempt.get("next_allowed_at"):
                    try:
                        allowed = datetime.fromisoformat(attempt["next_allowed_at"].replace("Z", "+00:00"))
                        if allowed.tzinfo is not None:
                            label = "等待发布间隔，最早北京时间" + allowed.astimezone(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
                    except (ValueError, TypeError, AttributeError):
                        pass
            elif status == "failed":
                state, label = "failed", "发布失败，核对原任务"
            elif status == "submitting":
                state, label = "submitting", "原提交意图已记录，待核对"
            else:
                state, label = "not_submitted", "尚未提交"
            receipts.append({**target, "task_id": attempt.get("task_id"), "state": state, "label": label,
                             "next_allowed_at": attempt.get("next_allowed_at")})
        states = [r["state"] for r in receipts]
        if all(s == "verified" for s in states):
            return "completed", "全部目标平台已提交并完整核验", receipts
        if any(s == "unknown" for s in states):
            return "uncertain", "部分平台提交结果未知；其他平台分别核对", receipts
        if all(s in {"verified", "submitted"} for s in states):
            return "running", "全部目标平台已提交，等待最终核验", receipts
        if all(s == "queued" for s in states):
            return "queued", "等待各账号发布间隔；原任务已排队", receipts
        if any(s in {"blocked", "login_blocked", "failed"} for s in states):
            return "running", "各平台分别执行；阻塞平台保留原任务", receipts
        return "running", "三平台发布进行中", receipts

    def report(self, slot=None):
        result = self.status(slot)
        for row in result["items"]:
            item = next(i for i in self.spec["items"] if i["slot_id"] == row["slot_id"])
            task = self._task(item)
            budget_floor = self._original_stage_budget(item, task)
            queue = row["queue"]
            stage = queue.get("stage") if queue else task["stage"]
            state = task["status"]
            if queue:
                state = {"completed": "running", "running": "running", "queued": "queued", "failed": "failed",
                         "ambiguous": "uncertain", "awaiting_human": "awaiting_human",
                         "paused": "paused", "cancelled": "cancelled"}.get(queue["status"], state)
                if queue["status"] == "completed":
                    stage = "成片已生成，等待Codex质量检查"
                    if not item["publishing"]["targets"]:
                        approval = task["facts"].get("execution", {})
                        video = self.projects / self._draft_id(item) / "renders" / f"studio-{approval.get('draft_revision')}" / "avatar-preview.mp4"
                        approved = (bool(approval.get("production_approval_sha256"))
                                    and video.is_file() and not video.is_symlink()
                                    and file_sha(video) == approval.get("approved_video_sha256"))
                        state = "completed" if approved else "awaiting_human"
                        stage = "成片已审核完成，仅制作未发布" if approved else stage
            receipts, source_error = [], None
            if row.get("work_id") and item["publishing"]["targets"]:
                try:
                    work = self.api.call(f"/api/works/{row['work_id']}/sync", {})
                    if work.get("project_id") != self._draft_id(item):
                        raise BatchError("作品不属于本槽位，不能借用其他作品回执")
                    if work.get("attempts"):
                        state, stage, receipts = self._publication_progress(item, task, work)
                except BatchError:
                    source_error = "发布回执同步暂不可用，不能据此判未发布"
                    # A temporary source outage must not regress a previously
                    # completed/verified orchestration receipt.
                    if task["status"] == "completed":
                        state, stage = task["status"], task["stage"]
            message = f"{item['title']}：{stage}。"
            if receipts:
                names = {"douyin": "抖音", "kuaishou": "快手", "shipinhao": "视频号"}
                message += "；".join(names.get(r["platform"], r["platform"]) + "：" + r["label"] for r in receipts) + "。"
            if source_error:
                message += source_error + "。"
            actual = budget_floor.get("actual_micros")
            previous_actual = _record_micros(task.get("budget", {}).get("actual_micros"))
            if previous_actual is not None:
                actual = max(actual, previous_actual) if actual is not None else previous_actual
            message += "实际结算金额未知；" if actual is None else f"已记录实际费用{actual}微元；"
            message += "失败和未知结果未释放本条保守额度。"
            self._patch(item, summary=message, stage=stage, status=state, budget_floor=budget_floor,
                        execution={"publication_receipts": receipts} if receipts else None,
                        links={"work_id": row["work_id"]} if row.get("work_id") else {})
            for command in task.get("commands", []):
                if command.get("kind") == "report_now" and command.get("status") == "requested":
                    self.api.call("/api/task-center/tasks/" + task["id"] + "/events", {
                        "client_id": "batch-report:" + fingerprint(command["id"])[:40], "kind": "report", "stage": stage, "message": message})
                    self.api.call("/api/task-center/commands/" + command["id"] + "/ack", {"status": "acknowledged", "result": message})
        result = self.status(slot)
        from backlot.codex_batch_report import write_report
        result["report_path"] = str(write_report(self, result, slot=slot))
        return result

    def advance(self, evidence=None, slot=None):
        """One host wake-up: advance original operations, then persist a report.

        There is no timer, content reasoning, or fabricated review here. The
        existing queue and publisher continue their own durable operations.
        """
        if evidence is not None and (not isinstance(evidence, dict)
                or evidence.get("spec_sha256") != self.spec_hash or evidence.get("batch_id") != self.spec["batch_id"]
                or not isinstance(evidence.get("items"), list) or any(not isinstance(e, dict) for e in evidence["items"])):
            raise BatchError("推进证据必须是本批冻结规格的对象和items列表，未启动制作或发布")
        self._guard()
        known = {t.get("client_id") for t in self._all_tasks()}
        if any(self._client_id(item) not in known for item in self.spec["items"]):
            self.init()
        errors = []
        for item in self._items(slot):
            identity = item["slot_id"]
            try:
                task = self._task(item)
                if task.get("status") == "completed":
                    continue
                execution = task["facts"].get("execution", {})
                if not execution.get("quote_id"):
                    self.prepare(identity)
                self.submit(identity)
                task = self._task(item)
                job = self._queue(item, task)
                if job and job.get("status") == "completed" and evidence is not None:
                    if item["publishing"]["targets"]:
                        self.publish(evidence, identity)
                    else:
                        self.approve(evidence, identity)
                elif job and job.get("status") in {"failed", "ambiguous", "awaiting_human", "cancelled"}:
                    errors.append({"slot_id": identity, "message": "原制作任务需要处理，请核对status后按原编号resume", "unknown_result": job.get("status") == "ambiguous"})
            except BatchError as exc:
                errors.append({"slot_id": identity, "message": str(exc), "unknown_result": exc.unknown})
        result = self.report(slot)
        for row in result["items"]:
            blocked = [r for r in row.get("publication_receipts", []) if r.get("state") in {"unknown", "failed", "blocked", "login_blocked"}]
            if blocked and not any(e["slot_id"] == row["slot_id"] for e in errors):
                errors.append({"slot_id": row["slot_id"], "message": "部分发布平台失败或阻塞，请核对文档并恢复原计划", "unknown_result": any(r["state"] == "unknown" for r in blocked)})
        result.update(ok=not errors, errors=errors)
        from backlot.codex_batch_report import write_report
        result["report_path"] = str(write_report(self, result, slot=slot))
        return result

    def approve(self, evidence, slot=None):
        """Confirm a reviewed production-only work; never create a publish plan."""
        self._guard()
        if (not isinstance(evidence, dict) or evidence.get("spec_sha256") != self.spec_hash
                or evidence.get("batch_id") != self.spec["batch_id"] or not isinstance(evidence.get("items"), list)):
            raise BatchError("审核证据不属于本批冻结规格")
        for item in self._items(slot):
            if item["publishing"]["targets"]:
                raise BatchError("此槽位有发布目标，请按原公开发布证据流程处理")
            check = next((e for e in evidence["items"] if isinstance(e, dict) and e.get("slot_id") == item["slot_id"]), None)
            if not check or any(check.get(k) is not True for k in ("technical_checks_passed", "frame_review_passed", "source_claims_verified")):
                raise BatchError("仅制作验收仍需要技术、画面与事实检查证据")
            task = self._task(item)
            job = self._queue(item, task)
            if not job or job.get("status") != "completed":
                raise BatchError("原制作队列尚未完成")
            project = self.projects / self._draft_id(item)
            if not isinstance(check.get("quality_report"), str):
                raise BatchError("请提供本项目技术报告")
            quality_path = Path(check["quality_report"]).resolve()
            if not quality_path.is_relative_to(project.resolve()) or not quality_path.is_file():
                raise BatchError("技术报告必须是本项目内文件")
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            revision = task["facts"]["execution"]["draft_revision"]
            video = project / "renders" / f"studio-{revision}" / "avatar-preview.mp4"
            digest = file_sha(video)
            if (quality.get("status") != "technical_checks_passed"
                    or quality.get("video", {}).get("sha256_after") != digest or check.get("video_sha256") != digest):
                raise BatchError("审核证据未绑定当前成片")
            work_id = (job.get("result") or {}).get("work_id") or task.get("links", {}).get("work_id")
            if not work_id:
                raise BatchError("完成作品尚未登记，请先恢复原作品入库")
            work = self.api.call("/api/works/" + work_id)
            if work.get("project_id") != self._draft_id(item):
                raise BatchError("作品不属于本槽位")
            if task["facts"]["execution"].get("production_approval_sha256") != fingerprint(check):
                mode = work.get("mode", "manual")
                work = self.api.call("/api/works/register", {"project_id": self._draft_id(item), "path": str(video),
                    "work_key": "main", "mode": mode, "event_id": "codex-quality:" + digest,
                    "quality_passed": mode == "automatic", "actor": "codex-batch"})
                version = next(v for v in work["versions"] if v["sha256"] == digest)
                if work.get("final_version_id") != version["version_id"]:
                    self.api.call(f"/api/works/{work_id}/confirm", {"revision": work["revision"], "version_id": version["version_id"],
                        "evidence": "production-only reviewed evidence " + fingerprint(check), "actor": "codex-batch"})
                self._patch(item, execution={"production_approval_sha256": fingerprint(check), "approved_video_sha256": digest},
                            links={"work_id": work_id}, status="completed", stage="成片已审核完成，仅制作未发布")
        return self.report(slot)

    def publish(self, evidence, slot=None):
        """Explicit second boundary: verified local evidence, then original plans."""
        self._guard()
        if (not isinstance(evidence, dict) or evidence.get("spec_sha256") != self.spec_hash
                or evidence.get("batch_id") != self.spec["batch_id"] or not isinstance(evidence.get("items"), list)
                or any(not isinstance(e, dict) for e in evidence["items"])):
            raise BatchError("发布证据不属于本批冻结规格")
        entries = evidence.get("items", [])
        for item in self._items(slot):
            if not item["publishing"]["targets"]:
                raise BatchError("本槽位仅制作，未授权发布目标")
            check = next((e for e in entries if e.get("slot_id") == item["slot_id"]), None)
            if not check or any(check.get(k) is not True for k in ("technical_checks_passed", "frame_review_passed", "source_claims_verified", "authorized_publication", "cover_reviewed")):
                raise BatchError("技术/画面/事实/封面或公开发布授权证据不完整")
            task = self._task(item)
            job = self._queue(item, task)
            if not job or job.get("status") != "completed":
                raise BatchError("原制作队列尚未完成")
            project = self.projects / self._draft_id(item)
            for key in ("quality_report", "cover_path"):
                path = Path(check[key]).resolve()
                if not path.is_relative_to(project.resolve()) or not path.is_file() or path.is_symlink():
                    raise BatchError("质检/封面证据必须是本项目内文件")
            quality = json.loads(Path(check["quality_report"]).read_text(encoding="utf-8"))
            if quality.get("status") != "technical_checks_passed" or quality.get("video", {}).get("sha256_after") != check.get("video_sha256"):
                raise BatchError("技术报告未绑定当前成片")
            video = project / "renders" / ("studio-" + str(task["facts"]["execution"]["draft_revision"])) / "avatar-preview.mp4"
            if file_sha(video) != check.get("video_sha256") or file_sha(check["cover_path"]) != check.get("cover_sha256"):
                raise BatchError("成片或封面SHA与已审证据不同")
            pub = item["publishing"]
            if check.get("source_rights_status") not in {"owned", "confirmed"} or pub["source_rights_status"] not in {"owned", "confirmed"}:
                raise BatchError("公开使用范围尚未确认")
            work_id = (job.get("result") or {}).get("work_id") or task.get("links", {}).get("work_id")
            if not work_id:
                raise BatchError("完成作品尚未登记；先恢复原入库，不新建制作任务")
            references = task.get("evidence", [])
            for label, suffix in (("查看本期成片", "media"), ("查看发布封面", "cover")):
                ref = self.api.base + f"/api/works/{work_id}/{suffix}" if isinstance(self.api, LocalAPI) else None
                if ref and not any(row.get("ref") == ref for row in references):
                    references = [*references, {"label": label, "ref": ref, "kind": "artifact"}]
            if references != task.get("evidence", []):
                self._patch(item, evidence=references)
            work = self.api.call("/api/works/" + work_id)
            plan_id = task["facts"].get("execution", {}).get("publish_plan_id")
            if not plan_id:
                # Preserve the existing work mode. Explicit approved evidence
                # confirms the exact version through the original contract.
                mode = work.get("mode", "manual")
                work = self.api.call("/api/works/register", {"project_id": self._draft_id(item), "path": str(video),
                    "work_key": "main", "mode": mode, "event_id": "codex-quality:" + check["video_sha256"],
                    "quality_passed": mode == "automatic", "actor": "codex-batch"})
                if mode != "automatic":
                    version = next(v for v in work["versions"] if v["sha256"] == check["video_sha256"])
                    work = self.api.call(f"/api/works/{work_id}/confirm", {"revision": work["revision"],
                        "version_id": version["version_id"], "evidence": "explicit approved evidence " + fingerprint(check), "actor": "codex-batch-user-authorized"})
                material = {"title": item["title"], "desc": pub["desc"], "topics": pub["topics"],
                    "cover_path": str(Path(check["cover_path"]).resolve()), "cover_origin": "approved_video_frame",
                    "source_rights_status": pub["source_rights_status"], "request_evidence": "codex-batch explicit approved evidence " + fingerprint(check)}
                work = self.api.call(f"/api/works/{work_id}/materials", {"revision": work["revision"], "data": material, "actor": "codex-batch"})
                work = self.api.call(f"/api/works/{work_id}/targets", {"revision": work["revision"], "targets": pub["targets"], "actor": "codex-batch"})
                plan = self.api.call(f"/api/works/{work_id}/preflight", {"revision": work["revision"]})
                plan_id = plan["plan_id"]
                self._patch(item, links={"work_id": work_id, "publish_plan_id": plan_id}, execution={"publish_plan_id": plan_id,
                    "publish_evidence_sha256": fingerprint(check)}, stage="发布计划已冻结/待原计划提交")
            elif task["facts"]["execution"].get("publish_evidence_sha256") != fingerprint(check):
                raise BatchError("原发布计划证据不能更换")
            # Existing plan/entry submission keys own every retry; an unknown
            # transport response never creates another plan or task here.
            self.api.call("/api/works/publish/" + plan_id, {"confirmed": True, "actor": "codex-batch-user-authorized"})
            self._patch(item, stage="已提交原发布计划/待平台核验")
        return self.status(slot)
