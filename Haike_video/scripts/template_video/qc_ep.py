# -*- coding: utf-8 -*-
"""单期成片 QC 门禁（L1+L2）：中央可见带 OCR 文本风险 + 人脸风险 + 暗帧风险。

用法:
  python qc_ep.py <final.mp4> <label> [step] [vis_top]

输出:
  <WORK>/qc_final_<label>.json   —— 逐帧明细（与既有 qc_final_*.json 同 schema）
  控制台 SUMMARY 行 + 退出码（有 risk 时 2）

判据:
  text_risk  = 中央可见带(y vis_top..1280) OCR 到含 CJK 的文本（烧录中文字幕/中文水印）
  face_risk  = 中央可见带检出人脸宽 >= 带宽 22%
  dark_risk  = 中央可见带平均亮度 V < 45
必须用带 onnxruntime/rapidocr 的解释器（本机 = Haike_video/.venv/Scripts/python.exe）。
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile

import onnxruntime  # noqa: F401  顺序敏感: 先于 rapidocr/cv2
from rapidocr import RapidOCR

import cv2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 路径收口：工作目录/模型/ffmpeg 统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import WORK_DIR, FACE_MODEL as _FACE_MODEL, FFMPEG  # noqa: E402
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backlot.material_library_template import validate_spec, text_is_approved, product_region_is_approved

W, H = 1080, 1920
WORK = str(WORK_DIR)
FACE_MODEL = str(_FACE_MODEL)
CJK = re.compile(r"[\u4e00-\u9fff]")
DARK_V = 45.0
# 单字命中几乎都是 OCR 噪声（实测：Claude 星芒 logo「✳」被稳定误读为「米」）。
# 默认要求 >=2 个 CJK 字才判 text_risk；需要严格模式可传 0 关闭。
MIN_CJK = 2

mp4 = sys.argv[1]
label = sys.argv[2]
step = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
VIS_TOP = int(sys.argv[4]) if len(sys.argv) > 4 else 650
VIS_BOT = 1280
approved_by_cue = []
regions_by_cue = []
# Only immutable, source-verified graded specs may permit on-set product text.
match = re.search(r"(t\d+)", label)
spec_file = Path(WORK) / f"spec_{match.group(1)}.json" if match else None
if spec_file and spec_file.is_file():
    cues = json.loads(spec_file.read_text(encoding="utf-8"))
    if validate_spec(cues):
        approved_by_cue = [cue.get("visible_text", []) for cue in cues]
        regions_by_cue = [cue.get("product_text_regions", []) for cue in cues]

ocr = RapidOCR()
assert os.path.isfile(FACE_MODEL), "face model missing: " + FACE_MODEL
det = cv2.FaceDetectorYN_create(FACE_MODEL, "", (W, VIS_BOT - VIS_TOP), score_threshold=0.6)

per_frame = []
risks = []
with tempfile.TemporaryDirectory(prefix="qcep_") as td:
    pat = os.path.join(td, "f_%05d.png")
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", mp4, "-vf",
         "fps=%f,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
         % (1.0 / step, W, H, W, H), "-start_number", "0", pat],
        check=True, timeout=1800)
    frames = sorted(glob.glob(os.path.join(td, "f_*.png")))
    for i, fp in enumerate(frames):
        t = round(i * step, 2)
        img = cv2.imread(fp)
        if img is None:
            continue
        cen = img[VIS_TOP:VIS_BOT, :]
        res = ocr(cen)
        txts = []
        boxes = []
        if res is not None and getattr(res, "txts", None):
            for index, (txt, score) in enumerate(zip(res.txts, res.scores)):
                s = str(txt)
                if float(score) >= 0.6 and len(CJK.findall(s)) >= MIN_CJK:
                    txts.append(s)
                    boxes.append(res.boxes[index] if getattr(res, "boxes", None) is not None else None)
        det.setInputSize((cen.shape[1], cen.shape[0]))
        _, fres = det.detect(cen)
        faces = [] if fres is None else [f for f in fres if f is not None and f[14] >= 0.6]
        big = [f for f in faces if f[2] >= cen.shape[1] * 0.22]
        v = float(cv2.cvtColor(cen, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
        approved = approved_by_cue[min(int(t // 3), 2)] if approved_by_cue else []
        regions = regions_by_cue[min(int(t // 3), 2)] if regions_by_cue and VIS_TOP == 650 else []
        accepted = [text_is_approved(text, approved) or product_region_is_approved(
            box, regions, t % 3, cen.shape[1], cen.shape[0]) for text, box in zip(txts, boxes)]
        unapproved = [text for text, allowed in zip(txts, accepted) if not allowed]
        rec = {
            "ocr_texts": txts,
            "approved_product_texts": [text for text, allowed in zip(txts, accepted) if allowed],
            "text_risk": bool(unapproved),
            "face_count": len(faces),
            "face_big": len(big),
            "face_risk": bool(big),
            "brightness": round(v, 1),
            "dark_risk": v < DARK_V,
            "frame": t,
        }
        per_frame.append(rec)
        for k in ("text_risk", "face_risk", "dark_risk"):
            if rec[k]:
                risks.append("%ss:%s" % (t, k))

out = [{"cue": os.path.basename(label), "per_frame": per_frame, "risks": risks,
        "pass": not risks}]
path = os.path.join(WORK, "qc_final_%s.json" % label)
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE", path)
print("SUMMARY: %d/%d CUES RISK: %s%s"
      % (1 if risks else 0, 1, os.path.basename(label),
         ("[" + ",".join(risks) + "]") if risks else " PASS"))
raise SystemExit(2 if risks else 0)
