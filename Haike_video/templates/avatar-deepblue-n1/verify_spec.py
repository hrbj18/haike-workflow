"""Check or regenerate the read-only N1 specification geometry projection."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def projections(layout: dict) -> tuple[dict, dict]:
    """Mirror logical component boxes, not compressed-frame glyph measurements."""
    canvas = layout["canvas"]
    width, height = canvas["width"], canvas["height"]
    title, source, window = (layout[key] for key in ("title", "source", "window"))
    caption, circle, brand, english, bottom, data = (
        layout[key] for key in ("caption", "circle", "brand", "english", "bottomLine", "data")
    )
    screenshot_height = window["height"] - window["screenshotCaptionReserve"]
    caption_height = caption["size"] * caption["lineHeight"]
    boxes = {
        "background": [0, 0, width, height],
        "source": [source["left"], source["top"], width - source["left"] * 2, source["size"] * source["lineHeight"]],
        "window": [window["left"], window["top"], window["width"], window["height"]],
        "presenter": [0, 0, window["width"], window["height"]],
        "material": [0, 0, window["width"], window["height"]],
        "screenshot": [0, 0, window["width"], screenshot_height],
        "highlight": [0, 0, window["width"], screenshot_height],
        "data_background": [0, 0, window["width"], window["height"]],
        "data_label": [data["left"], data["labelTop"], window["width"] - data["left"] * 2, data["labelSize"] * data["lineHeight"]],
        "data_title": [data["left"], data["titleTop"], window["width"] - data["left"] * 2, data["titleSize"] * data["lineHeight"]],
        "caption": [caption["left"], window["height"] - caption["bottom"] - caption_height, caption["width"], caption_height],
        "circle": [circle["left"], circle["top"], circle["diameter"], circle["diameter"]],
        "brand": [brand["left"], brand["top"], brand["width"], brand["height"]],
        "english": [english["left"], english["top"], english["width"], english["size"] * english["lineHeight"]],
        "bottom_line": [0, bottom["top"], width, bottom["height"]],
    }
    fonts = {
        "source": source["size"], "data_label": data["labelSize"],
        "data_title": data["titleSize"], "caption": caption["size"],
        "brand": brand["fontSize"], "english": english["size"],
    }
    for index in range(3):
        key = f"title_{index + 1}"
        boxes[key] = [title["left"], title["tops"][index], title["width"], title["sizes"][index] * title["lineHeight"]]
        fonts[key] = title["sizes"][index]
    for index in range(4):
        key = f"data_row_{index + 1}"
        boxes[key] = [data["left"], data["rowTop"] + index * data["rowStep"], window["width"] - data["left"] * 2, data["rowSize"] * data["lineHeight"]]
        fonts[key] = data["rowSize"]
    return boxes, fonts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Regenerate only derived boxes, font sizes and configuration identity.")
    args = parser.parse_args()
    spec_path, layout_path = ROOT / "template-spec.json", ROOT / "layout.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    boxes, fonts = projections(layout)
    layout_sha = hashlib.sha256(layout_path.read_bytes()).hexdigest()
    by_id = {item["id"]: item for item in spec["elements"]}
    if set(by_id) != set(boxes):
        raise ValueError("Specification element IDs differ from the projection contract; review implementation and projection together.")
    evidence = next(item for item in spec["evidence"] if item["id"] == "layout_projection")
    caption_slot = next(item for item in spec["slots"] if item["id"] == "caption_slot")
    if args.refresh:
        for key, box in boxes.items():
            by_id[key]["layout"]["box"] = box
        for key, size in fonts.items():
            by_id[key]["layout"]["style"]["font_size"] = size
        for key in ("width", "height", "fps"):
            spec["canvas"][key] = layout["canvas"][key]
        for index in range(3):
            by_id[f"title_{index + 1}"]["layout"]["style"]["line_height"] = layout["title"]["lineHeight"]
        by_id["title_1"]["transitions"][0]["end"] = layout["title"]["fadeSeconds"]
        by_id["caption"]["layout"]["style"]["line_height"] = layout["caption"]["lineHeight"]
        by_id["caption"]["layout"]["style"]["max_chars"] = layout["caption"]["maxChars"]
        caption_slot["limits"]["cue_max_chars"] = layout["caption"]["maxChars"]
        evidence["sha256"] = layout_sha
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = []
    for key in ("width", "height", "fps"):
        if spec["canvas"][key] != layout["canvas"][key]:
            errors.append(f"canvas/{key}: projection differs from layout.json")
    for key, box in boxes.items():
        actual = by_id[key]["layout"]["box"]
        if len(actual) != 4 or any(abs(a - b) > 1e-6 for a, b in zip(actual, box)):
            errors.append(f"{key}: geometry projection differs from layout.json")
    for key, size in fonts.items():
        if by_id[key]["layout"]["style"]["font_size"] != size:
            errors.append(f"{key}: nominal font projection differs from layout.json")
    if evidence["sha256"] != layout_sha:
        errors.append("layout_projection: source configuration hash differs")
    if by_id["title_1"]["transitions"][0]["end"] != layout["title"]["fadeSeconds"]:
        errors.append("title_1: animation projection differs from layout.json")
    if caption_slot["limits"]["cue_max_chars"] != layout["caption"]["maxChars"]:
        errors.append("caption_slot: caption length projection differs from layout.json")
    checker_path = ROOT.parents[2] / "Haike-Videohub/verify/check_template_standards.py"
    module_spec = importlib.util.spec_from_file_location("n1_template_checker", checker_path)
    checker = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(checker)
    errors.extend(checker.check_package())
    errors.extend(checker.check_spec(spec, ROOT))
    for error in errors:
        print(f"[FAIL] {error}")
    if errors:
        return 1
    print("[OK] N1 read-only geometry projection, configuration identity and video-template-v1 specification")
    print("[NOTE] Static checks do not certify rendered frames, listening, production, user approval or platform playback.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
