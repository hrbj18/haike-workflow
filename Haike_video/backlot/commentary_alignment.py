"""Immutable captions bound to real audio and supplied speech timestamps."""
import re
from pathlib import Path
from backlot import commentary_audio as audio
from backlot.commentary_common import CommentaryError, digest, immutable, read_json, identifier, number, text


def spoken(value):
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def directory(project, identity):
    identifier(identity, "AL-")
    return Path(project) / "assets/audio/commentary-alignments" / identity[:27]


def read(project, identity, audio_id):
    result = read_json(directory(project, identity) / "alignment.json")
    take = audio.read(project, audio_id)
    if result["id"] != identity or result["audio_id"] != audio_id or result["audio_sha256"] != take["sha256"]:
        raise CommentaryError("字幕对齐与配音身份不符")
    if "AL-" + digest({k:v for k,v in result.items() if k != "id"}) != identity:
        raise CommentaryError("字幕对齐记录已变化")
    return result


def list_alignments(project):
    return [read(project, r["id"], r["audio_id"]) for path in sorted(
        (Path(project)/"assets/audio/commentary-alignments").glob("AL-*/alignment.json"))
        for r in [read_json(path)]]


def import_alignment(project, payload):
    take = audio.read(project, payload.get("audio_id"))
    raw = payload.get("words")
    provenance = payload.get("provenance")
    if raw is None and payload.get("tencent_metadata_path"):
        metadata = read_json(Path(payload["tencent_metadata_path"]))
        if metadata.get("provider") != "tencent":
            raise CommentaryError("请选择腾讯配音对应的时间戳文件")
        raw = [{"text": r["Text"], "start": r["BeginTime"] / 1000, "end": r["EndTime"] / 1000}
               for r in metadata.get("subtitles", []) if spoken(r.get("Text", ""))]
        provenance = "腾讯TTS返回的逐字时间戳；元数据SHA：" + digest(metadata)
    if not isinstance(raw, list) or not 1 <= len(raw) <= 10000:
        raise CommentaryError("语音时间戳须为非空逐字/逐词列表")
    words, previous = [], 0
    for row in raw:
        value = text(row.get("text"), "语音单元", 120)
        start = number(row.get("start"), "语音起点", previous, take["duration"])
        end = number(row.get("end"), "语音终点", start, take["duration"])
        if spoken(value):
            if end <= start: raise CommentaryError("语音单元缺少有效时长")
            words.append({"text": value, "start": start, "end": end})
        previous = end
    if spoken("".join(w["text"] for w in words)) != spoken(take["text"]):
        raise CommentaryError("语音时间戳文字与当前解说不一致，不得按字数伪造对齐")
    # Attach canonical punctuation to each word, without changing speech timing.
    cursor, cues, current, canonical_words = 0, [], None, []
    for word in words:
        count = len(spoken(word["text"]))
        start_cursor = cursor
        for _ in range(count):
            while cursor < len(take["text"]) and not spoken(take["text"][cursor]): cursor += 1
            cursor += 1
        while cursor < len(take["text"]) and not spoken(take["text"][cursor]): cursor += 1
        caption = take["text"][start_cursor:cursor].strip()
        canonical_words.append({**word, "text": caption})
        if len(caption) > 32: raise CommentaryError("语音单元过长，请导入更细的逐字或逐词时间戳")
        if current and (word["start"] - current["end"] > .28 or len(current["text"] + caption) > 16):
            cues.append(current); current = None
        if current:
            current["text"] += caption; current["end"] = word["end"]
        else: current = {"start": word["start"], "end": word["end"], "text": caption}
        if caption.endswith(tuple("。！？!?；;，,")):
            cues.append(current); current = None
    if current: cues.append(current)
    ends = payload.get("cue_word_ends")
    if ends is not None:
        if not isinstance(ends, list) or not ends or any(type(i) is not int for i in ends) or ends != sorted(set(ends)) or ends[0] <= 0 or ends[-1] != len(words):
            raise CommentaryError("字幕分组须为递增的语音单元终点，并覆盖所有实际语音单元")
        cues, first = [], 0
        for last in ends:
            group = canonical_words[first:last]
            cues.append({"start": group[0]["start"], "end": group[-1]["end"], "text": "".join(w["text"] for w in group)})
            first = last
    record = {"audio_id": take["id"], "audio_sha256": take["sha256"], "text": take["text"],
        "method": "speech_timestamps", "provenance": text(provenance, "对齐来源", 2000),
        "words": words, "cues": cues}
    if ends is not None:
        record["cue_word_ends"] = ends
    identity = "AL-" + digest(record)
    immutable(directory(project, identity) / "alignment.json", {"id": identity, **record})
    return read(project, identity, take["id"])
