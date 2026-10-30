"""Local UI endpoints. Uploaded package bytes stay private; import never executes."""
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from backlot import studio_motiongit as motion
from backlot.work_api import call
from backlot.work_catalog import read_json, sha, WorkError

router = APIRouter(prefix='/api/studio/motiongit')


@router.get('/art-directions')
def art_directions():
    from backlot.studio_art_direction import catalog
    return call(catalog)


@router.get('/art-directions/{theme_slug}/image')
def art_direction_image(theme_slug: str):
    from backlot.studio_art_direction import theme_asset
    return FileResponse(call(theme_asset, theme_slug, 'jpg'), media_type='image/jpeg')


@router.get('/art-directions/{theme_slug}/reference')
def art_direction_reference(theme_slug: str):
    from backlot.studio_art_direction import theme_asset
    return FileResponse(call(theme_asset, theme_slug, 'md'), media_type='text/plain; charset=utf-8')


@router.get('/art-directions/{theme_slug}/video-brief')
def art_direction_brief(theme_slug: str):
    from backlot.studio_art_direction import video_brief
    return call(video_brief, theme_slug)


def mutation(request):
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, '请从本机海客工作台提交')


async def bounded_body(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > motion.MAX_PACKAGE: raise HTTPException(413, '文件超过386MiB')
        chunks.append(chunk)
    return b''.join(chunks)


@router.get('/packages')
def packages():
    return call(motion.packages)


@router.post('/packages')
async def upload(request: Request, filename: str = 'template.motion'):
    mutation(request)
    if Path(filename).suffix.lower() != '.motion': raise HTTPException(400, '请选择.motion原包')
    content = await bounded_body(request)
    folder = motion.STORE / 'incoming'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid4().hex + '.motion')
    with path.open('xb') as output: output.write(content)
    try:
        return await asyncio.to_thread(call, motion.import_package, path, filename=filename)
    finally:
        path.unlink(missing_ok=True)


@router.post('/packages/{package_id}/verify')
async def verify(package_id: str, request: Request):
    mutation(request)
    return await asyncio.to_thread(call, motion.verify_package, package_id)


@router.get('/drafts')
def drafts():
    return call(motion.draft_list)


@router.get('/drafts/{draft_id}')
def draft(draft_id: str):
    return call(motion.draft, draft_id)


@router.post('/drafts/{draft_id}/clone')
def clone(draft_id: str,request: Request):
    mutation(request)
    return call(motion.clone_draft,draft_id)


@router.post('/drafts')
def save(request: Request, data: dict = Body(...)):
    mutation(request)
    return call(motion.save_draft, data.get('package_id'), data.get('workflow'), data.get('parameters'),
                draft_id=data.get('id'), revision=data.get('revision', 0), title=data.get('title', '新视频'),
                output_profile=data.get('output_profile','native'),art_direction=data.get('art_direction'))


@router.post('/drafts/{draft_id}/check')
def check(draft_id: str, request: Request):
    mutation(request)
    return call(motion.validate_draft, draft_id)


@router.post('/drafts/{draft_id}/assets')
async def asset(draft_id: str, request: Request, filename: str):
    mutation(request)
    content = await bounded_body(request)
    return await asyncio.to_thread(call, motion.save_asset, draft_id, filename, content)


@router.get('/drafts/{draft_id}/assets')
def assets(draft_id: str):
    return call(motion.asset_list, draft_id)


def _queue(request):
    from backlot.server import _ensure_production_queue
    return _ensure_production_queue(request.app)


