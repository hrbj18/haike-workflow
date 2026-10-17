"""Account-scoped relay audio center with durable, recoverable call intents."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import tempfile
from pathlib import Path

from backlot.work_catalog import WorkError

TTS_MODELS = {"haike/cosyvoice", "haike/cosyvoice-public", "haike/internal-tts"}
MODELS = TTS_MODELS | {"haike/voice-clone"}
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
OPERATION = re.compile(r"call_[a-f0-9]{32}")


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise WorkError("音色或文件编号无效")
    return value


def relay_error(error):
    code = getattr(error, "code", "")
    if code == "tls_certificate_invalid":
        return WorkError("中转站HTTPS证书校验失败，请管理员续期证书或修复证书链", "unavailable")
    if getattr(error, "status", None) == 404:
        return WorkError("中转站未提供该音色服务或资源，请管理员核对新版部署", "unavailable")
    if code in {"insufficient_funds", "balance_insufficient", "commercial_balance_low"}:
        return WorkError("中转站余额不足，请充值后恢复原操作", "conflict")
    if code in {"price_pending", "model_unavailable", "provider_unavailable"}:
        return WorkError("该配音服务尚未开通或尚未确认价格，请联系管理员", "unavailable")
    if code == "quote_inactive":
        return WorkError("本次报价已过期，尚未受理新调用，请重新获取报价", "conflict")
    if code == "daily_limit":
        return WorkError("本次调用超过海客Key的每日预算，请调整预算后恢复原操作", "conflict")
    if getattr(error, "status", None) in {401, 403}:
        return WorkError("当前账号无权访问该音色或文件，请检查海客Key", "unavailable")
    return WorkError("中转站请求未完成，请检查服务状态；付费操作请保留原编号恢复", "unavailable")


class AudioCenter:
    def __init__(self, studio):
        self.studio = studio
        # Snapshot the connection: a concurrent settings change cannot mix hosts
        # or send the previous Key to the newly selected endpoint.
        self.sdk = studio.client(studio.configuration())
        summary = self.remote("/account/summary")
        account = summary.get("account_id") or summary.get("account_name")
        if not account:
            raise WorkError("中转站未返回账号身份，请管理员升级服务", "unavailable")
        self.account = hashlib.sha256(json.dumps([self.sdk.base_url, account], ensure_ascii=False).encode()).hexdigest()
        self.directory = studio.private / "audio-center" / self.account
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sdk.state_dir = self.directory / "intents"
        with studio.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS studio_audio_quotes(
                account TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY(account,id));
            CREATE TABLE IF NOT EXISTS studio_audio_operations(
                account TEXT NOT NULL, id TEXT NOT NULL, quote_id TEXT NOT NULL,
                maximum TEXT NOT NULL, outcome TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account,id), UNIQUE(account,quote_id));
            """)
            columns = {row[1] for row in db.execute('PRAGMA table_info(studio_audio_operations)')}
            if 'outcome' not in columns:
                db.execute('ALTER TABLE studio_audio_operations ADD COLUMN outcome TEXT')
            if 'attempts' not in columns:
                db.execute('ALTER TABLE studio_audio_operations ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0')

    def remote(self, path, body=None, **kwargs):
        try:
            return self.sdk.request(path, body, **kwargs)
        except Exception as error:
            raise relay_error(error) from None

    def voices(self):
        value = self.remote("/voices")
        for item in value.get("items", []):
            image = (item.get("preferences") or {}).get("image_file_id")
            if image:
                item["portrait_url"] = "/api/studio/audio-center/media/" + identifier(image)
        return value

    def preferences(self, data, voice_id=None):
        fields = {"speech_rate", "image_file_id"} if voice_id else {"voice_id"}
        if not data or set(data) - fields:
            raise WorkError("音色设置包含不支持的字段")
        path = "/voices/" + identifier(voice_id) + "/preferences" if voice_id else "/voice-preferences"
        return self.remote(path, data, method="PUT")

    def delete(self, voice_id):
        return self.remote("/voices/" + identifier(voice_id), method="DELETE")

    def upload(self, content, kind, filename):
        if kind not in {"audio", "image"} or not content or len(content) > 20 * 1024 * 1024:
            raise WorkError("请上传20MB内的样音或人物图")
        suffix = Path(filename).suffix.lower()
        supported = {"audio": {".wav", ".mp3", ".m4a", ".ogg"}, "image": {".png", ".jpg", ".jpeg"}}
        if suffix not in supported[kind]:
            raise WorkError("样音支持WAV、MP3、M4A、OGG；人物图支持PNG、JPEG")
        with tempfile.TemporaryDirectory(prefix="upload-", dir=self.directory) as temporary:
            source = Path(temporary) / ("source" + suffix)
            source.write_bytes(content)
            if kind == "image":
                from PIL import Image, ImageOps
                target = Path(temporary) / "portrait.jpg"
                try:
                    with Image.open(source) as image:
                        if min(image.size) < 256 or image.width * image.height > 40000000:
                            raise ValueError()
                        image = ImageOps.exif_transpose(image).convert("RGB")
                        image.thumbnail((2048, 2048))
                        image.save(target, quality=92)
                except Exception:
                    raise WorkError("人物图无法读取，宽高至少256像素") from None
            else:
                import subprocess
                from backlot.studio_render import media_probe
                from lib.ffmpeg_locator import resolve_ffmpeg_pair
                target = Path(temporary) / "sample.wav"
                try:
                    probe = media_probe(source)
                    if not probe.get("audio") or not 1 <= probe["duration"] <= 60:
                        raise ValueError()
                    ffmpeg, _ = resolve_ffmpeg_pair()
                    result = subprocess.run([
                        ffmpeg, "-v", "error", "-y", "-i", str(source), "-vn", "-ac", "1",
                        "-ar", "24000", "-c:a", "pcm_s16le", str(target)
                    ], capture_output=True, timeout=45)
                    if result.returncode:
                        raise ValueError()
                except Exception:
                    raise WorkError("样音无法读取，请上传1至60秒的清晰单人讲话录音") from None
            try:
                return self.sdk.upload(target, kind)
            except Exception as error:
                raise relay_error(error) from None

    def quote(self, data):
        if set(data) != {"model", "input"} or data["model"] not in MODELS or not isinstance(data["input"], dict):
            raise WorkError("请选择有效的海客配音或音色克隆服务")
        quote = self.remote("/quotes", {**data, "project_ref": "haike-audio-center"})
        operation = "call_" + hashlib.sha256((self.account + quote["id"]).encode()).hexdigest()[:32]
        with self.studio.db() as db:
            db.execute("INSERT INTO studio_audio_quotes VALUES(?,?,?)",
                       (self.account, quote["id"], json.dumps(quote, ensure_ascii=False)))
        return {**quote, "operation_id": operation}

    def operation(self, operation):
        if not isinstance(operation, str) or not OPERATION.fullmatch(operation):
            raise WorkError("操作编号无效")
        with self.studio.db() as db:
            row = db.execute("SELECT * FROM studio_audio_operations WHERE account=? AND id=?",
                             (self.account, operation)).fetchone()
        if not row:
            raise WorkError("操作不存在或不属于当前账号", "missing")
        return dict(row)

    def submit(self, data):
        if set(data) != {"quote_id", "max_charge_micros", "confirmed", "operation_id"} or data["confirmed"] is not True:
            raise WorkError("请先查看报价并确认本次费用上限")
        operation = data["operation_id"]
        if not isinstance(operation, str) or not OPERATION.fullmatch(operation):
            raise WorkError("请使用本次报价返回的操作编号")
        maximum = data["max_charge_micros"]
        if isinstance(maximum, bool) or not re.fullmatch(r"[0-9]{1,10}", str(maximum)) or int(maximum) > 1000000000:
            raise WorkError("费用上限无效，最高1,000元")
        with self.studio.db() as db:
            row = db.execute("SELECT data FROM studio_audio_quotes WHERE account=? AND id=?",
                             (self.account, data["quote_id"])).fetchone()
            if not row:
                raise WorkError("报价不存在或已更换账号，请重新读取报价", "missing")
            quote = json.loads(row[0])
            expected = "call_" + hashlib.sha256((self.account + quote["id"]).encode()).hexdigest()[:32]
            if expected != operation:
                raise WorkError("操作编号与报价不一致")
            if int(quote["max_charge_micros"]) > int(maximum):
                raise WorkError("费用上限低于报价，尚未提交")
            previous = db.execute("SELECT * FROM studio_audio_operations WHERE account=? AND id=?",
                                  (self.account, operation)).fetchone()
            if previous and previous['maximum'] != str(maximum):
                raise WorkError("原操作已保存费用上限，请恢复原操作", "conflict")
            resuming_unknown = bool(previous and previous['attempts'] and not previous['outcome'])
            db.execute("INSERT OR IGNORE INTO studio_audio_operations(account,id,quote_id,maximum) VALUES(?,?,?,?)",
                       (self.account, operation, quote["id"], str(maximum)))
            db.execute('UPDATE studio_audio_operations SET attempts=attempts+1,outcome=NULL WHERE account=? AND id=?',
                       (self.account, operation))
        # Application intent and SDK journal exist before the first network POST.
        try:
            self.sdk.confirm(quote, int(maximum), operation)
            job = self.sdk.resume(operation)
        except Exception as error:
            journal = self.sdk.state_dir / (operation + '.json')
            saved_job = False
            if journal.is_file():
                saved_job = bool(json.loads(journal.read_text(encoding='utf-8')).get('job_id'))
            definitive = getattr(error, 'code', '') in {
                'commercial_balance_low', 'daily_limit', 'maximum_low', 'quote_inactive', 'provider_disabled'
            } or getattr(error, "status", None) in {400, 401, 402, 403, 404, 422}
            # A 404 while querying an already submitted job is not evidence of
            # rejection. Keep its intent unresolved instead of enabling a new charge.
            if definitive and not resuming_unknown and not saved_job:
                outcome = {"id": operation, "operation_id": operation, "status": "failed",
                           "accepted": False, "error": str(relay_error(error)), "result": None}
                with self.studio.db() as db:
                    db.execute('UPDATE studio_audio_operations SET outcome=? WHERE account=? AND id=?',
                               (json.dumps(outcome, ensure_ascii=False), self.account, operation))
                return outcome
            return self.unknown(operation)
        return self.public_job(operation, job)

    @staticmethod
    def unknown(operation):
        return {"id": operation, "operation_id": operation, "status": "submission_unknown",
                "error": "尚未取得明确结果，请保留原操作编号查询，勿新建付费任务", "result": None}

    def job(self, operation):
        local = self.operation(operation)
        # GET polling never submits a paid request. An explicit repeated POST
        # can recover the same journal and idempotency key.
        try:
            job = self.sdk.request("/requests/" + operation)
        except Exception as error:
            if getattr(error, 'status', None) == 404 and local.get('outcome'):
                return json.loads(local['outcome'])
            return self.unknown(operation)
        return self.public_job(operation, job)

    def public_job(self, operation, job):
        self.operation(operation)
        value = {"id": operation, "operation_id": operation, "status": job.get("status", "submission_unknown"),
                 "charged_micros": job.get("charged_micros", "0"), "result": None}
        result = job.get("result") or {}
        if value["status"] == "succeeded":
            public = {}
            if result.get("voice"):
                public["voice"] = result["voice"]
            if result.get("audio_url") or result.get("audio_base64"):
                folder = self.directory / operation
                folder.mkdir(exist_ok=True)
                target = folder / "preview.audio"
                if not target.is_file():
                    if result.get("audio_base64"):
                        if len(result["audio_base64"]) > 28000000:
                            raise WorkError("试听文件过大，请缩短文本")
                        try:
                            content = base64.b64decode(result["audio_base64"], validate=True)
                        except ValueError:
                            raise WorkError("试听音频不完整，请恢复原操作") from None
                        target.write_bytes(content)
                    else:
                        from backlot.studio_avatar import download_result
                        download_result(result["audio_url"], target)
                public["audio_url"] = f"/api/studio/audio-center/jobs/{operation}/audio"
            value["result"] = public
        elif job.get("error"):
            value["error"] = "配音服务未完成，请核对原任务和账号额度后恢复"
        return value

    def preview(self, operation):
        self.operation(operation)
        path = self.directory / operation / "preview.audio"
        if not path.is_file():
            raise WorkError("试听音频尚未就绪，请先查询原操作", "missing")
        return path

    def media(self, file_id):
        # Recheck ownership with the current Key, including previously cached files.
        content = self.remote("/files/" + identifier(file_id), response_bytes=True)
        if len(content) > 5 * 1024 * 1024:
            raise WorkError("媒体文件过大")
        if content.startswith(b"\x89PNG"):
            media_type = "image/png"
        elif content.startswith(b"\xff\xd8\xff"):
            media_type = "image/jpeg"
        elif content.startswith(b"RIFF"):
            media_type = "audio/wav"
        else:
            raise WorkError("媒体文件格式不支持")
        return content, media_type
