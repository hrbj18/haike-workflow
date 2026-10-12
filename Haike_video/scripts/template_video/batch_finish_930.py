# -*- coding: utf-8 -*-
"""0930 夜间批次总控（无人看管）：轮询 batch_state_930.json，自动 选段→裁段→渲染→QC→归档→封面。

断点续跑原则（与 batch_finish_929.py 一致，并补了 QC/封面两环）：
- 每步完成即写回 state；stage==done 的条目直接跳过
- 单条失败记 failed_<step> 并继续下一条，不阻塞批次
- spec 由 auto_pick_0930.py 生成；本脚本发现 spec 就绪才推进

用法: python batch_finish_930.py [--once] [--no-cover]
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# 路径收口
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import HAIKE_ROOT as HAIKE, WORK_DIR, SCRIPTS_DIR  # noqa: E402

WORK = str(WORK_DIR)
STATE = os.path.join(WORK, "batch_state_930.json")
LOCK = os.path.join(WORK, "batch_930.lock")
LOCK_STALE_MIN = 10          # 持锁者 10 分钟没心跳 = 已死，可被抢占
# ★ 前提：run_step 在长步骤期间每 20s 刷新心跳，所以"心跳新"等价于"进程活着"。
#   若长步骤期间不刷心跳，陈旧阈值就会和步骤耗时打架（要么误判死锁、
#   要么看门狗在慢步骤中途拉起第二个进程造成并发）。
VENV_PY = os.path.join(HAIKE, ".venv", "Scripts", "python.exe")
PY = VENV_PY
TV = os.path.join(str(SCRIPTS_DIR), "template_video")
SELECT = os.path.join(TV, "select_cut_923.py")
BUILD = os.path.join(TV, "build_923.py")
QC = os.path.join(TV, "qc_ep.py")
COVER = os.path.join(TV, "make_cover.py")
AUTOPICK = os.path.join(TV, "auto_pick_0930.py")
IMAGEGEN = r"C:/Users/Administrator/.workbuddy/tools/relay-imagegen.py"

# 项目骨架名（assets 回写用）
PROJECT_IDS = {
    "t24": "sub3-0930-gpt61-stop",
    "t25": "sub3-0930-ascend950",
    "t26": "sub3-0930-vast10m",
    "t27": "sub3-0930-agent-sec",
    "t28": "sub3-0930-nv-chip",
    "t29": "sub3-0930-dex-hand",
}

# AI 封面提示词：暗底科技感 + 上下留白（给字板）。不含文字。
COVER_PROMPTS = {
    "t24": "Vertical 3:4 cinematic poster: a glowing AI model core suddenly frozen behind red warning containment bars, dark server hall, emergency amber light, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
    "t25": "Vertical 3:4 cinematic poster: rows of dark server racks glowing deep red in a vast data center, rising compute grid light, dark navy ambience, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
    "t26": "Vertical 3:4 cinematic poster: an enormous glowing scroll of text stretching into starry space, a single bright token river, deep cosmic background, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
    "t27": "Vertical 3:4 cinematic poster: a luminous containment shield wrapping a dark digital agent silhouette, cyan security grid, dark background, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
    "t28": "Vertical 3:4 cinematic poster: a stack of glowing GPU chips with a massive gate slowly opening, cool blue industrial light, dark background, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
    "t29": "Vertical 3:4 cinematic poster: a sleek robotic hand with glowing tactile sensor skin reaching toward light, dark studio background, fine metallic detail, dramatic negative space at top and bottom for text, ultra clean, high contrast, no text, no letters, no logo",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(os.path.join(WORK, "batch_finish_930.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_state(state: dict) -> None:
    state["updated_at"] = now()
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def touch_lock() -> None:
    """刷新心跳。任何耗时步骤都会调它，避免看门狗误判本进程已死。"""
    try:
        with open(LOCK, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "hb": now()}, f)
    except Exception:
        pass


def acquire_lock() -> bool:
    """互斥锁：常驻主进程与定时看门狗之间只让一个推进。

    锁带心跳时间戳——持锁进程被杀（会话中断/进程崩溃）时锁会残留，
    看门狗凭「心跳超过 LOCK_STALE_MIN 分钟」判定其已死并抢占。
    """
    if "--no-lock" in sys.argv:
        return True
    try:
        with open(LOCK, encoding="utf-8") as f:
            d = json.load(f)
        hb = d.get("hb", "")
        if hb:
            t0 = datetime.strptime(hb[:19], "%Y-%m-%dT%H:%M:%S")
            age = (datetime.now() - t0).total_seconds() / 60.0
            if age < LOCK_STALE_MIN:
                log(f"lock held by pid={d.get('pid')} age={age:.1f}min, skip")
                return False
            log(f"stale lock (pid={d.get('pid')} age={age:.1f}min), take over")
    except Exception:
        pass
    touch_lock()
    return True


STEPS_LOG = os.path.join(WORK, "batch_steps_930.log")


def run_step(t: str, step: str, cmd: list[str], timeout: int = 1800) -> tuple[bool, str]:
    """跑一步，子进程输出**实时**追加到 batch_steps_930.log。

    ★ 无人看管场景下不能用 capture_output：子进程跑 10 分钟期间日志全黑，
      卡死还是慢跑完全看不出来。实时落盘才能中途判断进度。
    """
    touch_lock()
    tail: list[str] = []
    try:
        with open(STEPS_LOG, "a", encoding="utf-8") as sf:
            sf.write(f"\n===== [{now()}] {t} {step}\n")
            sf.write("     $ " + " ".join(str(c) for c in cmd) + "\n")
            sf.flush()
            p = subprocess.Popen(cmd, stdout=sf, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL,
                                 encoding="utf-8", errors="replace")
            deadline = time.time() + timeout
            while True:
                try:
                    rc = p.wait(timeout=20)
                    break
                except subprocess.TimeoutExpired:
                    touch_lock()               # 长步骤期间持续报活
                    if time.time() >= deadline:
                        p.kill()
                        p.wait(timeout=30)
                        rc = -9
                        break
    except Exception as e:                      # noqa: BLE001
        log(f"[{t}] {step} EXC {e}")
        return False, str(e)
    try:
        with open(STEPS_LOG, encoding="utf-8", errors="replace") as sf:
            tail = sf.read().splitlines()[-3:]
    except Exception:
        pass
    msg = " / ".join(s.strip()[:140] for s in tail)
    log(f"[{t}] {step} rc={rc} | {msg}")
    return rc == 0, msg


# 各步重试上限（达到即视为终态，避免死循环）
MAX_TRIES = {"pick": 6, "cut": 3, "render": 3, "qc": 2, "archive": 3}


def collect_log_path(state: dict) -> str:
    return os.path.join(WORK, state.get("collect_log", "collect_0930b.log"))


def collect_done(state: dict, theme: str) -> bool:
    """该主题的采集是否已收尾。

    ★ 采集是串行的，且**先建目录后下载素材**。若不等它收尾就跑选段，
      会拿到半截素材（目录存在但 mp4 还没下完）。
    ★ 本批次有多轮采集日志（0930b 补采短词、0930c 补采缺素材的主题），
      要合并起来看；若该词压根没出现在任何 START 行里，说明它是历史目录
      关键词（兜底用），不存在"等采集"这回事，直接放行。
    """
    txt = ""
    for p in sorted(glob.glob(os.path.join(WORK, "collect_0930*.log"))):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                txt += f.read()
        except Exception:                          # noqa: BLE001
            pass
    if f"=== START {theme} " not in txt:
        return True
    return f"=== END {theme} " in txt


def is_pending(info: dict) -> bool:
    """stage 是否还需推进。

    ★ failed_* 不能一律排除——否则「失败即终态、永不重试」，
      与本脚本的断点续跑初衷相悖。按各步重试上限判定是否还值得再试。
    """
    s = info["stage"]
    if s.startswith(("done", "cover_done")) or s == "needs_material":
        return False
    if s.startswith("failed_"):
        kind = s[len("failed_"):]
        if kind not in MAX_TRIES:
            return False
        return info.get(f"{kind}_tries", 0) < MAX_TRIES[kind]
    return True


def process(t: str, info: dict, state: dict, do_cover: bool) -> None:
    spec = os.path.join(WORK, info["spec"])

    # --- 自动选段（若 spec 还不存在）
    if info["stage"] in ("awaiting_spec", "failed_pick"):
        if os.path.isfile(spec):
            info["stage"] = "spec_ready"
            save_state(state)
        else:
            # 主词优先，失败依次退到 collect_theme_alt（历史素材目录兜底）
            words = [w for w in [info.get("collect_theme")]
                     + list(info.get("collect_theme_alt") or []) if w]
            if not words:
                return
            # ★ 同轮内把候选词轮流试完：NO_FOLDER / NO_WINDOW 都是秒级失败，
            #   一轮只试一个词的话，缺素材的主题要等好几轮才能轮到兜底词，
            #   0930 凌晨实测 t26/t28 就是这么被卡住的。
            for _ in range(len(words)):
                idx = min(info.get("pick_idx", 0), len(words) - 1)
                theme = words[idx]
                if not collect_done(state, theme):
                    # 该词正在采集中（目录已建但素材没下完），换下一个词试
                    info["pick_idx"] = (idx + 1) % len(words)
                    continue
                if info.get("pick_tries", 0) >= MAX_TRIES["pick"]:
                    break
                info["stage"] = "picking"
                info["pick_tries"] = info.get("pick_tries", 0) + 1
                save_state(state)
                ok, msg = run_step(t, f"autopick[{theme}]",
                                   [PY, AUTOPICK, t, theme, "--topic", str(info.get("collect_theme") or theme)], timeout=3600)
                if ok and os.path.isfile(spec):
                    info["stage"] = "spec_ready"
                    info["picked_theme"] = theme
                    save_state(state)
                    break
                if os.path.isfile(os.path.join(WORK, f"material_gap_{t}.json")):
                    info["stage"] = "needs_material"
                    info["error"] = "已有素材需区间确认或有限补采；见 material_gap_" + t + ".json，完成后将阶段改为 awaiting_spec"
                    save_state(state)
                    return
                info["pick_idx"] = (idx + 1) % len(words)
                info["stage"] = "failed_pick"
                info["error"] = f"autopick failed: {theme} | {msg[:160]}"
                save_state(state)
            save_state(state)

    # --- 裁段
    if info["stage"] in ("spec_ready", "failed_cut"):
        if info.get("cut_tries", 0) >= 3:
            return
        info["cut_tries"] = info.get("cut_tries", 0) + 1
        info["stage"] = "cutting"
        save_state(state)
        pid = PROJECT_IDS.get(t)
        if not pid:
            info["stage"] = "failed_cut"
            info["error"] = f"no project_id for {t}"
            save_state(state)
            return
        ok, _ = run_step(t, "cut", [PY, SELECT, "cut", t, pid, spec])
        if not ok:
            info["stage"] = "failed_cut"
            save_state(state)
            return
        info["stage"] = "cut_done"
        save_state(state)

    # --- 渲染
    if info["stage"] in ("cut_done", "failed_render"):
        info["render_tries"] = info.get("render_tries", 0) + 1
        info["stage"] = "rendering"
        save_state(state)
        ok, _ = run_step(t, "render", [PY, BUILD, t], timeout=1800)
        out = os.path.join(WORK, "short_out", f"{t}_9s.mp4")
        if not ok or not os.path.isfile(out):
            info["stage"] = "failed_render"
            info["error"] = "render output missing"
            save_state(state)
            return
        info["stage"] = "render_done"
        save_state(state)

    # --- QC 门禁
    if info["stage"] in ("render_done", "failed_qc"):
        if info.get("qc_tries", 0) >= 2:
            # QC 两次不过也归档，交给人工复核（不阻塞交付）
            info["stage"] = "qc_warn"
            save_state(state)
        else:
            info["qc_tries"] = info.get("qc_tries", 0) + 1
            info["stage"] = "qcing"
            save_state(state)
            short = os.path.join(WORK, "short_out", f"{t}_9s.mp4")
            label = info.get("qc_label") or f"{t}_9s"
            ok, msg = run_step(t, "qc", [PY, QC, short, label], timeout=1800)
            info["qc_pass"] = bool(ok)
            info["qc_msg"] = msg[:300]
            if not ok:
                # ★ QC 挂了不要对同一条成片重跑 QC（同一批画面，必然再挂）。
                #   正确做法是**回退到选段**：换主题/换窗口重裁重渲。
                #   t27 就是 18 帧全 face_risk，只有换素材才救得回来。
                repick = info.get("qc_repick", 0)
                if repick < 2:
                    info["qc_repick"] = repick + 1
                    try:
                        os.remove(spec)
                    except OSError:
                        pass
                    info["pick_idx"] = info.get("pick_idx", 0) + 1
                    info["cut_tries"] = 0
                    info["render_tries"] = 0
                    info["qc_tries"] = 0
                    info["stage"] = "awaiting_spec"
                    info["error"] = f"qc failed -> repick#{repick + 1}: {msg[:160]}"
                    save_state(state)
                    log(f"[{t}] QC 未过，回退重选素材 (repick#{repick + 1})")
                    return
                # 重选两次仍不过：直接按 qc_warn 归档出片（不阻塞交付，
                # 由最终汇总报告标注风险，交人工复核）。
                info["qc_tries"] = MAX_TRIES["qc"]
                info["stage"] = "qc_warn"
                info["error"] = f"qc risk after 2 repicks: {msg[:160]}"
                save_state(state)
                return
            info["stage"] = "qc_done"
            save_state(state)

    # --- 归档
    if info["stage"] in ("qc_done", "qc_warn", "failed_archive"):
        info["stage"] = "archiving"
        info["archive_tries"] = info.get("archive_tries", 0) + 1
        save_state(state)
        short = os.path.join(WORK, "short_out", f"{t}_9s.mp4")
        final = os.path.join(WORK, info["final"])
        if not os.path.isfile(short):
            info["stage"] = "failed_archive"
            info["error"] = f"short missing: {short}"
            save_state(state)
            return
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.copy2(short, final)
        if not os.path.isfile(final) or os.path.getsize(final) < 10000:
            info["stage"] = "failed_archive"
            info["error"] = "archive copy failed / too small"
            save_state(state)
            return
        info["stage"] = "done"
        info["final_size"] = os.path.getsize(final)
        save_state(state)
        log(f"[{t}] DONE -> {info['final']}")

    # --- AI 封面（可选，失败不影响交付）
    if do_cover and info["stage"] == "done":
        info["stage"] = "covering"
        save_state(state)
        cov_dir = os.path.join(WORK, "_covers930")
        ai_dir = os.path.join(cov_dir, "_ai")
        chk_dir = os.path.join(cov_dir, "_check")
        os.makedirs(ai_dir, exist_ok=True)
        raw_png = os.path.join(ai_dir, f"{t}-raw.png")
        prompt = COVER_PROMPTS.get(t)
        ok = True
        if prompt and not os.path.isfile(raw_png):
            ok, _ = run_step(t, "cover-gen",
                             ["C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe",
                              IMAGEGEN, "generate", prompt, "--out", raw_png],
                             timeout=900)
        if ok and os.path.isfile(raw_png):
            ok, _ = run_step(t, "cover-make",
                             [PY, COVER, t, "--src", raw_png, "--check-dir", chk_dir],
                             timeout=900)
        info["stage"] = "cover_done" if ok else "done"
        info["cover"] = os.path.join(cov_dir, f"{t}-cover.jpg") if ok else ""
        save_state(state)


def main() -> int:
    once = "--once" in sys.argv
    do_cover = "--no-cover" not in sys.argv
    if not acquire_lock():
        return 0
    log(f"batch controller start (cover={do_cover}, pid={os.getpid()})")
    while True:
        touch_lock()
        try:
            state = json.load(open(STATE, encoding="utf-8"))
        except Exception as e:
            log(f"state load failed: {e}")
            return 1
        tasks = state["tasks"]
        pending = [t for t, i in tasks.items() if is_pending(i)]
        if not pending:
            log("all tasks settled, exit")
            return 0
        for t in pending:
            touch_lock()
            process(t, tasks[t], state, do_cover)
        if once:
            log("once mode, exit")
            return 0
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
