"""Same-origin task visibility and Agent tool calls within /avatar."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Body, Request, HTTPException
from fastapi.responses import FileResponse

from backlot.avatar_one_stop import OneStop
from backlot.work_api import call

router = APIRouter(prefix='/api/studio/one-stop')
log = logging.getLogger(__name__)


def flow(request):
    from backlot.studio_api import studio
    factory = getattr(request.app.state, 'one_stop_factory', OneStop)
    return factory(studio(request))


def launch(request, service, identity):
    # The server executes project tools; semantic and visual decisions are
    # returned to the current dialogue Agent, never to an unconfigured LLM.
    workers = getattr(request.app.state, 'one_stop_workers', None)
    if workers is None:
        workers = request.app.state.one_stop_workers = {}
    key = (service.scope, identity)
    if key in workers and not workers[key].done():
        return
    async def work():
        while True:
            result = await asyncio.to_thread(service.advance, identity)
            if result['status'] != 'waiting':
                return
            await asyncio.sleep(3)
    task = workers[key] = asyncio.create_task(work())
    def finished(done):
        if workers.get(key) is done:
            workers.pop(key, None)
        if not done.cancelled() and done.exception():
            # Persisted stage state is authoritative. Never log exception text:
            # supplier errors may contain signed URLs or private account data.
            log.warning('一条龙执行器中止；保留原任务：%s', type(done.exception()).__name__)
    task.add_done_callback(finished)


@router.get('/defaults')
def defaults(request: Request):
    return call(call(flow, request).defaults)


@router.get('/jobs')
def jobs(request: Request, draft_id: str | None = None):
    return {'items': call(call(flow, request).list, draft_id)}


@router.post('/jobs')
async def create(request: Request, data: dict = Body(...)):
    from backlot.studio_api import mutation
    mutation(request)
    service = call(flow, request)
    result = await asyncio.to_thread(call, service.create, data)
    launch(request, service, result['id'])
    return result


@router.get('/jobs/{identity}')
def get(identity: str, request: Request):
    return call(call(flow, request).get, identity)


@router.post('/jobs/{identity}/revise')
async def revise(identity: str, request: Request, data: dict = Body(...)):
    from backlot.studio_api import mutation
    mutation(request)
    service = call(flow, request)
    result = await asyncio.to_thread(call, service.revise, identity, data)
    launch(request, service, result['id'])
    return result


@router.get('/jobs/{identity}/context')
def context(identity: str, request: Request):
    return call(call(flow, request).context, identity)


@router.post('/jobs/{identity}/advance')
async def advance(identity: str, request: Request, data: dict = Body(...)):
    from backlot.studio_api import mutation
    mutation(request)
    if data:
        raise HTTPException(422, '恢复原任务无需更换参数')
    service = call(flow, request)
    result = call(service.get, identity)
    launch(request, service, identity)
    return result


@router.post('/jobs/{identity}/apply')
async def apply(identity: str, request: Request, data: dict = Body(...)):
    from backlot.studio_api import mutation
    mutation(request)
    service = call(flow, request)
    result = await asyncio.to_thread(call, service.apply, identity, data)
    launch(request, service, identity)
    return result


@router.get('/jobs/{identity}/files/{kind}')
def file(identity: str, kind: str, request: Request):
    path = call(call(flow, request).file, identity, kind)
    return FileResponse(path, headers={'Cache-Control': 'private, no-store'})
