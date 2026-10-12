"""Material-led commentary: free narrative order, source evidence and frozen timelines.

The director (human or agent) reasons from observations. This contract never invents
a hook/body/ending scaffold or equates an algorithmic score with understanding.
"""
from __future__ import annotations

import copy
import math
import re
from pathlib import Path
from uuid import uuid4

from backlot import material_library as library
from backlot import commentary_audio as audio
from backlot import commentary_evidence as evidence
from backlot import commentary_library_bridge as bridge
from backlot import commentary_editorial as editorial
from backlot import commentary_alignment as alignment
from backlot import commentary_captions as captions
from backlot import commentary_presenter as presenter
from backlot import commentary_layout as layout
from backlot.commentary_common import (
    CommentaryConflict, CommentaryError, FORMATS, FPS, RATE, SAMPLES_PER_FRAME,
    VERSION, WORKFLOW, atomic, digest, file_sha256, identifier, immutable, number,
    probe, project_dir, read_json, text, verified, subtitle_font,
)
from backlot.output_loudness_preferences import read_output_loudness_preferences
from lib.checkpoint import init_project


class MaterialGap(CommentaryError):
    def __init__(self, segment_id, missing_frames):
        self.detail = {"status": "needs_material", "segment_id": segment_id,
                       "missing_seconds": missing_frames / FPS,
                       "next_action": "补充已确认镜头或缩短解说；不会循环素材、拉伸语音或定格凑时长"}
        super().__init__(f"段落 {segment_id} 缺少 {missing_frames / FPS:.3f} 秒画面")


