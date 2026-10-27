#!/usr/bin/env python3
"""Install the distributed workspace entry only when missing; never replace local rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]


def install(source: Path, workspace: Path, create: bool = False) -> bool:
    text = source.read_text(encoding="utf-8-sig")
    target = workspace.resolve() / "AGENTS.md"
    if target.exists():
        if not target.is_file() or target.read_text(encoding="utf-8-sig") != text:
            raise ValueError("Existing root AGENTS.md differs; preserve it and merge the distribution source deliberately.")
        return False
    if not create:
        raise ValueError("Root AGENTS.md is missing; run with --install to create the distributed entry.")
    if not workspace.is_dir():
        raise ValueError("Workspace directory is missing.")
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--workspace-dir", type=Path, default=HUB.parent)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        created = install(HUB / "workspace/AGENTS.md", args.workspace_dir, args.install)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print("[OK] Workspace entry created." if created else "[OK] Workspace entry matches distribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
