# -*- coding: utf-8 -*-
"""上下窗口轻量复刻 · 参数化驱动（零付费：无配音 / 无数字人 / 纯 BGM）。

这条线在做什么
--------------
复刻「一张竖屏参考片」的版式，**只换画面上下的文字层，不动中间画面**：

    参考片 720x1280 的典型结构 = 中间一条清晰画面 + 上下两条模糊填充带
    （博主把横屏素材垫成竖屏的产物），标题 / 字幕本来就叠在模糊带上。
    ⇒ 用自己的深色板把上下带整块盖掉、写自己的字，**中间真实画面一点不损失**。

成片画布 1080x1920（原片 720x1280 精确 x1.5 放大，无变形）：

    顶部板    0            ─ plate_top_h        （默认 0.232，写四层标题）
    露出画面  plate_top_h  ─ plate_bot_y        （默认 0.232–0.652，原片真实画面）
    底部板    plate_bot_y  ─ 1.0                （默认 0.652–1.0，写逐段字幕）

三个子命令
----------
  measure <spec>   只读：量原片「清晰带」边界 + 原片自带的文字带，给板位建议。不写任何状态。
  prep    <spec>   建项目 → 传原片/BGM → 定时字幕 cue → 绑画面 → 写图层 → 全片预览。
  final   <spec>   人工看过预览后：批准全片 → 正式渲染。

用法
----
  PY=./.venv/Scripts/python.exe
  $PY scripts/remake_window_cli.py measure <spec.json>
  $PY scripts/remake_window_cli.py prep    <spec.json>
  # 人工看全片预览，确认画面/标题/字幕都对
  $PY scripts/remake_window_cli.py final   <spec.json>

  批量（多期串行，windows.json 之类单例资源不在本链路上，可放心循环）：
  for s in specs/*.json; do $PY scripts/remake_window_cli.py prep "$s"; done

前置条件（缺一条就会莫名失败）
------------------------------
  * 工作台服务在 127.0.0.1:4754 运行，且**必须无沙箱**并设 CODEBUDDY_SAFE_DELETE_ENABLED=0。
  * prep / final **必须后台跑** —— 前台 120s 会被 SIGTERM 杀掉，批次半途而废。
  * 每期一份 spec；同 project_id 重复跑 prep 是幂等的（素材按 name 跳过）。

已知坑（都是踩过的，改代码前先读）
----------------------------------
  1. **板层的 text 不能为空**：写全角空格会被服务端 strip 掉，报 422「文案不能为空」。
     本脚本用 "·" 且 color 与底色相同，视觉上不可见。
  2. **字幕必须走 overlay 层**，不能用字幕系统：字幕系统默认 y=0.89，超出安全窗
     （规范要求底边 < 0.80）。因此 prep 里会把字幕系统的 enabled 置 False，
     字幕改由 overlay 的 sub-* 图层承担（默认 y=0.755）。
  3. **改过 overlay ⇒ 各段 review_status 会被打回 needs_adjustment**，
     所以只能 overlay → full-preview → approve → video-render，
     **不能跳过预览直接 final**（服务端会拒）。
  4. **source_audio_only 模式不需要声音样板**；但 track_id 必须从 music_library 回读，
     **绝不能手打 hash**（尾部字符打错会得到无提示的 422）。
  5. **同一个 asset 可以被多个 cue 复用**，靠 visual-timeline 的 source_in/out 取不同区间，
     ⇒ 不必把原片切成 4 个文件（少一步、少占磁盘）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 本机全局代理会劫持回环请求，必须在起任何请求之前清掉
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_v, None)

REPO = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:4754"
UA = "openmontage-driver/1.0"
FULL_END = 86400.0          # 图层「全程挂载」用的哨兵值，退出动画交给组合层
POLL_S = 5                  # 渲染轮询间隔
SLOT_TIMEOUT_S = 900        # 单个后台步骤最长等待


# ────────────────────────────── HTTP ──────────────────────────────

def call(method, path, data=None, raw=None, timeout=900):
    """打工作台 API。返回 (status, parsed_or_text)。"""
    hdrs = {"User-Agent": UA}
    body = None
    if raw is not None:
        body = raw
        hdrs["Content-Type"] = "application/octet-stream"
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:900]
    except urllib.error.URLError as e:
        sys.exit(f"[fatal] 连不上工作台 {BASE} —— 服务没起？({e})")


def ok(st, what, res=None, allow=(200, 201)):
    print(f"    {what} -> {st}" + ("" if st in allow else f"  {str(res)[:400]}"), flush=True)
    return st in allow


# ─────────────────────────── 媒体探测 ───────────────────────────

def _ffmpeg() -> str:
    try:
        from static_ffmpeg import run as _r
        return _r.get_or_fetch_platform_executables_else_raise()[0]
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def _ffprobe() -> str:
    try:
        from static_ffmpeg import run as _r
        return _r.get_or_fetch_platform_executables_else_raise()[1]
    except Exception:  # noqa: BLE001
        return "ffprobe"


def probe_media(path) -> dict:
    """返回 {duration, width, height, fps, has_audio}。"""
    ff = _ffprobe()
    cmd = [ff, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120)
        info = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"[fatal] ffprobe 失败: {exc}")
    vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    fps_raw = str(vs.get("r_frame_rate") or "30/1")
    try:
        a, b = fps_raw.split("/")
        fps = float(a) / float(b or 1)
    except Exception:  # noqa: BLE001
        fps = 30.0
    return {
        "duration": float((info.get("format") or {}).get("duration") or 0.0),
        "width": int(vs.get("width") or 0),
        "height": int(vs.get("height") or 0),
        "fps": round(fps, 3),
        "has_audio": any(s.get("codec_type") == "audio" for s in info.get("streams", [])),
    }


def grab_frames(video, times):
    """按时间点抽帧，**经 stdout 取回内存**（不落盘，规避中文路径与编码问题）。

    returns [(t, bgr_ndarray), ...]
    """
    import cv2
    import numpy as np

    ff = _ffmpeg()
    out = []
    for t in times:
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
               "-i", str(video), "-frames:v", "1", "-f", "image2pipe",
               "-vcodec", "png", "-"]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=120)
        except Exception:  # noqa: BLE001
            continue
        if p.returncode != 0 or not p.stdout:
            continue
        img = cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            out.append((t, img))
    return out


# ─────────────────────── measure：量版式 ───────────────────────

def _row_energy(img):
    """逐行「锐利度」：Laplacian 幅值的行内 99 分位。

    用高分位而不是均值 —— 模糊填充带的 Laplacian 幅值**上限很低**，
    均值会把它拉成和清晰带一个量级（实测均值判据直接失效、找不到清晰带），
    分位数才分得开「这一行有没有锐边」。
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    return np.percentile(lap, 99, axis=1)


