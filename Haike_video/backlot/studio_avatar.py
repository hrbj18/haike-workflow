"""One-Key avatar producer. Native queue owns execution; intents own paid retries."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import math
import re
import shutil
import socket
import subprocess
from http.client import HTTPSConnection
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler
from uuid import uuid4

from backlot.studio import Studio, atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, sha


class _OfflineAsrFallback(Exception):
    def __init__(self, job):
        self.job = job


def key_identity(studio):
    from backlot.studio_services import service_mode
    if service_mode(studio) == 'internal':
        return hashlib.sha256(json.dumps(['internal-local', str(studio.private.resolve())]).encode()).hexdigest()
    c = studio.configuration()
    return hashlib.sha256(json.dumps([c.get("base_url"), c.get("api_key")]).encode()).hexdigest()


def renew_if_expired(sdk, quote):
    expiry=quote.get("expires_at")
    if not expiry or datetime.fromisoformat(expiry.replace("Z","+00:00"))>datetime.now(timezone.utc): return quote
    try: renewed=sdk.request("/quotes/"+quote["id"]+"/renew",{"confirmed":True})
    except Exception: raise WorkError("原报价已过期，已完成声音和素材保留；请管理员核对报价续期服务后恢复原任务", "unavailable") from None
    if any(renewed.get(k)!=quote.get(k) for k in ("id","model","price","quoted_usage","max_charge_micros")):
        raise WorkError("报价续期改变了原费用或模型快照，请重新确认；未提交新付费调用")
    return renewed


def prepare_audio(source, target, rate=1):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    info = media_probe(source)
    if not info.get("audio") or not 0 < info["duration"] / rate <= 120:
        raise WorkError("数字人口播音频需要在120秒内，请截取合适的口播")
    duration = math.ceil(info["duration"] / rate * 25) / 25
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source), "-af", f"atempo={rate},apad,atrim=0:{duration}", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target)], capture_output=True, timeout=60)
    if r.returncode: raise WorkError("无法准备数字人驱动音轨")
    return duration


def prepare_image(source, target):
    from PIL import Image, ImageOps
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1024, 1280))
        image.save(target, quality=94)


def validate_voice(value):
    if value.get("soundMode") == "voice" and value.get("voiceId") == "haike/tencent-tts":
        raise WorkError("腾讯精品配音已移除，请重新选择 CosyVoice，或上传已有音频")
    if value.get("soundMode") == "voice":
        from backlot.studio_audio import TTS_MODELS, identifier
        if value.get("modelId") not in TTS_MODELS:
            raise WorkError("请在海客配音中心重新选择音色，或上传已有音频")
        identifier(value.get("voiceId"))


def tts_request(draft):
    """New drafts carry separate model/voice identities; frozen legacy jobs keep
    their original model-only request and local tempo processing."""
    value = draft["input"]
    if value.get("modelId"):
        return value["modelId"], {"text": draft["text"], "voice_id": value["voiceId"],
                                  "speech_rate": value.get("rate", 1)}
    return value["voiceId"], {"text": draft["text"]}


def validate(studio, draft):
    if studio.template(draft["template_id"])["kind"] != "avatar": raise WorkError("请选择数字人口播模板")
    value = draft["input"]
    validate_voice(value)
    from backlot.studio_n1 import TEMPLATE_ID as N1_TEMPLATE, settings as n1_settings
    if draft["template_id"] == N1_TEMPLATE:
        n1_settings(draft, studio=studio)
    from backlot.studio_storyboard import options, motion_options
    options(studio, draft)
    motion_options(draft)
    from backlot.studio_network_materials import validate_preflight
    validate_preflight(studio, draft)
    if not draft["text"].strip() or len(draft["text"]) > 5000: raise WorkError("口播文案需要1至5,000字")
    image = value.get("portrait") or {}
    studio.asset(image.get("id"), draft["id"])
    if value.get("soundMode") == "audio":
        audio = studio.asset((value.get("audio") or {}).get("id"), draft["id"])
        if media_probe(audio)["duration"] > 120: raise WorkError("数字人口播音频最长120秒")
        if draft["template_id"] == N1_TEMPLATE: n1_settings(draft, media_probe(audio)["duration"], studio)
    elif value.get("soundMode") == "voice":
        rate = value.get("rate", 1)
        if type(rate) not in {float, int} or not math.isfinite(rate) or not .5 <= rate <= 2:
            raise WorkError("配音语速需要在0.5至2倍之间")
    else: raise WorkError("请选择已有音频或网关配音")
    title = draft["title"]
    maximum = 120 if value.get("motion") or draft["template_id"] == N1_TEMPLATE else 36 if draft["template_id"].startswith("avatar-template3") else 16
    if len(title) > maximum: raise WorkError(f"当前版式标题最多{maximum}字，请在排版配置中缩短")
    composer = Path(__file__).resolve().parents[1] / "remotion-composer/node_modules"
    if not composer.is_dir(): raise WorkError("缺少本地Remotion渲染依赖，尚未提交付费调用")


def quote(studio, draft):
    validate(studio, draft)
    from backlot.studio_asr import snapshot
    from backlot.studio_network_materials import needs_clock
    clock_required = needs_clock(draft)
    asr = snapshot(studio) if clock_required else {"provider": "gateway"}
    sdk = studio.client()
    identity = "studioquote-" + uuid4().hex
    folder = studio.projects_root / draft["id"] / "assets/studio-quotes" / identity
    folder.mkdir(parents=True, exist_ok=True)
    portrait = folder / "portrait.jpg"
    prepare_image(studio.asset(draft["input"]["portrait"]["id"], draft["id"]), portrait)
    prepared = {"portrait_path": str(portrait), "image_file": sdk.upload(portrait, "image")["id"]}
    quotes = {}
    if draft["input"]["soundMode"] == "audio":
        audio = folder / "narration.wav"
        duration = prepare_audio(studio.asset(draft["input"]["audio"]["id"], draft["id"]), audio)
        prepared.update(audio_path=str(audio), duration=duration, audio_file=sdk.upload(audio, "audio")["id"])
        quotes["avatar"] = sdk.quote("haike/avatar", {"audio_file": prepared["audio_file"], "image_file": prepared["image_file"]}, draft["id"])
        if clock_required and asr["provider"] == "gateway": quotes["asr"] = sdk.quote("haike/tencent-asr", {"audio_file": prepared["audio_file"]}, draft["id"])
        elif clock_required and asr["provider"] == "bailian":
            local_audio = sdk.prepare_asr_audio(audio)
            prepared["bailian_audio_file"] = local_audio["id"]
            quotes["asr_bailian"] = sdk.quote(asr["model"], {"audio_file": local_audio["id"]}, draft["id"])
    else:
        model, inputs = tts_request(draft)
        quotes["tts"] = sdk.quote(model, inputs, draft["id"])
        # Availability is checked before any TTS charge. Its exact avatar quote needs the real audio.
        models = {m.get("id") or m.get("model") for m in sdk.request("/capabilities").get("items", [])}
        needs_asr = clock_required
        required = {"haike/avatar"} | ({"haike/tencent-asr"} if needs_asr and asr["provider"] == "gateway" else set())
        if required - models: raise WorkError("数字人或字幕模型尚不可用，请由管理员确认成本费率后再制作")
    data = {"id": identity, "draft": draft, "prepared": prepared, "quotes": quotes, "asr": asr, "key_identity": key_identity(studio), "created_at": datetime.now(timezone.utc).isoformat()}
    with studio.db() as db: db.execute("INSERT INTO studio_quotes VALUES(?,?)", (identity, json.dumps(data, ensure_ascii=False)))
    return public_quote(data)


def public_quote(data):
    metadata = ('mode', 'billing_mode', 'provider', 'provider_model', 'estimate_only',
                'provider_budget_enforced', 'billing_note', 'backend')
    items = [{"stage": stage, "model": q["model"], "max_charge_micros": q["max_charge_micros"],
              **{key: q[key] for key in metadata if key in q}} for stage, q in data['quotes'].items()]
    estimated = any(item.get('estimate_only') for item in items)
    return {"id": data["id"], "revision": data["draft"]["revision"], "known_max_micros": sum(int(q["max_charge_micros"]) for q in data["quotes"].values()),
            "needs_audio_quote": data["draft"]["input"]["soundMode"] == "voice", "ai_trial": data["draft"]["input"].get("ai", {}).get("enabled", False) or data["draft"]["input"].get("network_materials_enabled", False),
            "mode": "mixed" if estimated else "gateway", "estimate_only": estimated,
            "billing_note": "含内部供应商直连估算，供应商最终账单为准；中转服务按账号计费" if estimated else "中转服务按账号额度与本次报价计费",
            "items": items + ([{"stage": "asr", "model": "local/whisper", "max_charge_micros": "0"}] if data.get("asr", {}).get("provider") == "local-whisper" else [])}


def frozen_request(studio, draft, quote_id, maximum):
    # New submissions cannot reuse a retired-model quote. Already queued requests
    # keep their original execution state and resume through the native queue.
    validate_voice(draft["input"])
    with studio.db() as db: row = db.execute("SELECT data FROM studio_quotes WHERE id=?", (quote_id,)).fetchone()
    if not row: raise WorkError("请先读取本次制作报价")
    data = json.loads(row[0])
    if data["draft"] != draft or data["key_identity"] != key_identity(studio): raise WorkError("内容或Key已改变，请重新读取报价")
    if type(maximum) is not int or not 1 <= maximum <= 1000000000: raise WorkError("请填写有效费用上限，最高1,000元")
    if maximum < public_quote(data)["known_max_micros"]: raise WorkError("费用上限低于已读取报价，未提交任务")
    # The original gateway quote expires server-side. Do not silently replace it before charging.
    return {**data, "max_charge_micros": maximum, "render_id": "studio-" + str(draft["revision"])}


def public_media_address(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if ips and all(ip.is_global for ip in ips): return str(ips[0])
    # A local TUN fake-DNS address is not an origin address. For known public
    # media hosts only, verify public DNS over HTTPS and pin the actual socket.
    known = (re.fullmatch(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com", host)
             or re.fullmatch(r"v[0-9]+(?:-[a-z0-9]+)*\.douyinvod\.com", host)
             or host in {"videos.pexels.com", "images.pexels.com", "rh-comfyui01.tos-cn-beijing.volces.com",
                         "www.douyin.com"})
    benchmark = ipaddress.ip_network("198.18.0.0/15")
    if not known or not ips or not all(ip.version == 4 and ip in benchmark for ip in ips):
        raise WorkError("供应商媒体地址不能指向本地网络")
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    # Some local proxies cannot validate the first resolver's certificate chain.
    # Both fixed resolvers still require normal TLS and a public destination;
    # the resulting media socket remains pinned to the checked IP below.
    for resolver in ("https://1.1.1.1/dns-query", "https://dns.alidns.com/resolve"):
        try:
            dns = resolver + "?" + urlencode({"name": host, "type": "A"})
            with build_opener(ProxyHandler({}), NoRedirect()).open(Request(dns, headers={"Accept": "application/dns-json"}), timeout=10) as response:
                raw = response.read(65537)
            if len(raw) > 65536: raise ValueError()
            data = json.loads(raw)
            answers = [ipaddress.ip_address(a["data"]) for a in data.get("Answer", []) if a.get("type") == 1]
            if data.get("Status") != 0 or not answers: continue
        except Exception:
            continue
        if not all(a.is_global for a in answers):
            raise WorkError("代理DNS未能核对真实公网媒体地址，请核对代理DNS后恢复原任务")
        return str(answers[0])
    raise WorkError("代理DNS未能核对真实公网媒体地址，请核对代理DNS后恢复原任务")


def media_https_handler(address):
    class PinnedConnection(HTTPSConnection):
        def connect(self):
            if self._tunnel_host: raise WorkError("媒体下载不允许额外代理隧道")
            self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
    class Handler(HTTPSHandler):
        def https_open(self, request):
            return self.do_open(PinnedConnection, request, context=self._context)
    return Handler()


def download_result(url, path, referer=None, *, max_bytes=100 * 1024 * 1024):
    # Gateway results contain supplier media only. Follow validated HTTPS redirects, with no Key headers.
    if type(max_bytes) is not int or not 1 <= max_bytes <= 100 * 1024 * 1024:
        raise WorkError("媒体下载大小上限无效")
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    from urllib.error import HTTPError
    for _ in range(5):
        p = urlsplit(url)
        # Some CosyVoice receipts use HTTP OSS links. Upgrade only the known
        # output hosts; preserve signatures and keep TLS/DNS checks below.
        if p.scheme == "http" and not p.username and not p.password and p.port in {None, 80} and re.fullmatch(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com", p.hostname or ""):
            url = p._replace(scheme="https", netloc=p.hostname).geturl()
            p = urlsplit(url)
        if p.scheme != "https" or p.username or p.password or not p.hostname: raise WorkError("供应商媒体地址无效")
        address = public_media_address(p.hostname, p.port or 443)
        opener = build_opener(ProxyHandler({}), NoRedirect(), media_https_handler(address))
        try:
            headers = {"User-Agent": "HaikeVideo/1.0", **({"Referer": referer} if referer else {})}
            with opener.open(Request(url, headers=headers), timeout=90) as response:
                temporary = path.with_suffix(path.suffix + ".part")
                count = 0
                try:
                    with temporary.open("wb") as out:
                        while chunk := response.read(1024 * 1024):
                            count += len(chunk)
                            if count > max_bytes: raise WorkError("供应商媒体超过下载大小上限")
                            out.write(chunk)
                    temporary.replace(path)
                except BaseException:
                    try: temporary.unlink(missing_ok=True)
                    except OSError: pass
                    raise
                return
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}: raise WorkError("供应商媒体暂时无法下载，请恢复原任务") from None
            from urllib.parse import urljoin
            url = urljoin(url, exc.headers.get("Location", ""))
    raise WorkError("供应商媒体跳转过多")


def captions(result, duration, split=True, max_chars=18):
    """Sentence timing comes from ASR, never from input text/duration guesses."""
    values = result.get("segments") or result.get("sentences") or []
    if not values:
        for match in re.finditer(r"\[(\d+):(\d+(?:\.\d+)?),(\d+):(\d+(?:\.\d+)?)\]\s*([^\n]+)", result.get("text") or ""):
            values.append({"start": int(match[1]) * 60 + float(match[2]), "end": int(match[3]) * 60 + float(match[4]), "text": match[5].strip()})
    out = []
    for s in values:
        start, end, text = float(s["start"]), min(float(s["end"]), duration), str(s["text"]).strip()
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and text): continue
        if split and s.get("words"):
            group = []
            for word in s["words"]:
                if group and len("".join(w["text"] for w in group)) + len(word["text"]) > max_chars:
                    out.append({"text": "".join(w["text"] for w in group).strip(), "startMs": group[0]["start"]*1000,
                                "endMs": group[-1]["end"]*1000, "timestampMs": None, "confidence": None})
                    group = []
                group.append(word)
            if group:
                out.append({"text": "".join(w["text"] for w in group).strip(), "startMs": group[0]["start"]*1000,
                            "endMs": group[-1]["end"]*1000, "timestampMs": None, "confidence": None})
            continue
        # Short groups inside each recognised sentence; this is sentence-aligned, not word-level karaoke.
        groups = [text[i:i+max_chars] for i in range(0, len(text), max_chars)] if split else [text]
        for i, group in enumerate(groups):
            out.append({"text": group, "startMs": (start+(end-start)*i/len(groups))*1000, "endMs": (start+(end-start)*(i+1)/len(groups))*1000, "timestampMs": None, "confidence": None})
    if not out: raise WorkError("语音识别没有返回可用句级时间轴，保留音频和数字人，请检查字幕阶段")
    return out


def clock_captions(result, duration):
    # GPT can select observed word boundaries even if Whisper returns a single
    # long segment. Display wrapping must not determine storyboard timing.
    segments = result.get("segments") or []
    if not segments or not all(s.get("words") for s in segments if s.get("text", "").strip()):
        return captions(result, duration, split=False)
    return [{"text": w["text"].strip(), "startMs": w["start"]*1000, "endMs": min(w["end"], duration)*1000,
             "timestampMs": None, "confidence": w.get("probability"), "clock": "word"}
            for s in result["segments"] for w in s.get("words", []) if w.get("text", "").strip() and w["end"] > w["start"]]


def development_captions(request, project_dir, output_dir):
    """Private queue-only N1 layout sample. Public draft/quote schemas omit this."""
    import wave
    from backlot.studio_n1 import TEMPLATE_ID
    sample = request["development_sample"]
    draft = request["draft"]
    inputs = draft["input"]
    if (not isinstance(sample, dict) or set(sample) != {"silent", "label", "captions"}
            or sample["silent"] is not True or sample["label"] != "版式与动效演示"
            or draft["template_id"] != TEMPLATE_ID or inputs.get("soundMode") != "audio"
            or inputs.get("subtitles") is not False or inputs.get("ai", {}).get("enabled") or inputs.get("network_materials_enabled")
            or inputs.get("motion") or request.get("quotes") != {}):
        raise WorkError("本地版式样片必须明确无声、禁用AI与识别，并且没有付费报价")
    prepared = request["prepared"]
    video = Path(output_dir) / "avatar-source.mp4"
    audio = Path(prepared.get("audio_path", ""))
    duration = prepared.get("duration")
    if (type(duration) not in {int, float} or not math.isfinite(duration) or not 0 < duration <= 120
            or not video.is_file() or video.is_symlink() or not audio.is_file() or audio.is_symlink()
            or not video.resolve().is_relative_to(Path(project_dir).resolve())
            or not audio.resolve().is_relative_to(Path(project_dir).resolve())):
        raise WorkError("本地版式样片需要已有的人物视频和项目内无声音轨")
    for source, kind in ((audio, "audio"), (video, "video")):
        info = media_probe(source)
        if not info.get(kind) or abs(info["duration"] - duration) > .1:
            raise WorkError("本地版式样片已有素材与演示时钟不匹配")
    try:
        with wave.open(str(audio), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 24000, "NONE"):
                raise ValueError()
            if abs(stream.getnframes() / stream.getframerate() - duration) > .001: raise ValueError()
            while block := stream.readframes(32768):
                if any(block): raise ValueError()
    except (ValueError, wave.Error, EOFError, OSError):
        raise WorkError("版式演示必须使用PCM16/24kHz单声道全零音轨，不能冒充口播验收") from None
    raw = sample["captions"]
    if not isinstance(raw, list) or len(raw) > 100: raise WorkError("演示字幕数量无效")
    previous = 0
    out = []
    for cue in raw:
        if not isinstance(cue, dict) or set(cue) - {"text", "startMs", "endMs", "timestampMs", "confidence"}:
            raise WorkError("演示字幕需要明确的手工时间范围")
        text, start, end = cue.get("text"), cue.get("startMs"), cue.get("endMs")
        if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 18
                or type(start) not in {int, float} or type(end) not in {int, float}
                or not math.isfinite(start) or not math.isfinite(end)
                or not previous <= start < end <= duration * 1000):
            raise WorkError("演示字幕每条最多18字，需按顺序位于演示时长内")
        previous = end
        out.append({"text": text.strip(), "startMs": start, "endMs": end, "timestampMs": None, "confidence": None})
    return out


def _recovered_avatar_receipt(video, duration, job, previous=None):
    """Validate an original uncertain job's artifact without settling its bill."""
    if not video.is_file() or video.is_symlink():
        raise WorkError("原数字人视频文件无效，请核对原任务产物", "unavailable")
    digest = sha(video)
    if previous and (previous.get("job_id") != job["id"] or previous.get("sha256") != digest):
        raise WorkError("已验证的原数字人视频发生变化，保留文件待核对；未新建调用", "unavailable")
    info = media_probe(video)
    stream = info.get("video")
    actual = info.get("duration")
    if (not isinstance(stream, dict)
            or any(type(stream.get(key)) is not int or stream[key] <= 0 for key in ("width", "height"))
            or type(actual) not in {int, float} or not math.isfinite(actual) or actual <= 0
            or type(duration) not in {int, float} or not math.isfinite(duration) or not 0 < duration <= 120
            or abs(actual - duration) > 1):
        raise WorkError("原数字人视频的流、尺寸或时长未通过校验，请恢复同一任务", "unavailable")
    if stream.get("duration") is not None:
        try:
            stream_duration = float(stream["duration"])
        except (TypeError, ValueError):
            stream_duration = math.nan
        if not math.isfinite(stream_duration) or stream_duration <= 0 or abs(stream_duration - duration) > 1:
            raise WorkError("原数字人视频流时长与驱动音频不一致，请恢复同一任务", "unavailable")
    return {"job_id": job["id"], "status": job["status"], "sha256": digest,
            "duration": actual, "width": stream["width"], "height": stream["height"],
            "billing_pending": True, "billing_usage_status": (job.get("billing") or {}).get("usage_status"),
            "at": (previous or {}).get("at") or datetime.now(timezone.utc).isoformat()}


