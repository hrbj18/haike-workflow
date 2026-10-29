"""Account-scoped portrait refinement; original and candidate stay separate."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re

from lib.bailian_speech import operation_lock
from PIL import Image, ImageOps

from backlot.studio import atomic_private
from backlot.studio_audio import AudioCenter
from backlot.work_catalog import WorkError

MODEL = "haike/image-refinement"
PRESET_VERSION = "avatar-seated-v1"
PROMPT = """将人物调整为端正、放松自然的坐姿，采用适合数字人口播的上半身人像构图，头部完整、肩颈舒展、头顶适度留白，面部在画面中大小适中、清晰突出。
保持人物身份、年龄感、原有五官特征、发型、服装款式和配饰。精细优化面部质感，保持五官自然协调，面部光影柔和，肤色自然通透、适度提亮，保留原有肤色特征；不过度磨皮，保留毛孔与皮肤细节。眉间自然舒展，避免紧皱眉头；双眼清晰有神，避免油亮反光、塑料感和过度锐化，呈现真实、细腻的人像质感。
整理服饰，使衣着整齐，衣料褶皱自然合理，提升面料质感，避免过度平滑或改变原有款式。保留原背景风格，清理杂物和干扰元素，使人物与背景光照协调。
输出4:5竖幅、1K图像。"""


class RefinementCenter(AudioCenter):
    def __init__(self, studio):
        super().__init__(studio)
        # Reuse the proven quote/intent journal, with a distinct account scope
        # so the audio routes cannot resume or read image operations.
        identity = self.account
        self.account = "image-" + identity
        self.directory = studio.private / "image-refinement" / identity[:32]
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sdk.state_dir = self.directory / "intents"

    def remote(self, path, body=None, **kwargs):
        try:
            return self.sdk.request(path, body, **kwargs)
        except (ValueError, OSError) as error:
            if getattr(error, "code", "") in {"model_unavailable", "model_missing", "price_pending"}:
                raise WorkError("图片精修尚未开通或尚未确认价格；原图已保留，请联系管理员开通", "unavailable") from None
            raise WorkError("海客图片服务暂时不可用；原图已保留，请检查账号与服务状态", "unavailable") from None

    def task_path(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r"ir_[a-f0-9]{32}", task_id):
            raise WorkError("精修任务编号无效")
        return self.directory / (task_id + ".json")

    def read(self, task_id):
        path = self.task_path(task_id)
        if not path.is_file():
            raise WorkError("精修任务不存在或不属于当前账号", "missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def prepare(self, draft_id, asset_id):
        draft = self.studio.draft(draft_id)
        if draft["kind"] != "avatar" or (draft["input"].get("portrait") or {}).get("id") != asset_id:
            raise WorkError("请先保存当前项目的人物图片", "conflict")
        source = self.studio.asset(asset_id, draft_id)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        task_id = "ir_" + hashlib.sha256((draft_id + asset_id + digest + PRESET_VERSION + PROMPT).encode()).hexdigest()[:32]
        path = self.task_path(task_id)
        with operation_lock(self.directory / "locks" / task_id):
            if path.is_file():
                return self.read(task_id)
            # No paid submission during preparation. Unsupported models stop
            # before uploading the portrait to the gateway.
            capabilities = self.remote("/capabilities").get("items", [])
            if not any(v.get("model") == MODEL and v.get("status") == "available" for v in capabilities):
                raise WorkError("图片精修尚未开通；原图已保留，可使用原图继续", "unavailable")
            uploaded = self.upload(source.read_bytes(), "image", source.name)
            quote = self.remote("/quotes", {"model": MODEL, "input": {"prompt": PROMPT, "image_file": uploaded["id"]}, "project_ref": draft_id})
            operation = "call_" + hashlib.sha256((self.account + quote["id"]).encode()).hexdigest()[:32]
            with self.studio.db() as db:
                db.execute("INSERT INTO studio_audio_quotes VALUES(?,?,?)", (self.account, quote["id"], json.dumps(quote, ensure_ascii=False)))
            record = {"id": task_id, "draft_id": draft_id, "source_id": asset_id, "source_sha256": digest,
                      "source_url": f"/api/studio/assets/{asset_id}", "preset_version": PRESET_VERSION, "prompt": PROMPT,
                      "quote": {**quote, "operation_id": operation}, "status": "quoted", "decision": None}
            atomic_private(path, record)
            return record

    def get(self, task_id):
        self.task_path(task_id)
        with operation_lock(self.directory / "locks" / task_id):
            record = self.read(task_id)
            if record["status"] != "quoted":
                try:
                    result = self.job(record["quote"]["operation_id"])
                except WorkError as error:
                    if error.code != 'missing':
                        raise
                    # A process can stop between the image record and the
                    # shared journal. GET must still never submit a request.
                    result = self.unknown(record["quote"]["operation_id"])
                record.update(result)
                record["id"] = task_id
                atomic_private(self.task_path(task_id), record)
            return record

    def renew(self, task_id):
        self.task_path(task_id)
        with operation_lock(self.directory / "locks" / task_id):
            record = self.read(task_id)
            if record['status'] != 'quoted' or record.get('decision'):
                raise WorkError("已提交的精修只恢复原任务，不能重新报价", "conflict")
            quote = self.remote('/quotes/' + record['quote']['id'] + '/renew', {'confirmed': True})
            if any(quote.get(k) != record['quote'].get(k) for k in ('id', 'model', 'price', 'quoted_usage', 'max_charge_micros')):
                raise WorkError("报价快照发生变化，已停止提交", "conflict")
            quote['operation_id'] = record['quote']['operation_id']
            record['quote'] = quote
            with self.studio.db() as db:
                db.execute('UPDATE studio_audio_quotes SET data=? WHERE account=? AND id=?',
                           (json.dumps(quote, ensure_ascii=False), self.account, quote['id']))
            atomic_private(self.task_path(task_id), record)
            return record

    def start(self, task_id, data):
        self.task_path(task_id)
        with operation_lock(self.directory / "locks" / task_id):
            record = self.read(task_id)
            draft = self.studio.draft(record["draft_id"])
            if (draft["input"].get("portrait") or {}).get("id") != record["source_id"]:
                raise WorkError("人物图片已经更换，旧图不会再提交修图", "conflict")
            if set(data) != {"confirmed", "max_charge_micros"} or data["confirmed"] is not True:
                raise WorkError("请确认本次精修费用上限")
            if record.get("decision"):
                raise WorkError("本图已确认采用，请勿重复提交精修", "conflict")
            maximum = str(data["max_charge_micros"])
            if not re.fullmatch(r"[0-9]{1,10}", maximum) or not int(record['quote']['max_charge_micros']) <= int(maximum) <= 1000000000:
                raise WorkError("精修费用上限无效或低于报价")
            if record.get("maximum") is not None and record["maximum"] != maximum:
                raise WorkError("请恢复原精修任务及费用上限", "conflict")
            record.update(status="submitting", maximum=maximum)
            atomic_private(self.task_path(task_id), record)
            value = super().submit({"quote_id": record["quote"]["id"], "operation_id": record["quote"]["operation_id"],
                                    "confirmed": True, "max_charge_micros": maximum})
            record.update(value)
            if record.get("error"):
                record["error"] = "精修调用未完成，请核对原任务、海客额度或报价有效期"
            record["id"] = task_id
            atomic_private(self.task_path(task_id), record)
            return record

    def public_job(self, operation, job):
        self.operation(operation)
        value = {"operation_id": operation, "status": job.get("status", "submission_unknown"),
                 "charged_micros": job.get("charged_micros", "0"), "result": None}
        if value["status"] == "succeeded":
            folder = self.directory / operation
            folder.mkdir(exist_ok=True)
            raw_path, target = folder / "raw", folder / "result.png"
            # A local decode/normalization failure can be recovered by querying
            # the same operation; its paid request is never repeated.
            if not target.is_file():
                encoded = (job.get("result") or {}).get("image_base64")
                if not raw_path.is_file():
                    if not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024:
                        raise WorkError("精修图片回执缺失，请核对原任务", "unavailable")
                    try:
                        raw_path.write_bytes(base64.b64decode(encoded, validate=True))
                    except ValueError:
                        raise WorkError("精修图片回执损坏，请核对原任务", "unavailable") from None
                try:
                    with Image.open(io.BytesIO(raw_path.read_bytes())) as image:
                        if image.format not in {"PNG", "JPEG", "WEBP"} or min(image.size) < 64 or max(image.size) > 7000:
                            raise ValueError()
                        image = ImageOps.exif_transpose(image).convert("RGBA")
                        background = Image.new("RGBA", image.size, "white")
                        background.alpha_composite(image)
                        normalized = ImageOps.fit(background.convert("RGB"), (1024, 1280), Image.Resampling.LANCZOS)
                        temporary = folder / "result.tmp"
                        normalized.save(temporary, "PNG")
                        temporary.replace(target)
                except (OSError, ValueError, Image.DecompressionBombError):
                    raise WorkError("精修图本地处理未完成，原始结果已保留，请查询原任务恢复", "unavailable") from None
            value["result"] = {"image_url": f"/api/studio/refinement/media/{operation}"}
        elif job.get("error"):
            value["error"] = "精修尚未完成，请核对原任务；结果未知时不要重新提交"
        return value

    def image(self, operation):
        self.operation(operation)
        path = self.directory / operation / "result.png"
        if not path.is_file():
            raise WorkError("精修结果尚未就绪", "missing")
        return path

    def decide(self, task_id, use_refined):
        self.task_path(task_id)
        with operation_lock(self.directory / "locks" / task_id):
            record = self.read(task_id)
            draft = self.studio.draft(record["draft_id"])
            portrait = draft["input"].get("portrait") or {}
            if record.get("adopted_asset") and portrait.get("id") == record["adopted_asset"]["id"]:
                return {"task": record, "draft": draft}
            if portrait.get("id") != record["source_id"]:
                raise WorkError("人物图片已经更换，旧精修结果不会覆盖新图片", "conflict")
            if use_refined:
                if record["status"] != "succeeded":
                    raise WorkError("请先等待精修图完成")
                asset = record.get("adopted_asset")
                if not asset:
                    asset = self.studio.save_asset(draft["id"], "精修人物.png", "image", self.image(record["quote"]["operation_id"]).read_bytes())
                    asset.update(refined=True, original_id=record["source_id"], preset_version=record["preset_version"])
                    record["adopted_asset"] = asset
                    atomic_private(self.task_path(task_id), record)
                draft = self.studio.save_draft({**draft, "input": {**draft["input"], "portrait": asset}})
            record["decision"] = "refined" if use_refined else "original"
            atomic_private(self.task_path(task_id), record)
            return {"task": record, "draft": draft}
