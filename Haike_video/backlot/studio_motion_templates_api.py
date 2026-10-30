"""HTTP facade for the same MotionGit sessions exposed by motion_templates.py."""
from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from backlot import studio_motion_templates as model
from backlot.studio_dark_full_script import operation_lock
from backlot.work_api import call
from backlot.work_catalog import WorkError

router = APIRouter(prefix='/api/studio/motion-templates')
_ACTIVE_PREPARATIONS = set()


def store(request):
    if not hasattr(request.app.state, 'motion_template_sessions'):
        from backlot.studio_api import studio
        request.app.state.motion_template_sessions = model.Sessions(studio(request).projects_root)
    return request.app.state.motion_template_sessions


def queue(request):
    from backlot.server import _ensure_production_queue
    return _ensure_production_queue(request.app)


def mutation(request, raw=False):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'): raise HTTPException(403, '请从本机工作台提交')
    if ('application/octet-stream' if raw else 'application/json') not in request.headers.get('content-type', ''):
        raise HTTPException(415, '请求格式不支持')


def public(request, value):
    s = store(request)
    if value.get('operation', {}).get('status') == 'running' and value['id'] not in _ACTIVE_PREPARATIONS:
        current = s.get(value['id'])
        if current['revision'] != value['revision']: value = current
    result = call(s.public, value, queue(request))
    if result['operation'].get('status') == 'running' and value['id'] not in _ACTIVE_PREPARATIONS:
        result['operation'].update(status='interrupted', message='本地准备进程已中断，原输入与产物保留，可恢复本地准备。')
    return result


def start_operation(s, q, identity, revision, kind, function, payload=None):
    """A durable local preparation, never an alternative full-video queue."""
    with operation_lock(s.folder(identity)/'lock'):
        value = s.get(identity)
        model.require(value['revision'] == revision, '内容已更新，请重新读取', 'conflict')
        previous = value.get('operation', {})
        model.require(identity not in _ACTIVE_PREPARATIONS, '此版本正在准备，请等待原操作', 'conflict')
        value['operation'] = {'kind': kind, 'status': 'running', 'message': '正在本地准备，关闭页面后仍保留进度。', 'payload': payload or {}}
        value = s.put(value, revision)
        _ACTIVE_PREPARATIONS.add(identity)
    def execute():
        try:
            function(value['revision'])
            with operation_lock(s.folder(identity)/'lock'):
                current = s.get(identity)
                current['operation'] = {'kind': kind, 'status': 'completed', 'message': '本地准备完成，请检查本期画面。'}
                s.put(current, current['revision'])
        except Exception as exc:
            with operation_lock(s.folder(identity)/'lock'):
                current = s.get(identity)
                message = str(exc) if isinstance(exc, (WorkError, ValueError)) else '本地准备中断；原输入和已生成产物保留，请检查依赖或恢复原操作。'
                current['operation'] = {'kind': kind, 'status': 'failed', 'message': message, 'payload': payload or {}}
                s.put(current, current['revision'])
            from backlot.studio import atomic_private
            atomic_private(s.folder(identity)/'local-operation-error.json', {'type': type(exc).__name__, 'message': str(exc)[:1600]})
        finally:
            _ACTIVE_PREPARATIONS.discard(identity)
    threading.Thread(target=execute, daemon=True, name='motion-template-'+identity).start()
    return value


def dispatch(q, identity):
    from backlot.production_queue_worker import ProductionQueueWorker
    job = q.get(identity)
    if job['status'] not in {'paused', 'failed'} or job['status'] == 'failed' and not job.get('retryable'): return
    def execute():
        try: ProductionQueueWorker(q, q.projects_root, worker_id='motion-template-'+uuid4().hex[:8], lease_seconds=7200).run_local_recompose(identity)
        except Exception: pass  # Exclusive claimant records actual job state; keep the same ID for resume.
    threading.Thread(target=execute, daemon=True).start()


