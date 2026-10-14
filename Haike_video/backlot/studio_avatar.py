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


def key_identity(studio):
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
    if value.get("soundMode") == "voice" and value.get("voiceId") != "haike/cosyvoice":
        raise WorkError("请选择网关提供的 CosyVoice 配音，或上传已有音频")


def validate(studio, draft):
    if studio.template(draft["template_id"])["kind"] != "avatar": raise WorkError("请选择数字人口播模板")
    value = draft["input"]
    validate_voice(value)
    from backlot.studio_storyboard import options, motion_options
    options(studio, draft)
    motion_options(draft)
    if not draft["text"].strip() or len(draft["text"]) > 5000: raise WorkError("口播文案需要1至5,000字")
    image = value.get("portrait") or {}
    studio.asset(image.get("id"), draft["id"])
    if value.get("soundMode") == "audio":
        audio = studio.asset((value.get("audio") or {}).get("id"), draft["id"])
        if media_probe(audio)["duration"] > 120: raise WorkError("数字人口播音频最长120秒")
    elif value.get("soundMode") == "voice":
        if value.get("rate", 1) not in {.8, 1, 1.2, 1.5}: raise WorkError("配音语速不支持")
    else: raise WorkError("请选择已有音频或网关配音")
    title = draft["title"]
    maximum = 120 if value.get("motion") else 36 if draft["template_id"].startswith("avatar-template3") else 16
    if len(title) > maximum: raise WorkError(f"当前版式标题最多{maximum}字，请在排版配置中缩短")
    composer = Path(__file__).resolve().parents[1] / "remotion-composer/node_modules"
    if not composer.is_dir(): raise WorkError("缺少本地Remotion渲染依赖，尚未提交付费调用")


def quote(studio, draft):
    validate(studio, draft)
    from backlot.studio_asr import snapshot
    needs_clock = draft["input"].get("subtitles", True) or draft["input"].get("ai", {}).get("enabled")
    asr = snapshot(studio) if needs_clock else {"provider": "gateway"}
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
        if (draft["input"].get("subtitles", True) or draft["input"].get("ai", {}).get("enabled")) and asr["provider"] == "gateway": quotes["asr"] = sdk.quote("haike/tencent-asr", {"audio_file": prepared["audio_file"]}, draft["id"])
    else:
        quotes["tts"] = sdk.quote(draft["input"]["voiceId"], {"text": draft["text"]}, draft["id"])
        # Availability is checked before any TTS charge. Its exact avatar quote needs the real audio.
        models = {m.get("id") or m.get("model") for m in sdk.request("/capabilities").get("items", [])}
        needs_asr = draft["input"].get("subtitles", True) or draft["input"].get("ai", {}).get("enabled")
        required = {"haike/avatar"} | ({"haike/tencent-asr"} if needs_asr and asr["provider"] == "gateway" else set())
        if required - models: raise WorkError("数字人或字幕模型尚不可用，请由管理员确认成本费率后再制作")
    data = {"id": identity, "draft": draft, "prepared": prepared, "quotes": quotes, "asr": asr, "key_identity": key_identity(studio), "created_at": datetime.now(timezone.utc).isoformat()}
    with studio.db() as db: db.execute("INSERT INTO studio_quotes VALUES(?,?)", (identity, json.dumps(data, ensure_ascii=False)))
    return public_quote(data)


