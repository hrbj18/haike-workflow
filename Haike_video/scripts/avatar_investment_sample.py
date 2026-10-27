"""Template 6 private layout sample; only the native queue may render it.

Default: prepare a 12-second silent still-portrait project. --submit admits that
frozen request to the existing queue; --resume continues its original job.
This is neither a talking-avatar generation nor speech/ASR acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import wave

HAIKE = Path(__file__).resolve().parents[1]
WORKSPACE = HAIKE.parent
sys.path.insert(0, str(HAIKE))

TEMPLATE_ID = "avatar-investment-a-v6"
DURATION = 12
STATE_FILE = "sample-state.json"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_evidence_dir(path):
    """Keep private paths and sample media in this checkout's ignored storage."""
    target = Path(path).expanduser().resolve()
    roots = (WORKSPACE / ".local", HAIKE / ".backlot")
    if not any(target.is_relative_to(root.resolve()) for root in roots):
        raise ValueError("开发证据目录只能放在本工作区 .local 或 Haike_video/.backlot 内")
    if (WORKSPACE / ".git").exists():
        checked = subprocess.run(["git", "check-ignore", "--quiet", str(target)], cwd=WORKSPACE,
                                 capture_output=True, timeout=15)
        if checked.returncode:
            raise ValueError("开发证据目录未被Git忽略，请选择现有本地证据目录")
    return target


def check_workspace(base):
    url = urllib.parse.urlsplit(base)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("开发样片只连接本机工作台，请使用本机HTTP根地址")
    def read(endpoint):
        with urllib.request.urlopen(base.rstrip("/") + endpoint, timeout=15) as response:
            return json.load(response)
    health = read("/api/health")
    if health.get("edition") != "haike-workflow-2" or Path(health.get("workspace", "")).resolve() != WORKSPACE.resolve():
        raise ValueError("工作台不是本源码工作区，未读取或写入制作数据")
    if not any(item.get("id") == TEMPLATE_ID for item in read("/api/studio/templates").get("templates", [])):
        raise ValueError("当前工作台尚未载入招商A模板，请由总控刷新服务后继续")
    return health


def sample_input():
    return {"soundMode": "audio", "subtitles": False, "ai": {"enabled": False},
            "network_materials_enabled": False, "investment": {
                "brand": "海客AI社区服务站", "headline": "社区AI新生意\n全国招商",
                "cta": "点击视频下方链接\n加入我们", "opening": True, "closing": True,
                "emphasis": [{"match": "年后优先", "text": "年后优先", "kind": "sticker"},
                             {"match": "30个平方", "text": "30㎡", "kind": "card", "detail": "小区门口", "footnote": "稿件信息示意"}]}}


def manual_cues():
    return [{"text": text, "startMs": start, "endMs": end, "timestampMs": None, "confidence": None}
            for text, start, end in [("开发样片无声示意", 0, 1200), ("你在哪里", 1500, 3500),
                ("年后优先", 3500, 5300), ("30个平方", 5500, 8500), ("开发演示非口型验收", 9500, 12000)]]


def make_request(draft, prepared, identity, render_id):
    return {"id": "local-investment-sample-" + draft["id"], "draft": draft,
            "prepared": prepared, "quotes": {}, "key_identity": identity,
            "max_charge_micros": 0, "render_id": render_id, "asr": {"provider": "gateway"},
            "development_sample": {"silent": True, "label": "版式与动效演示", "captions": manual_cues()}}