@router.get('/catalog')
def catalog(request: Request):
    return {'templates': call(model.catalog), 'presets': call(store(request).presets),
            'session_endpoint': '/api/studio/motion-templates/sessions',
            'agent_guide': 'Haike_video/docs/MOTION_TEMPLATE_STUDIO.md'}


@router.post('/onboarding/{package_id}')
def onboarding(package_id: str, request: Request, data: dict = Body(...)):
    mutation(request); return call(store(request).onboarding, package_id)


@router.get('/sessions')
def sessions(request: Request): return {'sessions': call(store(request).list, queue(request))}


@router.post('/sessions')
def create(request: Request, data: dict = Body(...)):
    mutation(request)
    if set(data)-{'template_id', 'script', 'preset_id', 'source_session_id'}: raise HTTPException(422, '创建参数包含未开放字段')
    return public(request, call(store(request).create, data.get('template_id'), initial_script=data.get('script'),
                               preset_id=data.get('preset_id'), source_session_id=data.get('source_session_id'),
                               queue=queue(request) if data.get('source_session_id') is not None else None))


@router.get('/sessions/{identity}')
def session(identity: str, request: Request): return public(request, call(store(request).get, identity))


@router.post('/sessions/{identity}')
def save(identity: str, request: Request, data: dict = Body(...)):
    mutation(request)
    if set(data) != {'revision', 'patch'}: raise HTTPException(422, '请提交版本和修改内容')
    return public(request, call(store(request).patch, identity, data['revision'], data['patch']))


@router.post('/sessions/{identity}/clone')
def clone(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); return public(request, call(store(request).clone, identity, data.get('revision')))


@router.post('/sessions/{identity}/preset')
def preset(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); return call(store(request).save_preset, identity, data.get('revision'), data.get('name'))


@router.post('/sessions/{identity}/assets')
async def upload(identity: str, request: Request, revision: int, slot: str, filename: str, kind: str):
    mutation(request, True); content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 80*1024*1024: raise HTTPException(413, '单个上传文件最多80MB')
    return public(request, await asyncio.to_thread(call, store(request).upload, identity, revision, slot, filename, kind, bytes(content)))


@router.get('/sessions/{identity}/source/{slot}')
def source(identity: str, slot: str, revision: int, request: Request):
    return FileResponse(call(store(request).media_preview, identity, slot, revision), media_type='image/jpeg')


