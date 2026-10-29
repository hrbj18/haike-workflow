"""CLI entry point for the delivery report (`汇报文档.md`).

The implementation lives in :mod:`douyin_intelligence.report_doc` so the
material-replication pipeline can call it directly; this file only keeps the
documented `scripts/build_report_doc.py` invocation working.

Usage:
    python scripts/build_report_doc.py --delivery <交付目录>
    python scripts/build_report_doc.py --delivery <交付目录> --check
    python scripts/build_report_doc.py --check --all
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running this file directly puts ``scripts/`` on sys.path, not ``src/``: add the
# sibling source tree so the wrapper works from a plain checkout too, not only
# inside the virtualenv that has the package installed.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from douyin_intelligence.report_doc import (  # noqa: E402
    DEFAULT_MIN_DELIVERED_MIB,
    HUMAN_ORDINALS,
    HUMAN_TODO,
    MANIFEST_FILENAME,
    PROCESS_DIRNAME,
    REPORT_FILENAME,
    SECTIONS,
    STATUS_AWAITING_HUMAN,
    STATUS_COMPLETE,
    Section,
    audit_deliveries,
    build,
    carry_over_report,
    collect_facts,
    human_section_titles,
    main,
    pending_sections,
    render_report,
    report_doc_settings,
    report_status,
    write_report_doc,
)

__all__ = [
    "DEFAULT_MIN_DELIVERED_MIB",
    "HUMAN_ORDINALS",
    "HUMAN_TODO",
    "MANIFEST_FILENAME",
    "PROCESS_DIRNAME",
    "REPORT_FILENAME",
    "SECTIONS",
    "STATUS_AWAITING_HUMAN",
    "STATUS_COMPLETE",
    "Section",
    "audit_deliveries",
    "build",
    "carry_over_report",
    "collect_facts",
    "human_section_titles",
    "main",
    "pending_sections",
    "render_report",
    "report_doc_settings",
    "report_status",
    "write_report_doc",
]


if __name__ == "__main__":
    raise SystemExit(main())
