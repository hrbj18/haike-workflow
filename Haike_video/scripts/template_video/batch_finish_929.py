# -*- coding: utf-8 -*-
"""929 夜间批次总控: 轮询 batch_state.json, 发现 spec 后自动 裁段→渲染→归档。

断点续跑原则:
- stage==done 的条目直接跳过
- 每步完成即写回 batch_state.json
- spec 文件由 agent 目检后写入, 本脚本只负责机械流程
- 同一条失败会记 stage=failed_<step> 并继续下一条(不阻塞批次)

用法: python batch_finish_929.py [--once]
  默认循环轮询直到所有条目 done/failed; --once 只扫一轮。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# 路径收口：不硬编码盘符/工作区绝对路径，统一由 _paths 推导（见同目录 _paths.py）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import (  # noqa: E402
    VIDEOHUB_ROOT as ROOT,
    HAIKE_ROOT as HAIKE,
    WORK_DIR,
    SCRIPTS_DIR,
)

WORK = str(WORK_DIR)
STATE = os.path.join(WORK, "batch_state.json")
# 解释器已合流：渲染与门禁同用 Haike_video/.venv（自带 onnxruntime + rapidocr）。
# 原先「非 OCR 步骤走系统 Python」的分工已废除 —— 一个环境即可，跨机只需重建这一个 venv。
VENV_PY = os.path.join(HAIKE, ".venv", "Scripts", "python.exe")
PY = VENV_PY
TV = os.path.join(str(SCRIPTS_DIR), "template_video")   # 生产脚本正式位置
SELECT = os.path.join(TV, "select_cut_923.py")
BUILD = os.path.join(TV, "build_923.py")

# project_id 由 label 推导: 新条目项目骨架名
PROJECT_IDS = {
    "t17": "sub3-0929-meta-muse",
    "t18": "sub3-0929-tesla-optimus",
    "t19": "sub3-0929-gpt6-drive",
    "t20": "sub3-0929-colossus2",
    "t21": "sub3-0929-embodied-bot",
    "t22": "sub3-0929-openai-devday",
    "t23": "sub3-0929-claude-sonnet55",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(os.path.join(WORK, "batch_finish.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_state(state: dict) -> None:
    state["updated_at"] = now()
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def run_step(t: str, step: str, cmd: list[str]) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = r.returncode == 0
    tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    tail = tail[-3:] if tail else []
    log(f"[{t}] {step} rc={r.returncode} | " + " / ".join(s.strip()[:120] for s in tail))
    return ok


def process(t: str, info: dict, state: dict) -> None:
    spec = os.path.join(WORK, info["spec"])
    if not os.path.isfile(spec):
        return

    # --- 裁段
    if info["stage"] in ("awaiting_spec", "failed_cut"):
        info["stage"] = "cutting"
        save_state(state)
        pid = PROJECT_IDS.get(t)
        if not pid:
            info["stage"] = "failed_cut"
            info["error"] = f"no project_id for {t}"
            save_state(state)
            return
        ok = run_step(t, "cut", [PY, SELECT, "cut", t, pid, spec])
        if not ok:
            info["stage"] = "failed_cut"
            save_state(state)
            return
        info["stage"] = "cut_done"
        save_state(state)

    # --- 渲染
    if info["stage"] in ("cut_done", "failed_render"):
        info["stage"] = "rendering"
        save_state(state)
        ok = run_step(t, "render", [VENV_PY, BUILD, t])
        out = os.path.join(WORK, "short_out", f"{t}_9s.mp4")
        if not ok or not os.path.isfile(out):
            info["stage"] = "failed_render"
            info["error"] = "render output missing"
            save_state(state)
            return
        info["stage"] = "render_done"
        save_state(state)

    # --- 归档
    if info["stage"] in ("render_done", "failed_archive"):
        info["stage"] = "archiving"
        save_state(state)
        final = os.path.join(WORK, info["final"])
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.copy2(os.path.join(WORK, "short_out", f"{t}_9s.mp4"), final)
        info["stage"] = "done"
        info["final_size"] = os.path.getsize(final)
        save_state(state)
        log(f"[{t}] DONE -> {info['final']}")


def main() -> int:
    once = "--once" in sys.argv
    log("batch controller start")
    while True:
        state = json.load(open(STATE, encoding="utf-8"))
        tasks = state["tasks"]
        pending = [t for t, i in tasks.items() if not i["stage"].startswith(("done", "failed"))]
        if not pending:
            log("all tasks settled, exit")
            return 0
        for t in pending:
            info = tasks[t]
            if info["stage"].startswith(("done", "failed", "awaiting_collect")):
                continue
            process(t, info, state)
        if once:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
