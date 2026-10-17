# -*- coding: utf-8 -*-
"""模板分级选段：默认采用共享素材库中经过裁切确认的秒段。

默认用法：auto_pick_0930.py t25 昇腾950 [--library-plan plan.json]
指定交付目录时用 --exact，并用 --topic 保留原主题；--folders-file
需包含 t_key/topic/folders。未确认或覆盖不足返回2及 material_gap_*.json。
成功保存冻结spec及旧版；执行者须通过 material_library_cli.py prepare/submit
确认原片和实际裁切图，随后运行 select_cut_923.py 和成片QC。

以下为显式 --legacy-pick 下的历史扫描说明，默认入口不运行这些启发式。

原来这一步靠人看画面挑 3 个镜头；无人看管场景改成**数据驱动**：
对每个候选素材逐秒抽帧，用 OCR 排掉中央可见带（canvas y650-1280）里带中文的
烧录字幕/水印，用亮度排掉近黑/过曝帧，用灰度方差排掉纯色无内容帧，
再结合采集端给的 relevance_score 打分，挑 3 个 3 秒窗口。

v2 的两处关键提速（0930 凌晨实测，否则 6 条视频跑到天亮也出不完）:
  1) **两阶段判定**：先对所有帧做「便宜判据」（HSV 的 V 均值 / 灰度标准差 /
     YuNet 人脸），只对通过便宜判据且排在前面的候选窗口的帧做 OCR。
     OCR 是绝对瓶颈（约 1.5s/帧，占单素材耗时的 90%），v1 对每条素材的
     全部 193 帧都跑 OCR，扫一条 96s 素材要 9 分 40 秒。
  2) **多进程并行**：一条素材一个 worker（各自初始化 RapidOCR + YuNet），
     7 条素材并行。配合 1) 后单条任务从 ~68 分钟降到 ~3 分钟。

用法:
  python auto_pick_0930.py <t_key> <theme_keyword>          # 自动匹配最新素材目录
  python auto_pick_0930.py <t_key> <素材目录名> --exact      # 直接指定目录
  python auto_pick_0930.py <t_key> <kw> --jobs 4            # 并行度（默认 4）
  python auto_pick_0930.py --folders-file cfg.json          # ★ 多目录合并 + 强制无脸
    cfg.json:
      {"t_key":"t25", "folders":["9.29昇腾950复刻视频", "..."],
       "strict_noface":true, "jobs":4, "min_face_free":3}

★ 为什么要有 `--folders-file`（2026-09-30 老大返工 t25 时加）：
  1) 单主题素材目录常常**整条都是博主口播大脸**（昇腾950-主素材-01），
     原来"无脸不足 3 个就带脸兜底"会把大脸选进成片，开场就是一张脸。
  2) 主题词是中文，直接从命令行传参在 MSYS 下会被参数转换搞坏，
     所以候选目录走 JSON 文件。
  3) strict_noface=true 时**禁止带脸兜底**，无脸窗口不够就 rc=2 报错，
     让调用方去扩素材池，而不是悄悄交一条大脸成片。

输出:
  <WORK>/spec_<t_key>.json       —— 格式对齐 spec_t23.json，供 select_cut_923.py cut 用
  <WORK>/autopick_<t_key>.json   —— 评分明细（返工/审计用）

退出码: 0 成功写出 spec；1 未找到素材目录；2 可用窗口不足 3 个。
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
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ★ 路径常量必须在模块顶层导入，不能放进 `if __name__ == "__main__"`：
#   Windows 的 ProcessPoolExecutor 用 spawn，子进程会重新 import 本模块
#   （此时 __name__ == "__mp_main__"），__main__ 块不会执行 —— 放里面会导致
#   worker 里 DELIV / FFMPEG / FACE_MODEL 全部 NameError。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (WORK_DIR, COPY_SKILL_OUT as DELIV, FFMPEG, FFPROBE,
                    FACE_MODEL)  # noqa: E402

WORK = str(WORK_DIR)
W, H = 1080, 1920
VIS_TOP, VIS_BOT = 650, 1280          # 版式 v2 中央可见带
CJK = re.compile(r"[\u4e00-\u9fff]")
CLIP = 3.0
# 抽帧密度与 qc_ep.py 完全一致（2fps、从 t=0 起）。低于此密度会漏检中间帧的
# 中文烧录字幕，成片必然在 QC 栽 text_risk（t24 第一版就是 1fps 漏检的）。
FPS = 2.0
# ★ 亮度判据必须与 qc_ep.py 用同一把尺子：QC 的 dark_risk 判的是 HSV 的 V 均值 <45，
#   而不是灰度均值。早期版本误用灰度均值并设 LUMA_MIN=35，把大量暗色科技风素材
#   （灰度 20-33 但 V 有 45+）整片排除，导致 windows=0。
DARK_V = 48.0            # QC 阈值 45 + 余量 3；低于此判过暗
OVER_V = 245.0           # 高于此判过曝
# ★ 灰度标准差只用于「排掉纯色静止帧」，QC 并不判这一项，属于我自己加的审美过滤，
#   所以阈值要松：0930 实测 6.0 会把整条暗色机房素材判成 windows=0（昇腾950 前
#   两条素材全 0），直接断掉一条选题的素材来源。窗口最终按 std 降序挑选，
#   放宽阈值并不会让"差画面"被选中，只是不再误杀。
STD_MIN = 4.0
OCR_SCORE = 0.6                       # 与 scan_subs_929.py 一致
# 人脸判据与 qc_ep.py 完全一致（YuNet, score>=0.6, 脸宽>=中央带宽 22%）。
# ★ 不在选段阶段排掉大脸的话，成片必然 face_risk —— t24 第一条就栽在这：
#   18 帧里 12 帧 face_risk，text/dark 全干净。
FACE_BIG_RATIO = 0.22
FACE_SCORE = 0.6

# 两阶段判定的批次控制：每批取 WIN_BATCH 个候选窗口做 OCR，够 WIN_TARGET 个
# 干净窗口就停。OCR 是瓶颈，宁可少判也不要全扫。
# ★ 批次一定要小：OCR 约 1.5s/帧，WIN_BATCH=20 时单条 16s 素材也要 OCR 约 60 帧
#   （窗口间隔 1.5s 但窗长 3s，相邻窗口的帧大量重叠，去重后仍随批次数线性增长），
#   实测 1 分 50 秒才扫完一条 33 帧的素材。我们只需要每个素材贡献 3 个镜头，
#   取 6 个候选窗口做 OCR 足够，不够再补一批。
WIN_BATCH = 6
WIN_TARGET = 8           # 每个素材最多返回 8 个窗口（跨素材多样性另算）
MAX_BATCHES = 3

# ★ 只抽中央可见带，不再落全帧：1080x1920 全帧 PNG 约 2.5MB/帧，一条素材 770 帧
#   就是 ~2GB 磁盘 IO，反而比逐帧 seek 还慢（t24 曾跑 26 分钟没完）。
#   OCR/人脸/亮度都只在这一带上判定，全帧信息本来就是浪费。
SCALE = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
         f"crop={W}:{VIS_BOT - VIS_TOP}:0:{VIS_TOP}")
FRAME_EXT = ".jpg"
FRAME_Q = "3"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_folder(kw: str) -> str | None:
    """按关键词匹配素材目录。

    ★ 0930 有两个坑，必须按优先级处理：
      1) v1 整句式主题留下过**空目录**（如 "9.29OpenAI取消GPT-6.1发布复刻视频"），
         短主体词 "GPT-6.1" 会命中它。故先按**批次日期前缀**过滤（优先 9.30）。
      2) 同名主题的旧批次目录（backup/empty）一律跳过。
    """
    if not os.path.isdir(DELIV):
        return None
    batch_pref = ("9.30", "9.29")          # 本批次目录日期前缀，按序优先
    cands = []
    for d in os.listdir(DELIV):
        if kw not in d:
            continue
        low = d.lower()
        if "empty" in low or "backup" in low or "trash" in low:
            continue
        p = os.path.join(DELIV, d)
        if not os.path.isdir(p):
            continue
        pref_rank = next((i for i, x in enumerate(batch_pref) if d.startswith(x)), 99)
        cands.append((pref_rank, os.path.getmtime(p), d))
    if not cands:
        return None
    # rank 小(9.30)优先；同 rank 取 mtime 最新（-mtime 升序 = 新的在前）
    cands.sort(key=lambda x: (x[0], -x[1]))
    log(f"FOLDER theme={kw} -> {cands[0][2]}  (cands={len(cands)})")
    return cands[0][2]


def probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def grab_all(td: str, video: str) -> list[tuple[float, str]]:
    """一次解码、按 FPS 输出全部缩放到 1080x1920 的帧。

    ★ 早期版本每帧单独起一次 `ffmpeg -ss` seek：1.7s/帧里约 1.4s 是进程启动+
      重新 seek 解码的开销，扫一条素材要 10 分钟。批量解码把这部分摊掉，
      使抽帧密度提到与 QC 相同的 2fps 仍然更快。
    ★ 同时与 qc_ep.py 的抽帧方式对齐（fps=2、从 t=0 起、同 SCALE），
      否则选段抽 1fps、QC 抽 2fps，中间帧的中文会漏检 → 成片 text_risk。
    """
    pat = os.path.join(td, "f_%05d" + FRAME_EXT)
    try:
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", video, "-vf",
             f"fps={FPS},{SCALE}", "-q:v", FRAME_Q, "-start_number", "0", pat],
            capture_output=True, text=True, timeout=3600)
    except Exception:
        return []
    out = []
    for i, fp in enumerate(sorted(glob.glob(os.path.join(td, "f_*" + FRAME_EXT)))):
        out.append((round(i / FPS, 2), fp))
    return out


def norm_rel(v) -> float:
    try:
        x = float(v)
    except Exception:
        return 0.5
    if x > 1.0:          # 采集端可能给 0-100
        x = x / 100.0
    return max(0.0, min(1.0, x))


# ----------------------------------------------------------------------------
# worker 侧（每个子进程独立初始化 RapidOCR + YuNet）
# ----------------------------------------------------------------------------
_OCR = None
_DET = None


def _init_worker() -> None:
    global _OCR, _DET
    # ★ 顺序敏感：先 onnxruntime，再 rapidocr / cv2（见 README §1）
    import onnxruntime  # noqa: F401
    from rapidocr import RapidOCR
    import cv2
    _OCR = RapidOCR()
    try:
        assert os.path.isfile(str(FACE_MODEL)), "face model missing"
        _DET = cv2.FaceDetectorYN_create(str(FACE_MODEL), "",
                                         (W, VIS_BOT - VIS_TOP),
                                         score_threshold=FACE_SCORE)
    except Exception:                       # noqa: BLE001
        _DET = None


def _fast_frame(img, face_ratio: float = None) -> dict:
    """便宜判据：HSV 的 V 均值 / 灰度标准差 / 人脸。不调 OCR。"""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std = float(g.std())
    v = float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].mean())
    ratio = FACE_BIG_RATIO if face_ratio is None else float(face_ratio)
    face_big, face_w = False, 0.0
    if _DET is not None:
        try:
            _DET.setInputSize((img.shape[1], img.shape[0]))
            _, fres = _DET.detect(img)
            if fres is not None:
                for f in fres:
                    if f is None or f[14] < FACE_SCORE:
                        continue
                    face_w = max(face_w, float(f[2]))
                    if f[2] >= img.shape[1] * ratio:
                        face_big = True
        except Exception:
            pass
    return {"std": std, "v": round(v, 1), "face_big": face_big,
            "face_w": round(face_w, 1)}


def _ocr_frame(img) -> tuple[bool, str]:
    """贵判据：中央带是否有中文烧录字幕/水印。"""
    try:
        res = _OCR(img)
    except Exception:
        return False, ""
    if res is None or not getattr(res, "txts", None):
        return False, ""
    hit = []
    for txt, score in zip(res.txts, res.scores):
        if float(score) >= OCR_SCORE and CJK.search(str(txt)):
            hit.append(str(txt))
    return (bool(hit), " | ".join(hit)[:40])


def scan_one(job: dict) -> dict:
    """扫描单条素材 → 返回最多 WIN_TARGET 个合格窗口。

    两阶段：全部帧走便宜判据 → 候选窗口排序 → 只 OCR 排在前面的候选窗口的帧。
    """
    import cv2
    abs_path, rel_path, dur = job["abs"], job["rel"], job["dur"]
    ratio = job.get("face_ratio", FACE_BIG_RATIO)
    with tempfile.TemporaryDirectory(prefix="ap930_") as td:
        pairs = grab_all(td, abs_path)
        if not pairs:
            return {"rel": rel_path, "dur": dur, "nframes": 0, "wins": []}
        by_t: dict[float, str] = {}
        fast: dict[float, dict] = {}
        for t, fp in pairs:
            img = cv2.imread(fp)
            if img is None:
                continue
            by_t[round(t, 2)] = fp
            fast[round(t, 2)] = _fast_frame(img, ratio)

        # ---- 阶段 1：候选窗口（只按 v/std 过滤）----
        # ★ 窗口起点强制对齐 0.5s 网格：成片里 cue 的帧位于 source_in+0/0.5/1.0…，
        #   只有 source_in 本身落在 0.5 网格上，QC 抽到的帧才和选段判过的帧逐帧重合。
        seen: set[float] = set()
        cands = []
        for anchor in sorted(fast):
            w = round(round(anchor * 2) / 2, 2)
            if w in seen:
                continue
            seen.add(w)
            if w + CLIP > dur:
                continue
            need = [round(w + k * 0.5, 2) for k in range(6)]      # 0.0 .. 2.5
            fr = [fast.get(x) for x in need]
            if any(f is None for f in fr):
                continue
            vs = [x["v"] for x in fr]
            stds = [x["std"] for x in fr]
            if min(vs) < DARK_V or max(vs) > OVER_V:
                continue
            if max(stds) < STD_MIN:
                continue
            cands.append({
                "start": round(w, 2),
                "need": need,
                "v": round(sum(vs) / len(vs), 1),
                "std": round(max(stds), 1),
                "nframes": len(fr),
                "face_big": any(x["face_big"] for x in fr),
                "face_w": round(max([x["face_w"] for x in fr] or [0.0]), 1),
            })
        # 去重：相邻 <1.5s 的只留 std 更高的；再按 std 降序（细节更足的先 OCR）
        cands.sort(key=lambda x: -x["std"])
        kept: list[dict] = []
        for w in cands:
            if all(abs(w["start"] - k["start"]) >= 1.5 for k in kept):
                kept.append(w)
        cands = kept

        # ---- 阶段 2：分批 OCR，够用就停 ----
        wins: list[dict] = []
        ocr_cache: dict[float, tuple[bool, str]] = {}
        for bi in range(MAX_BATCHES):
            batch = cands[bi * WIN_BATCH:(bi + 1) * WIN_BATCH]
            if not batch:
                break
            todo = sorted({tt for w in batch for tt in w["need"]
                           if tt not in ocr_cache})
            for tt in todo:
                fp = by_t.get(tt)
                if not fp:
                    ocr_cache[tt] = (False, "")
                    continue
                img = cv2.imread(fp)
                ocr_cache[tt] = _ocr_frame(img) if img is not None else (False, "")
            for w in batch:
                if any(ocr_cache.get(x, (False, ""))[0] for x in w["need"]):
                    continue
                w.pop("need", None)
                wins.append(w)
                if len(wins) >= WIN_TARGET:
                    break
            if len(wins) >= WIN_TARGET:
                break
        return {"rel": rel_path, "dur": dur, "nframes": len(fast), "wins": wins}


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def build_joblist(folders: list[str]) -> list[dict]:
    """把若干素材目录的全部条目拍平成一个 job 列表（多目录合并扫描）。

    ★ 只把「无脸窗口」当硬条件、采集相关性 rel 当软分，就必须允许跨目录合并：
      昇腾950 主题目录里可能整条都是口播大脸，无脸画面反而在邻主题目录里
      （芯片/GPU 目录的机房与芯片特写，语义上同样贴"算力"）。
    """
    joblist: list[dict] = []
    for folder in folders:
        src_json = os.path.join(DELIV, folder, "00-素材目录.json")
        if not os.path.isfile(src_json):
            log(f"NO_INDEX {folder}")
            continue
        entries = json.load(open(src_json, encoding="utf-8")).get("entries", [])
        log(f"  folder={folder} entries={len(entries)}")
        for e in entries:
            rel_path = e.get("file_path", "")
            abs_path = os.path.join(DELIV, folder, rel_path.replace("/", os.sep))
            if not os.path.isfile(abs_path):
                log(f"  skip(missing) {folder}/{rel_path}")
                continue
            dur = probe_duration(abs_path) or float(e.get("duration_seconds") or 0)
            if dur < CLIP + 0.5:
                log(f"  skip(short {dur:.1f}s) {rel_path}")
                continue
            joblist.append({"abs": abs_path, "rel": rel_path, "dur": dur,
                            "e": e, "folder": folder})
    return joblist


def main() -> int:
    # New production uses interval evidence and graded selection. The old
    # scanner remains an explicit historical compatibility tool only.
    if "--legacy-pick" not in sys.argv:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
        from backlot.material_library_template import indexed_pick
        from backlot.material_library import MaterialLibraryError
        try:
            config = {}
            if "--folders-file" in sys.argv:
                config = json.load(open(sys.argv[sys.argv.index("--folders-file") + 1], encoding="utf-8"))
                key = str(config["t_key"])
                topic = str(config.get("topic") or config.get("theme") or "")
                if not topic:
                    raise MaterialLibraryError("多目录选材必须单独填写原始topic，不能以兜底目录冒充主题")
                folders = [str(item) for item in config.get("folders", [])]
            else:
                if len(sys.argv) < 3:
                    print("用法：auto_pick_0930.py t25 昇腾950 [--library-plan 需求.json]")
                    return 2
                key, keyword = sys.argv[1:3]
                topic = sys.argv[sys.argv.index("--topic") + 1] if "--topic" in sys.argv else keyword
                folder = keyword if "--exact" in sys.argv else find_folder(keyword)
                folders = [folder] if folder else []
            plan = config.get("plan")
            if "--library-plan" in sys.argv:
                plan = json.load(open(sys.argv[sys.argv.index("--library-plan") + 1], encoding="utf-8"))
            catalogs = []
            for folder in folders:
                directory = __import__("pathlib").Path(DELIV) / folder
                base = __import__("pathlib").Path(DELIV).resolve()
                if not directory.resolve().is_relative_to(base):
                    raise MaterialLibraryError("素材交付目录越界")
                catalog = directory / "00-素材目录.json"
                if not catalog.is_file():
                    catalog = directory / "清单.json"
                if catalog.is_file():
                    catalogs.append(catalog)
            result = indexed_pick(key, topic, catalogs, WORK, raw_plan=plan)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "ready" else 2
        except (ValueError, OSError, KeyError) as exc:
            print("分级选材未完成：" + str(exc))
            return 2
    cfg = None
    if "--folders-file" in sys.argv:
        p = sys.argv[sys.argv.index("--folders-file") + 1]
        cfg = json.load(open(p, encoding="utf-8"))

    if cfg:
        t_key = str(cfg["t_key"])
        folders = [str(x) for x in cfg["folders"]]
        strict = bool(cfg.get("strict_noface"))
        need_n = int(cfg.get("min_face_free", 3))
        jobs = int(cfg.get("jobs", 4))
        face_ratio = float(cfg.get("face_ratio", FACE_BIG_RATIO))
    else:
        if len(sys.argv) < 3:
            print(__doc__)
            return 2
        t_key, kw = sys.argv[1], sys.argv[2]
        need_n = 3
        strict = "--strict-noface" in sys.argv
        face_ratio = FACE_BIG_RATIO
        jobs = 4
        if "--jobs" in sys.argv:
            try:
                jobs = max(1, int(sys.argv[sys.argv.index("--jobs") + 1]))
            except Exception:
                jobs = 4
        folder = kw if "--exact" in sys.argv else find_folder(kw)
        if not folder:
            log(f"NO_FOLDER theme={kw}")
            return 1
        folders = [folder]

    log(f"t_key={t_key} folders={len(folders)} strict_noface={strict} "
        f"face_ratio={face_ratio} jobs={jobs}")
    joblist = build_joblist(folders)

    if not joblist:
        log("NO_WINDOW at all")
        return 2

    log("face detector + OCR init in workers ...")
    t0 = time.time()
    results: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=min(jobs, len(joblist)),
                             initializer=_init_worker) as pool:
        futs = {pool.submit(scan_one, {"abs": x["abs"], "rel": x["rel"],
                                       "dur": x["dur"],
                                       "face_ratio": face_ratio}): x
                for x in joblist}
        for fu in as_completed(futs):
            x = futs[fu]
            try:
                r = fu.result()
            except Exception as ex:                     # noqa: BLE001
                log(f"  FAIL {os.path.basename(x['rel'])[:30]}: {ex}")
                continue
            results[x["rel"]] = r
            log(f"  {os.path.basename(x['rel'])[:34]:<34} dur={r['dur']:5.1f}s "
                f"frames={r['nframes']:3d} windows={len(r['wins'])}")
    log(f"scan done in {time.time() - t0:.0f}s")

    scored: list[dict] = []
    for x in joblist:
        r = results.get(x["rel"])
        if not r:
            continue
        e = x["e"]
        rel = norm_rel(e.get("relevance_score"))
        for w in r["wins"]:
            # 以 HSV 的 V 均值打分，110 附近最佳（与 QC 的 dark 判据同口径）
            v_score = 1.0 - abs(w["v"] - 110) / 110.0
            v_score = max(0.0, min(1.0, v_score))
            std_score = max(0.0, min(1.0, w["std"] / 60.0))
            # 带大脸的窗口重罚，但**不抹掉**——否则素材全是口播时会直接选不出镜头
            face_pen = 0.6 if w["face_big"] else 0.0
            total = 0.5 * rel + 0.3 * v_score + 0.2 * std_score - face_pen
            scored.append({
                "file": x["abs"].replace("\\", "/"),
                "rel_path": x["rel"],
                "source_in": w["start"],
                "v": w["v"], "std": w["std"],
                "face_big": w["face_big"], "face_w": w["face_w"],
                "rel": rel, "total": round(total, 4),
                "video_id": e.get("video_id", ""),
                "source_url": e.get("source_url", ""),
                "title": e.get("title", ""),
                "author": e.get("author", "") or "未署名",
                "role": e.get("role", "") or "support",
                "suggested_use": e.get("suggested_use", ""),
            })

    if not scored:
        log("NO_WINDOW at all")
        return 2

    scored.sort(key=lambda x: -x["total"])

    def select_diverse(cands: list[dict], need: int,
                       already: list[dict]) -> list[dict]:
        """分两轮挑：先保证**不同素材各出 1 个镜头**，不够再允许同素材第二个窗口。

        ★ 只按总分从高到低取的话，三条镜头会全部落在同一条素材上
          （t29 实测：三个 PICK 全来自 灵巧手-主素材-01，只是起点不同），
          成片观感是同一机位连切三刀，很廉价。跨素材多样性优先于单窗口分数。
        """
        base = list(already)
        got: list[dict] = []
        ok_gap = lambda s, pool: all(           # noqa: E731
            abs(s["source_in"] - p["source_in"]) >= 3.0
            for p in pool if p["file"] == s["file"])

        # 轮次 1：每个素材最多 1 个镜头
        for s in cands:
            if len(got) >= need:
                break
            if any(s["file"] == p["file"] for p in base + got):
                continue
            if not ok_gap(s, base + got):
                continue
            got.append(s)
        # 轮次 2：素材不够多时，允许同素材再来一刀（间隔 >=3s）
        if len(got) < need:
            for s in cands:
                if len(got) >= need:
                    break
                if any(s is p for p in base + got):
                    continue
                if not ok_gap(s, base + got):
                    continue
                got.append(s)
        return got

    # 一级：无大脸窗口；二级：带脸兜底（保证六条都能出片）
    picked = select_diverse([s for s in scored if not s["face_big"]], need_n, [])
    if len(picked) < need_n:
        if strict:
            # ★ strict_noface：宁可不交片也不给大脸。调用方负责扩素材池
            #   （t25 返工：老大的原话是"开头就是一个大脸，素材肯定是不通过的"）。
            log(f"STRICT-NOFACE: only {len(picked)} face-free windows "
                f"(need {need_n}), refuse face fallback")
            return 2
        log(f"WARN only {len(picked)} face-free windows; filling with face windows")
        picked += select_diverse([s for s in scored if s["face_big"]],
                                 need_n - len(picked), picked)

    if len(picked) < need_n:
        log(f"ONLY {len(picked)} windows (need {need_n})")
        return 2

    # ★ 开场镜必须无脸（index 1 == 成片第 0-3 秒）。老大明确要求开场不能是大脸；
    #   即便走了兜底，只要存在无脸窗口就把最高分的无脸窗口提到第一位。
    if picked and picked[0]["face_big"]:
        free = next((s for s in picked if not s["face_big"]), None)
        if free is not None:
            picked.remove(free)
            picked.insert(0, free)
            log("  note: moved a face-free window to the opening shot")

    spec = []
    for i, s in enumerate(picked, 1):
        spec.append({
            "cue": f"cue-{i:003d}",
            "t_key": t_key,
            "index": i,
            "file": s["file"],
            "source_in": s["source_in"],
            "source_video_id": s["video_id"],
            "source_url": s["source_url"],
            "source_title": s["source_title"] if "source_title" in s else s["title"],
            "creator": s["author"],
            "material_role": s["role"],
            "original_delivery_path": s["rel_path"],
            "pick_reason": (
                f"自动选段（无人看管）：该 3 秒窗口内逐秒 OCR 扫描中央可见带 y{VIS_TOP}-{VIS_BOT} "
                f"未检出中文烧录字幕/水印（置信度阈值 {OCR_SCORE}）；平均亮度 V={s['v']} "
                f"（亮度阈值 V>={DARK_V} 且 <={OVER_V}），灰度标准差 {s['std']} "
                f"（纯色阈值 {STD_MIN}）说明画面有内容；采集端相关性 {s['rel']:.2f}，"
                f"综合分 {s['total']}。素材建议用途：{s['suggested_use'] or '未标注'}。"
            ),
        })

    spec_path = os.path.join(WORK, f"spec_{t_key}.json")
    json.dump(spec, open(spec_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    detail_path = os.path.join(WORK, f"autopick_{t_key}.json")
    json.dump({"t_key": t_key, "folders": folders, "picked": picked,
               "all_scored": scored[:40]},
              open(detail_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for s in picked:
        log(f"  PICK @{s['source_in']:6.2f}s  total={s['total']:.3f}  {os.path.basename(s['file'])[:40]}")
    log(f"WROTE {spec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