@router.post('/sessions/{identity}/source-quote')
async def source_quote(identity: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return public(request, await asyncio.to_thread(call, store(request).quote_source, identity, data.get('revision')))


@router.post('/sessions/{identity}/source-submit')
def source_submit(identity: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return public(request, call(store(request).submit_source, identity, data.get('revision'), queue(request), data.get('max_charge_micros'), data.get('confirmed')))


@router.post('/sessions/{identity}/source-resume')
def source_resume(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); value = call(s.get, identity)
    call(model.require, value['revision'] == data.get('revision'), '内容已更新', 'conflict')
    g = value.get('generation', {}); call(model.require, g.get('job_id'), '没有原口播人物任务')
    q = queue(request); job = q.get(g['job_id'])
    if job['status'] == 'failed':
        call(q.retry if job.get('retryable') else q.recover_studio_avatar_download, job['job_id'])
    elif job['status'] == 'paused': call(q.resume, job['job_id'])
    return public(request, value)


@router.post('/sessions/{identity}/source-frames')
def source_frames(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); q = queue(request)
    value = call(start_operation, s, q, identity, data.get('revision'), 'source-frames', lambda rev: s.prepare_source_review(identity, rev, q))
    return public(request, value)


@router.get('/sessions/{identity}/review')
def review(identity: str, request: Request):
    value = call(store(request).get, identity); s = value.get('source_frames', {}); p = value.get('plan', {})
    return {'source': {'token': s.get('token'), 'images': [{'id': i, 'label': r['label'], 'at': r['at'],
             'url': f'/api/studio/motion-templates/sessions/{identity}/review/source/{i}'} for i, r in enumerate(s.get('rows', []))]},
            'plan': {'token': p.get('token'), 'summary': p.get('summary'), 'images': [{'id': i, 'url': f'/api/studio/motion-templates/sessions/{identity}/review/plan/{i}'} for i in range(len(p.get('images', [])))]}}


@router.get('/sessions/{identity}/review/{kind}/{index}')
def review_image(identity: str, kind: str, index: int, request: Request):
    value = call(store(request).get, identity)
    rows = [r['image'] for r in value.get('source_frames', {}).get('rows', [])] if kind == 'source' else value.get('plan', {}).get('images', []) if kind == 'plan' else []
    if not 0 <= index < len(rows): raise HTTPException(404, '本期预览不存在')
    return FileResponse(call(model.verified, rows[index]), headers={'Cache-Control': 'no-cache'})


@router.post('/sessions/{identity}/source-review')
def source_review(identity: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return public(request, call(store(request).review_sources, identity, data.get('revision'), data.get('token'), data.get('seen'), data.get('description')))


@router.post('/sessions/{identity}/prepare')
def prepare(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); q = queue(request)
    return public(request, call(start_operation, s, q, identity, data.get('revision'), 'prepare', lambda rev: s.prepare(identity, q)))


@router.post('/sessions/{identity}/plan-review')
def plan_review(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); q = queue(request)
    return public(request, call(start_operation, s, q, identity, data.get('revision'), 'native-preview',
                    lambda rev: s.approve_plan(identity, rev, data.get('token'), data.get('seen'), q), {'token': data.get('token'), 'seen': data.get('seen')}))


@router.post('/sessions/{identity}/local-resume')
def local_resume(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); q = queue(request); value = call(s.get, identity)
    op = value.get('operation', {}); payload = op.get('payload', {})
    actions = {'source-frames': lambda rev: s.prepare_source_review(identity, rev, q),
               'prepare': lambda rev: s.prepare(identity, q),
               'native-preview': lambda rev: s.approve_plan(identity, rev, payload.get('token'), payload.get('seen'), q)}
    call(model.require, op.get('kind') in actions and op.get('status') in {'failed', 'running'}, '没有可恢复的本地准备')
    return public(request, call(start_operation, s, q, identity, data.get('revision'), op['kind'], actions[op['kind']], payload))


@router.get('/sessions/{identity}/preview/{index}')
def preview_image(identity: str, index: int, request: Request):
    value = call(store(request).get, identity); rows = value.get('preview_files', [])
    if not 0 <= index < len(rows): raise HTTPException(404, '预览不存在')
    return FileResponse(call(model.verified, rows[index]), headers={'Cache-Control': 'no-cache'})


@router.post('/sessions/{identity}/preview-review')
async def preview_review(identity: str, request: Request, data: dict = Body(...)):
    mutation(request)
    return public(request, await asyncio.to_thread(call, store(request).approve_preview, identity, data.get('revision'), data.get('token'), data.get('seen'), queue(request)))


@router.post('/sessions/{identity}/submit')
def submit(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); q = queue(request)
    value = call(store(request).submit, identity, data.get('revision'), q)
    dispatch(q, value['run']['job_id']); return public(request, value)


@router.post('/sessions/{identity}/resume')
def resume(identity: str, request: Request, data: dict = Body(...)):
    mutation(request); s = store(request); value = call(s.get, identity)
    call(model.require, value['revision'] == data.get('revision'), '内容已更新', 'conflict')
    call(model.require, value.get('run', {}).get('job_id'), '没有原制作任务')
    dispatch(queue(request), value['run']['job_id']); return public(request, value)


@router.get('/sessions/{identity}/video')
def video(identity: str, request: Request):
    return FileResponse(call(store(request).video, identity, queue(request)), media_type='video/mp4', headers={'Cache-Control': 'no-cache'})
