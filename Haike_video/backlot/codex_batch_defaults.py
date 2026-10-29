"""Resolve omitted creation parameters once, using the existing account preset.

This performs local reads only, apart from caching an owned portrait. It never
creates a draft, quote, supplier operation or publication task.
"""
from __future__ import annotations

import copy
import hashlib
from io import BytesIO
from pathlib import Path

from backlot.codex_batch import BatchError, LocalAPI, _no_secrets, validate_spec

PARAMETERS = ("voice_id", "speech_rate", "template_id", "target_duration_seconds",
              "max_charge_micros", "allow_graphic_fallback", "network_materials_enabled")


def _portrait(content, root):
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or min(image.size) < 256:
                raise BatchError("默认人物图需为至少256像素的PNG、JPG或WebP")
            image.load()
            suffix = ".jpg" if image.format == "JPEG" else ".png"
            if image.format == "WEBP":
                buffer = BytesIO()
                image.convert("RGB").save(buffer, format="PNG")
                content = buffer.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise BatchError("默认人物图无法解码") from None
    folder = root / "Haike_video/.backlot/preset-media"
    for path in (folder, *folder.parents):
        if path == root:
            break
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise BatchError("预设图片缓存不能穿过目录链接")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (hashlib.sha256(content).hexdigest() + suffix)
    if target.is_symlink():
        raise BatchError("预设图片缓存不能是链接")
    try:
        with target.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if target.read_bytes() != content:
            raise BatchError("预设图片缓存校验失败，请保留原文件核对") from None
    return str(target)


def resolve_spec_defaults(raw, *, root=None, api=None):
    """Explicit fields win, including false; invalid explicit values never fall back."""
    _no_secrets(raw)
    if (not isinstance(raw, dict) or set(raw) - {"batch_id", "limit_micros", "items"}
            or not isinstance(raw.get("items"), list) or not 1 <= len(raw["items"]) <= 20):
        raise BatchError("请提供batch_id及1至20条已核实的选题规格")
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    api = api or LocalAPI()
    health = api.call("/api/health")
    if health.get("edition") != "haike-workflow-2" or Path(health.get("workspace", "")).resolve() != root:
        raise BatchError("服务不是当前新版项目，未读取预设")
    spec, portraits, scope = copy.deepcopy(raw), {}, None
    for item in spec["items"]:
        if not isinstance(item, dict):
            raise BatchError("视频槽位格式无效")
        # A previously frozen item is complete and remains independent of
        # today's account preferences. Ordinary resume never calls this helper.
        if "avatar_defaults_snapshot" in item:
            continue
        explicit_portrait = "portrait_path" in item
        audio_mode = "audio_path" in item
        parameters = tuple(key for key in PARAMETERS if not audio_mode or key not in {"voice_id", "speech_rate"})
        overrides = {key: item[key] for key in parameters if key in item}
        if explicit_portrait:
            overrides["portrait_file_id"] = None
        resolved = api.call("/api/studio/audio-center/avatar-defaults/resolve", {"overrides": overrides})
        if scope is not None and scope != resolved.get("scope_id"):
            raise BatchError("当前海客账号发生变化，请重新解析新规格")
        scope = resolved.get("scope_id")
        missing = set(resolved.get("missing_fields", [])) - ({"portrait_file_id"} if explicit_portrait else set())
        if audio_mode:
            missing -= {"voice_id", "speech_rate"}
        if missing:
            raise BatchError("请先补全口播默认设置：" + "、".join(sorted(missing)))
        values = resolved["values"]
        for key in parameters:
            if key not in item:
                item[key] = values[key]
        if audio_mode:
            pass  # Uploaded narration needs no TTS model, voice or rate.
        elif "model_id" not in item:
            item["model_id"] = resolved["voice_model"]
        elif item["model_id"] != resolved["voice_model"]:
            raise BatchError("明确指定的配音模型与所选音色不符，未自动换源")
        if not explicit_portrait:
            file_id = values.get("portrait_file_id")
            if not file_id:
                raise BatchError("请先设置默认形象或明确人物图片路径")
            if file_id not in portraits:
                portraits[file_id] = _portrait(api.portrait(file_id), root)
            item["portrait_path"] = portraits[file_id]
        if not audio_mode:
            item["avatar_defaults_snapshot"] = resolved["snapshot"]
    if "limit_micros" not in spec:
        spec["limit_micros"] = sum(item["max_charge_micros"] for item in spec["items"])
    return validate_spec(spec)