def suggest_plates(merged, max_line_h=0.045, margin=0.006, min_span=0.30):
    """由「原片自带的文字带」反推两个板位。

    只要板子盖住原片的标题带和字幕带，中间画面就干净了：
        plate_top_h = 原片上半区最低那条文字带的下沿 + margin
        plate_bot_y = 原片下半区最高那条文字带的上沿 - margin

    ★ 两道过滤缺一不可（都是实测踩出来的）：
      * **行段高度 ≤ max_line_h**：画面里的大片同色区域（落日荒原的黄土地、
        深色废墟）会被颜色掩码整段判成「黄色 / 白色」，高度往往 0.1 以上，
        而文字行只有 0.02–0.035。不滤这一刀，板位会算到画面中间去。
      * **水平跨度 ≥ min_span**：画面里的白色高光（士兵的枪、背包反光、
        无人机准星）也是白色小块，行高很矮、能骗过高度过滤（实测把
        plate_top_h 顶到 0.388）。文字是**成行的笔画**，横跨画面较宽；
        物体高光只占一小段。
    """
    narrow, dropped = [], []
    for kind, segs in (merged or {}).items():
        for s in segs:
            s0, s1 = float(s[0]), float(s[1])
            span = float(s[2]) if len(s) > 2 else 1.0
            if (s1 - s0) > max_line_h:
                dropped.append((s0, s1, kind, span, "太高→判为画面色块"))
            elif span < min_span:
                dropped.append((s0, s1, kind, span, "太窄→判为物体高光"))
            else:
                narrow.append((s0, s1, kind, span))

    fallback = False
    if not narrow:
        # 全被滤掉 ⇒ 退回「只按行高过滤」，至少给个人工可复核的建议，别直接摆烂
        fallback = True
        narrow = [(a, b, k, sp) for a, b, k, sp, _ in dropped if sp >= 0.15]
    narrow.sort()

    upper = [s for s in narrow if s[1] < 0.5]
    lower = [s for s in narrow if s[0] >= 0.5]
    out = {}
    if upper:
        out["plate_top_h"] = round(min(0.60, max(s[1] for s in upper) + margin), 3)
    if lower:
        out["plate_bot_y"] = round(max(0.30, min(s[0] for s in lower) - margin), 3)
    return out, narrow, dropped, fallback


def _text_bands(img, min_rows=3, min_span=0.30):
    """找「高对比文字的成行笔画」的 y 区间：白 / 黄 / 红。

    returns {kind: [[top, bottom, x_span], ...]}（全部归一化）
    """
    import numpy as np

    h, w = img.shape[:2]
    b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    masks = {
        "white": (r > 225) & (g > 225) & (b > 225),
        "yellow": (r > 200) & (g > 170) & (b < 120),
        "red": (r > 140) & (g < 90) & (b < 90),
    }
    out = {}
    for name, mask in masks.items():
        if not mask.sum():
            out[name] = []
            continue
        cnt = mask.sum(axis=1)
        thr = max(3, int(mask.sum() / h * 0.03))
        segs, cur = [], None
        for y in range(h + 1):
            hit = y < h and cnt[y] > thr
            if hit:
                cur = [y, y] if cur is None else [cur[0], y]
            elif cur is not None:
                if cur[1] - cur[0] >= min_rows:
                    cols = np.where(mask[cur[0]:cur[1] + 1, :].any(axis=0))[0]
                    span = float((cols[-1] - cols[0] + 1) / w) if len(cols) else 0.0
                    if span >= min_span:
                        segs.append([round(cur[0] / h, 4), round(cur[1] / h, 4),
                                     round(span, 3)])
                cur = None
        out[name] = segs
    return out


