"""本地视频理解交接：prepare → agent 读图 → submit；不调用模型或制片服务。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlot.ai_vision import (  # noqa: E402
    CONTACT_SHEET_SYSTEM_PROMPT,
    VisionAIError,
    normalize_agent_contact_sheet_descriptions,
)
from backlot.material_overview import (  # noqa: E402
    MaterialOverviewError,
    build_material_overview_index,
    validate_material_overview_index,
)
from backlot.media_index import MediaIndexError, media_content_fingerprint  # noqa: E402
from lib.ffmpeg_locator import resolve_ffmpeg_pair  # noqa: E402

VERSION = 1
PURPOSES = ("overview", "layout", "material", "speech", "motion", "qa")
FOLLOW_UP_KINDS = ("detail", "fine", "vision", "audio", "playback", "source_check", "window_qa")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象")
    return value


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def task_lock(directory):
    path = directory / ".task.lock"
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError(f"任务正在写入或遗留锁未清理：{path}；确认无进程运行后再处理") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def require_text(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} 必须为 1–{maximum} 字符的文字")
    return value.strip()


def verify_evidence(index):
    validate_material_overview_index(index)
    source = Path(index["source"]["path"])
    if media_content_fingerprint(source) != index["source"]["fingerprint"]:
        raise ValueError("源视频已变化；重新准备分析，不能提交旧结论")
    for rows, hash_key in ((index["sheets"], "sha256"), (index["frames"], "source_frame_sha256")):
        for row in rows:
            if file_hash(row["path"]) != row[hash_key]:
                raise ValueError("证据图片缺失或变化；保留已有结果并重新生成对应概览")


def prepare(args):
    source = args.source.resolve()
    model = require_text(args.model, "model", 160)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model):
        raise ValueError("model 格式无效")
    goal = require_text(args.goal, "goal", 2000)
    if args.index:
        index = read_json(args.index)
        if Path(index["source"]["path"]).resolve() != source:
            raise ValueError("--index 与 --source 必须指向同一原片")
    else:
        if bool(args.ffmpeg) != bool(args.ffprobe):
            raise ValueError("显式二进制路径必须同时传 --ffmpeg 和 --ffprobe")
        pair = (str(args.ffmpeg), str(args.ffprobe)) if args.ffmpeg else resolve_ffmpeg_pair()
        if not pair or not all(Path(item).is_file() for item in pair):
            raise ValueError("找不到 FFmpeg/ffprobe；请同时指定两个现有二进制路径")
        index = build_material_overview_index(source, args.output.resolve() / "evidence", ffmpeg=pair[0], ffprobe=pair[1])
    verify_evidence(index)
    all_chapters = [row["chapter_id"] for row in index["sampling"]["chapters"]]
    selected = args.chapters or all_chapters
    if not selected or len(set(selected)) != len(selected) or not set(selected).issubset(all_chapters):
        raise ValueError(f"章节必须从以下 ID 中选择且不能重复：{', '.join(all_chapters)}")
    selected = [chapter for chapter in all_chapters if chapter in selected]
    if index["probe"]["duration_seconds"] > 3600 and not args.chapters:
        raise ValueError(f"已建立长视频章节索引：{index['index_path']}；请用 --chapters 选择章节后继续")
    subset = deepcopy(index)
    subset.pop("cache_hit", None)
    subset["sampling"]["chapters"] = [row for row in index["sampling"]["chapters"] if row["chapter_id"] in selected]
    for key in ("frames", "sheets", "cells"):
        subset[key] = [row for row in index[key] if row["chapter_id"] in selected]
    subset.update(status="sheets_ready", overview={"status": "not_requested"}, detail={"status": "not_requested"})
    identity = {
        "version": VERSION, "execution_mode": "agent", "model": model,
        "purpose": args.purpose, "goal": goal, "revision": args.revision,
        "source": index["source"], "evidence_digest": digest(subset),
        "coverage": {"selected_chapter_ids": selected, "all_chapter_ids": all_chapters,
                     "whole_video_sampled": set(selected) == set(all_chapters)},
        "prompt": CONTACT_SHEET_SYSTEM_PROMPT,
        "limits": ["只有离散画面证据，未听音频或连续播放", "候选区间不是精确剪切点", "尚未通过生产选材门"],
    }
    task_id = digest(identity)
    directory = args.output.resolve() / "tasks" / task_id
    directory.mkdir(parents=True, exist_ok=True)
    task = {**identity, "task_fingerprint": task_id}
    template = {
        "model": model, "task_fingerprint": task_id, "reviewed_sheet_ids": [],
        "answer_status": "needs_more_evidence", "answer": "",
        "follow_up": [],
        "proposal": {"chapters": [
            {"chapter_id": row["chapter_id"], "summary": "", "subjects": [], "actions": [],
             "quality": {"blur": "", "notes": ""}, "usable_ranges": [], "detail_candidates": [], "unknowns": []}
            for row in subset["sampling"]["chapters"]
        ]},
    }
    with task_lock(directory):
        task_path = directory / "task.json"
        if task_path.exists():
            if read_json(task_path) != task or read_json(directory / "evidence.json") != subset:
                raise ValueError("已有任务文件与证据不一致；保留现场并使用新的 --revision")
        else:
            write_json(directory / "evidence.json", subset)
            write_json(directory / "submission-template.json", template)
            write_json(task_path, task)
    return {"status": "task_ready", "task_path": str(task_path),
            "evidence_path": str(directory / "evidence.json"),
            "template_path": str(directory / "submission-template.json"),
            "sheet_count": len(subset["sheets"]), "coverage": identity["coverage"]}


def load_task(path):
    task = read_json(path)
    identity = {key: value for key, value in task.items() if key != "task_fingerprint"}
    if task.get("version") != VERSION or digest(identity) != task.get("task_fingerprint"):
        raise ValueError("任务版本或指纹无效；重新准备任务")
    index = read_json(path.parent / "evidence.json")
    if digest(index) != task["evidence_digest"]:
        raise ValueError("任务证据已变化；不能使用旧任务提交")
    verify_evidence(index)
    return task, index


def read_task(args):
    task, index = load_task(args.task.resolve())
    return {**task, "chapters": index["sampling"]["chapters"], "sheets": index["sheets"],
            "cells": index["cells"], "frames": [
                {key: row[key] for key in ("frame_id", "path", "actual_pts_seconds")}
                for row in index["frames"] if row.get("selected_for_overview")
            ], "result_exists": (args.task.resolve().parent / "analysis.json").is_file()}


def report(result, index):
    task = result["task"]
    video = next((stream for stream in index["probe"].get("streams", []) if stream.get("codec_type") == "video"), {})
    lines = ["# 视频理解报告", "", f"目标：{task['goal']}", f"模型：{task['model']}",
             f"状态：{result['answer_status']}（视觉概览完成，非制片验收）", "",
             "## 原片与覆盖", "",
             f"- 原片：[{task['source'].get('name', '视频')}](<{Path(task['source']['path']).as_posix()}>)",
             f"- 时长：{index['probe']['duration_seconds']:.3f}s；画幅：{video.get('width', '?')}×{video.get('height', '?')}；帧率：{video.get('r_frame_rate', '?')}",
             f"- 来源指纹：`{task['source']['fingerprint']}`（项目采样指纹）",
             f"- 已看章节：{', '.join(task['coverage']['selected_chapter_ids'])}；共 {len(index['sheets'])} 张多宫格、{len(index['cells'])} 个证据格",
             "- 覆盖范围：" + ("全片离散采样" if task["coverage"]["whole_video_sampled"] else "仅所选章节"), "",
             "## 结论", "", result["answer"], "", "## 分段证据", ""]
    for chapter in result["chapters"]:
        lines += [f"### {chapter['chapter_id']} · {chapter['start_seconds']:.3f}–{chapter['end_seconds']:.3f}s", "", chapter["summary"], ""]
        for row in chapter["usable_ranges"]:
            lines += [f"- 候选：{row['label']}；样本 {row['start_seconds']:.3f}–{row['end_seconds']:.3f}s；证据 {', '.join(row['evidence_cell_ids'])}"]
        lines += [f"- 未确认：{value}" for value in chapter["unknowns"]]
        lines += [""]
    lines += ["## 后续取证", ""]
    for row in result["follow_up"]:
        lines += [f"- {'必需' if row['required'] else '可选'} · {row['kind']}：{row['reason']}；证据 {', '.join(row['evidence_cell_ids']) or '全局'}"]
    if not result["follow_up"]:
        lines += ["当前目标无需继续取证。"]
    lines += ["", "## 多宫格", ""]
    for sheet in index["sheets"]:
        lines += [f"- [{sheet['sheet_id']}](<{Path(sheet['path']).as_posix()}>)"]
    lines += ["", "## 边界", "", *[f"- {value}" for value in task["limits"]],
              "- 本报告不替代项目 overview/vision 提交、V2 选材证据或最终源区间 QA。", ""]
    return "\n".join(lines)


def submit(args):
    task_path = args.task.resolve()
    with task_lock(task_path.parent):
        task, index = load_task(task_path)
        raw = read_json(args.submission)
        if set(raw) != {"model", "task_fingerprint", "reviewed_sheet_ids", "answer_status", "answer", "follow_up", "proposal"}:
            raise ValueError("提交字段必须与 submission-template.json 一致")
        if raw["model"] != task["model"] or raw["task_fingerprint"] != task["task_fingerprint"]:
            raise ValueError("提交模型或任务指纹不一致")
        reviewed = raw["reviewed_sheet_ids"]
        expected = {row["sheet_id"] for row in index["sheets"]}
        if not isinstance(reviewed, list) or not all(isinstance(v, str) for v in reviewed) or len(reviewed) != len(expected) or set(reviewed) != expected:
            raise ValueError("必须实际查看并声明本任务的全部多宫格 ID")
        answer = require_text(raw["answer"], "answer", 6000)
        chapters = normalize_agent_contact_sheet_descriptions(index, raw["proposal"])
        follow_up = raw["follow_up"]
        if not isinstance(follow_up, list) or len(follow_up) > 30:
            raise ValueError("follow_up 必须为不超过 30 项的数组")
        cells = {row["cell_id"] for row in index["cells"]}
        for row in follow_up:
            if not isinstance(row, dict) or set(row) != {"kind", "reason", "required", "evidence_cell_ids"}:
                raise ValueError("follow_up 每项需要 kind/reason/required/evidence_cell_ids")
            if row["kind"] not in FOLLOW_UP_KINDS or not isinstance(row["required"], bool):
                raise ValueError("follow_up 的 kind 或 required 无效")
            require_text(row["reason"], "follow_up.reason", 1000)
            refs = row["evidence_cell_ids"]
            if not isinstance(refs, list) or not all(isinstance(v, str) for v in refs) or not set(refs).issubset(cells):
                raise ValueError("follow_up 引用了无效单元格")
        status = raw["answer_status"]
        required = any(row["required"] for row in follow_up)
        if status not in {"sufficient_for_goal", "needs_more_evidence"} or required != (status == "needs_more_evidence"):
            raise ValueError("answer_status 必须与必需的后续取证项一致")
        if task["purpose"] in {"speech", "motion", "qa"} and status == "sufficient_for_goal":
            raise ValueError("口播、连续动作、成片验收不能只凭概览完成；需列出必需的后续取证")
        result = {"version": VERSION, "status": "overview_completed", "production_ready": False,
                  "task": task, "answer_status": status, "answer": answer, "chapters": chapters,
                  "follow_up": follow_up, "reviewed_sheet_ids": reviewed, "submission_hash": digest(raw)}
        output = task_path.parent / "analysis.json"
        if output.exists() and read_json(output) != result:
            raise ValueError("该任务已有不同结论；使用 prepare --revision 新值创建新任务，保留旧结果")
        write_json(output, result)
        write_text(task_path.parent / "report.md", report(result, index))
        return {"status": result["status"], "answer_status": status, "analysis_path": str(output),
                "report_path": str(task_path.parent / "report.md"), "production_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="生成或复用多宫格，冻结 agent 分析任务")
    prep.add_argument("--source", type=Path, required=True)
    prep.add_argument("--model", required=True, help="当前 agent 的真实模型标识，不自动猜测")
    prep.add_argument("--purpose", choices=PURPOSES, default="overview")
    prep.add_argument("--goal", required=True)
    prep.add_argument("--output", type=Path, default=ROOT / ".backlot" / "video-understanding")
    prep.add_argument("--index", type=Path, help="复用已有 material-overview-index.json")
    prep.add_argument("--chapters", nargs="+")
    prep.add_argument("--revision", default="1")
    prep.add_argument("--ffmpeg", type=Path)
    prep.add_argument("--ffprobe", type=Path)
    prep.set_defaults(handler=prepare)
    read = commands.add_parser("read", help="检查指纹，读取任务、图片路径和证据 ID")
    read.add_argument("--task", type=Path, required=True)
    read.set_defaults(handler=read_task)
    sub = commands.add_parser("submit", help="保存 agent 结论及可读报告，不调用 AI")
    sub.add_argument("--task", type=Path, required=True)
    sub.add_argument("--submission", type=Path, required=True)
    sub.set_defaults(handler=submit)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(args.handler(args), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, MaterialOverviewError, MediaIndexError, VisionAIError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
