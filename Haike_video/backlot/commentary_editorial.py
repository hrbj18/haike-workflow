"""Material-led event cards and editorial diagnostics; no story scaffold."""
from backlot.commentary_common import CommentaryError, identifier, text
from backlot import commentary_evidence as evidence
from copy import deepcopy


def normalize(project, raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("version") != 2:
        raise CommentaryError("事件方案版本须为2")
    candidates = raw.get("candidate_media_ids", [])
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 1000:
        raise CommentaryError("请声明本次候选素材集合，最多1000条")
    candidates = list(dict.fromkeys(identifier(i, "MAT-") for i in candidates))
    def records(value, label):
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise CommentaryError(label + "须为对象列表")
        return value

    def evidence_ids(row):
        values = row.get("evidence_ids", [])
        if not isinstance(values, list): raise CommentaryError("证据编号须为列表")
        return list(dict.fromkeys(identifier(value, "EV-") for value in values))

    coverage, seen = [], set()
    for row in records(raw.get("coverage", []), "覆盖记录"):
        mid = identifier(row.get("media_id"), "MAT-")
        if mid not in candidates or mid in seen:
            raise CommentaryError("覆盖记录须属于候选集合且不能重复")
        seen.add(mid)
        state = row.get("status")
        if state not in {"reviewed", "excluded", "pending"}:
            raise CommentaryError("覆盖状态须为 reviewed、excluded 或 pending")
        ids = evidence_ids(row)
        for eid in ids:
            if evidence.confirmed(project, eid)["media_id"] != mid:
                raise CommentaryError("覆盖证据与素材身份不符")
        if state == "reviewed" and not ids:
            raise CommentaryError("采用素材须有已确认区间证据")
        coverage.append({"media_id": mid, "status": state, "reason": text(row.get("reason"), "覆盖或排除理由", 2000),
                         "evidence_ids": ids})
    events, seen = [], set()
    rows = raw.get("events", [])
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise CommentaryError("事件卡须为1至500项")
    for row in records(rows, "事件卡"):
        eid = identifier(row.get("id"))
        if eid in seen: raise CommentaryError("事件编号重复")
        seen.add(eid)
        ids = evidence_ids(row)
        if not ids: raise CommentaryError("事件卡缺少素材证据")
        for value in ids:
            item = evidence.confirmed(project, value)
            if item["media_id"] not in candidates:
                raise CommentaryError("事件素材未纳入候选覆盖集合")
        events.append({"id": eid, "evidence_ids": ids,
            **{key: text(row.get(key), "事件" + key, 2000) for key in
               ("summary", "context", "setup", "action", "result", "tone", "original_reason")},
            "duplicate_group": text(row.get("duplicate_group", ""), "同类事件组", 160, empty=True)})
    return {"version": 2, "candidate_media_ids": candidates, "coverage": coverage, "events": events}


def audit(plan, timeline=None, project=None):
    editorial = plan.get("editorial")
    if not editorial:
        return {"enabled": False, "next_action": "建立候选覆盖清单和事件卡后启用精剪检查"}
    coverage = {r["media_id"]: r for r in editorial["coverage"]}
    counts = {key: 0 for key in ("reviewed", "excluded", "pending")}
    for mid in editorial["candidate_media_ids"]:
        counts[coverage.get(mid, {}).get("status", "pending")] += 1
    repeats, long_shots, windows = [], [], []
    rows = deepcopy((timeline or {}).get("segments", plan["segments"]))
    for row in rows:
        for index, shot in enumerate(row["shots"]):
            mid = shot.get("media_id") or (evidence.read(project, shot["evidence_id"])["media_id"] if project else shot["evidence_id"])
            for old in windows:
                overlap = min(old["end"], shot["end"]) - max(old["start"], shot["start"])
                if old["media_id"] == mid and overlap > .1:
                    repeats.append({"segment_id": row["id"], "shot_index": index, "previous_segment": old["segment_id"],
                        "overlap_seconds": round(overlap, 3), "reason": shot.get("repeat_reason", "")})
            windows.append({"media_id": mid, "segment_id": row["id"], "start": shot["start"], "end": shot["end"]})
            if shot["end"] - shot["start"] > 8:
                long_shots.append({"segment_id": row["id"], "shot_index": index,
                    "seconds": round(shot["end"] - shot["start"], 3), "note": "核对动作/台词价值，不自动截短"})
    groups = {}
    for event in editorial["events"]:
        if event["duplicate_group"]:
            groups.setdefault(event["duplicate_group"], []).append(event["id"])
    return {"enabled": True, "coverage": {"total": len(editorial["candidate_media_ids"]), **counts},
        "events": editorial["events"], "duplicate_groups": groups, "repeated_windows": repeats,
        "long_shots": long_shots, "shot_count": len(windows), "segment_count": len(rows),
        "duration": (timeline or {}).get("duration"), "subtitle_modes": [r["subtitle_mode"] for r in rows],
        "pending_media_ids": [mid for mid in editorial["candidate_media_ids"] if coverage.get(mid, {}).get("status", "pending") == "pending"]}


def metrics(frozen):
    sounds, shots, cuts = [], [], []
    for segment in frozen["segments"]:
        start = segment["start_frame"] / frozen["profile"]["fps"]
        if "source_audio" in segment:
            sounds.extend((c["timeline_start"], c["timeline_start"] + c["end"] - c["start"]) for c in segment["source_audio"])
        elif segment["mode"] != "narration":
            sounds.append((start, start + segment["frames"] / frozen["profile"]["fps"]))
        at = start
        for shot in segment["shots"]:
            duration = shot["frames"] / frozen["profile"]["fps"]
            if at > 0: cuts.append(round(at, 3))
            shots.append(duration); at += duration
    union, current = 0, None
    for a,b in sorted(sounds):
        if current and a <= current[1]: current = (current[0], max(b, current[1]))
        else:
            if current: union += current[1]-current[0]
            current = (a,b)
    if current: union += current[1]-current[0]
    return {"project_id": frozen["project_id"], "revision": frozen["revision"], "duration": frozen["duration"],
        "shot_count": len(shots), "cut_seconds": cuts, "average_shot_seconds": round(sum(shots)/len(shots), 3),
        "longest_shot_seconds": max(shots), "original_audio_ratio": round(union/frozen["duration"], 4),
        "subtitle_methods": sorted(set(s["subtitle_mode"] for s in frozen["segments"])),
        "independent_audio_clips": sum(len(s.get("source_audio", [])) for s in frozen["segments"]),
        "editorial": frozen.get("editorial_report"), "source_sha256": sorted(s["sha256"] for s in frozen["sources"].values())}


def compare(identity, payload, *, projects_root, db_path=None):
    from backlot import material_commentary as flow, material_library as library
    from backlot.commentary_common import read_json
    def frozen(project_id, signature=None):
        flow.read(project_id, db_path=db_path)
        if not signature:
            with library.connect(db_path) as db:
                row = db.execute("SELECT signature FROM commentary_versions WHERE project_id=? ORDER BY revision DESC LIMIT 1", (project_id,)).fetchone()
            if not row: raise CommentaryError("比较项目尚无冻结版本，请先提交版本")
            signature = row["signature"]
        result = read_json(flow.version_dir(project_id, signature, projects_root=projects_root) / "request.json")
        if result.get("project_id") != project_id: raise CommentaryError("比较版本身份不符")
        return metrics(result)
    target = frozen(identity, payload.get("target_signature"))
    baseline = frozen(payload.get("baseline_project_id"), payload.get("baseline_signature"))
    return {"baseline": baseline, "target": target,
        "same_source_pool": target["source_sha256"] == baseline["source_sha256"],
        "note": "指标用于定位节奏变化，不是主观流畅度评分；需观看和回听同源版本"}
