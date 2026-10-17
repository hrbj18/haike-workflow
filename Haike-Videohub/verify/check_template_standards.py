#!/usr/bin/env python3
"""Offline authoring checks: no rendering, network, queue submission or media certification."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

HUB = Path(__file__).resolve().parents[1]
VERSION = "video-template-v1"
SCHEMA = HUB / "contracts/video-template-spec-v1.schema.json"
MANIFEST = HUB / "contracts/video-template-standard-v1.json"
EXTENSIONS = {
    "avatar": ("face_crop", "synchronization"),
    "graphic": ("text_policy", "asset_fit"),
    "chart": ("data_mapping", "label_policy"),
    "tutorial": ("step_mapping", "callout_policy"),
    "material_edit": ("source_ranges", "cut_policy"),
    "custom": ("contract", "rules"),
}
KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "const",
    "enum", "anyOf", "required", "properties", "additionalProperties", "items",
    "minItems", "maxItems", "minLength", "minimum", "exclusiveMinimum", "pattern",
    "minProperties",
}
LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def read_json(path: Path) -> Any:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid_constant)


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def schema_contract_errors(rule: Any, root: dict, path: str = "schema") -> list[str]:
    """Reject unsupported schema constructs even in branches absent from the input."""
    if isinstance(rule, bool):
        return []
    if not isinstance(rule, dict):
        return [f"{path}: schema must be an object or boolean"]
    errors = []
    unsupported = set(rule) - KEYWORDS
    if unsupported:
        errors.append(f"{path}: unsupported keywords {sorted(unsupported)}")
    annotations = {"$schema", "$id", "$defs", "title", "description"}
    for branch in ("$ref", "anyOf"):
        if branch in rule and set(rule) - annotations - {branch}:
            errors.append(f"{path}: unsupported sibling constraints beside {branch}")
    if "$ref" in rule:
        target = rule["$ref"]
        if not isinstance(target, str) or not target.startswith("#/$defs/") or target[8:] not in root.get("$defs", {}):
            errors.append(f"{path}: invalid local reference")
    for collection in ("properties", "$defs"):
        for key, child in rule.get(collection, {}).items():
            errors.extend(schema_contract_errors(child, root, f"{path}/{collection}/{key}"))
    for key in ("items", "additionalProperties"):
        if key in rule:
            errors.extend(schema_contract_errors(rule[key], root, f"{path}/{key}"))
    for index, child in enumerate(rule.get("anyOf", [])):
        errors.extend(schema_contract_errors(child, root, f"{path}/anyOf/{index}"))
    return errors


def schema_errors(value: Any, rule: Any, root: dict, path: str = "$", depth: int = 0) -> list[str]:
    """Interpret only the explicit JSON Schema subset used by the bundled contract."""
    if depth == 0:
        contract = schema_contract_errors(root, root)
        if rule is not root:
            contract.extend(schema_contract_errors(rule, root))
        if contract:
            return contract
    if depth > 100:
        return [f"{path}: schema reference recursion exceeds the supported depth"]
    if rule is True:
        return []
    if rule is False:
        return [f"{path}: additional value is not allowed"]
    unsupported = set(rule) - KEYWORDS
    if unsupported:
        return [f"schema: unsupported keywords {sorted(unsupported)}"]
    if "$ref" in rule:
        target = rule["$ref"]
        if not target.startswith("#/$defs/"):
            return [f"schema: unsupported reference {target}"]
        return schema_errors(value, root["$defs"][target[8:]], root, path, depth + 1)
    if "anyOf" in rule:
        candidates = [schema_errors(value, item, root, path, depth + 1) for item in rule["anyOf"]]
        return [] if any(not errors for errors in candidates) else [f"{path}: no allowed schema matches"]
    kind = rule.get("type")
    matches = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "number": number(value),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool), "null": value is None,
    }
    if kind and not matches.get(kind, False):
        return [f"{path}: expected {kind}"]
    errors: list[str] = []
    if "const" in rule and (value != rule["const"] or isinstance(value, bool) != isinstance(rule["const"], bool)):
        errors.append(f"{path}: expected constant {rule['const']!r}")
    if "enum" in rule and not any(value == item and isinstance(value, bool) == isinstance(item, bool) for item in rule["enum"]):
        errors.append(f"{path}: value is outside the allowed enum")
    if isinstance(value, dict):
        if len(value) < rule.get("minProperties", 0):
            errors.append(f"{path}: object is empty")
        for key in rule.get("required", []):
            if key not in value:
                errors.append(f"{path}/{key}: required field missing")
        properties = rule.get("properties", {})
        for key, item in value.items():
            child = properties.get(key, rule.get("additionalProperties", True))
            errors.extend(schema_errors(item, child, root, f"{path}/{key}", depth + 1))
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0) or len(value) > rule.get("maxItems", math.inf):
            errors.append(f"{path}: array length is outside the allowed range")
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, rule.get("items", True), root, f"{path}/{index}", depth + 1))
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0) or (rule.get("minLength", 0) and not value.strip()):
            errors.append(f"{path}: non-empty text required")
        if "pattern" in rule and re.search(rule["pattern"], value) is None:
            errors.append(f"{path}: text does not match the required pattern")
    if number(value):
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{path}: below minimum")
        if "exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]:
            errors.append(f"{path}: must exceed minimum")
    return errors


def unknown_paths(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        if value.get("status") == "unknown":
            return [path]
        return [item for key, child in value.items() for item in unknown_paths(child, f"{path}/{key.replace('~', '~0').replace('/', '~1')}")]
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in unknown_paths(child, f"{path}/{index}")]
    return []


def pointer_value(value: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must begin with /")
    for segment in pointer[1:].split("/"):
        key = segment.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def check_spec(spec: Any, base_dir: Path | None = None, schema: dict | None = None) -> list[str]:
    schema = schema if schema is not None else read_json(SCHEMA)
    errors = schema_errors(spec, schema, schema)
    if errors:
        return errors
    errors = []

    def unique(items: list[dict], label: str) -> dict:
        result = {}
        for item in items:
            if item["id"] in result:
                errors.append(f"{label}: duplicate id {item['id']}")
            result[item["id"]] = item
        return result

    scenes = unique(spec["scenes"], "scenes")
    elements = unique(spec["elements"], "elements")
    assets = unique(spec["assets"], "assets")
    slots = unique(spec["slots"], "slots")
    evidence = unique(spec["evidence"], "evidence")
    unique(spec["operations"], "operations")
    if "global" in scenes:
        errors.append("scenes: global is a reserved timebase name")
    duration = spec["canvas"]["duration_seconds"]
    previous_end: Any = 0
    used_elements = set()
    for scene in spec["scenes"]:
        start, end = scene["start"], scene["end"]
        if number(start) and start < 0:
            errors.append(f"scene {scene['id']}: start is negative")
        if number(end) and end <= 0:
            errors.append(f"scene {scene['id']}: end must be positive")
        if number(start) and number(duration) and start >= duration:
            errors.append(f"scene {scene['id']}: start reaches past canvas duration")
        if number(end) and number(duration) and end > duration + 1e-6:
            errors.append(f"scene {scene['id']}: extends past canvas duration")
        if number(start) and number(end):
            if start < 0 or end <= start:
                errors.append(f"scene {scene['id']}: invalid interval")
            if number(previous_end) and abs(start - previous_end) > 1e-6:
                errors.append(f"scene {scene['id']}: timeline gap or overlap")
            if number(duration) and end > duration + 1e-6:
                errors.append(f"scene {scene['id']}: extends past canvas duration")
        previous_end = end
        for element_id in scene["element_ids"]:
            if element_id not in elements:
                errors.append(f"scene {scene['id']}: missing element {element_id}")
            used_elements.add(element_id)
    if number(duration) and number(previous_end) and abs(previous_end - duration) > 1e-6:
        errors.append("scenes: timeline does not cover canvas duration")
    for element_id in elements.keys() - used_elements:
        errors.append(f"element {element_id}: not assigned to a scene")

    for slot in slots.values():
        if slot["element_id"] != "global" and slot["element_id"] not in elements:
            errors.append(f"slot {slot['id']}: missing target element")
        if not slot["limits"]:
            errors.append(f"slot {slot['id']}: replacement limits must be explicit")
        if slot["element_id"] in elements:
            target = elements[slot["element_id"]]
            prop = slot["property"]
            if not any(prop == item or prop.startswith(item + ".") for item in target["replaceable"]):
                errors.append(f"slot {slot['id']}: property is not an open replacement field")
            if any(prop == item or prop.startswith(item + ".") or item.startswith(prop + ".") for item in target["fixed"]):
                errors.append(f"slot {slot['id']}: property conflicts with a fixed field")
    for element in elements.values():
        label = f"element {element['id']}"
        parent = element["parent_id"]
        if parent is not None and parent not in elements:
            errors.append(f"{label}: missing parent {parent}")
        if element["layout"]["coordinate_space"] == "parent" and parent is None:
            errors.append(f"{label}: parent coordinates need a parent_id")
        seen = {element["id"]}
        cursor = parent
        while cursor in elements:
            if cursor in seen:
                errors.append(f"{label}: parent cycle")
                break
            seen.add(cursor)
            cursor = elements[cursor]["parent_id"]
        for fixed in element["fixed"]:
            for replaceable in element["replaceable"]:
                if fixed == replaceable or fixed.startswith(replaceable + ".") or replaceable.startswith(fixed + "."):
                    errors.append(f"{label}: fixed and replaceable fields conflict")
        content = element["content"]
        if content["asset_id"] is not None and content["asset_id"] not in assets:
            errors.append(f"{label}: missing asset")
        binding = content["binding"]
        if binding is not None:
            slot = slots.get(binding)
            if slot is None or slot["element_id"] != element["id"]:
                errors.append(f"{label}: binding must target its own slot")
            elif content["mode"] == "embedded" and not (slot["value_type"] == "asset" and slot["property"] == "content.asset_id"):
                errors.append(f"{label}: baked-in content is not an editable interior text slot")
        if content["mode"] == "embedded" and content["asset_id"] is None:
            errors.append(f"{label}: embedded content needs an asset")
        if content["mode"] == "editable" and binding is None:
            errors.append(f"{label}: editable content needs a slot binding")
        layout = element["layout"]
        box = layout["box"]
        if isinstance(box, list):
            x, y, width, height = box
            if width <= 0 or height <= 0:
                errors.append(f"{label}: box size must be positive")
            bounds = [spec["canvas"]["width"], spec["canvas"]["height"]]
            if layout["coordinate_space"] == "parent" and parent in elements:
                parent_box = elements[parent]["layout"]["box"]
                bounds = parent_box[2:] if isinstance(parent_box, list) else None
            allow_overflow = any(c["kind"] == "allow_overflow" for c in element["constraints"])
            if bounds and not allow_overflow and (x < 0 or y < 0 or x + width > bounds[0] + 1e-6 or y + height > bounds[1] + 1e-6):
                errors.append(f"{label}: nominal box exceeds its container; document intentional overflow")
        if element["type"] in {"text", "subtitle"}:
            for key in ("font", "font_size", "max_lines", "overflow"):
                if key not in layout["style"]:
                    errors.append(f"{label}: text style missing {key}")
        clock = element["timing"]
        if clock["relative_to"] != "global" and clock["relative_to"] not in scenes:
            errors.append(f"{label}: missing scene timebase")
        start, end = clock["start"], clock["end"]
        if number(start) and start < 0:
            errors.append(f"{label}: start is negative")
        if number(end) and end <= 0:
            errors.append(f"{label}: end must be positive")
        limit = duration
        if clock["relative_to"] in scenes:
            scene = scenes[clock["relative_to"]]
            limit = scene["end"] - scene["start"] if number(scene["end"]) and number(scene["start"]) else None
        if number(start) and number(limit) and start >= limit:
            errors.append(f"{label}: start reaches past its timebase")
        if number(end) and number(limit) and end > limit + 1e-6:
            errors.append(f"{label}: timing exceeds its timebase")
        if number(start) and number(end):
            if start < 0 or end <= start:
                errors.append(f"{label}: invalid timing")
            limit = duration
            if clock["relative_to"] in scenes:
                scene = scenes[clock["relative_to"]]
                limit = scene["end"] - scene["start"] if number(scene["end"]) and number(scene["start"]) else None
            if number(limit) and end > limit + 1e-6:
                errors.append(f"{label}: timing exceeds its timebase")
        states = unique(element["states"], label + " states")
        for transition in element["transitions"]:
            if transition["from"] not in states or transition["to"] not in states:
                errors.append(f"{label}: transition refers to missing state")
            first, last = transition["start"], transition["end"]
            if number(first) and (first < 0 or (number(start) and first < start) or (number(end) and first >= end)):
                errors.append(f"{label}: transition start outside element timing")
            if number(last) and (last <= 0 or (number(start) and last <= start) or (number(end) and last > end)):
                errors.append(f"{label}: transition end outside element timing")
            if number(first) and number(last) and (last <= first or (number(start) and first < start) or (number(end) and last > end)):
                errors.append(f"{label}: transition outside element timing")
        for constraint in element["constraints"]:
            if constraint["target_id"] is not None and constraint["target_id"] not in elements:
                errors.append(f"{label}: constraint refers to missing element")
        for evidence_id in element["evidence_ids"]:
            if evidence_id not in evidence:
                errors.append(f"{label}: missing evidence {evidence_id}")

    if not isinstance(spec["extensions"].get(spec["template_type"]), dict):
        errors.append("extensions: template type needs its declared module")
    for name, module in spec["extensions"].items():
        if not isinstance(module, dict):
            errors.append(f"extensions/{name}: module must be an object")
            continue
        for key in EXTENSIONS.get(name, ("contract", "rules")):
            if key not in module or module[key] in (None, "", [], {}):
                errors.append(f"extensions/{name}: missing {key}")
    for element in elements.values():
        if element["type"] in {"avatar", "chart"} and element["type"] not in spec["extensions"]:
            errors.append(f"extensions: element {element['id']} needs {element['type']} rules")
    unresolved = unknown_paths(spec)
    registered = {item["path"] for item in spec["unknowns"]}
    for path in unresolved:
        if path not in registered:
            errors.append(f"{path}: unknown value needs an unknowns record")
        marker = pointer_value(spec, path)
        errors.extend(schema_errors(marker, schema["$defs"]["unknown"], schema, path))
    for item in spec["unknowns"]:
        try:
            pointer_value(spec, item["path"])
        except (ValueError, KeyError, IndexError, TypeError):
            errors.append(f"unknowns: target JSON pointer does not resolve: {item['path']}")
    for gate, result in spec["validation"].items():
        if result["status"] == "pass" and not result["evidence_ids"]:
            errors.append(f"validation/{gate}: pass needs evidence")
        for evidence_id in result["evidence_ids"]:
            record = evidence.get(evidence_id)
            if record is None:
                errors.append(f"validation/{gate}: missing evidence {evidence_id}")
            elif result["status"] == "pass" and record["source_kind"] in {"illustrative", "design"}:
                errors.append(f"validation/{gate}: a design or example does not prove a passed check")
    if spec["stage"] == "ready":
        if spec["spec_kind"] != "implementation":
            errors.append("ready requires implementation, not reference observations")
        if unresolved or any("execution" in item["blocks"] for item in spec["unknowns"]):
            errors.append("ready cannot contain unresolved execution parameters")
        authority = spec["authority"]
        if not authority["implementation_paths"]:
            errors.append("ready needs archived implementation sources")
        if any(operation["entrypoint"] is None for operation in spec["operations"]):
            errors.append("ready: every operation needs an explicit executable or manual entrypoint")
        for gate in ("technical", "visual"):
            result = spec["validation"][gate]
            records = [evidence[key] for key in result["evidence_ids"] if key in evidence]
            if result["status"] != "pass" or not records or not all(item["file"] and item["sha256"] for item in records):
                errors.append(f"ready: {gate} needs passed, file-bound evidence")
        if base_dir is not None:
            sources = authority["implementation_paths"] + ([] if authority["parameter_source"] == "self" else [authority["parameter_source"]])
            for path in sources:
                if not (base_dir / path).is_file():
                    errors.append(f"ready: missing authority file {path}")
            for asset in assets.values():
                if asset["path"] is not None and not (base_dir / asset["path"]).is_file():
                    errors.append(f"ready: missing runtime asset {asset['id']}")
    if base_dir is not None:
        if not (base_dir / spec["authority"]["runbook"]).is_file():
            errors.append("authority: runbook file is missing")
        for record in evidence.values():
            if record["file"] is not None:
                path = base_dir / record["file"]
                if not path.is_file():
                    errors.append(f"evidence {record['id']}: missing file")
                elif record["sha256"] is not None and hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                    errors.append(f"evidence {record['id']}: file hash mismatch")
    return errors


def check_package(hub: Path = HUB, workspace: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        manifest = read_json(hub / "contracts/video-template-standard-v1.json")
        if manifest["standard_version"] != VERSION:
            return ["standard distribution version mismatch"]
    except (OSError, ValueError, KeyError) as exc:
        return [f"standard distribution manifest: {exc}"]
    for name in manifest["required_files"]:
        if not (hub / name).is_file():
            errors.append(f"distribution: missing {name}")
    for name, kind in manifest["reference_documents"].items():
        file = hub / name
        if file.is_file():
            body = file.read_text(encoding="utf-8-sig")
            if f"文档类型：{kind}" not in body or f"标准版本：{VERSION}" not in body:
                errors.append(f"{name}: document kind or standard version mismatch")
    for route in manifest["hub_routes"]:
        file = hub / route["path"]
        if not file.is_file() or route["target"] not in file.read_text(encoding="utf-8-sig"):
            errors.append(f"route: {route['path']} cannot reach {route['target']}")
    for file in (hub / "agent-runbooks/template-standards").rglob("*.md"):
        for raw in LINK.findall(file.read_text(encoding="utf-8-sig")):
            target = unquote(raw.split("#", 1)[0].split("?", 1)[0])
            if target and not re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) and not (file.parent / target).exists():
                errors.append(f"{file.relative_to(hub)}: missing local link {target}")
    schema = read_json(hub / "contracts/video-template-spec-v1.schema.json")
    for folder in ("examples", "specs"):
        for file in sorted((hub / "agent-runbooks/template-standards" / folder).glob("*.json")):
            try:
                errors.extend(f"{file.relative_to(hub)}: {item}" for item in check_spec(read_json(file), file.parent, schema))
            except (OSError, ValueError, KeyError) as exc:
                errors.append(f"{file.relative_to(hub)}: {exc}")
    for file in (hub / "agent-runbooks").glob("*.md"):
        body = file.read_text(encoding="utf-8-sig")
        match = re.search(r"(?m)^标准版本：([^\n]+)", body)
        kind = re.search(r"(?m)^文档类型：([^\n]+)", body)
        declared_kind = kind.group(1).strip() if kind else ""
        is_reference = f"agent-runbooks/{file.name}" in manifest["reference_documents"]
        if file.name not in {"README.md", "TEMPLATE.md"} and not is_reference and file.name not in manifest["legacy_runbooks"]:
            if declared_kind not in {"video-template-runbook", "operation-runbook"}:
                errors.append(f"{file.name}: new runbook must declare video-template-runbook or operation-runbook")
        if declared_kind == "video-template-runbook" and not match:
            errors.append(f"{file.name}: video template runbook requires a standard version")
        if match and not is_reference:
            if match.group(1).strip() != VERSION:
                errors.append(f"{file.name}: unsupported template standard version")
            link = re.search(r"(?m)^模板规格：\[[^]]+\]\(([^)]+\.json)\)", body)
            if link is None:
                errors.append(f"{file.name}: template standard requires a spec link")
            else:
                spec_path = file.parent / unquote(link.group(1))
                try:
                    spec = read_json(spec_path)
                    errors.extend(f"{file.name}: {item}" for item in check_spec(spec, spec_path.parent, schema))
                    if (spec_path.parent / spec["authority"]["runbook"]).resolve() != file.resolve():
                        errors.append(f"{file.name}: specification points to another runbook")
                except (OSError, ValueError, KeyError) as exc:
                    errors.append(f"{file.name}: spec cannot be read: {exc}")
    if workspace:
        for route in manifest["workspace_routes"]:
            file = hub.parent / route["path"]
            if not file.is_file() or route["target"] not in file.read_text(encoding="utf-8-sig"):
                errors.append(f"workspace route: {route['path']} cannot reach {route['target']}")
        root = hub.parent / "AGENTS.md"
        source = hub / manifest["workspace_root_source"]
        if root.is_file() and source.is_file() and root.read_text(encoding="utf-8-sig") != source.read_text(encoding="utf-8-sig"):
            errors.append("workspace root AGENTS.md differs from its distribution source; merge before packaging")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", action="store_true", help="also require root and producer Agent routes")
    parser.add_argument("--spec", type=Path, help="validate a particular authoring specification")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        errors = check_package(workspace=args.workspace)
        if args.spec:
            path = args.spec.resolve()
            errors.extend(f"{path.name}: {item}" for item in check_spec(read_json(path), path.parent))
    except (OSError, ValueError, KeyError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"[FAIL] {error}")
    if errors:
        return 1
    scope = "complete workspace routes" if args.workspace else "Videohub distribution"
    print(f"[OK] {VERSION}: {scope}, schema, examples and registered specifications")
    print("[NOTE] Static checks do not certify visual quality, listening, user approval, or platform playback.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