def public_quote(data):
    return {"id": data["id"], "revision": data["draft"]["revision"], "known_max_micros": sum(int(q["max_charge_micros"]) for q in data["quotes"].values()),
            "needs_audio_quote": data["draft"]["input"]["soundMode"] == "voice", "ai_trial": data["draft"]["input"].get("ai", {}).get("enabled", False), "items": [{"stage": k, "model": q["model"], "max_charge_micros": q["max_charge_micros"]} for k, q in data["quotes"].items()] + ([{"stage": "asr", "model": "local/whisper", "max_charge_micros": "0"}] if data.get("asr", {}).get("provider") == "local-whisper" else [])}


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
    known = re.fullmatch(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com", host) or host in {"videos.pexels.com", "images.pexels.com", "rh-comfyui01.tos-cn-beijing.volces.com"}
    benchmark = ipaddress.ip_network("198.18.0.0/15")
    if not known or not ips or not all(ip.version == 4 and ip in benchmark for ip in ips):
        raise WorkError("供应商媒体地址不能指向本地网络")
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    try:
        dns = "https://1.1.1.1/dns-query?" + urlencode({"name": host, "type": "A"})
        with build_opener(ProxyHandler({}), NoRedirect()).open(Request(dns, headers={"Accept": "application/dns-json"}), timeout=10) as response:
            raw = response.read(65537)
        if len(raw) > 65536: raise ValueError()
        data = json.loads(raw)
        answers = [ipaddress.ip_address(a["data"]) for a in data.get("Answer", []) if a.get("type") == 1]
        if data.get("Status") != 0 or not answers or not all(a.is_global for a in answers): raise ValueError()
        return str(answers[0])
    except Exception: raise WorkError("代理DNS未能核对真实公网媒体地址，请核对代理DNS后恢复原任务") from None


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


def download_result(url, path, referer=None):
    # Gateway results contain supplier media only. Follow validated HTTPS redirects, with no Key headers.
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
                with temporary.open("wb") as out:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > 100 * 1024 * 1024: raise WorkError("供应商媒体超过100MB")
                        out.write(chunk)
                temporary.replace(path)
                return
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}: raise WorkError("供应商媒体暂时无法下载，请恢复原任务") from None
            from urllib.parse import urljoin
            url = urljoin(url, exc.headers.get("Location", ""))
    raise WorkError("供应商媒体跳转过多")


def captions(result, duration, split=True):
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
                if group and len("".join(w["text"] for w in group)) + len(word["text"]) > 18:
                    out.append({"text": "".join(w["text"] for w in group).strip(), "startMs": group[0]["start"]*1000,
                                "endMs": group[-1]["end"]*1000, "timestampMs": None, "confidence": None})
                    group = []
                group.append(word)
            if group:
                out.append({"text": "".join(w["text"] for w in group).strip(), "startMs": group[0]["start"]*1000,
                            "endMs": group[-1]["end"]*1000, "timestampMs": None, "confidence": None})
            continue
        # Short groups inside each recognised sentence; this is sentence-aligned, not word-level karaoke.
        groups = [text[i:i+18] for i in range(0, len(text), 18)] if split else [text]
        for i, group in enumerate(groups):
            out.append({"text": group, "startMs": (start+(end-start)*i/len(groups))*1000, "endMs": (start+(end-start)*(i+1)/len(groups))*1000, "timestampMs": None, "confidence": None})
    if not out: raise WorkError("语音识别没有返回可用句级时间轴，保留音频和数字人，请检查字幕阶段")
    return out


def clock_captions(result, duration):
    # GPT can select observed word boundaries even if Whisper returns a single
    # long segment. Display wrapping must not determine storyboard timing.
    if result.get("provider") != "local-whisper": return captions(result, duration, split=False)
    return [{"text": w["text"].strip(), "startMs": w["start"]*1000, "endMs": min(w["end"], duration)*1000,
             "timestampMs": None, "confidence": w.get("probability"), "clock": "word"}
            for s in result["segments"] for w in s["words"]]


