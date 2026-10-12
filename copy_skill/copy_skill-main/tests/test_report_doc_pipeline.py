"""交付汇报文档：管线收尾自动落骨架 + 交付门禁（report-doc v2）。

The report used to be produced only by a human remembering to run
``scripts/build_report_doc.py``.  Nothing under ``src/`` referenced it, so the
pipeline neither wrote it nor noticed it was missing: 31 of 39 published
deliveries shipped without one while ``status=success``, the whole-folder size
and the manifest self-check all stayed green.

These tests pin the seam **end to end, through the real
``run_material_replication``**.  Calling the private helper directly would pass
even if a call site were missing altogether -- and a missing call site is
exactly the failure this fix is about, so it is the one thing the suite must be
able to see.  Every published path is covered: full-chain success, download-only
success, empty pool, prefiltered-empty and dry-run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from douyin_intelligence.config import load_config
from douyin_intelligence.replication_delivery import report_doc_lines
from douyin_intelligence.replication_pipeline import ReplicationDeps, run_material_replication
from douyin_intelligence.report_doc import (
    HUMAN_ORDINALS,
    HUMAN_TODO,
    REPORT_FILENAME,
    STATUS_AWAITING_HUMAN,
    STATUS_COMPLETE,
    audit_deliveries,
    human_section_titles,
    pending_sections,
    report_doc_settings,
    report_status,
)

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_report_doc.py"
PROCESS_DIR = "05-过程数据"


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #
def _row(video_id: str, author: str, *, duration: float = 60.0, digg: int = 100) -> dict:
    return {
        "aweme_id": video_id,
        "desc": f"标题-{video_id}",
        "author": {"uid": f"uid-{author}", "nickname": author},
        "create_time": "2026-09-11T08:00:00+08:00",
        "statistics": {"digg_count": digg, "comment_count": 10, "share_count": 5, "collect_count": 20},
        "duration": duration,
        "video_download_url": f"https://signed.example/{video_id}",
        "share_url": f"https://www.douyin.com/video/{video_id}",
    }


def _config(tmp_path: Path, *, report_doc: bool | None) -> dict:
    """Live config with ``_project_root`` redirected, plus an explicit switch.

    ``report_doc`` is set explicitly in both directions so neither test depends
    on the value conftest strips to, nor on the shipped production value.
    """
    config = load_config()
    config["_project_root"] = str(tmp_path)
    material = config["jobs"]["material_replication"]
    # The fake downloader writes non-media bytes, so the real ffprobe layer does
    # not apply here (it has its own test module).
    material["validation"] = {"enabled": False}
    if report_doc is None:
        material.pop("report_doc", None)
    else:
        material["report_doc"] = {"enabled": report_doc}
    return config


def _collector(rows: list[dict]):
    def collect(config, budget, *, run_id=None, keywords=None, hard_max=None, before_sanitize=None, **kwargs):
        source = Path(str(config.get("_project_root"))) / "raw" / "search_contents_1.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        before_sanitize([source])
        return {"status": "success", "keywords": keywords, "budget": budget}
    return collect


def _deps(rows: list[dict]) -> ReplicationDeps:
    def downloader(url, destination, config, **kwargs):
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"video-bytes" * 100)

    def prober(path, config):
        return {"duration_seconds": 60.0, "width": 1080, "height": 1920, "codec": "h264"}

    return ReplicationDeps(
        collector=_collector(rows), downloader=downloader, prober=prober,
    )


def _run(tmp_path: Path, *, report_doc: bool | None, rows: list[dict] | None = None,
         pool_size: int = 8, overwrite: bool = False) -> tuple[dict, Path, dict]:
    # ``is not None`` rather than ``or``: an empty *list* is falsy, so ``rows or
    # default`` would silently substitute a row and the empty-pool case would
    # quietly exercise the happy path instead (it did, until this was fixed).
    collected = rows if rows is not None else [_row("v1", "甲")]
    config = _config(tmp_path, report_doc=report_doc)
    result = run_material_replication(
        config, "苹果折叠屏手机", business_date="2026-09-12",
        pool_size=pool_size, download_only=True, overwrite=overwrite, deps=_deps(collected),
    )
    output_dir = Path(result["output_dir"])
    manifest = json.loads((output_dir / "清单.json").read_text(encoding="utf-8"))
    return result, output_dir, manifest


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False,
    )


def _fill_human_sections(path: Path) -> None:
    """Replace every TODO marker, the way an agent filling them in would."""
    path.write_text(path.read_text(encoding="utf-8").replace(HUMAN_TODO, "已填写。"), encoding="utf-8")


# --------------------------------------------------------------------------- #
# switch off -- the no-op guard
# --------------------------------------------------------------------------- #
def test_disabled_switch_writes_no_report_and_leaves_manifest_untouched(tmp_path: Path) -> None:
    """With the switch off the delivery is unchanged: no file, no manifest key.

    This is the "off == no-op" contract the conftest seam depends on: a test
    fixture that never asked for the feature must not gain a root file, a
    manifest block or a changed readme.
    """
    result, output_dir, manifest = _run(tmp_path, report_doc=False)

    assert not (output_dir / REPORT_FILENAME).exists()
    assert "report_doc" not in manifest
    assert "report_doc" not in result
    assert "## 汇报文档" not in (output_dir / "00-交付说明.md").read_text(encoding="utf-8")
    assert report_status(output_dir) == (STATUS_AWAITING_HUMAN, human_section_titles())


def test_absent_block_defaults_to_on_so_the_gate_cannot_go_missing(tmp_path: Path) -> None:
    """A missing block means *on*, mirroring ``episode_research_pack``.

    ``block.get("enabled", True)`` is deliberate, and the assertion below pins
    the reasoning: the bug this whole change fixes is a gate that silently did
    not exist.  Defaulting to ``False`` would reintroduce exactly that the first
    time the key went missing from a config, so the safe direction is on.

    Test isolation does not lean on this default.  ``tests/conftest.py`` closes
    the block on every ``load_config()`` payload, and the shipped config is the
    only source of those payloads -- every module that drives the pipeline builds
    its fixture from ``load_config()``.  An explicit ``false`` remains the one
    way off (see the test above).
    """
    result, output_dir, manifest = _run(tmp_path, report_doc=None)

    assert (output_dir / REPORT_FILENAME).is_file()
    assert manifest["report_doc"]["status"] == STATUS_AWAITING_HUMAN
    assert result["report_doc"] == manifest["report_doc"]

    assert report_doc_settings({"jobs": {"material_replication": {}}}) == {"enabled": True}
    explicit_off = {"jobs": {"material_replication": {"report_doc": {"enabled": False}}}}
    assert report_doc_settings(explicit_off) == {"enabled": False}


# --------------------------------------------------------------------------- #
# switch on -- the structural fix
# --------------------------------------------------------------------------- #
def test_enabled_switch_publishes_a_skeleton_inside_the_delivery(tmp_path: Path) -> None:
    result, output_dir, manifest = _run(tmp_path, report_doc=True)

    report = output_dir / REPORT_FILENAME
    assert report.is_file(), "汇报文档必须随交付一起落盘"

    block = manifest["report_doc"]
    assert block["status"] == STATUS_AWAITING_HUMAN
    assert block["path"] == REPORT_FILENAME
    assert block["pending_sections"] == human_section_titles()
    assert result["report_doc"] == block

    text = report.read_text(encoding="utf-8")
    # The skeleton is honest: it says what is missing rather than looking done.
    assert HUMAN_TODO in text
    for ordinal in HUMAN_ORDINALS:
        assert f"## {ordinal}、" in text
    assert pending_sections(text) == human_section_titles()

def test_report_is_counted_by_the_folder_size_gate(tmp_path: Path) -> None:
    """The skeleton must ship *inside* the published folder, not beside it.

    ``delivery_folder_bytes`` is the number the 200 MB ceiling is enforced on.
    A report written after ``_publish`` would be invisible to that gate -- and
    could push the folder over the limit without anyone noticing.
    """
    _, output_dir, manifest = _run(tmp_path, report_doc=True)
    recorded = manifest["delivery_folder"]["delivery_folder_bytes"]
    actual = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    assert recorded == actual
    assert (output_dir / REPORT_FILENAME).is_file()


def test_overwrite_rerun_keeps_the_filled_report(tmp_path: Path) -> None:
    """``--overwrite`` must not revert a finished delivery to the skeleton.

    ``publish_directory`` replaces the published folder with the freshly staged
    one, so the stage has no report of its own: without a carry-over, re-running
    an episode -- the normal way to redo one -- would discard the written
    analysis and flip ``report_doc.status`` back to ``awaiting_human``.  The gate
    exists precisely so that a filled report stays filled.
    """
    _, output_dir, _ = _run(tmp_path, report_doc=True, rows=[_row("v1", "甲")])
    _fill_human_sections(output_dir / REPORT_FILENAME)
    assert report_status(output_dir) == (STATUS_COMPLETE, [])

    _, again, manifest = _run(
        tmp_path, report_doc=True, rows=[_row("v1", "甲"), _row("v2", "乙")], overwrite=True,
    )

    assert again == output_dir
    text = (again / REPORT_FILENAME).read_text(encoding="utf-8")
    # the written analysis survived...
    assert HUMAN_TODO not in text
    assert "已填写。" in text
    assert manifest["report_doc"]["status"] == STATUS_COMPLETE
    assert manifest["report_doc"]["pending_sections"] == []
    assert report_status(again) == (STATUS_COMPLETE, [])
    # ...while the automatic sections were still refreshed by the new run, so
    # this is a real re-render and not a stale copy of the previous document.
    downloaded = manifest["counters"]["downloaded"]
    assert downloaded == 2, manifest["counters"]
    assert f"| `downloaded` | {downloaded} |" in text


def test_manifest_and_readme_say_the_report_is_still_pending(tmp_path: Path) -> None:
    _, output_dir, _ = _run(tmp_path, report_doc=True)
    readme = (output_dir / "00-交付说明.md").read_text(encoding="utf-8")
    assert "## 汇报文档" in readme
    assert "待人工填写" in readme
    assert "二、产品是什么（事实层）" in readme


def test_empty_pool_delivery_also_carries_a_report(tmp_path: Path) -> None:
    """A degenerate delivery is still a published folder.

    "Nothing was produced, and here is why" is the case a human-readable summary
    is most useful for, so the early-return publish paths carry one too -- that
    is the point of hooking every ``_publish`` call site rather than only the
    two obvious ones.
    """
    result, output_dir, manifest = _run(tmp_path, report_doc=True, rows=[])
    assert result["status"] == "failed"
    assert (output_dir / REPORT_FILENAME).is_file()
    assert manifest["report_doc"]["status"] == STATUS_AWAITING_HUMAN


def test_dry_run_delivery_also_carries_a_report(tmp_path: Path) -> None:
    config = _config(tmp_path, report_doc=True)
    result = run_material_replication(
        config, "苹果折叠屏手机", business_date="2026-09-12",
        pool_size=8, dry_run=True, deps=_deps([_row("v1", "甲")]),
    )
    output_dir = Path(result["output_dir"])
    manifest = json.loads((output_dir / "清单.json").read_text(encoding="utf-8"))
    assert result["dry_run"] is True
    assert (output_dir / REPORT_FILENAME).is_file()
    assert manifest["material_replica"]["conclusion"] == "dry_run"
    # ...and it is exempt from the human-fill requirement (see the audit tests).
    assert [row["status"] for row in audit_deliveries(output_dir.parent)] == ["rehearsal"]


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #
def test_check_exits_two_until_every_human_section_is_filled(tmp_path: Path) -> None:
    _, output_dir, _ = _run(tmp_path, report_doc=True)
    report = output_dir / REPORT_FILENAME

    blocked = _cli("--delivery", str(output_dir), "--check")
    assert blocked.returncode == 2, blocked.stdout + blocked.stderr
    assert "人工段未填完" in blocked.stdout

    _fill_human_sections(report)
    passed = _cli("--delivery", str(output_dir), "--check")
    assert passed.returncode == 0, passed.stdout + passed.stderr


def test_manifest_status_is_a_publish_time_snapshot(tmp_path: Path) -> None:
    """Filling the sections does not rewrite the published manifest block.

    A published ``清单.json`` is immutable by design (see the research-pack
    ``annotate_delivery`` rationale), so ``report_doc.status`` records the state
    *at publish time*.  The live truth is the report file itself, which is what
    ``report_status`` / ``--check`` read.  Pinning this keeps someone from
    "fixing" the staleness by making a pipeline run rewrite a finished manifest.
    """
    _, output_dir, manifest = _run(tmp_path, report_doc=True)
    _fill_human_sections(output_dir / REPORT_FILENAME)

    assert manifest["report_doc"]["status"] == STATUS_AWAITING_HUMAN  # snapshot
    assert report_status(output_dir) == (STATUS_COMPLETE, [])  # live truth
    assert _cli("--delivery", str(output_dir), "--check").returncode == 0


def test_check_reports_a_missing_delivery_file_as_incomplete(tmp_path: Path) -> None:
    _, output_dir, _ = _run(tmp_path, report_doc=True)
    (output_dir / REPORT_FILENAME).unlink()
    result = _cli("--delivery", str(output_dir), "--check")
    assert result.returncode == 2
    assert "缺少汇报文档" in result.stdout


# --------------------------------------------------------------------------- #
# batch audit -- making absence visible to an automated sweep
# --------------------------------------------------------------------------- #
def _delivery(root: Path, name: str, *, business_date: str, conclusion: str = "selected") -> Path:
    delivery = root / name
    delivery.mkdir(parents=True, exist_ok=True)
    (delivery / "02-主素材").mkdir(parents=True, exist_ok=True)
    (delivery / "02-主素材" / "a.mp4").write_bytes(b"x" * 1024)
    (delivery / "清单.json").write_text(json.dumps({
        "theme": name, "business_date": business_date, "folder": name,
        "material_replica": {"conclusion": conclusion},
    }, ensure_ascii=False), encoding="utf-8")
    return delivery


def test_audit_all_fails_on_pending_and_passes_once_filled(tmp_path: Path) -> None:
    root = tmp_path / "复刻视频"
    done = _delivery(root, "9.18已完成", business_date="2026-09-18")
    pending = _delivery(root, "9.19待填", business_date="2026-09-19")
    (root / "_backup_9.19旧版").mkdir(parents=True, exist_ok=True)
    for delivery in (done, pending):
        assert _cli("--delivery", str(delivery)).returncode == 0
    _fill_human_sections(done / REPORT_FILENAME)

    blocked = _cli("--check", "--all", "--root", str(root))
    assert blocked.returncode == 2, blocked.stdout
    assert "9.19待填" in blocked.stdout
    assert "9.18已完成" not in blocked.stdout
    assert "_backup_9.19旧版" not in blocked.stdout  # working copies are skipped

    _fill_human_sections(pending / REPORT_FILENAME)
    passed = _cli("--check", "--all", "--root", str(root))
    assert passed.returncode == 0, passed.stdout
    assert "[OK]" in passed.stdout


def test_audit_all_treats_pre_convention_episodes_as_legacy(tmp_path: Path) -> None:
    """`--since` is what keeps the gate usable: the convention cannot be
    enforced on deliveries that predate it, and failing them forever would train
    everyone to ignore the sweep."""
    root = tmp_path / "复刻视频"
    old = _delivery(root, "9.12老期", business_date="2026-09-12")
    new = _delivery(root, "9.19新期", business_date="2026-09-19")
    for delivery in (old, new):
        assert _cli("--delivery", str(delivery)).returncode == 0
    _fill_human_sections(new / REPORT_FILENAME)

    assert _cli("--check", "--all", "--root", str(root)).returncode == 2
    scoped = _cli("--check", "--all", "--root", str(root), "--since", "2026-09-18")
    assert scoped.returncode == 0, scoped.stdout
    assert "legacy" in scoped.stdout

    rows = audit_deliveries(root, since="2026-09-18")
    assert {row["delivery"]: row["status"] for row in rows} == {
        "9.12老期": "legacy", "9.19新期": STATUS_COMPLETE,
    }


def test_audit_all_missing_root_is_a_failure_not_a_silent_pass(tmp_path: Path) -> None:
    """A wrong --root must not read as "everything is fine"."""
    result = _cli("--check", "--all", "--root", str(tmp_path / "nope"))
    assert result.returncode == 1
    assert "不存在" in result.stdout


def test_audit_all_on_empty_root_passes(tmp_path: Path) -> None:
    root = tmp_path / "复刻视频"
    root.mkdir()
    result = _cli("--check", "--all", "--root", str(root))
    assert result.returncode == 0
    assert "没有交付目录" in result.stdout


# --------------------------------------------------------------------------- #
# legacy manifests / readme section
# --------------------------------------------------------------------------- #
def test_report_section_absent_for_manifests_without_the_block() -> None:
    """A delivery published before the convention keeps an unchanged readme.

    ``report_doc_lines`` returns an empty list for both an absent key and an
    explicit ``None``, which is what makes ``render_delivery_readme`` a no-op for
    every historical manifest.
    """
    assert report_doc_lines({}) == []
    assert report_doc_lines({"delivery_folder": {"delivery_folder_bytes": 1}}) == []
    assert report_doc_lines({"report_doc": None}) == []
    assert report_doc_lines({"report_doc": {}}) == []


def test_report_section_states_complete_versus_pending() -> None:
    complete = "\n".join(report_doc_lines({"report_doc": {"status": STATUS_COMPLETE}}))
    assert "已填完" in complete
    assert "待人工填写" not in complete

    pending = "\n".join(
        report_doc_lines({"report_doc": {"status": STATUS_AWAITING_HUMAN, "pending_sections": ["二、x"]}})
    )
    assert "待人工填写" in pending
    assert "二、x" in pending
    assert "--check" in pending  # the section names the gate, not just the state


# --------------------------------------------------------------------------- #
# structural invariant -- every publish path must write the report
# --------------------------------------------------------------------------- #
def _publish_sites() -> tuple[int, list[int]]:
    """Count ``_publish`` call sites in ``run_material_replication`` and find any
    that lack a sibling ``report_doc_block = ...`` earlier in the same block.

    A runtime test can only cover the branch it drives, and a human reading the
    diff can only see the two obvious call sites -- which is precisely how three
    further publish paths (empty pool, prefiltered-empty, dry-run) were missed on
    the first pass.  That omission produced an ``UnboundLocalError`` in the
    download-only path, so the invariant is worth machine-checking: an
    assignment inherited from an *outer* block does not help, because Python's
    function scoping leaves the name unbound when that branch did not run.
    """
    import ast

    pipeline = ROOT / "src" / "douyin_intelligence" / "replication_pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_material_replication"
    )
    parents = {
        child: node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }

    def is_report_assignment(node: ast.AST) -> bool:
        return isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "report_doc_block"
            for target in node.targets
        )

    def enclosing_statement(node: ast.AST) -> ast.stmt:
        while node is not None and not isinstance(node, ast.stmt):
            node = parents.get(node)
        return node  # type: ignore[return-value]

    def containing_list(statement: ast.stmt) -> list[ast.stmt]:
        owner = parents.get(statement)
        for field in ("body", "orelse", "finalbody"):
            block = getattr(owner, field, None)
            if isinstance(block, list) and statement in block:
                return block
        return []

    sites = 0
    offenders: list[int] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name != "_publish":
            continue
        sites += 1
        statement = enclosing_statement(node)
        block = containing_list(statement)
        if not any(is_report_assignment(earlier) for earlier in block[: block.index(statement)]):
            offenders.append(statement.lineno)
    return sites, offenders


def test_every_publish_path_writes_a_report_skeleton() -> None:
    sites, offenders = _publish_sites()
    # Guards the instrument itself: a walker that silently matched nothing would
    # otherwise report a clean sweep forever.
    assert sites >= 5, f"只找到 {sites} 个 _publish 调用点，AST 巡检可能已失效"
    assert offenders == [], f"这些发布路径没有落汇报文档骨架：行 {offenders}"


def test_every_report_call_passes_the_destination_for_the_carry_over() -> None:
    """Omitting ``destination=`` reintroduces the exact failure of the call sites.

    The parameter is optional (the helper is also usable on its own), so one
    forgotten keyword at any of the five mount points leaves that path silently
    reverting a finished delivery back to the skeleton on ``--overwrite``.  Only
    the download-only path has a runtime test for this, and that is precisely the
    blind spot that let three of five publish paths go unhooked the first time.
    """
    import ast

    pipeline = ROOT / "src" / "douyin_intelligence" / "replication_pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_maybe_write_report_doc"
    ]
    assert len(calls) >= 5, f"只找到 {len(calls)} 处调用，AST 巡检可能已失效"
    missing = [node.lineno for node in calls if "destination" not in {kw.arg for kw in node.keywords}]
    assert missing == [], f"这些挂载点没传 destination，重跑会把人工段重置成骨架：行 {missing}"


# --------------------------------------------------------------------------- #
# full chain -- the production path
# --------------------------------------------------------------------------- #
class _Face:
    backend = "opencv_yunet"

    def status(self) -> dict:
        return {"backend": "opencv_yunet", "status": "ok", "model_present": True}

    def run(self, video, duration, cache_dir, temp_dir) -> dict:
        return {
            "backend": "opencv_yunet", "status": "ok", "face_frame_ratio": 0.0,
            "max_face_area_ratio": 0.0, "face_class": "face_free", "sampled_frames": 10,
            "face_per_frame": [False] * 10, "sample_interval_seconds": 1,
        }


class _Ocr:
    def run(self, video, duration, cache_dir, temp_dir) -> dict:
        return {"status": "no_text", "items": [], "sampled_frames": 10}


class _Transcriber:
    def run(self, video, cache_dir, temp_dir, **kwargs) -> dict:
        if "script" in str(cache_dir):
            return {"status": "success", "text": "字" * 200, "segments": [{"start": 0, "end": 5, "text": "开场"}]}
        return {"status": "no_speech", "text": "", "segments": []}


def _full_chain_deps(rows: list[dict]) -> ReplicationDeps:
    deps = _deps(rows)
    deps.face_detector = _Face()
    deps.ocr = _Ocr()
    deps.transcriber = _Transcriber()
    return deps


def test_full_chain_delivery_carries_a_report(tmp_path: Path) -> None:
    """The production path (not download-only) must leave the skeleton too.

    The download-only tests above cover the helper; this one covers the *call
    site* the real batches go through, which is the one an operator actually
    depends on.
    """
    config = _config(tmp_path, report_doc=True)
    config["jobs"]["material_replication"]["material_replica"]["min_count"] = 1
    rows = [_row("v1", "甲", digg=900), _row("v2", "乙", digg=800)]
    result = run_material_replication(
        config, "苹果折叠屏手机", business_date="2026-09-12",
        pool_size=8, deps=_full_chain_deps(rows),
    )
    output_dir = Path(result["output_dir"])
    manifest = json.loads((output_dir / "清单.json").read_text(encoding="utf-8"))

    assert result["mode"] if "mode" in result else True
    assert (output_dir / REPORT_FILENAME).is_file(), f"完整链路未落汇报文档：{result['status']}"
    assert manifest["report_doc"]["status"] == STATUS_AWAITING_HUMAN
    assert manifest["report_doc"]["pending_sections"] == human_section_titles()
    assert report_status(output_dir)[0] == STATUS_AWAITING_HUMAN
    readme = (output_dir / "00-交付说明.md").read_text(encoding="utf-8")
    assert "## 汇报文档" in readme
