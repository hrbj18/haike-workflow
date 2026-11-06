"""One confirmed budget for voice cloning, an optional portrait, and an audition.

Each paid stage keeps the existing audio centre's quote and durable operation.
Polling an enrollment only reads its record; recovery resumes those same children.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from backlot.work_catalog import WorkError
from lib import bailian_speech as records

ENROLLMENT = re.compile(r"enroll_[a-f0-9]{32}")
OPERATION = re.compile(r"call_[a-f0-9]{32}")
FILE = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
SUCCESS = {"succeeded", "completed"}
TERMINAL = SUCCESS | {"failed", "cancelled"}


def _micros(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,10}", str(value)) or int(value) > 1_000_000_000:
        raise WorkError("请填写有效的本次总预算，最高1,000元")
    return int(value)


class AudioEnrollment:
    def __init__(self, center):
        self.center = center
        self.directory = center.directory / "enrollments"

    def _path(self, identity):
        if not isinstance(identity, str) or not ENROLLMENT.fullmatch(identity):
            raise WorkError("音色创建任务编号无效")
        return self.directory / identity / "enrollment.json"

    def _save(self, value):
        value["updated_at"] = datetime.now(timezone.utc).isoformat()
        records.write_record(self._path(value["id"]), value)

    def _read(self, identity):
        # Recheck account scope even when this wrapper is cached by a worker.
        self.center.voices()
        value = records.read_record(self._path(identity))
        if not value or value.get("id") != identity:
            raise WorkError("音色创建任务不存在或不属于当前账号", "missing")
        return value

    @staticmethod
    def public(value):
        children = value.get("children", {})
        return {"id": value["id"], "operation_id": value["id"], "kind": "enrollment",
                "status": value["status"], "stage": value.get("stage", "clone"),
                "max_charge_micros": value["request"]["max_charge_micros"],
                "reserved_micros": sum(int(child["quote"]["max_charge_micros"]) for child in children.values()),
                "result": value.get("result") or None, "error": value.get("error"),
                "warning": value.get("warning"), "updated_at": value.get("updated_at"),
                "estimate_only": any(child["quote"].get("estimate_only") for child in children.values()),
                "quotes": [{key: quote[key] for key in (
                    "model", "provider", "provider_model", "max_charge_micros", "estimate_only", "billing_note"
                ) if key in quote} for quote in (child["quote"] for child in children.values())]}

    def create(self, data):
        fields = {"operation_id", "name", "audio_file", "image_file", "text",
                  "max_charge_micros", "confirmed", "consent"}
        if not isinstance(data, dict) or set(data) != fields or data["confirmed"] is not True or data["consent"] is not True:
            raise WorkError("请确认录音及图片使用权，并批准本次克隆和试听的总预算")
        path = self._path(data["operation_id"])
        name, text = data["name"], data["text"]
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40 or any(ord(c) < 32 for c in name):
            raise WorkError("请填写1至40字音色名称")
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > 180:
            raise WorkError("试听文案需为1至180字")
        for key in ("audio_file", "image_file"):
            if key == "image_file" and data[key] is None:
                continue
            if not isinstance(data[key], str) or not FILE.fullmatch(data[key]):
                raise WorkError("请先上传有效的参考录音和可选人物图")
        request = {key: data[key] for key in ("name", "audio_file", "image_file", "text")}
        request.update(name=name.strip(), text=text.strip(), max_charge_micros=_micros(data["max_charge_micros"]))
        signature = records.fingerprint(request)
        self.center.voices()
        previous = records.read_record(path)
        if previous:
            if previous["signature"] != signature:
                raise WorkError("原任务的录音、配图、文案和预算已保存，请继续原任务", "conflict")
            return self.public(previous)
        with records.operation_lock(path.parent):
            previous = records.read_record(path)
            if previous:
                if previous["signature"] != signature:
                    raise WorkError("原任务的录音、配图、文案和预算已保存，请继续原任务", "conflict")
                return self.public(previous)
            # Validate file ownership before the first paid stage.
            for key, mime in (("audio_file", "audio/"), ("image_file", "image/")):
                if request[key] is not None:
                    _, content_type = self.center.media(request[key])
                    if not content_type.startswith(mime):
                        raise WorkError("参考录音或人物图的文件类型不正确")
            value = {"id": data["operation_id"], "signature": signature, "request": request,
                     "status": "queued", "stage": "clone", "children": {}, "result": {},
                     "authorization": {"confirmed": True, "consent": True, "scope": "clone_and_preview"}}
            self._save(value)
            return self.public(value)

    def read(self, identity):
        return self.public(self._read(identity))

    def _paid_stage(self, value, stage, request):
        child = value["children"].get(stage)
        if child is None:
            quote = self.center.quote(request)
            maximum = _micros(quote.get("max_charge_micros"))
            if not OPERATION.fullmatch(str(quote.get("operation_id", ""))) or not quote.get("id"):
                raise WorkError("音色服务未提供可恢复的调用编号，请管理员更新服务")
            reserved = sum(int(item["quote"]["max_charge_micros"]) for item in value["children"].values())
            if reserved + maximum > value["request"]["max_charge_micros"]:
                value.update(status="partial" if value["result"].get("voice") else "failed",
                             error="本次总预算不足，已停止后续调用；已创建的音色会保留，请在音色详情中试听。")
                self._save(value)
                return None
            child = value["children"][stage] = {"quote": quote, "submitted": False}
            self._save(value)
        quote = child["quote"]
        body = {"quote_id": quote["id"], "operation_id": quote["operation_id"],
                "max_charge_micros": quote["max_charge_micros"], "confirmed": True}
        if not child["submitted"]:
            # Parent intent precedes the child's own pre-network intent.
            child["submitted"] = True
            self._save(value)
            outcome = self.center.submit(body)
        else:
            try:
                self.center.operation(quote["operation_id"])
            except WorkError as error:
                if error.code != "missing":
                    raise
                expires = quote.get("expires_at")
                if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                    # No child intent exists, so this expired quote never reached
                    # a supplier. Refresh it inside the original total budget.
                    del value["children"][stage]
                    self._save(value)
                    return self._paid_stage(value, stage, request)
                # A crash before center.submit cannot have reached a supplier:
                # both centres persist their operation before the network call.
                outcome = self.center.submit(body)
            else:
                outcome = self.center.job(quote["operation_id"])
        child["status"] = outcome.get("status", "submission_unknown")
        child["result"] = outcome.get("result") or {}
        self._save(value)
        if child["status"] in SUCCESS:
            return child["result"]
        if child["status"] in TERMINAL:
            value.update(status="partial" if value["result"].get("voice") else "failed",
                         error=("音色已保留，试听未完成，请在音色详情中查看。" if stage == "preview" else
                                "声音克隆未完成，请检查服务状态和原任务；本次未继续试听。"))
        else:
            value["status"] = "submission_unknown" if child["status"] in {"submission_unknown", "unknown", "uncertain"} else "processing"
        self._save(value)
        return None

    def _advance(self, value):
        request = value["request"]
        result = value["result"]
        if not result.get("voice"):
            value.update(stage="clone", status="processing", error=None)
            self._save(value)
            cloned = self._paid_stage(value, "clone", {"model": "haike/voice-clone", "input": {
                "name": request["name"], "audio_file": request["audio_file"], "consent": True}})
            if cloned is None:
                return
            voice = cloned.get("voice")
            if not isinstance(voice, dict) or not isinstance(voice.get("id"), str) or not voice["id"]:
                raise WorkError("克隆服务未返回音色编号，已保留原任务，请管理员核对")
            result["voice"] = voice
            self._save(value)
        voice_id = result["voice"]["id"]
        if request["image_file"] and not result.get("image_linked"):
            value.update(stage="image", status="processing")
            self._save(value)
            try:
                self.center.preferences({"image_file_id": request["image_file"]}, voice_id)
                result["image_linked"] = True
                value.pop("warning", None)
            except Exception:
                value["warning"] = "音色已创建，人物图暂未关联成功；可继续原任务补上图片。"
            self._save(value)
        if not result.get("audio_url"):
            value.update(stage="preview", status="processing", error=None)
            self._save(value)
            voice = next((item for item in self.center.voices().get("items", []) if item["id"] == voice_id), None)
            if not voice:
                raise WorkError("音色已创建，列表尚未同步；请稍后继续原任务生成试听")
            preview = self._paid_stage(value, "preview", {"model": voice["model"], "input": {
                "voice_id": voice_id, "text": request["text"], "speech_rate": 1}})
            if preview is None:
                return
            if not preview.get("audio_url"):
                raise WorkError("试听结果已返回，音频尚未就绪；请继续查询原任务")
            result["audio_url"] = preview["audio_url"]
        value.update(stage="done", status="partial" if value.get("warning") else "succeeded", error=None)
        self._save(value)

    def run(self, identity, *, max_wait=900, poll_interval=2):
        path = self._path(identity)
        try:
            lock = records.operation_lock(path.parent)
            lock.__enter__()
        except records.BailianSpeechError:
            return  # Another worker owns this exact enrollment.
        try:
            deadline = time.monotonic() + max_wait
            while True:
                value = self._read(identity)
                if value["status"] in SUCCESS | {"failed"}:
                    return
                try:
                    self._advance(value)
                except Exception as error:
                    value.update(status="paused", error=str(error) if isinstance(error, WorkError) else
                                 "原任务已保留，请检查连接和音色服务后继续；已完成的步骤会自动复用。")
                    self._save(value)
                    return
                if value["status"] in TERMINAL | {"partial"}:
                    return
                if time.monotonic() >= deadline:
                    value.update(status="paused", error="音色服务仍在处理，稍后可继续原任务，已提交的调用不会重新创建。")
                    self._save(value)
                    return
                time.sleep(poll_interval)
        finally:
            lock.__exit__(None, None, None)
