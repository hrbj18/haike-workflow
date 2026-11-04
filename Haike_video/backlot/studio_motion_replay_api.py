"""Capability listing and read-only preparation, without submitting production."""
from fastapi import APIRouter, Body, HTTPException, Request
from backlot import motion_replay

router = APIRouter()


@router.get('/api/studio/motion-replay')
def catalog():
    try:
        return {'schema': 'haike.motion-replay-catalog/1',
                'templates': motion_replay.catalog(), 'sources_verified': False}
    except (ValueError, OSError):
        raise HTTPException(409, '动效复刻合同需要修复；原模板与样片仍保留') from None


@router.post('/api/studio/motion-replay/prepare')
def prepare(request: Request, body: dict = Body(...)):
    from backlot.studio_api import mutation
    mutation(request)
    if set(body) - {'template_id', 'version', 'request'}:
        raise HTTPException(422, '复刻请求包含未开放字段')
    try:
        return motion_replay.prepare(body.get('template_id'), body.get('version'), body.get('request'))
    except motion_replay.ReplayError as exc:
        raise HTTPException(409, str(exc)) from None
    except (ValueError, OSError, ImportError):
        raise HTTPException(409, '此模板或输入尚未满足复刻条件，请核对精确版本、来源与开放槽位') from None