def _quarantine_avatar_download(video, output_dir):
    """Preserve only this attempt's unverified download, without touching caches."""
    if video.is_file() and not video.is_symlink() and video.resolve().parent == output_dir.resolve():
        video.replace(video.with_name("avatar-source.unverified-" + uuid4().hex + ".mp4"))


def run_avatar(project_dir, request, sdk=None, *, progress=None):
    studio = Studio(Path(project_dir).parent)
    if request["key_identity"] != key_identity(studio): raise WorkError("API Key已改变；恢复付费任务前请恢复原账户连接")
    development = "development_sample" in request
    sdk = sdk if development else sdk or studio.client()
    output_dir = Path(project_dir) / "renders" / request["render_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "gateway-state.json"
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {"stages": {}, "prepared": request["prepared"]}
    def save(): atomic_private(state_path, state)
    def report(stage):
        state["progress"] = {"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat()}
        save()
        if progress is not None:
            progress(stage)
    def paid(stage, model, inputs):
        if development: raise WorkError("本地版式样片禁止提交任何供应商调用")
        label = {"tts": "生成口播配音", "asr": "识别字幕时间轴", "asr_bailian": "百炼识别字幕时间轴", "avatar": "生成数字人口播"}.get(stage, "生成画面素材")
        report(label + "：核对原任务及费用")
        if stage not in state["stages"]:
            q = request["quotes"].get(stage) or sdk.quote(model, inputs, request["draft"]["id"])
            committed = sum(int(s["quote"]["max_charge_micros"]) for s in state["stages"].values())
            if committed + int(q["max_charge_micros"]) > request["max_charge_micros"]:
                raise WorkError("后续报价超过本次总费用上限，已完成产物保留；未提交这一步")
            state["stages"][stage] = {"quote": q}; save()
        s = state["stages"][stage]
        original_job_id = (s.get("job") or {}).get("id")
        if stage == "avatar" and s.get("job") and not s.get("intent"):
            raise WorkError("原数字人调用意图缺失，请核对原记录；未新建付费调用", "unavailable")
        if not s.get("job"):
            s["quote"]=renew_if_expired(sdk,s["quote"]);save()
        if not s.get("intent"):
            identity = "call_" + hashlib.sha256((request["id"] + ":" + stage).encode()).hexdigest()[:32]
            s["intent"] = sdk.confirm(s["quote"], int(s["quote"]["max_charge_micros"]), identity); save()
        report(label + "：等待供应商结果")
        job = sdk.wait(s["intent"], timeout=600)
        if stage == "avatar" and original_job_id and job.get("id") != original_job_id:
            raise WorkError("读回的数字人任务与原调用编号不一致，保留原记录待核对", "unavailable")
        s["job"] = job; save()
        if job["status"] != "succeeded":
            result = job.get("result") or {}
            if (stage == "avatar" and job["status"] == "submission_unknown" and s.get("intent")
                    and isinstance(job.get("id"), str) and job["id"].strip()
                    and isinstance(result, dict) and isinstance(result.get("video_url"), str) and result["video_url"].strip()):
                report("原数字人视频已返回：复用原产物，费用仍待核对")
                return result
            from backlot.studio_asr import should_fallback
            if stage == "asr_bailian" and should_fallback(request.get("asr", {}), job):
                raise _OfflineAsrFallback(job)
            if job["status"] in {"failed", "cancelled"}: raise WorkError("模型任务未成功，请到账户中心核对原调用明细")
            raise WorkError("原模型任务仍在处理或结果待核对，请恢复此任务；不会新建付费调用", "unavailable")
        return job["result"]
    try:
        p = state["prepared"]; draft = request["draft"]
        asr = request.get("asr", {"provider": "gateway"})
        if not development and asr["provider"] == "local-whisper":
            from backlot.studio_asr import configuration, identity
            if identity(configuration(studio)) != asr["identity"]:
                raise WorkError("字幕引擎已改变，请恢复原配置后继续原任务")
        if development and state["stages"]: raise WorkError("本地版式样片不能包含供应商任务状态")
        manual_cues = development_captions({**request, "prepared": p}, project_dir, output_dir) if development else None
        if not p.get("audio_path"):
            report("准备口播音轨")
            raw = output_dir / "tts-source.wav"
            if not raw.exists():
                model, inputs = tts_request(draft)
                result = paid("tts", model, inputs)
                if result.get("audio_base64"): raw.write_bytes(base64.b64decode(result["audio_base64"], validate=True))
                else: download_result(result["audio_url"], raw)
            audio = output_dir / "narration.wav"
            # The selected speed is already applied by the relay for new jobs.
            # Applying atempo again would square the user's chosen multiplier.
            local_rate = 1 if draft["input"].get("modelId") else draft["input"].get("rate", 1)
            duration = prepare_audio(raw, audio, local_rate)
            p.update(audio_path=str(audio), duration=duration, audio_file=sdk.upload(audio, "audio")["id"]); save()
        cues = manual_cues or []
        clock_cues = []
        caption_timing = "off"
        from backlot.studio_network_materials import needs_clock, enabled as network_enabled, write_result as write_network_result
        if not development and needs_clock(draft):
            if asr["provider"] == "local-whisper":
                report("本地识别字幕时间轴")
                from backlot.studio_asr import transcribe
                result = transcribe(studio, asr, Path(p["audio_path"]), output_dir, p["duration"])
            elif asr["provider"] == "bailian":
                report("百炼识别字幕时间轴")
                if not p.get("bailian_audio_file"):
                    p["bailian_audio_file"] = sdk.prepare_asr_audio(Path(p["audio_path"]))["id"]
                    save()
                try:
                    result = paid("asr_bailian", asr["model"], {"audio_file": p["bailian_audio_file"]})
                    state["asr_resolution"] = {"provider": "bailian", "model": asr["model"],
                                               "stage": "asr_bailian", "updated_at": datetime.now(timezone.utc).isoformat()}
                except _OfflineAsrFallback as rejection:
                    from backlot.studio_asr import transcribe
                    reason = rejection.job["failure_kind"]
                    report("百炼Key无效，使用本地Whisper" if reason == "invalid_key" else "百炼余额不足，使用本地Whisper")
                    result = transcribe(studio, asr["fallback"], Path(p["audio_path"]), output_dir, p["duration"])
                    state["asr_resolution"] = {"provider": "local-whisper", "fallback_from": "bailian",
                                               "reason": reason, "rejected_job_id": rejection.job["id"],
                                               "updated_at": datetime.now(timezone.utc).isoformat()}
                save()
            else:
                result = paid("asr", "haike/tencent-asr", {"audio_file": p["audio_file"]})
            cues = captions(result, p["duration"], max_chars=14 if draft["template_id"] == "avatar-deepblue-n1-v1" else 18)
            clock_cues = clock_captions(result, p["duration"])
            word_clock = any(segment.get("words") for segment in result.get("segments", []))
            caption_timing = ("Whisper word-level" if result.get("provider") == "local-whisper"
                              else "Bailian word-level" if word_clock and asr["provider"] == "bailian"
                              else "ASR word-level" if word_clock else "ASR sentence-level")
        from backlot.studio_storyboard import produce
        from backlot.studio_n1 import TEMPLATE_ID as N1_TEMPLATE, settings as n1_settings
        if draft["template_id"] == N1_TEMPLATE:
            n1_settings(draft, p["duration"], studio)
        report("编排本期画面与字幕")
        storyboard = produce(studio, draft, output_dir, clock_cues, p["duration"], paid)
        video = output_dir / "avatar-source.mp4"
        downloaded_avatar = False
        if not video.exists():
            result = paid("avatar", "haike/avatar", {"audio_file": p["audio_file"], "image_file": p["image_file"]})
            report("下载已生成的数字人视频")
            try:
                download_result(result["video_url"], video)
                downloaded_avatar = True
            except Exception:
                if state["stages"]["avatar"]["job"]["status"] == "submission_unknown":
                    _quarantine_avatar_download(video, output_dir)
                raise
        avatar_stage = state["stages"].get("avatar", {})
        avatar_job = avatar_stage.get("job") or {}
        if not development and avatar_job.get("status") in {"failed", "cancelled"}:
            raise WorkError("原数字人模型任务未成功，保留原素材待核对；不会新建调用")
        if not development and avatar_job and avatar_job.get("status") not in {"succeeded", "submission_unknown"}:
            raise WorkError("原数字人任务仍在处理，保留已有文件并恢复同一调用", "unavailable")
        if not development and avatar_job.get("status") == "submission_unknown":
            artifact = avatar_job.get("result") or {}
            if (not avatar_stage.get("intent") or not isinstance(avatar_job.get("id"), str)
                    or not avatar_job["id"].strip() or not isinstance(artifact, dict)
                    or not isinstance(artifact.get("video_url"), str) or not artifact["video_url"].strip()):
                raise WorkError("原数字人任务产物信息不完整，请核对原调用；未新建付费调用", "unavailable")
            try:
                recovery = _recovered_avatar_receipt(video, p["duration"], avatar_job, state.get("avatar_artifact_recovery"))
            except Exception:
                if downloaded_avatar:
                    _quarantine_avatar_download(video, output_dir)
                raise
            state["avatar_artifact_recovery"] = recovery
            save()
        from backlot.studio_composition import compose_avatar
        report("本地合成成片")
        if draft["input"].get("motion"):
            from backlot.studio_storyboard import compose_motion
            outcome = compose_motion(studio, draft, output_dir, video, Path(p["audio_path"]), clock_cues, storyboard, caption_cues=cues if "word-level" in caption_timing else None)
            if state.get("avatar_artifact_recovery"):
                outcome.setdefault("result", {})["avatar_artifact_recovery"] = state["avatar_artifact_recovery"]
            if network_enabled(draft) and outcome.get("status") == "completed":
                outcome.setdefault("result", {})["network_materials"] = write_network_result(output_dir, status="used", message="已将核验通过的网络画面用于成片", plan=storyboard, used=True)
            return outcome
        output = compose_avatar(output_dir, draft, video, Path(p["audio_path"]), p["duration"], cues if draft["input"].get("subtitles", True) else [], storyboard=storyboard) if storyboard else compose_avatar(output_dir, draft, video, Path(p["audio_path"]), p["duration"], cues)
        report = {"template_id": draft["template_id"], "adapter_version": 1, "sources": [{"path": str(video), "sha256": sha(video)}, {"path": p["audio_path"], "sha256": sha(p["audio_path"])}],
                  "caption_timing": "illustrative_manual" if development else caption_timing, "provider_jobs": [s["job"]["id"] for s in state["stages"].values() if s.get("job")], "human_review": "pending"}
        if development: report["development_sample"] = {"silent": True, "label": "版式与动效演示", "captions": "手工示意，非真实转写", "cloud_calls": 0}
        if state.get("avatar_artifact_recovery"):
            report["avatar_artifact_recovery"] = state["avatar_artifact_recovery"]
        atomic_private(output_dir / "qa.json", report)
        network_result = write_network_result(output_dir, status="used", message="已将核验通过的网络画面用于成片", plan=storyboard, used=True) if network_enabled(draft) else None
        return {"status": "completed", "stage": "数字人口播已合成，等待观看审核", "result": {"output_path": str(output), "qa_status": "pending", "provider_jobs": report["provider_jobs"],
                **({"network_materials": network_result} if network_result is not None else {}),
                **({"avatar_artifact_recovery": report["avatar_artifact_recovery"]} if "avatar_artifact_recovery" in report else {})}}
    except WorkError as exc:
        return {"status": "failed", "stage": str(exc), "error": {"message": str(exc), "type": "StudioAvatar", "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}, "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}
    except Exception:
        return {"status": "failed", "stage": "制作中断，原调用与产物已保留，可恢复同一任务", "error": {"message": "请检查API连接与本地渲染依赖，再恢复此任务", "type": "StudioAvatar"}, "retryable": True, "safe_resume_point": "studio_avatar"}
