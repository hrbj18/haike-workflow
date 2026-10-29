"""Local agent entrypoint; same domain module and revision guards as the UI."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.work_catalog import WorkCatalog, WorkError
from backlot import work_ingest, work_publish, work_storage
from lib.paths import PROJECTS_DIR


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="历史作品管理；发布和清理默认只做预览")
    p.add_argument("command", choices=["list", "show", "register", "change", "handoff", "export-handoff", "import-preview", "import",
        "storage", "cleanup-preview", "cleanup", "cleanup-cancel", "plans", "preflight", "publish", "sync", "acceptance"])
    p.add_argument("id", nargs="?")
    p.add_argument("--data", type=Path, help="UTF-8 JSON 参数文件，避免 shell 转义")
    p.add_argument("--projects", type=Path, default=PROJECTS_DIR)
    p.add_argument("--db", type=Path)
    p.add_argument("--confirm", action="store_true", help="提交确切计划；发布可能立即执行，清理为永久删除")
    a = p.parse_args()
    try:
        c = WorkCatalog(a.projects, a.db)
        d = json.loads(a.data.read_text(encoding="utf-8")) if a.data else {}
        if a.command == "list": result = c.list(include_candidates=True)
        elif a.command == "show": result = c.get(a.id)
        elif a.command == "handoff": result = c.handoff(a.id)
        elif a.command == "export-handoff":
            from backlot.work_handoff import export
            result = export(c, a.id)
        elif a.command == "register": result = c.register(**d)
        elif a.command == "change": result = c.change(a.id, d["action"], d, actor=d.get("actor", "local-agent"))
        elif a.command == "import-preview": result = work_ingest.import_preview(c)
        elif a.command == "import": result = work_ingest.import_apply(c, a.id, **d)
        elif a.command == "storage": result = work_storage.report(c, a.id)
        elif a.command == "cleanup-preview": result = work_storage.plan(c, d["work_ids"])
        elif a.command == "cleanup": result = work_storage.execute(c, a.id, d.get("digest"), a.confirm)
        elif a.command == "cleanup-cancel": result = work_storage.cancel(c, a.id)
        elif a.command == "plans":
            with c.transaction() as db:
                result = [json.loads(r[0]) for r in db.execute("SELECT data FROM work_plans WHERE kind=? ORDER BY rowid DESC", (d.get("kind", "cleanup"),))]
        elif a.command == "preflight": result = work_publish.prepare(c, a.id, d["revision"])
        elif a.command == "publish": result = work_publish.submit(c, a.id, a.confirm)
        elif a.command == "sync": result = work_publish.sync(c, a.id)
        else: result = work_publish.acceptance(c, a.id, d.pop("task_id"), d)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except WorkError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False)); return 2
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"error": "参数或文件不可读取，请检查参数文件和编号", "code": "invalid"}, ensure_ascii=False)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
