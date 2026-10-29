#!/usr/bin/env python3
"""Check the structure of current Agent runbooks without reading runtime secrets."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote


HUB = Path(__file__).resolve().parents[1]
RUNBOOKS = HUB / "agent-runbooks"
REQUIRED = ("状态", "最近核验", "适用范围", "核验条件", "权威入口", "完成证据")
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
INDEX_ENTRY = re.compile(r"^\|[^\n]*\]\(([^)]+\.md)\)[^\n]*\|", re.MULTILINE)
SECRET = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|cookie|password)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
)


def check() -> list[str]:
    errors: list[str] = []
    index = RUNBOOKS / "README.md"
    if not index.is_file():
        return ["agent-runbooks/README.md: missing index"]

    indexed = {unquote(path) for path in INDEX_ENTRY.findall(index.read_text(encoding="utf-8"))}
    if not indexed:
        errors.append("agent-runbooks/README.md: no current runbook in index")

    files = sorted(RUNBOOKS.glob("*.md"))
    for name in indexed:
        if Path(name).name != name:
            errors.append(f"README.md: indexed path must stay in agent-runbooks/: {name}")
    for doc in files:
        content = doc.read_text(encoding="utf-8")
        for number, line in enumerate(content.splitlines(), 1):
            for raw in LINK.findall(line):
                target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
                if target and not re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                    if not (doc.parent / target).exists():
                        errors.append(f"{doc.name}:{number}: missing local link {target}")
            for kind, pattern in SECRET:
                if pattern.search(line):
                    errors.append(f"{doc.name}:{number}: possible {kind}; inspect privately")

        if doc.name in {"README.md", "TEMPLATE.md"}:
            continue
        if doc.name not in indexed:
            errors.append(f"{doc.name}: not listed in README.md; archive or index it")
        values: dict[str, str] = {}
        for field in REQUIRED:
            match = re.search(rf"(?m)^{field}：([^\n]+)", content)
            if match:
                values[field] = match.group(1).strip()
            else:
                errors.append(f"{doc.name}: missing {field}")
        status = values.get("状态", "")
        if status and not status.startswith(("已实测", "待验证", "停用")):
            errors.append(f"{doc.name}: invalid status")
        if status.startswith("停用") and doc.name in indexed:
            errors.append(f"{doc.name}: stopped runbook is still in current index")
        recent = values.get("最近核验", "")
        if recent and recent != "无":
            match = re.match(r"\d{4}-\d{2}-\d{2}", recent)
            try:
                if match is None:
                    raise ValueError("missing date")
                date.fromisoformat(match.group())
            except ValueError:
                errors.append(f"{doc.name}: invalid recent verification date")
        authority = values.get("权威入口", "")
        for raw in re.findall(r"`([^`]+)`", authority):
            if "/" not in raw:
                continue
            source = Path(raw)
            if len(source.parts) > 1 and source.parts[0] == "..":
                sibling = HUB.parent / source.parts[1]
                if not sibling.exists():
                    # A standalone Videohub clone has no sibling repositories.
                    continue
            if not (HUB / raw).exists():
                errors.append(f"{doc.name}: missing authoritative path {raw}")
    for name in indexed:
        if not (RUNBOOKS / name).is_file():
            errors.append(f"README.md: indexed runbook missing: {name}")
    return errors


if __name__ == "__main__":
    findings = check()
    for finding in findings:
        print(f"[FAIL] {finding}")
    if findings:
        sys.exit(1)
    print("[OK] Agent runbook structure and local references")