@router.post('/drafts/{draft_id}/produce')
def produce(draft_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    from backlot import studio_motiongit_render as render
    queue = _queue(request)
    value = call(motion.draft,draft_id)
    if data.get('revision') != value['revision']: raise HTTPException(409,'草稿已更新，请重新读取')
    phase=data.get('phase','preview')
    try:
        frozen = render.recorded_request(queue,draft_id,data['render_id']) if data.get('render_id') else render.freeze(queue,draft_id)
    except WorkError as exc:
        if phase=='preview' and data.get('render_id'): frozen=call(render.freeze,queue,draft_id)
        else: raise HTTPException(422,str(exc)) from exc
    job=call(render.submit,queue,frozen,phase=phase)
    # Jobs remain durable when the page closes; failures keep the original job.
    if job['status'] != 'completed':
        import threading
        from backlot.production_queue_worker import ProductionQueueWorker
        def execute():
            try: ProductionQueueWorker(queue,queue.projects_root,worker_id='motiongit-ui-'+uuid4().hex[:8],lease_seconds=7200).run_local_recompose(job['job_id'])
            except Exception:
                # A busy global lane leaves the paused job available for explicit resume.
                return
        threading.Thread(target=execute,daemon=True).start()
    return {'job':job,'project_id':frozen['project_id'],'render_id':frozen['render_id']}


@router.get('/jobs/{job_id}')
def job(job_id: str, request: Request):
    queue=_queue(request)
    return call(queue.get,job_id)


@router.get('/drafts/{draft_id}/productions')
def productions(draft_id: str,request: Request):
    from backlot import studio_motiongit_render as render
    queue=_queue(request)
    result=[]
    for entry in call(motion.productions,draft_id)['productions']:
        try: frozen=render.recorded_request(queue,draft_id,entry['render_id'])
        except WorkError: continue
        prefix=entry['contract']+':'+entry['request_sha256']
        job=queue.find_by_idempotency_key(prefix+':render') or queue.find_by_idempotency_key(prefix+':preview')
        if entry['contract'] in {'motiongit-narrated-pilot-v1','hum-production-v1'}: job=queue.find_by_idempotency_key(prefix)
        result.append({**entry,'job':job})
    return {'productions':result}


@router.get('/productions/{project_id}/{render_id}')
def production(project_id: str, render_id: str, request: Request):
    import re
    if not re.fullmatch(r'studio-[0-9a-f]{16}',project_id) or not re.fullmatch(r'(motiongit-(component|narrated-pilot)|hum-production-v1)-[0-9a-f]{20}',render_id):
        raise HTTPException(404,'工程不存在')
    folder=_queue(request).projects_root/project_id/'renders'/render_id
    state=read_json(folder/'native-state.json')
    root=f'{base_path()}/productions/{project_id}/{render_id}/media/'
    review=read_json(folder/'visual-review.json')
    preview_receipt=Path(state.get('preview_receipt') or Path(state['preview_directory'])/'preview-review.json') if state.get('preview_directory') else None
    preview_sha=sha(preview_receipt) if preview_receipt and preview_receipt.is_file() else None
    plan=Path(state['plan_directory']) if state.get('workflow')=='motion-kit' and state.get('plan_directory') else None
    plan_details={'report_url':root+'component-plan.json','report_sha256':sha(plan/'report.json'),
                  'inputs_sha256':sha(plan/'inputs.json'),'reviewed':bool(read_json(folder/'plan-semantic-review.json'))} if plan else None
    return {'images':[{'name':name,'url':root+name} for name in state.get('images',[])],
            'plan':plan_details,
            'preview_sha256':preview_sha,'reviewed':bool(review and review.get('reviewed_preview_sha256')==preview_sha),
            'nomusic':root+'hum-production-nomusic.mp4' if (folder/'hum-production-nomusic.mp4').is_file() else None,
            'sample':root+'native-final.mp4' if (folder/'native-final.mp4').is_file() else root+'narrated-pilot.mp4' if (folder/'narrated-pilot.mp4').is_file() else root+'hum-production.mp4' if (folder/'hum-production.mp4').is_file() else None}


def base_path():
    return '/api/studio/motiongit'


@router.get('/productions/{project_id}/{render_id}/media/{name}')
def production_media(project_id: str, render_id: str, name: str, request: Request):
    details=production(project_id,render_id,request)
    folder=_queue(request).projects_root/project_id/'renders'/render_id
    state=read_json(folder/'native-state.json')
    if name in {'native-final.mp4','narrated-pilot.mp4','hum-production.mp4','hum-production-nomusic.mp4'} and (folder/name).is_file():
        return FileResponse(folder/name)
    if name=='component-plan.json' and details.get('plan') and (folder/name).is_file():return FileResponse(folder/name,media_type='application/json')
    if name not in [i['name'] for i in details['images']]: raise HTTPException(404,'预览不存在')
    return FileResponse(Path(state.get('images_directory') or state['preview_directory'])/name)


@router.post('/productions/{project_id}/{render_id}/review')
def visual_review(project_id: str, render_id: str, request: Request, data: dict = Body(...)):
    mutation(request)
    production(project_id,render_id,request)
    from backlot import studio_motiongit_render as render
    queue=_queue(request)
    frozen=read_json(queue.projects_root/project_id/'artifacts/motiongit-component-request.json')
    if frozen.get('render_id') != render_id: raise HTTPException(404,'工程不存在')
    return call(render.review,queue,frozen,data)


@router.post('/productions/{project_id}/{render_id}/plan-review')
def component_plan_review(project_id: str, render_id: str, request: Request, data: dict = Body(...)):
    mutation(request);production(project_id,render_id,request)
    from backlot import studio_motiongit_render as render
    queue=_queue(request);frozen=read_json(queue.projects_root/project_id/'artifacts/motiongit-component-request.json')
    if frozen.get('render_id')!=render_id:raise HTTPException(404,'工程不存在')
    return call(render.review_plan,queue,frozen,data)