class Sample:
    def __init__(self, evidence_dir, base):
        # Validate the service before constructing Studio or opening any database.
        check_workspace(base)
        self.directory = validate_evidence_dir(evidence_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        from backlot.studio import Studio
        from backlot.production_queue import ProductionQueue
        from lib.paths import PROJECTS_DIR
        if PROJECTS_DIR.resolve() != (HAIKE / "projects").resolve():
            raise ValueError("开发样片需使用当前工作区标准projects目录，不能切换到其他制作数据")
        self.studio = Studio(PROJECTS_DIR)
        self.queue = ProductionQueue(self.studio.private / "production-queue.sqlite3", projects_root=PROJECTS_DIR)
        path = self.directory / STATE_FILE
        self.state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def save(self):
        from backlot.studio import atomic_private
        atomic_private(self.directory / STATE_FILE, self.state)

    @property
    def project(self):
        return self.studio.projects_root / self.state["project_id"]

    def run(self, args):
        from lib.subprocess_window import no_window_kwargs
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=180, **no_window_kwargs())
        if result.returncode:
            raise ValueError("本地样片媒体处理失败：" + result.stderr[-1200:])

    def prepare(self, portrait=None):
        from backlot.studio import atomic_private
        from backlot.studio_avatar import development_captions, key_identity
        from lib.checkpoint import init_project
        from lib.ffmpeg_locator import resolve_ffmpeg_pair
        if self.state and self.state.get("request"):
            if portrait and digest(portrait) != self.state["portrait_sha256"]:
                raise ValueError("人物原图已改变，请为新样片使用另一个忽略的证据目录")
            self.validate()
            return self.summary()
        portrait = portrait or self.state.get("portrait_source")
        if portrait is None:
            raise ValueError("首次准备开发样片需提供 --portrait 本机授权人物图")
        original = Path(portrait).expanduser()
        if original.is_symlink():
            raise ValueError("人物图需为本机原文件")
        portrait = original.resolve(strict=True)
        if portrait.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("人物图需为本机PNG或JPEG原文件")
        original_sha = digest(portrait)
        project_id = "studio-" + hashlib.sha256((str(self.directory) + original_sha).encode()).hexdigest()[:16]
        if self.state and (self.state["project_id"] != project_id or self.state["portrait_sha256"] != original_sha):
            raise ValueError("人物原图已改变，请使用另一个忽略的证据目录")
        if not self.state:
            self.state = {"project_id": project_id, "template_id": TEMPLATE_ID, "portrait_source": str(portrait),
                          "portrait_sha256": original_sha, "duration": DURATION, "cloud_calls": 0, "publication": False}
            self.save()
        ffmpeg, _ = resolve_ffmpeg_pair()
        silence = self.directory / "silent-12s.wav"
        with wave.open(str(silence), "wb") as stream:
            stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            stream.writeframes(bytes(DURATION * 24000 * 2))
        still = self.directory / "still-portrait-12s.mp4"
        if not still.is_file():
            self.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-loop", "1", "-i", str(portrait), "-t", str(DURATION),
                      "-vf", "scale=896:1120:force_original_aspect_ratio=decrease,pad=896:1120:(ow-iw)/2:(oh-ih)/2,setsar=1",
                      "-r", "30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "18", "-pix_fmt", "yuv420p", str(still)])
        initial = {"id": project_id, "template_id": TEMPLATE_ID, "title": "招商A无声开发样片",
                   "text": "开发样片无声示意。你在哪里。年后优先。30个平方。开发演示非口型验收。", "input": sample_input()}
        if not self.state.get("draft"):
            self.state["draft"] = self.studio.save_draft(initial)
            self.save()
        assets = self.state.setdefault("assets", {})
        for name, source, kind in (("portrait", portrait, "image"), ("audio", silence, "audio")):
            if name not in assets:
                assets[name] = self.studio.save_asset(project_id, source.name, kind, source.read_bytes())
                self.save()
        portrait_asset, audio_asset = assets["portrait"], assets["audio"]
        if not self.state.get("configured"):
            self.state["draft"] = self.studio.save_draft({**initial, "revision": self.state["draft"]["revision"],
                "input": {**initial["input"], "portrait": portrait_asset, "audio": audio_asset}})
            self.state["configured"] = True
            self.save()
        draft = self.state["draft"]
        init_project(project_id, title="招商A · 无声版式开发样片", pipeline_type="animated-explainer", pipeline_dir=self.studio.projects_root)
        render_id = "studio-" + str(draft["revision"])
        folder = self.project / "renders" / render_id
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(still, folder / "avatar-source.mp4")
        prepared = {"duration": DURATION, "audio_path": str(self.studio.asset(audio_asset["id"], project_id)),
                    "portrait_path": str(self.studio.asset(portrait_asset["id"], project_id))}
        request = make_request(draft, prepared, key_identity(self.studio), render_id)
        development_captions(request, self.project, folder)
        self.state.update(request=request, render_id=render_id, folder=str(folder),
                          source_video_sha256=digest(folder / "avatar-source.mp4"), audio_sha256=digest(prepared["audio_path"]))
        self.save()
        atomic_private(self.directory / "sample-input.json", request)
        atomic_private(self.project / "artifacts" / "layout-sample-provenance.json", {
            "portrait_sha256": original_sha, "audio": "PCM16/24kHz单声道全零无声WAV", "cloud_calls": 0,
            "avatar": "本地静态人物图，非数字人生成或口型验收", "caption_clock": "手工示意，非真实转写", "publication": False})
        return self.summary()

    def validate(self):
        from backlot.studio_avatar import development_captions
        if not self.state or self.state.get("template_id") != TEMPLATE_ID:
            raise ValueError("请先准备本模板开发样片")
        if (not re.fullmatch(r"studio-[a-f0-9]{16}", str(self.state.get("project_id", "")))
                or not re.fullmatch(r"studio-[1-9][0-9]*", str(self.state.get("render_id", "")))
                or Path(self.state["folder"]).resolve() != (self.project / "renders" / self.state["render_id"]).resolve()):
            raise ValueError("开发样片项目或渲染目录不属于原工作区")
        request = self.state["request"]
        if (request.get("quotes") != {} or request.get("max_charge_micros") != 0
                or request.get("draft", {}).get("id") != self.state["project_id"]
                or request.get("draft", {}).get("template_id") != TEMPLATE_ID
                or request.get("render_id") != self.state["render_id"]):
            raise ValueError("开发样片必须无报价、无费用上限，禁止供应商调用")
        if (digest(Path(self.state["folder"]) / "avatar-source.mp4") != self.state["source_video_sha256"]
                or digest(request["prepared"]["audio_path"]) != self.state["audio_sha256"]):
            raise ValueError("开发样片原媒体发生变化，不能恢复原队列")
        development_captions(request, self.project, Path(self.state["folder"]))

    def submit(self):
        self.validate()
        self.state["queue"] = self.queue.submit(project_id=self.state["project_id"], kind="studio_avatar", source="codex",
            priority="normal", parent_job_id=self.state["render_id"], frozen_request=self.state["request"],
            idempotency_key="investment-layout-sample:" + self.state["project_id"])
        self.save()
        return self.status()

    def resume(self):
        self.validate()
        if not self.state.get("queue"):
            raise ValueError("尚未提交队列，请先 --submit")
        job_id = self.state["queue"]["job_id"]
        job = self.original_job(job_id)
        if job["status"] == "failed" and job.get("retryable"):
            self.queue.retry(job_id)
        elif job["status"] == "paused":
            self.queue.resume(job_id)
        elif job["status"] not in {"queued", "running", "completed"}:
            raise ValueError("原队列当前不能安全恢复，请核对原任务状态")
        return self.status()

    def original_job(self, job_id):
        job = self.queue.get(job_id, include_private=True)
        if (job["project_id"] != self.state["project_id"] or job["kind"] != "studio_avatar"
                or job["parent_job_id"] != self.state["render_id"]
                or job["frozen_request"] != self.state["request"]):
            raise ValueError("原开发队列与冻结请求不一致，不能重试其他制作任务")
        return job

    def summary(self):
        return {"project_id": self.state["project_id"], "folder": self.state["folder"], "duration": DURATION,
                "cloud_calls": 0, "queued": bool(self.state.get("queue")), "evidence_dir": str(self.directory)}

    def status(self):
        if not self.state:
            return {"prepared": False, "queued": False}
        if not self.state.get("queue"):
            return self.summary()
        job = self.original_job(self.state["queue"]["job_id"])
        self.state["queue_status"] = {key: value for key, value in job.items() if key != "frozen_request"}
        self.save()
        return {k: job.get(k) for k in ("job_id", "project_id", "status", "stage", "result", "error", "retryable")}

    def evidence(self):
        from backlot.studio import atomic_private
        from backlot.studio_render import media_probe
        from lib.ffmpeg_locator import resolve_ffmpeg_pair
        self.validate()
        if self.status().get("status") != "completed":
            raise ValueError("原样片队列尚未完成，不能生成完成证据")
        folder = Path(self.state["folder"])
        qa = json.loads((folder / "qa.json").read_text(encoding="utf-8"))
        gateway = json.loads((folder / "gateway-state.json").read_text(encoding="utf-8"))
        if gateway["stages"] or qa["provider_jobs"] or qa["caption_timing"] != "illustrative_manual" or qa["development_sample"]["cloud_calls"] != 0:
            raise ValueError("样片回执未满足零云调用与手工示意标签")
        ffmpeg, _ = resolve_ffmpeg_pair()
        video = folder / "avatar-preview.mp4"
        self.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(video), "-f", "null", "-"])
        frames = []
        for label, time in [("opening", .5), ("presenter", 2.4), ("sticker", 4.2), ("card", 6.8), ("closing", 10.5)]:
            path = self.directory / (label + ".jpg")
            self.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", str(time), "-i", str(video), "-frames:v", "1", "-q:v", "2", str(path)])
            frames.append({"label": label, "time": time, "path": str(path)})
        info = media_probe(video)
        if (info["video"]["width"], info["video"]["height"]) != (1080, 1920) or abs(info["duration"] - DURATION) > .1 or not info.get("audio"):
            raise ValueError("样片画幅、时长或无声音轨未通过检查")
        result = {"status": "technical_checks_passed", "development_sample": True, "video": str(video),
                  "video_sha256": digest(video), "media": info, "cloud_calls": 0, "quotes": {}, "provider_jobs": [],
                  "paid_stages": [], "publication": False, "caption_clock": "手工示意，非真实转写",
                  "static_avatar_not_lip_sync": True, "full_decode": "passed", "frame_review": "pending", "frames": frames}
        atomic_private(self.directory / "sample-evidence.json", result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="招商A模板12秒无云开发样片，默认只准备，不制作口播或发布")
    parser.add_argument("--portrait", type=Path, help="首次准备时的本机授权人物PNG/JPEG原图")
    parser.add_argument("--evidence-dir", type=Path, default=HAIKE / ".backlot" / "template6-sample")
    parser.add_argument("--base", default="http://127.0.0.1:14756")
    action = parser.add_mutually_exclusive_group()
    for name in ("prepare", "submit", "resume", "status", "evidence"):
        action.add_argument("--" + name, dest="action", action="store_const", const=name)
    parser.set_defaults(action="prepare")
    args = parser.parse_args(argv)
    try:
        sample = Sample(args.evidence_dir, args.base)
        if args.action in {"prepare", "submit"}:
            result = sample.prepare(args.portrait)
            if args.action == "submit": result = sample.submit()
        else:
            result = getattr(sample, args.action)()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
