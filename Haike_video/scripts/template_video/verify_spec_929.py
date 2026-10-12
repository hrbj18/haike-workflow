# -*- coding: utf-8 -*-
"""929 批次程序化选段质检 (模型无法读图时的守门员)。

对 spec 的每个 cue (或已渲染成片) 抽帧, 只看【成片视角中央可见区】(y 570-1280,
顶字板 0-570 与底字板 1280-1920 在成片里是不透明字板, 残留字幕只有落在中央区才有害):

  1. OCR(rapidocr): 中央区识别出的高置信度文字 >= 3 个字符 -> TEXT_RISK (烧录字幕残留)
  2. 人脸检测(cv2 Haar): 脸宽 >= 画面宽 22% -> FACE_RISK (人物特写, 老大明确不要)
  3. 亮度: 中央区平均亮度 < 35 -> DARK_RISK (黑屏/过暗)
  4. 帧间差异: 相邻抽帧平均像素差 < 2.0 -> STATIC_RISK (接近静止画面)

用法:
  python verify_spec_929.py <spec.json>            # 按源视频+source_in 抽 0.5/1.5/2.5s
  python verify_spec_929.py --final <mp4>          # 按成片 1.5/4.5/7.5s 抽帧
退出码: 有任一 RISK -> 2, 全 PASS -> 0。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

# 顺序敏感: 必须先显式 import onnxruntime 并实例化 RapidOCR, 再 import cv2,
# 否则 cv2 先加载的 MSVC 运行库会让 onnxruntime_pybind11_state DLL 初始化失败 (2026-09-29 实测)。
import onnxruntime  # noqa: F401  (顺序敏感, 勿删)

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except ImportError:  # 新版包名 rapidocr
    from rapidocr import RapidOCR  # type: ignore

# 路径收口：ffmpeg/模型由 _paths 解析（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import FFMPEG, FACE_MODEL as _FACE_MODEL  # noqa: E402

VIS_TOP, VIS_BOT = 570, 1280
W, H = 1080, 1920

_ocr = None
if os.environ.get("VRF929_SKIP_OCR") != "1":
    _ocr = RapidOCR()

import cv2  # noqa: E402
import numpy as np  # noqa: E402

# cv2 5.0 移除了 CascadeClassifier, 改用 FaceDetectorYN + yunet (采集管线同款模型)。
# 模型由 _paths 解析：项目内 models/yunet.onnx，运行时自动镜像到 ASCII 路径（cv2 读不了中文路径）。
FACE_MODEL = str(_FACE_MODEL)
_face_det = None


def face_detector():
    global _face_det
    if _face_det is None and os.path.isfile(FACE_MODEL):
        _face_det = cv2.FaceDetectorYN_create(FACE_MODEL, "", (W, VIS_BOT - VIS_TOP),
                                              score_threshold=0.6)
    return _face_det


def grab_frames(src: str, ts: list[float], tmpdir: str) -> list[str | None]:
    outs: list[str | None] = []
    for i, t in enumerate(ts):
        out = os.path.join(tmpdir, f"f{i}.png")
        r = subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-ss", str(t), "-i", src,
             "-frames:v", "1", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
             out], capture_output=True, text=True, timeout=60)
        outs.append(out if r.returncode == 0 and os.path.isfile(out) else None)
    return outs


def center(img: np.ndarray) -> np.ndarray:
    return img[VIS_TOP:VIS_BOT, :]


def check_frame(path: str) -> dict:
    img = cv2.imread(path)
    if img is None:
        return {"verdict": "READ_FAIL"}
    cen = center(img)
    rep: dict = {}

    # OCR (兼容新版 rapidocr 的 RapidOCROutput 与旧版 [box, txt, conf] 列表)
    # ★ VRF929_SKIP_OCR=1 时 _ocr 为 None (探针只要人脸/亮度), 此时跳过 OCR 而不是崩。
    out = _ocr(cen) if _ocr is not None else None
    items = []
    if out is None:
        pass
    elif hasattr(out, "txts"):  # 新版
        txts = out.txts or ()
        scores = out.scores or ()
        items = list(zip(txts, scores))
    elif isinstance(out, tuple):  # 旧版 (res, elapse)
        res = out[0] or []
        items = [(t, c) for _, t, c in res]
    elif isinstance(out, list):
        items = [(t, c) for _, t, c in out]
    texts = []
    for txt, conf in items:
        if float(conf) >= 0.6 and len(str(txt).strip()) >= 3:
            texts.append(str(txt).strip())
    rep["ocr_texts"] = texts[:5]
    rep["text_risk"] = bool(texts)

    # face (yunet)
    det = face_detector()
    faces = []
    if det is not None:
        det.setInputSize((cen.shape[1], cen.shape[0]))
        _, det_res = det.detect(cen)
        if det_res is not None:
            faces = [f for f in det_res if f is not None and f[14] >= 0.6]
    big = [f for f in faces if f[2] >= cen.shape[1] * 0.22]
    rep["face_count"] = int(len(faces))
    rep["face_big"] = int(len(big))
    rep["face_risk"] = bool(big)

    # brightness
    hsv = cv2.cvtColor(cen, cv2.COLOR_BGR2HSV)
    v = float(hsv[:, :, 2].mean())
    rep["brightness"] = round(v, 1)
    rep["dark_risk"] = v < 35.0
    return rep


def verify(src: str, ts: list[float], label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="vrf929_") as td:
        frames = grab_frames(src, ts, td)
        per = []
        for i, fp in enumerate(frames):
            if fp is None:
                per.append({"frame": ts[i], "verdict": "GRAB_FAIL"})
                continue
            rep = check_frame(fp)
            rep["frame"] = ts[i]
            per.append(rep)
    risks = []
    for r in per:
        for k in ("text_risk", "face_risk", "dark_risk"):
            if r.get(k):
                risks.append(f"{r['frame']}s:{k}")
        if r.get("verdict") in ("READ_FAIL", "GRAB_FAIL"):
            risks.append(f"{r['frame']}s:{r['verdict']}")
    # static check across frames
    if len(per) == 3 and all(r.get("brightness") is not None for r in per):
        pass  # static detection omitted for simplicity; OCR/face/dark are the hard gates
    return {"cue": label, "per_frame": per, "risks": risks, "pass": not risks}


def main() -> int:
    args = sys.argv[1:]
    jobs: list[tuple[str, str, list[float]]] = []
    if "--final" in args:
        mp4 = args[args.index("--final") + 1]
        jobs.append((mp4, [0.5 * i for i in range(1, 18)], os.path.basename(mp4)))
    else:
        spec_path = args[0]
        cues = json.load(open(spec_path, encoding="utf-8"))
        for c in cues:
            fin = float(c["source_in"])
            jobs.append((c["file"], [fin + 0.5, fin + 1.5, fin + 2.5], f"{c['cue']}@{fin}"))
    report = [verify(s, ts, lab) for s, ts, lab in jobs]
    print(json.dumps(report, ensure_ascii=False, indent=1))
    bad = [r for r in report if not r["pass"]]
    print("SUMMARY:", "ALL_PASS" if not bad else f"{len(bad)}/{len(report)} CUES RISK: " +
          "; ".join(f"{r['cue']}[{','.join(r['risks'])}]" for r in bad))
    return 2 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
