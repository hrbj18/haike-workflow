"""One source crop contract for evidence, preview and template rendering."""
from backlot.material_library import MaterialLibraryError, number


def normalize_crop(raw=None):
    raw = raw or {"x": 0, "y": 0, "w": 1, "h": 1}
    if not isinstance(raw, dict) or set(raw) != {"x", "y", "w", "h"}:
        raise MaterialLibraryError("裁切须为归一化 x/y/w/h")
    crop = {key: round(number(raw[key], "裁切" + key, 0, 1), 6) for key in raw}
    if min(crop["w"], crop["h"]) < .1 or crop["x"] + crop["w"] > 1.000001 or crop["y"] + crop["h"] > 1.000001:
        raise MaterialLibraryError("裁切越界或区域过小")
    return crop


def crop_filter(raw=None):
    crop = normalize_crop(raw)
    return (f"crop=trunc(iw*{crop['w']}/2)*2:trunc(ih*{crop['h']}/2)*2:"
            f"trunc(iw*{crop['x']}/2)*2:trunc(ih*{crop['y']}/2)*2")


def template_filter(raw):
    # Fit the selected source region inside the actual template band, never
    # stretch it or center-crop away the entity that was reviewed.
    return (crop_filter(raw) + ",scale=1080:630:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1080:630:(ow-iw)/2:(oh-ih)/2:black,pad=1080:1920:0:650:black,setsar=1,fps=30")