def _tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS commentary_drafts (
          id TEXT PRIMARY KEY,title TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commentary_versions (
          project_id TEXT NOT NULL,signature TEXT NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(project_id,signature));
    """)


def _row(row):
    import json
    if row is None:
        raise CommentaryError("素材解说项目不存在")
    return {**dict(row), "payload": json.loads(row["payload"])}


def read(identity, *, db_path=None):
    with library.connect(db_path) as db:
        _tables(db)
        return _row(db.execute("SELECT * FROM commentary_drafts WHERE id=?", (identity,)).fetchone())


def list_drafts(*, db_path=None):
    with library.connect(db_path) as db:
        _tables(db)
        return [_row(r) for r in db.execute("SELECT * FROM commentary_drafts ORDER BY updated_at DESC,id LIMIT 200")]


def create(title, *, projects_root, db_path=None):
    import json
    title = text(title, "项目标题", 120)
    identity = "commentary-" + uuid4().hex[:16]
    directory = project_dir(identity, projects_root)
    init_project(identity, title=title, pipeline_type=WORKFLOW, pipeline_dir=Path(projects_root))
    payload = {"version": VERSION, "format": "portrait", "content_kind": "通用", "intent": "",
               "structure": "", "segments": [], "music": None,
               "target_lufs": read_output_loudness_preferences()["target_lufs"]}
    with library.connect(db_path) as db:
        _tables(db)
        db.execute("INSERT INTO commentary_drafts VALUES(?,?,1,?,?,?)",
                   (identity, title, json.dumps(payload, ensure_ascii=False), library.now(), library.now()))
    immutable(directory / "artifacts/commentary-workflow.json", {
        "workflow": WORKFLOW, "version": VERSION, "render_runtime": "local-ffmpeg",
        "planning": "source-evidence-first", "automatic_publication": False,
        "review_gate": "human-review", "tts": "explicit-frozen-voice-or-imported-audio"})
    return read(identity, db_path=db_path)


def _cues(raw, maximum):
    if not isinstance(raw, list) or len(raw) > 300:
        raise CommentaryError("逐句字幕必须是不超过300项的列表")
    result, previous = [], 0.0
    for cue in raw:
        if not isinstance(cue, dict):
            raise CommentaryError("字幕格式错误")
        start = number(cue.get("start"), "字幕起点", previous, maximum)
        end = number(cue.get("end"), "字幕终点", start + .01, maximum)
        caption = text(cue.get("text"), "字幕", 120)
        if any(c in caption for c in "{}\\\n\r"):
            raise CommentaryError("字幕请用纯文本，不支持控制标记或手工换行")
        result.append({"start": start, "end": end, "text": caption})
        previous = end
    return result


def normalize(project, payload):
    if not isinstance(payload, dict) or payload.get("version", VERSION) != VERSION:
        raise CommentaryError("素材解说配置版本无效")
    shape = payload.get("format", "portrait")
    if shape not in FORMATS:
        raise CommentaryError("画幅须为 portrait、landscape 或 square")
    rows = payload.get("segments")
    if not isinstance(rows, list) or len(rows) > 240:
        raise CommentaryError("段落必须为不超过240项的列表")
    result = {"version": VERSION, "format": shape,
              "content_kind": text(payload.get("content_kind", "通用"), "素材类型", 80),
              "intent": text(payload.get("intent", ""), "解说目标", empty=True),
              "structure": text(payload.get("structure", ""), "依据素材形成的叙事方案", 6000, empty=True),
              "target_lufs": number(payload.get("target_lufs", -9), "响度目标", -16, -8),
              "music": None, "segments": []}
    if payload.get("editorial") is not None:
        result["editorial"] = editorial.normalize(project, payload["editorial"])
    if payload.get("subtitle_style") is not None:
        result["subtitle_style"] = captions.normalize_style(payload["subtitle_style"])
    identities = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CommentaryError("段落格式错误")
        identity = identifier(row.get("id"))
        if identity in identities:
            raise CommentaryError("段落编号重复")
        identities.add(identity)
        mode = row.get("mode")
        if mode not in {"narration", "original", "mixed"}:
            raise CommentaryError("声音方式须为 narration、original 或 mixed")
        narration = text(row.get("text", ""), "解说文案", 10000, empty=mode == "original")
        audio_id = row.get("audio_id") or None
        if mode == "original" and (audio_id or narration):
            raise CommentaryError("原声段不使用新解说；需要旁白请选旁白或混合模式")
        if audio_id:
            take = audio.read(project, audio_id)
            if take["kind"] != "narration" or take["text"] != narration:
                raise CommentaryError("配音与当前文案不一致，请重新配音或恢复对应文案")
        shots = row.get("shots")
        if not isinstance(shots, list) or not 1 <= len(shots) <= 100:
            raise CommentaryError("每段须有一至一百个已观察镜头")
        output_shots = []
        for shot in shots:
            if not isinstance(shot, dict) or set(shot) - {"evidence_id", "start", "end", "repeat_reason"}:
                raise CommentaryError("镜头只接受 evidence_id、start、end；裁切变化须重新取证")
            item = evidence.confirmed(project, shot.get("evidence_id"))
            start = number(shot.get("start"), "镜头起点", item["start"], item["end"])
            end = number(shot.get("end"), "镜头终点", start + 1 / FPS, item["end"])
            output_shots.append({"evidence_id": item["id"], "start": start, "end": end})
            if "repeat_reason" in shot:
                output_shots[-1]["repeat_reason"] = text(shot["repeat_reason"], "重复镜头的叙事理由", 1000, empty=True)
        subtitle_mode = row.get("subtitle_mode", "estimated" if mode != "original" else "none")
        position = row.get("subtitle_position", "bottom")
        if subtitle_mode not in {"estimated", "timed", "aligned", "none"} or position not in {"top", "bottom"}:
            raise CommentaryError("字幕方式或位置无效")
        if subtitle_mode == "estimated" and not narration:
            raise CommentaryError("原声字幕需要转写后的逐句时间戳，不能按空文案估计")
        result["segments"].append({"id": identity, "mode": mode, "text": narration, "audio_id": audio_id,
            "purpose": text(row.get("purpose"), "本段叙事作用", 200),
            "basis": text(row.get("basis"), "素材依据与编排理由", 2000),
            "source_subtitle_note": text(row.get("source_subtitle_note", ""), "原字幕处理说明", 1000, empty=True),
            "source_gain_db": number(row.get("source_gain_db", -18 if mode == "mixed" else 0), "原声音量", -60, 0),
            "subtitle_mode": subtitle_mode, "subtitle_position": position,
            "subtitles": _cues(row.get("subtitles", []), 3600), "shots": output_shots})
        if row.get("presenter") is not None:
            result["segments"][-1]["presenter"] = presenter.normalize(project, row["presenter"], audio_id)
        if row.get("subtitle_layout") is not None:
            result["segments"][-1]["subtitle_layout"] = captions.normalize_layout(row["subtitle_layout"])
        if row.get("presenter_layout") is not None:
            if "presenter" not in result["segments"][-1]:
                raise CommentaryError("自动选位须先选择本段出镜素材")
            result["segments"][-1]["presenter_layout"] = layout.normalize(project, row["presenter_layout"], output_shots)
        if result.get("editorial"):
            event_id = identifier(row.get("event_id"))
            event = next((e for e in result["editorial"]["events"] if e["id"] == event_id), None)
            if not event or any(s["evidence_id"] not in event["evidence_ids"] for s in output_shots):
                raise CommentaryError("段落镜头须属于其关联事件的证据")
            result["segments"][-1]["event_id"] = event_id
        if subtitle_mode == "aligned":
            if not audio_id: raise CommentaryError("语音对齐字幕须绑定旁白音轨")
            item = alignment.read(project, row.get("alignment_id"), audio_id)
            result["segments"][-1]["alignment_id"] = item["id"]
        if "sentence_links" in row:
            links = row["sentence_links"]
            if not isinstance(links, list) or len(links) > 300:
                raise CommentaryError("逐句配镜须为不超过300项的列表")
            result["segments"][-1]["sentence_links"] = []
            for link in links:
                index = link.get("cue_index")
                indexes = link.get("shot_indexes")
                if type(index) is not int or index < 0 or not isinstance(indexes, list) or not indexes or any(type(i) is not int or not 0 <= i < len(output_shots) for i in indexes):
                    raise CommentaryError("逐句配镜的字幕或镜头编号无效")
                result["segments"][-1]["sentence_links"].append({"cue_index": index,
                    "shot_indexes": list(dict.fromkeys(indexes)), "basis": text(link.get("basis"), "逐句配镜依据", 1000)})
        if "source_audio" in row:
            clips = row["source_audio"]
            if not isinstance(clips, list) or len(clips) > 100:
                raise CommentaryError("独立原声须为不超过100项的列表")
            sounds = []
            for clip in clips:
                item = evidence.confirmed(project, clip.get("evidence_id"))
                start = number(clip.get("start"), "原声起点", item["start"], item["end"])
                end = number(clip.get("end"), "原声终点", start + .01, item["end"])
                if result.get("editorial") and item["id"] not in event["evidence_ids"]:
                    raise CommentaryError("独立原声须属于段落关联事件的证据")
                sounds.append({"evidence_id": item["id"], "start": start, "end": end,
                    "offset": number(clip.get("offset", 0), "原声进入偏移", -2, 3600),
                    "gain_db": number(clip.get("gain_db", row.get("source_gain_db", 0)), "独立原声音量", -60, 0),
                    "fade_in": number(clip.get("fade_in", .02), "原声淡入", 0, min(2, (end-start)/2)),
                    "fade_out": number(clip.get("fade_out", .08), "原声淡出", 0, min(2, (end-start)/2))})
            result["segments"][-1]["source_audio"] = sounds
    music = payload.get("music")
    if music:
        if not isinstance(music, dict):
            raise CommentaryError("配乐格式错误")
        take = audio.read(project, music.get("audio_id"))
        if take["kind"] != "music":
            raise CommentaryError("配乐必须使用登记为音乐的音轨")
        result["music"] = {"audio_id": take["id"], "gain_db": number(music.get("gain_db", -18), "配乐增益", -60, 0),
                           "allow_source_music_mix": music.get("allow_source_music_mix") is True}
    return result


def save(identity, payload, *, projects_root, db_path=None):
    import json
    directory = project_dir(identity, projects_root)
    title = text(payload.get("title"), "项目标题", 120)
    normalized = normalize(directory, payload.get("payload"))
    with library.connect(db_path) as db:
        _tables(db)
        db.execute("BEGIN IMMEDIATE")
        current = _row(db.execute("SELECT * FROM commentary_drafts WHERE id=?", (identity,)).fetchone())
        if type(payload.get("revision")) is not int or payload["revision"] != current["revision"]:
            raise CommentaryConflict("草稿已更新，请重新打开后合并修改；未覆盖其他编辑")
        if title != current["title"] or normalized != current["payload"]:
            db.execute("UPDATE commentary_drafts SET title=?,payload=?,revision=revision+1,updated_at=? WHERE id=?",
                       (title, json.dumps(normalized, ensure_ascii=False), library.now(), identity))
    return read(identity, db_path=db_path)


def estimated_cues(narration, seconds, shape):
    # Split at punctuation/word boundaries; estimates are explicitly labelled in the manifest.
    limit = 16 if shape != "landscape" else 32
    tokens = re.findall(r"[A-Za-z0-9]+(?:[:：.'’_-][A-Za-z0-9]+)*(?:[%％])?|[^A-Za-z0-9]", narration)
    phrases, current = [], ""
    for token in tokens:
        if len(token) > limit * 2:
            raise CommentaryError("字幕中的连续英文或数字过长，请精简文案或提供逐句字幕")
        if len(current + token) > limit and current:
            phrases.append(current.strip()); current = ""
        current += token
        if token in "。！？!?；;\n" and current.strip():
            phrases.append(current.strip()); current = ""
    if current.strip(): phrases.append(current.strip())
    phrases = [p for p in phrases if p]
    total = sum(len(p) for p in phrases)
    cues, at = [], 0.0
    for phrase in phrases:
        end = at + seconds * len(phrase) / total
        cues.append({"start": round(at, 6), "end": round(end, 6), "text": phrase})
        at = end
    return cues


def compile_timeline(project, payload, *, db_path=None):
    plan = normalize(project, payload)
    if not plan["intent"] or not plan["structure"] or not plan["segments"]:
        raise CommentaryError("先根据已观察素材填写解说目标、叙事方案和段落，再提交预览")
    timeline, sources, warnings, cursor = [], {}, [], 0
    checked_evidence = {}
    for row in plan["segments"]:
        take = audio.read(project, row["audio_id"]) if row["audio_id"] else None
        if row["mode"] != "original" and not take:
            raise CommentaryError(f"段落 {row['id']} 缺少已登记配音，请先生成或导入")
        speech_cues = None
        if plan.get("editorial") and row["subtitle_mode"] == "aligned":
            aligned = alignment.read(project, row["alignment_id"], take["id"])
            first = max(0, math.floor((aligned["words"][0]["start"]-.06)*RATE))
            last = min(take["samples"], math.ceil((aligned["words"][-1]["end"]+.12)*RATE))
            take = {**take, "playback_start_sample": first, "playback_samples": last-first,
                    "samples": last-first, "duration": (last-first)/RATE}
            speech_cues = [{**c, "start": c["start"]-first/RATE, "end": c["end"]-first/RATE} for c in aligned["cues"]]
        required = math.ceil(take["samples"] / SAMPLES_PER_FRAME) if take else None
        shots, available = [], 0
        for shot in row["shots"]:
            item = checked_evidence.get(shot["evidence_id"])
            if item is None:
                item = evidence.confirmed(project, shot["evidence_id"], check_files=True, db_path=db_path)
                checked_evidence[item["id"]] = item
            frames = math.floor((shot["end"] - shot["start"]) * FPS + 1e-7)
            if required is not None:
                frames = min(frames, required - available)
            if frames <= 0: break
            review = item["review"]
            if row["mode"] != "narration" and not review["audio_reviewed"]:
                warnings.append(f"{row['id']}：原声与切口待人工回听")
            if review["source_subtitles"] != "none" and row["subtitle_mode"] != "none":
                if not row["source_subtitle_note"] or row["subtitle_position"] != "top":
                    raise CommentaryError(f"段落 {row['id']} 有原字幕或状态未知，请说明处理方式并将新字幕置顶，或重新取证裁切")
            if plan["music"] and row["mode"] != "narration" and review["source_music"] != "none" and not plan["music"]["allow_source_music_mix"]:
                raise CommentaryError("原声可能已有配乐，请确认混音策略后再添加新音乐")
            media_id = item["media_id"]
            if media_id not in sources:
                source_path = bridge.resolve_source(media_id, item["sha256"], db_path=db_path)
                info = probe(source_path)
                sources[media_id] = {"media_id": media_id, "path": str(source_path), "sha256": item["sha256"],
                    "origins": item["origins"], "has_audio": any(s.get("codec_type") == "audio" for s in info["streams"])}
            shots.append({**shot, "end": shot["start"] + frames / FPS, "frames": frames,
                          "media_id": media_id, "crop": item["crop"], "evidence_digest": digest(item)})
            available += frames
        if required is not None and available < required:
            raise MaterialGap(row["id"], required - available)
        if not available:
            raise CommentaryError("片段没有可用画面")
        duration = available / FPS
        cues = (speech_cues if speech_cues is not None else alignment.read(project, row["alignment_id"], take["id"])["cues"] if row["subtitle_mode"] == "aligned"
                else estimated_cues(row["text"], take["duration"], plan["format"]) if row["subtitle_mode"] == "estimated"
                else _cues(row["subtitles"], duration) if row["subtitle_mode"] == "timed" else [])
        if plan.get("editorial") and row["mode"] != "original":
            if row["subtitle_mode"] != "aligned":
                raise CommentaryError("精剪旁白须先导入实际语音时间戳，使用 aligned 字幕")
            links = row.get("sentence_links", [])
            if sorted(link["cue_index"] for link in links) != list(range(len(cues))):
                raise CommentaryError("每句旁白字幕须有且仅有一条配镜依据")
            boundaries, at = [], 0
            for shot in shots:
                boundaries.append((at/FPS, (at+shot["frames"])/FPS)); at += shot["frames"]
            for link in links:
                cue = cues[link["cue_index"]]
                if not any(i < len(boundaries) and min(cue["end"], boundaries[i][1]) > max(cue["start"], boundaries[i][0]) for i in link["shot_indexes"]):
                    raise CommentaryError("旁白句与关联镜头时间不相交，请重新配镜")
        if row["subtitle_mode"] == "estimated": warnings.append(f"{row['id']}：字幕按字数估时，待听辨校准")
        timeline.append({**row, "audio": take, "shots": shots, "frames": available,
                         "start_frame": cursor, "end_frame": cursor + available, "cues": cues})
        if "presenter" in row:
            width, height = FORMATS[plan["format"]]
            layer = {**row['presenter'],'x':.97-row['presenter']['diameter'],'y':.05} if 'presenter_layout' in row else row['presenter']
            timeline[-1]["presenter"] = presenter.freeze(project, layer, take,
                {"width": width, "height": height}, available)
        cursor += available
    for segment in timeline:
        if "source_audio" not in segment: continue
        sounds = []
        for clip in segment["source_audio"]:
            item = evidence.confirmed(project, clip["evidence_id"], check_files=True, db_path=db_path)
            checked_evidence[item["id"]] = item
            media_id = item["media_id"]
            if media_id not in sources:
                path = bridge.resolve_source(media_id, item["sha256"], db_path=db_path)
                sources[media_id] = {"media_id": media_id, "path": str(path), "sha256": item["sha256"],
                    "origins": item["origins"], "has_audio": any(s.get("codec_type") == "audio" for s in probe(path)["streams"])}
            if not sources[media_id]["has_audio"]:
                raise CommentaryError("独立原声来源没有音轨")
            stamp = segment["start_frame"] / FPS + clip["offset"]
            if stamp < 0 or stamp + clip["end"] - clip["start"] > cursor/FPS + .00001:
                raise CommentaryError("独立原声超出成片时间范围，请调整提前量或源终点")
            if clip["offset"] > segment["frames"]/FPS or clip["offset"] + clip["end"] - clip["start"] > segment["frames"]/FPS + 2:
                raise CommentaryError("独立原声最多延续到下一段2秒，请保持局部声画关系")
            review = item["review"]
            if not review["audio_reviewed"]: warnings.append(f"{segment['id']}：独立原声与切口待人工回听")
            if plan["music"] and review["source_music"] != "none" and not plan["music"]["allow_source_music_mix"]:
                raise CommentaryError("独立原声可能已有配乐，请确认混音策略")
            sounds.append({**clip, "media_id": media_id, "crop": item["crop"], "timeline_start": stamp,
                "evidence_digest": digest(item)})
        segment["source_audio"] = sounds
    if cursor > FPS * 3600:
        raise CommentaryError("本版单条解说最多一小时；长素材可分多个主题项目")
    report = editorial.audit(plan, {"segments": timeline, "duration": cursor / FPS})
    if report["enabled"]:
        if report["coverage"]["pending"]:
            raise CommentaryError("候选素材覆盖未完成，请查看或记录排除理由后提交")
        dispositions = {r["media_id"]: r["status"] for r in plan["editorial"]["coverage"]}
        if any(dispositions.get(mid) == "excluded" for mid in sources):
            raise CommentaryError("已排除的候选素材进入成片，请先更新采用观察与覆盖记录")
        for repeated in report["repeated_windows"]:
            if not repeated["reason"]:
                raise CommentaryError("存在重复镜头，请精剪或填写回调、对照等叙事理由")
        warnings.extend(f"{s['segment_id']}：长镜头 {s['seconds']} 秒，请核对保留价值" for s in report["long_shots"])
    music = {**plan["music"], "audio": audio.read(project, plan["music"]["audio_id"])} if plan["music"] else None
    frozen = {"version": VERSION, "format": plan["format"], "profile": {"width": FORMATS[plan['format']][0],
            "height": FORMATS[plan['format']][1], "fps": FPS, "audio_rate": RATE}, "target_lufs": plan["target_lufs"],
            "font": subtitle_font(), "content_kind": plan["content_kind"], "intent": plan["intent"], "structure": plan["structure"],
            "sources": sources, "segments": timeline, "evidence": checked_evidence, "music": music,
            "frames": cursor, "duration": cursor / FPS, "warnings": list(dict.fromkeys(warnings))}
    if plan.get("editorial"):
        frozen.update(editorial=plan["editorial"], editorial_report=report)
    if "subtitle_style" in plan:
        frozen["subtitle_style"] = plan["subtitle_style"]
    for segment in timeline:
        if "presenter_layout" in segment:
            segment["layout_plan"] = layout.compile_layout(project, segment, frozen["profile"], frozen["font"]["path"], plan.get("subtitle_style"))
            frozen["warnings"].extend(f"{segment['id']}：{message}" for row in segment["layout_plan"]["shots"] for message in row["warnings"])
        if segment["cues"] and ("subtitle_style" in plan or "presenter" in segment or "subtitle_layout" in segment):
            captions.validate_layout(segment, frozen["profile"], frozen["font"]["path"], plan.get("subtitle_style"))
    return frozen


def preflight(identity, revision, *, projects_root, db_path=None):
    draft = read(identity, db_path=db_path)
    if type(revision) is not int or revision != draft["revision"]:
        raise CommentaryConflict("草稿版本已变化，请重新保存并预检")
    try:
        timeline = compile_timeline(project_dir(identity, projects_root), draft["payload"], db_path=db_path)
        for media_id in timeline["sources"]:
            bridge.ensure_available(media_id, db_path=db_path)
        return {"status": "ready", "revision": revision, "duration": timeline["duration"],
                "frames": timeline["frames"], "warnings": timeline["warnings"], "segment_count": len(timeline["segments"]),
                "editorial": timeline.get("editorial_report"),
                "layouts": [{"segment_id":s["id"],**s["layout_plan"]} for s in timeline["segments"] if "layout_plan" in s]}
    except MaterialGap as exc:
        return exc.detail


def version_dir(identity, signature, *, projects_root):
    identifier(signature, "")
    if not re.fullmatch(r"[a-f0-9]{64}", signature): raise CommentaryError("版本签名无效")
    return project_dir(identity, projects_root) / "artifacts/commentary/versions" / signature[:24]


def prepare(identity, revision, *, projects_root, db_path=None):
    draft = read(identity, db_path=db_path)
    if type(revision) is not int or revision != draft["revision"]:
        raise CommentaryConflict("草稿版本已变化，请重新保存并提交")
    # Re-submission of an already frozen revision recovers its exact identity,
    # including when the source was archived or moved since the first submit.
    with library.connect(db_path) as db:
        _tables(db)
        old = db.execute("SELECT signature FROM commentary_versions WHERE project_id=? AND revision=?",
                         (identity, revision)).fetchone()
    if old:
        frozen = read_json(version_dir(identity, old["signature"], projects_root=projects_root) / "request.json")
        bridge.record_usages(identity, old["signature"], frozen, db_path=db_path)
        return {"signature": old["signature"], "revision": revision}
    project = project_dir(identity, projects_root)
    frozen = {**compile_timeline(project, draft["payload"], db_path=db_path),
              "project_id": identity, "revision": revision, "title": draft["title"]}
    frozen = bridge.bind_references(identity, frozen, project_dir=project, db_path=db_path)
    signature = digest(frozen)
    directory = version_dir(identity, signature, projects_root=projects_root)
    immutable(directory / "request.json", frozen)
    bridge.record_usages(identity, signature, frozen, db_path=db_path)
    with library.connect(db_path) as db:
        _tables(db)
        db.execute("INSERT OR IGNORE INTO commentary_versions VALUES(?,?,?,?)", (identity, signature, revision, library.now()))
    return {"signature": signature, "revision": revision}


def submit(identity, revision, queue, *, projects_root, db_path=None):
    frozen = prepare(identity, revision, projects_root=projects_root, db_path=db_path)
    return queue.submit(project_id=identity, kind="material_commentary", source="workbench", priority="normal",
        parent_job_id=frozen["signature"], frozen_request=frozen, revive=True,
        idempotency_key=f"material_commentary:{identity}:{frozen['signature']}")


def versions(identity, *, projects_root, db_path=None):
    read(identity, db_path=db_path)
    with library.connect(db_path) as db:
        _tables(db)
        rows = db.execute("SELECT * FROM commentary_versions WHERE project_id=? ORDER BY revision DESC", (identity,)).fetchall()
    return [{**dict(row), **(read_json(path) if path.is_file() else {"status": "queued"})}
            for row in rows for path in [version_dir(identity, row["signature"], projects_root=projects_root) / "result.json"]]


def output_path(identity, signature, *, projects_root, db_path=None, artifact="preview.mp4"):
    if artifact not in {"preview.mp4", "subtitles.srt"}: raise CommentaryError("交付文件不存在")
    matches = [v for v in versions(identity, projects_root=projects_root, db_path=db_path) if v["signature"] == signature]
    if not matches or matches[0]["status"] != "completed":
        raise CommentaryError("该版本尚未通过技术检查")
    path = version_dir(identity, signature, projects_root=projects_root) / artifact
    return verified(path, matches[0]["files"][artifact])


def brief(identity, *, projects_root, db_path=None):
    draft = read(identity, db_path=db_path)
    project = project_dir(identity, projects_root)
    observations = evidence.list_evidence(project)
    return {"draft": draft, "observations": observations, "audio": audio.list_audio(project),
            "presenters": presenter.list_presenters(project),
            "protections": layout.list_protections(project),
            "alignments": alignment.list_alignments(project),
            "director_instruction": "先读素材观察、前后文和未知项，再写 intent/structure 和自由数量段落。每镜引用证据。"
                "电影保留人物、时序与因果；直播保留问题和回答上下文。可倒叙、并列、解释、原声主导，"
                "但必须在 basis 说明理由。不要求固定开场/结尾，不编造看不到的情节或台词。"
                "按实际配音时长配镜；长素材先概览/转写定位，再对采用窗口取证。"}