def run_avatar(project_dir, request, sdk=None):
    studio = Studio(Path(project_dir).parent)
    if request["key_identity"] != key_identity(studio): raise WorkError("API Key已改变；恢复付费任务前请恢复原账户连接")
    sdk = sdk or studio.client()
    output_dir = Path(project_dir) / "renders" / request["render_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "gateway-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"stages": {}, "prepared": request["prepared"]}
    def save(): atomic_private(state_path, state)
    def paid(stage, model, inputs):
        if stage not in state["stages"]:
            q = request["quotes"].get(stage) or sdk.quote(model, inputs, request["draft"]["id"])
            committed = sum(int(s["quote"]["max_charge_micros"]) for s in state["stages"].values())
            if committed + int(q["max_charge_micros"]) > request["max_charge_micros"]:
                raise WorkError("后续报价超过本次总费用上限，已完成产物保留；未提交这一步")
            state["stages"][stage] = {"quote": q}; save()
        s = state["stages"][stage]
        if not s.get("job"):
            s["quote"]=renew_if_expired(sdk,s["quote"]);save()
        if not s.get("intent"):
            identity = "call_" + hashlib.sha256((request["id"] + ":" + stage).encode()).hexdigest()[:32]
            s["intent"] = sdk.confirm(s["quote"], int(s["quote"]["max_charge_micros"]), identity); save()
        job = sdk.wait(s["intent"], timeout=600)
        s["job"] = job; save()
        if job["status"] != "succeeded":
            if job["status"] in {"failed", "cancelled"}: raise WorkError("模型任务未成功，请到账户中心核对原调用明细")
            raise WorkError("原模型任务仍在处理或结果待核对，请恢复此任务；不会新建付费调用", "unavailable")
        return job["result"]
    try:
        p = state["prepared"]; draft = request["draft"]
        asr = request.get("asr", {"provider": "gateway"})
        if asr["provider"] == "local-whisper":
            from backlot.studio_asr import configuration, identity
            if identity(configuration(studio)) != asr["identity"]:
                raise WorkError("字幕引擎已改变，请恢复原配置后继续原任务")
        if not p.get("audio_path"):
            raw = output_dir / "tts-source.wav"
            if not raw.exists():
                result = paid("tts", draft["input"]["voiceId"], {"text": draft["text"]})
                if result.get("audio_base64"): raw.write_bytes(base64.b64decode(result["audio_base64"], validate=True))
                else: download_result(result["audio_url"], raw)
            audio = output_dir / "narration.wav"
            duration = prepare_audio(raw, audio, draft["input"].get("rate", 1))
            p.update(audio_path=str(audio), duration=duration, audio_file=sdk.upload(audio, "audio")["id"]); save()
        cues = []
        clock_cues = []
        if draft["input"].get("subtitles", True) or draft["input"].get("ai", {}).get("enabled"):
            if asr["provider"] == "local-whisper":
                from backlot.studio_asr import transcribe
                result = transcribe(studio, asr, Path(p["audio_path"]), output_dir, p["duration"])
            else:
                result = paid("asr", "haike/tencent-asr", {"audio_file": p["audio_file"]})
            cues = captions(result, p["duration"])
            clock_cues = clock_captions(result, p["duration"])
        from backlot.studio_storyboard import produce
        storyboard = produce(studio, draft, output_dir, clock_cues, p["duration"], paid)
        video = output_dir / "avatar-source.mp4"
        if not video.exists():
            result = paid("avatar", "haike/avatar", {"audio_file": p["audio_file"], "image_file": p["image_file"]})
            download_result(result["video_url"], video)
        from backlot.studio_composition import compose_avatar
        if draft["input"].get("motion"):
            from backlot.studio_storyboard import compose_motion
            return compose_motion(studio, draft, output_dir, video, Path(p["audio_path"]), clock_cues, storyboard, caption_cues=cues if asr["provider"] == "local-whisper" else None)
        output = compose_avatar(output_dir, draft, video, Path(p["audio_path"]), p["duration"], cues if draft["input"].get("subtitles", True) else [], storyboard=storyboard) if storyboard else compose_avatar(output_dir, draft, video, Path(p["audio_path"]), p["duration"], cues)
        report = {"template_id": draft["template_id"], "adapter_version": 1, "sources": [{"path": str(video), "sha256": sha(video)}, {"path": p["audio_path"], "sha256": sha(p["audio_path"])}],
                  "caption_timing": "Whisper word-level" if cues and asr["provider"] == "local-whisper" else "ASR sentence-level" if cues else "off", "provider_jobs": [s["job"]["id"] for s in state["stages"].values()], "human_review": "pending"}
        atomic_private(output_dir / "qa.json", report)
        return {"status": "completed", "stage": "数字人口播已合成，等待观看审核", "result": {"output_path": str(output), "qa_status": "pending", "provider_jobs": report["provider_jobs"]}}
    except WorkError as exc:
        return {"status": "failed", "stage": str(exc), "error": {"message": str(exc), "type": "StudioAvatar", "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}, "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}
    except Exception:
        return {"status": "failed", "stage": "制作中断，原调用与产物已保留，可恢复同一任务", "error": {"message": "请检查API连接与本地渲染依赖，再恢复此任务", "type": "StudioAvatar"}, "retryable": True, "safe_resume_point": "studio_avatar"}
