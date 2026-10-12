"""Small, isolated FastAPI surface for the published clip index."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from backlot.published_clip_index import (
    ClipIndexError, configured_source, get_video, list_videos, media_path,
    save_description, save_event, search, summary,
)
from backlot import published_clip_analysis as analysis


router = APIRouter()
UI_DIR = Path(__file__).resolve().parent / "ui"


def _invalid(exc: ClipIndexError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/published-clips", response_class=HTMLResponse)
def page() -> HTMLResponse:
    return HTMLResponse((UI_DIR / "published_clips.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-cache"})


@router.get("/api/published-clips/status")
def status() -> dict:
    return summary()


@router.get("/api/published-clips/videos")
def videos() -> list[dict]:
    return list_videos()


@router.get("/api/published-clips/search")
def find(query: str = "", tag: str = "", confirmed_only: bool = False,
         actor: str = "", reaction: str = "", review_status: str = "",
         limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    try:
        return search(query, tag=tag, confirmed_only=confirmed_only, limit=limit,
                      actor=actor, reaction=reaction, review_status=review_status)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.get("/api/published-clips/videos/{video_id}")
def video_detail(video_id: str) -> dict:
    try:
        return get_video(video_id)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.patch("/api/published-clips/videos/{video_id}")
def edit_video(video_id: str, payload: dict = Body(...)) -> dict:
    try:
        if "description" not in payload:
            raise ClipIndexError("缺少视频摘要")
        return save_description(video_id, payload["description"])
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.get("/api/published-clips/videos/{video_id}/media")
def video_media(video_id: str) -> FileResponse:
    root = configured_source()
    if root is None:
        raise HTTPException(status_code=404, detail="成片目录尚未配置")
    try:
        path = media_path(video_id, source_root=root)
    except ClipIndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="video/mp4" if path.suffix.lower() == ".mp4" else None)


@router.post("/api/published-clips/videos/{video_id}/events")
def add_event(video_id: str, payload: dict = Body(...)) -> dict:
    try:
        return save_event(video_id, payload)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.patch("/api/published-clips/videos/{video_id}/events/{event_id}")
def edit_event(video_id: str, event_id: int, payload: dict = Body(...)) -> dict:
    try:
        return save_event(video_id, payload, event_id=event_id)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.get("/api/published-clips/videos/{video_id}/analysis")
def get_analysis(video_id: str) -> dict:
    try:
        return analysis.analysis_status(video_id)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc


@router.post("/api/published-clips/videos/{video_id}/analysis")
def run_analysis(video_id: str) -> dict:
    root = configured_source()
    if root is None:
        raise HTTPException(422, "请先配置成片目录")
    try:
        result = analysis.analyze(video_id, source_root=root)
        # The timeline has a separate GET endpoint; keep submission response small.
        return {"status": result["status"], "cached": result["cached"]}
    except (ValueError, OSError, RuntimeError) as exc:
        raise HTTPException(422, f"分析未完成：{exc}") from exc


@router.get("/api/published-clips/benchmark")
def benchmark() -> dict:
    cases = analysis.benchmark_cases()
    return {"cases": cases, "evaluation": analysis.evaluate(cases)}


@router.patch("/api/published-clips/benchmark/{video_id}")
def edit_truth(video_id: str, payload: dict = Body(...)) -> dict:
    try:
        return analysis.save_truth(video_id, payload)
    except ClipIndexError as exc:
        raise _invalid(exc) from exc