def find_clear_band(energies, min_frac=0.12):
    """从平均逐行能量里找「最长的强能量连续带」，返回归一化 [top, bottom]。

    energies: [(t, ndarray_h), ...] 已按帧对齐（同分辨率）。
    """
    import numpy as np

    if not energies:
        return None
    stack = np.vstack([e for _, e in energies])
    prof = stack.mean(axis=0)
    if not np.any(prof > 0):
        return None
    # 平滑一下，避免单行噪点把边界带偏
    k = max(3, len(prof) // 120)
    kernel = np.ones(k) / k
    prof = np.convolve(prof, kernel, mode="same")

    peak = float(prof.max())
    strong = prof >= peak * 0.35
    # 找最长连续 True 段
    best = (0, 0, -1)
    i = 0
    n = len(strong)
    while i < n:
        if strong[i]:
            j = i
            while j + 1 < n and strong[j + 1]:
                j += 1
            if j - i > best[2]:
                best = (i, j, j - i)
            i = j + 1
        else:
            i += 1
    top, bot, span = best
    if span < n * min_frac:
        return None
    return {
        "top": round(top / n, 4),
        "bottom": round(bot / n, 4),
        "span": round(span / n, 4),
        "contiguous": bool(span == n or prof[top:bot + 1].min() >= peak * 0.35),
    }


def cmd_measure(spec):
    src = spec["source"]["video"]
    p = Path(src)
    if not p.exists():
        sys.exit(f"[fatal] 原片不存在: {p}")

    meta = probe_media(p)
    print(f"[measure] {p.name}  {meta['width']}x{meta['height']}  "
          f"{meta['fps']}fps  {meta['duration']:.2f}s  audio={meta['has_audio']}", flush=True)

    clip = float(spec["source"].get("clip_seconds") or min(meta["duration"], 20.0))
    n = 12
    lo = float(spec["source"].get("start_seconds") or 0.0)
    times = [lo + (clip - lo) * (i + 0.5) / n for i in range(n)]
    times = [t for t in times if t < meta["duration"] - 0.05]
    frames = grab_frames(p, times)
    if not frames:
        sys.exit("[fatal] 抽帧失败（ffmpeg 读不到这个文件？）")
    print(f"[measure] 抽到 {len(frames)} 帧，逐行清晰度分析中 …", flush=True)

    energies = [(t, _row_energy(img)) for t, img in frames]
    band = find_clear_band(energies)

    # 文字带：抽几帧扫一遍（原片的标题/字幕是钉住的）
    picks = [img for _, img in frames[:: max(1, len(frames) // 5)]][:6]
    tb = [_text_bands(img) for img in picks]
    merged = {}
    for k in ("white", "yellow", "red"):
        segs = []
        for d in tb:
            segs.extend(d.get(k) or [])
        segs.sort(key=lambda s: s[0])
        keep = []
        for s0, s1, span in segs:
            if keep and s0 <= keep[-1][1] + 0.01:
                keep[-1][1] = max(keep[-1][1], s1)
                keep[-1][2] = max(keep[-1][2], span)
            else:
                keep.append([s0, s1, span])
        merged[k] = [[round(a, 4), round(b, 4), round(c, 3)] for a, b, c in keep]

    sug, narrow, dropped, fallback = suggest_plates(merged)

    print("\n[measure] ---- 原片自带的文字带（top-bottom · 水平跨度）----", flush=True)
    for k, v in merged.items():
        if v:
            print(f"  {k:7s}: " + ", ".join(f"{a:.3f}-{b:.3f}(w{c:.2f})" for a, b, c in v),
                  flush=True)
    if dropped:
        print("  —— 已忽略（不是文字，别手动拿去算板位）——", flush=True)
        for a, b, k, sp, why in dropped:
            print(f"    {k:7s} {a:.3f}-{b:.3f}(w{sp:.2f})  {why}", flush=True)
    up = [s for s in narrow if s[1] < 0.5]
    lo = [s for s in narrow if s[0] >= 0.5]
    if not narrow:
        print("  （没有任何候选段同时满足「行高够矮 + 横跨够宽」）", flush=True)
    else:
        if up:
            print(f"  上半区文字带最低到 y={max(s[1] for s in up):.3f}", flush=True)
        if lo:
            print(f"  下半区文字带最高从 y={min(s[0] for s in lo):.3f} 起", flush=True)
    if fallback:
        print("  ⚠ 低置信回退：标准判据全滤空了，下面是放宽后的建议，**务必人眼复核**",
              flush=True)

    print("\n[measure] ---- 板位建议（主判据：盖住原片自带文字带）----", flush=True)
    if "plate_top_h" in sug and "plate_bot_y" in sug:
        print(f"  plate_top_h = {sug['plate_top_h']}    plate_bot_y = {sug['plate_bot_y']}",
              flush=True)
        print(f"  ⇒ 露出原片画面 {sug['plate_top_h']:.3f} – {sug['plate_bot_y']:.3f}"
              f"（占全高 {(sug['plate_bot_y'] - sug['plate_top_h']) * 100:.1f}%）", flush=True)
        cur_t = (spec.get("layout") or {}).get("plate_top_h")
        cur_b = (spec.get("layout") or {}).get("plate_bot_y")
        if cur_t is not None and cur_b is not None:
            dt = round(float(cur_t) - sug["plate_top_h"], 3)
            db = round(float(cur_b) - sug["plate_bot_y"], 3)
            tag = "一致" if (abs(dt) <= 0.012 and abs(db) <= 0.012) else "★ 差别大，复核 spec"
            print(f"  spec 现值 {cur_t} / {cur_b} ⇒ 差 {dt:+} / {db:+}  [{tag}]", flush=True)
    else:
        print("  ⚠ 原片没有可识别的文字带 ⇒ 板位自动定不了，请人眼看帧后手工填 spec.layout。",
              flush=True)

    if band:
        print(f"\n[measure] ---- 辅助：清晰带 {band['top']:.4f} – {band['bottom']:.4f}"
              f"（占全高 {band['span'] * 100:.1f}%）----", flush=True)
        if band["span"] > 0.85:
            print("  ⚠ 清晰带几乎占满整幅 ⇒ 原片上下**没有**模糊垫底，"
                  "板子会真的吃掉画面，板位请手工定。", flush=True)
    else:
        print("\n[measure] 辅助：没测出明显清晰带（原片上下不是纯模糊垫底，正常）。", flush=True)

    out = {
        "source": {"width": meta["width"], "height": meta["height"],
                   "fps": meta["fps"], "duration": meta["duration"],
                   "has_audio": meta["has_audio"]},
        "clear_band": band,
        "text_bands": merged,
        "narrow_bands": [{"top": a, "bottom": b, "kind": k, "x_span": sp}
                         for a, b, k, sp in narrow],
        "dropped_bands": [{"top": a, "bottom": b, "kind": k, "x_span": sp, "why": why}
                          for a, b, k, sp, why in dropped],
        "low_confidence": fallback,
        "suggested": sug,
        "spec_plate": {
            "plate_top_h": (spec.get("layout") or {}).get("plate_top_h"),
            "plate_bot_y": (spec.get("layout") or {}).get("plate_bot_y"),
        },
        "sampled_frames": [round(t, 3) for t, _ in frames],
    }
    dst = Path(spec.get("_path", ".")).resolve().parent / f"{spec['project_id']}.measure.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[measure] 结果已存 {dst}", flush=True)

    # 抽帧存图供人眼复核。★ 不能用 cv2.imwrite —— 它对中文路径**静默失败**（不报错、不写文件）
    try:
        import cv2
        shot = Path(spec.get("_path", ".")).resolve().parent / "_measure"
        shot.mkdir(parents=True, exist_ok=True)
        written = 0
        for t, img in frames[:6]:
            good, buf = cv2.imencode(".png", img)
            if good:
                (shot / f"{spec['project_id']}_t{t:.1f}.png").write_bytes(buf.tobytes())
                written += 1
        print(f"[measure] {written} 张代表帧 -> {shot}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[measure] 存帧跳过: {exc}", flush=True)
    return out


# ─────────────────── 字幕时序 / 图层构造 ───────────────────

def resolve_subtitles(spec):
    """把 subtitles 展开成 [{id, text, start, end}]。未给时序则按时长均分。

    ★ cues 与 overlay 分离（可选）：
        subtitles.cues     —— 必须**连续铺满** 0..clip_seconds 的段边界，喂给 source-audio-only
                              （服务端会校验相邻 cue 间隙 ≤0.02s、末段须到片尾，否则 422）
        subtitles.overlay  —— 真正上屏的字幕时序，按参考片字幕的实际出现时间，允许断续
    只给 items 时二者共用同一份（旧行为）。
    """
    sub = spec.get("subtitles") or {}
    items = list(sub.get("cues") or sub.get("items") or [])
    if not items:
        sys.exit("[fatal] spec.subtitles.cues / items 为空")
    clip = spec["source"].get("clip_seconds")
    if clip is None:
        clip = float(spec["source"].get("end_seconds") or 0) or None
    if clip is None:
        sys.exit("[fatal] spec.source.clip_seconds 必填（成片总时长）")
    n = int(spec["source"].get("segments") or len(items))
    seg = round(float(clip) / max(1, n), 4)

    out = []
    for i, it in enumerate(items):
        s = it.get("start_seconds")
        e = it.get("end_seconds")
        if s is None or e is None:
            s, e = round(i * seg, 4), round((i + 1) * seg, 4)
        out.append({"id": f"sub-{i + 1:03d}", "text": str(it["text"]).strip(),
                    "start": float(s), "end": float(e)})
    return out, seg


def _plate(lid, y, h, z, color):
    """整块深色板。text 必须非空（服务端会 strip 全角空格并报 422）。"""
    return {
        "id": lid, "text": "·",
        "x": 0.0, "y": round(y, 4), "width": 1.0, "height": round(h, 4),
        "font_family": "Microsoft YaHei", "font_size": 10, "font_weight": 400,
        "color": color, "stroke_color": color, "stroke_width": 0,
        "shadow_color": "#00000000", "shadow_blur": 0, "shadow_offset_x": 0, "shadow_offset_y": 0,
        "line_height": 1.0, "text_align": "center",
        "background_color": color, "background_opacity": 1.0,
        "enter_animation": "none", "exit_animation": "none",
        "start_seconds": 0.0, "end_seconds": FULL_END, "z_index": z,
    }


def _line(lid, text, y, h, size, weight, color, z, *, start=0.0, end=FULL_END,
          stroke="#000000", sw=0, x=0.05, w=0.90, glow=True):
    return {
        "id": lid, "text": text,
        "x": x, "y": round(y, 4), "width": w, "height": round(h, 4),
        "font_family": "Microsoft YaHei", "font_size": int(size), "font_weight": int(weight),
        "color": color, "stroke_color": stroke, "stroke_width": int(sw),
        "shadow_color": "#000000C0" if glow else "#00000000",
        "shadow_blur": 6 if glow else 0,
        "shadow_offset_x": 0, "shadow_offset_y": 2 if glow else 0,
        "line_height": 1.15, "text_align": "center",
        "background_color": "#000000", "background_opacity": 0.0,
        "enter_animation": "none", "exit_animation": "none",
        "start_seconds": start, "end_seconds": end, "z_index": z,
    }


def build_layers(spec, subs):
    """返回 (layers, plate_top_h, plate_bot_y)。

    标题在顶板内**垂直均分**（复刻参考片的四层结构）：
        TOTAL_H = Σ H_i + GAP*(n-1)      H_i = size_i * 1.15 / canvas_h
        Y_1     = (plate_top_h - TOTAL_H) / 2
        Y_{i+1} = Y_i + H_i + GAP
    """
    lay = spec.get("layout") or {}
    canvas_h = int(lay.get("height") or 1920)
    plate_color = str(lay.get("plate_color") or "#0E1218")
    plate_top_h = float(lay.get("plate_top_h") or 0.232)
    plate_bot_y = float(lay.get("plate_bot_y") or 0.652)
    gap = float(lay.get("title_gap") or 0.004)

    titles = list(spec.get("titles") or [])
    if not titles:
        sys.exit("[fatal] spec.titles 为空")

    hs = [round(float(t.get("size") or 46) * 1.15 / canvas_h, 4) for t in titles]
    total_h = sum(hs) + gap * (len(titles) - 1)
    y = (plate_top_h - total_h) / 2
    if y < 0.01:
        print(f"    ⚠ 标题总高 {total_h:.3f} 塞不进顶板 {plate_top_h}，已顶到 0.012 起排", flush=True)
        y = 0.012

    layers = [_plate("plate-top", 0.0, plate_top_h, 5, plate_color)]

    # 中板：盖掉参考片**画面内部**的烧入字幕带（落在中段画面与下段画面之间的黑缝里）。
    # 光靠上下板盖不住这类「落在画面内部的烧入字」，必须单独加一条中间板。
    mid_y = lay.get("plate_mid_y")
    if mid_y is not None:
        mid_y = float(mid_y)
        mid_h = float(lay.get("plate_mid_h") or 0.0)
        if mid_h > 0.01:
            layers.append(_plate("plate-mid", mid_y, mid_h, 5, plate_color))

    if lay.get("plate_bot", True) and (1.0 - plate_bot_y) > 0.01:
        layers.append(_plate("plate-bot", plate_bot_y, 1.0 - plate_bot_y, 5, plate_color))

    for i, t in enumerate(titles, 1):
        layers.append(_line(
            f"title-l{i}", str(t["text"]).strip(), y, hs[i - 1],
            t.get("size") or 46, t.get("weight") or 700, str(t.get("color") or "#FFFFFF"),
            9 + i,
            stroke=str(t.get("stroke_color") or "#000000"),
            sw=int(t.get("stroke_width") or 0),
            x=float(lay.get("title_x") or 0.05),
            w=float(lay.get("title_w") or 0.90),
        ))
        y += hs[i - 1] + gap

    sub_cfg = spec.get("subtitles") or {}
    if sub_cfg.get("emit_overlay", True):
        st = sub_cfg.get("style") or {}
        sy = float(sub_cfg.get("y") or st.get("y") or 0.755)
        ss = int(st.get("size") or 46)
        sh = max(round(ss * 1.15 / canvas_h, 4), 0.04)
        # overlay 优先取 subtitles.overlay（按参考片字幕真实出现时间，允许断续）；
        # 没给就退回用 cues（连续铺满）——那会让字幕整片常驻，仅在无更细时序时使用。
        raw_ov = list(sub_cfg.get("overlay") or [])
        for k, s in enumerate((raw_ov or subs), 1):
            s_start = float(s.get("start", s.get("start_seconds", 0.0)))
            s_end = float(s.get("end", s.get("end_seconds", FULL_END)))
            layers.append(_line(
                s.get("id") or f"sub-{k:03d}", str(s["text"]).strip(), sy, sh, ss,
                st.get("weight") or 700, str(st.get("color") or "#FFFFFF"), 20,
                start=s_start, end=s_end,
                stroke=str(st.get("stroke_color") or "#07111F"),
                sw=int(st.get("stroke_width") or 4),
                x=float(st.get("x") or 0.05), w=float(st.get("width") or 0.90),
            ))
    else:
        print("    [提示] subtitles.emit_overlay=false ⇒ 不生成 overlay 字幕层（沿用原片烧入字）",
              flush=True)

    return layers, plate_top_h, plate_bot_y


# ─────────────────────────── prep ───────────────────────────

def cmd_prep(spec):
    pid = spec["project_id"]
    src = Path(spec["source"]["video"])
    if not src.exists():
        sys.exit(f"[fatal] 原片不存在: {src}")

    subs, seg = resolve_subtitles(spec)
    clip = float(spec["source"]["clip_seconds"])
    n_seg = int(spec["source"].get("segments") or len(subs))
    layers, plate_top_h, plate_bot_y = build_layers(spec, subs)
    # Choose one caption source. Some deployed backends still burn disabled ASS;
    # see the runbook's opaque-plate fallback and verify the rendered output.
    subtitle_mode = str((spec.get("subtitles") or {}).get("mode") or "system")
    if subtitle_mode not in {"system", "overlay", "source"}:
        sys.exit("[fatal] subtitles.mode 必须是 system / overlay / source")
    if subtitle_mode in {"system", "source"}:
        layers = [layer for layer in layers if not layer["id"].startswith("sub-")]
    if spec.get("composition_layers") is not None:
        layers = list(spec["composition_layers"])

    print(f"[prep] {pid}  原片={src.name}  成片 {clip}s / {n_seg} 段 x {seg}s  "
          f"板 {plate_top_h}-{plate_bot_y}", flush=True)

    # ---- 1. 建项目（已存在则复用）----
    st, res = call("POST", "/api/projects", {
        "project_id": pid,
        "title": str(spec.get("meta", {}).get("title") or pid),
        "pipeline_type": "animated-explainer",
        "aspect": "portrait",
        "duration_seconds": int(round(clip)),
        "style_playbook": str(spec.get("meta", {}).get("style_playbook") or "dark-tech-news"),
        "brief": str(spec.get("meta", {}).get("brief")
                     or "上下窗口轻量复刻：原片画面居中保留，上下换自有板 + 标题 / 字幕。无配音、纯 BGM。"),
    })
    if not ok(st, "create project", res) and "已存在" not in str(res):
        sys.exit("[fatal] 建项目失败")
    if spec.get("output_target_lufs") is not None:
        st, res = call("PUT", f"/api/project/{pid}/workbench/output-loudness-policy",
                       {"target_lufs": float(spec["output_target_lufs"])})
        if not ok(st, "output loudness", res):
            sys.exit("[fatal] 响度设置失败")

    # ---- 2. 上传原片（一个文件复用 N 段，走 visual-timeline 的 source_in/out）----
    wb = call("GET", f"/api/project/{pid}/workbench")[1]
    existing = {str(a.get("name") or "") for a in (wb.get("assets") or [])}
    asset_label = str(spec["source"].get("asset_label") or "复刻原片")
    if asset_label in existing:
        print(f"    [2] 原片已上传（{asset_label}），跳过", flush=True)
    else:
        st, res = call("PUT",
                       f"/api/project/{pid}/workbench/assets/uploads"
                       f"?filename={urllib.parse.quote(src.name)}"
                       f"&name={urllib.parse.quote(asset_label)}"
                       f"&license={urllib.parse.quote(str(spec['source'].get('license') or '用户自有复刻素材'))}",
                       raw=src.read_bytes(), timeout=1800)
        if not ok(st, "upload source video", res):
            sys.exit("[fatal] 上传原片失败")

    # ---- 3. 上传 BGM ----
    bgm = spec.get("assets", {}).get("bgm")
    if bgm:
        bp = (REPO / bgm) if not Path(bgm).is_absolute() else Path(bgm)
        if not bp.exists():
            print(f"    [3] BGM 找不到，跳过: {bp}", flush=True)
        else:
            st, res = call("POST",
                           f"/api/project/{pid}/workbench/music/uploads"
                           f"?filename={urllib.parse.quote(bp.name)}",
                           raw=bp.read_bytes(), timeout=600)
            ok(st, f"upload bgm {bp.name}", res)

    # ---- 4. track_id 必须回读，不许手打 hash ----
    sys.path.insert(0, str(REPO))
    from backlot.music_library import list_music_tracks  # noqa: E402

    cat = list_music_tracks(REPO / "projects" / pid)
    tracks = cat.get("tracks") if isinstance(cat, dict) else list(cat or [])
    proj_tracks = [t for t in tracks
                   if isinstance(t, dict) and str(t.get("scope") or "") == "project"]
    if not proj_tracks:
        sys.exit("[fatal] 项目里没有音轨 —— BGM 没上传成功？")
    track_id = str(proj_tracks[-1]["id"])
    print(f"    [4] track_id = {track_id}", flush=True)

    # ---- 5. 源音频时钟 + 定时字幕 cue ----
    wb = call("GET", f"/api/project/{pid}/workbench")[1]
    rev = int(((wb.get("source_audio_contract") or {}).get("revision")) or 0)
    cues = [{"id": f"cue-{i + 1:03d}", "label": f"片{i + 1}",
             "start_seconds": s["start"], "end_seconds": s["end"],
             "text": s["text"],
             "visual_query": str(spec["source"].get("visual_query") or "original footage")}
            for i, s in enumerate(subs)]
    st, res = call("PUT", f"/api/project/{pid}/workbench/source-audio-only", {
        "confirmed": True, "expected_revision": rev, "track_id": track_id,
        "source_start_seconds": 0.0, "source_end_seconds": clip,
        "speed": 1.0, "loop": False,
        "title": str(spec.get("meta", {}).get("title") or pid),
        "cues": cues,
    })
    if not ok(st, f"source-audio-only ({len(cues)} cues)", res):
        sys.exit("[fatal] source-audio-only 失败")

    # ---- 6. 逐段绑画面：同一个 asset，用 source_in/out 取不同区间 ----
    wb = call("GET", f"/api/project/{pid}/workbench")[1]
    by_name = {str(a.get("name") or ""): a for a in (wb.get("assets") or [])}
    a = by_name.get(asset_label) or {}
    if not a.get("id"):
        sys.exit(f"[fatal] 找不到素材「{asset_label}」")
    offset = float(spec["source"].get("start_seconds") or 0.0)
    for i in range(n_seg):
        sid = f"cue-{i + 1:03d}"
        st, res = call("PATCH", f"/api/project/{pid}/workbench/scenes/{sid}",
                       {"source_strategy": "human_provided"})
        if not ok(st, f"{sid} strategy"):
            continue
        # 段边界以 cues 的真实时间为准 —— source-audio-only 已按 cues 建好 scene 边界；
        # 若这里退回均分（offset + i*seg），与 scene 时长不符就会 422。
        if len(subs) == n_seg:
            s_start = round(float(subs[i]["start"]), 3)
            s_end = round(float(subs[i]["end"]), 3)
        else:
            s_start = round(i * seg, 3)
            s_end = round((i + 1) * seg, 3)
        dur = round(s_end - s_start, 3)
        s0 = round(offset + s_start, 3)
        st, res = call("PUT", f"/api/project/{pid}/workbench/scenes/{sid}/visual-timeline",
                       {"blocks": [{
                           "id": "VB-001", "start_seconds": 0.0, "end_seconds": dur,
                           "source_mode": "human_provided", "asset_id": a.get("id"),
                           "label": asset_label,
                           "source_in_seconds": s0, "source_out_seconds": round(s0 + dur, 3),
                       }]})
        ok(st, f"{sid} timeline  [{s0}–{round(s0 + dur, 3)}] dur={dur}", res)

    # ---- 7. 写 overlay 图层 ----
    cur = call("GET", f"/api/project/{pid}/workbench/text-overlay-composition")[1]
    orev = int((cur or {}).get("revision") or 0) if isinstance(cur, dict) else 0
    st, res = call("PUT", f"/api/project/{pid}/workbench/text-overlay-composition",
                   {"expected_revision": orev,
                    "composition": {"version": 1, "layers": layers}})
    if not ok(st, f"overlay ({len(layers)} layers)", res):
        sys.exit("[fatal] overlay 写入失败")
    for l in layers:
        print(f"      {l['id']:12s} y={l['y']:<8} h={l['height']:<8} "
              f"fs={l['font_size']:<4} z={l['z_index']:<3} {str(l['text'])[:24]!r}", flush=True)

    # ---- 8. 显式选择字幕模式；最终仍须核验服务端是否遵守 enabled ----
    #   ★ 踩过的坑：source-audio-only 会把 cues 的 text 落到 scene.description / narration.text，
    #     渲染时 _write_subtitles 用它落成 assets/subtitles.srt+.ass，再由 ffmpeg 烧进画面
    #     （默认 \pos(540,1450) ⇒ y=0.755）。如果这时 overlay 再画一份字幕，同一句话会出现两遍
    #     （实测成片：中缝一条 + 下段画面内一条，内容相同）。
    #   ⇒ 字幕只保留一处来源：工作台字幕系统。把它的 position.y 调到「中板内」即可——
    #     中板盖掉参考片的烧入字幕，我们的字幕正好落在中板上，视觉上就是替换而非叠加。
    sstyle = (spec.get("subtitles") or {}).get("style") or {}
    sys_y = float((spec.get("subtitles") or {}).get("system_y") or 0.566)
    sys_w = float(sstyle.get("width") or 0.94)
    st, res = call("POST", f"/api/project/{pid}/workbench/subtitle-styles", {
        "template_id": "subtitle-default", "name": "标准中文短句字幕",
        "set_default": True, "apply_scope": "all",
        "style": {"enabled": subtitle_mode == "system", "font": "Microsoft YaHei",
                  "font_size": int(sstyle.get("size") or 46),
                  "bold": bool(int(sstyle.get("weight") or 700) >= 600),
                  "text_color": str(sstyle.get("color") or "#FFFFFF"),
                  "outline_color": str(sstyle.get("stroke_color") or "#07111F"),
                  "outline_width": max(2, int(sstyle.get("stroke_width") or 4)),
                  "background_enabled": False, "background_color": "#07111F",
                  "background_opacity": 68,
                  "position": {"x": 0.5, "y": sys_y, "width": sys_w, "anchor": "bottom-center"},
                  "max_lines": 3},
    })
    ok(st, f"subtitle system applied (bottom-center y={sys_y})", res)

    # ---- 9. 全片预览（改过 overlay ⇒ 必须 preview → approve → render）----
    return _run_job(pid, "full-preview", spec)


def _run_job(pid, kind, spec):
    """起 full-preview / video-render 任务并等终态。"""
    if kind == "full-preview" and spec.get("queue_preview", True):
        # Full previews are cross-project production and must go through the
        # shared queue; new specs may set this explicitly for readability.
        key = str(spec.get("queue_idempotency_key") or f"window-remake:{pid}:full-preview")
        st, res = call("POST", "/api/production-queue/jobs", {
            "project_id": pid,
            "kind": "full_preview",
            "priority": "normal",
            "idempotency_key": key,
            "request": {"confirmed": True},
        })
        if not ok(st, "enqueue full-preview", res):
            sys.exit("[fatal] 全片预览入队失败")
        q = (res or {}).get("queue_job") or {}
        qid = str(q.get("job_id") or q.get("id") or "")
        if not qid:
            sys.exit("[fatal] 统一队列没有返回任务编号")
        t0 = time.time()
        while time.time() - t0 < SLOT_TIMEOUT_S:
            time.sleep(POLL_S)
            st, q = call("GET", f"/api/production-queue/jobs/{urllib.parse.quote(qid)}")
            if st != 200:
                continue
            status = str(q.get("status") or "")
            if status in {"completed", "failed", "cancelled", "ambiguous", "awaiting_human"}:
                print(f"    [queue {int(time.time()-t0)}s] full-preview={status} "
                      f"job={qid} result={q.get('result')} error={q.get('error')}", flush=True)
                if status != "completed":
                    sys.exit(1)
                wb = call("GET", f"/api/project/{pid}/workbench")[1]
                preview = ((wb.get("automation") or {}).get("preview_render") or {})
                if preview.get("status") != "completed":
                    sys.exit("[fatal] 队列已完成，但项目预览状态未完成")
                return preview
            if int(time.time() - t0) % 30 < POLL_S:
                print(f"    [queue {int(time.time()-t0)}s] {status or 'queued'} …", flush=True)
        sys.exit(f"[fatal] 统一队列全片预览超时 {SLOT_TIMEOUT_S}s")

    path = f"/api/project/{pid}/workbench/automation/{kind}/jobs"
    wb = call("GET", f"/api/project/{pid}/workbench")[1]
    key = "preview_render" if kind == "full-preview" else "render"
    before = ((wb.get("automation") or {}).get(key) or {}).get("finished_at")

    st, res = call("POST", path, {"confirmed": True})
    if not ok(st, f"start {kind}", res):
        sys.exit(f"[fatal] {kind} 起不来")

    t0 = time.time()
    while time.time() - t0 < SLOT_TIMEOUT_S:
        time.sleep(POLL_S)
        wb = call("GET", f"/api/project/{pid}/workbench")[1]
        j = ((wb.get("automation") or {}).get(key)) or {}
        s = j.get("status")
        done = (s == "completed" and j.get("finished_at") and j.get("finished_at") != before)
        if done or s == "failed":
            el = int(time.time() - t0)
            print(f"    [{el}s] {kind}={s} ver={j.get('version')} "
                  f"out={j.get('output_path')} err={str(j.get('error'))[:300]}", flush=True)
            if s != "completed":
                sys.exit(1)
            return j
        if int(time.time() - t0) % 30 < POLL_S:
            print(f"    [{int(time.time() - t0)}s] {s} …", flush=True)
    sys.exit(f"[fatal] {kind} 超时 {SLOT_TIMEOUT_S}s")


# ─────────────────────────── final ───────────────────────────

def cmd_final(spec):
    pid = spec["project_id"]

    wb = call("GET", f"/api/project/{pid}/workbench")[1]
    pv = ((wb.get("automation") or {}).get("preview_render")) or {}
    print(f"[final] preview={pv.get('status')} ver={pv.get('version')} "
          f"out={pv.get('output_path')}", flush=True)
    if pv.get("status") != "completed":
        sys.exit("[fatal] 全片预览还没完成 —— 先跑 prep，并**人工看过预览**再 final")

    st, res = call("POST", f"/api/project/{pid}/workbench/review/full-preview/approve",
                   {"confirmed": True})
    ok(st, "approve full-preview", res)
    if st != 200:
        sys.exit("[fatal] 批准失败")
    for s in (res.get("scenes") or []):
        print(f"      {s.get('id')} {s.get('review_status')}", flush=True)

    j = _run_job(pid, "video-render", spec)
    print(f"\n[final] 成片 = {j.get('output_path')}", flush=True)
    return j


# ─────────────────────────── main ───────────────────────────

def main():
    ap = argparse.ArgumentParser(description="上下窗口轻量复刻驱动")
    ap.add_argument("cmd", choices=["measure", "prep", "final"])
    ap.add_argument("spec", help="spec JSON 路径")
    args = ap.parse_args()

    sp = Path(args.spec)
    if not sp.exists():
        sys.exit(f"[fatal] spec 不存在: {sp}")
    spec = json.loads(sp.read_text(encoding="utf-8"))
    spec["_path"] = str(sp)
    if "project_id" not in spec:
        sys.exit("[fatal] spec.project_id 必填")

    if args.cmd == "measure":
        cmd_measure(spec)
    elif args.cmd == "prep":
        cmd_prep(spec)
    else:
        cmd_final(spec)


if __name__ == "__main__":
    main()
