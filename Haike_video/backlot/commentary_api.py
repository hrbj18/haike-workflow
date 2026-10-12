"""HTTP editor for the source-first commentary template."""
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from backlot import material_commentary as commentary
from backlot import commentary_audio as audio
from backlot import commentary_evidence as evidence
from backlot import commentary_library_bridge as bridge
from backlot import commentary_editorial as editorial
from backlot import commentary_alignment as alignment
from backlot import commentary_presenter as presenter
from backlot import commentary_presenter_job as presenter_job
from backlot import commentary_layout as layout
from backlot.commentary_common import CommentaryConflict, project_dir
from backlot.production_queue import ProductionQueueConflict

router = APIRouter()
BASE = "/api/material-commentaries"


def runtime(request):
    from backlot import server
    return server.PROJECTS_DIR, server._ensure_production_queue(request.app)


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409 if isinstance(exc, (CommentaryConflict, ProductionQueueConflict)) else 422, str(exc)) from exc


def project(request, identity):
    root, _ = runtime(request)
    call(commentary.read, identity)
    return call(project_dir, identity, root)


@router.get("/material-commentary", response_class=HTMLResponse)
def page():
    return HTMLResponse((Path(__file__).parent / "ui/material_commentary.html").read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@router.get(BASE)
def listing(): return call(commentary.list_drafts)


@router.get(BASE + "/sources/search")
def search(query: str = ""):
    return {"media": call(bridge.search, query)}


@router.post(BASE)
def create(request: Request, payload: dict = Body(...)):
    root, _ = runtime(request)
    return call(commentary.create, payload.get("title"), projects_root=root)


@router.get(BASE + "/{identity}")
def read(identity: str, request: Request):
    root, queue = runtime(request)
    result = call(commentary.brief, identity, projects_root=root)
    result["versions"] = call(commentary.versions, identity, projects_root=root)
    for version in result["versions"]:
        job = queue.find_by_idempotency_key(f"material_commentary:{identity}:{version['signature']}")
        if job: version["queue_job"] = job
    return result


@router.put(BASE + "/{identity}")
def save(identity: str, request: Request, payload: dict = Body(...)):
    root, _ = runtime(request)
    return call(commentary.save, identity, payload, projects_root=root)


@router.get(BASE + "/{identity}/editorial")
def editorial_report(identity: str, request: Request):
    draft = call(commentary.read, identity)
    return call(editorial.audit, draft["payload"], project=project(request, identity))


@router.post(BASE + "/{identity}/compare")
def comparison(identity: str, request: Request, payload: dict = Body(...)):
    root, _ = runtime(request)
    return call(editorial.compare, identity, payload, projects_root=root)


@router.post(BASE + "/{identity}/preflight")
def preflight(identity: str, request: Request, payload: dict = Body(...)):
    root, _ = runtime(request)
    return call(commentary.preflight, identity, payload.get("revision"), projects_root=root)


@router.post(BASE + "/{identity}/render")
def render(identity: str, request: Request, payload: dict = Body(...)):
    root, queue = runtime(request)
    return call(commentary.submit, identity, payload.get("revision"), queue, projects_root=root)


@router.post(BASE + "/{identity}/evidence")
def prepare_evidence(identity: str, request: Request, payload: dict = Body(...)):
    return call(evidence.prepare, project(request, identity), payload)


@router.post(BASE + "/{identity}/evidence/{evidence_id}/review")
def review(identity: str, evidence_id: str, request: Request, payload: dict = Body(...)):
    return call(evidence.review, project(request, identity), evidence_id, payload)


@router.get(BASE + "/{identity}/evidence/{evidence_id}/{name}")
def evidence_file(identity: str, evidence_id: str, name: str, request: Request):
    if name not in {"sheet.jpg", "source.mp4"}: raise HTTPException(404, "证据文件不存在")
    directory = call(evidence.directory, project(request, identity), evidence_id)
    value = call(evidence.read, project(request, identity), evidence_id)
    from backlot.commentary_common import verified
    return FileResponse(call(verified, directory / name, value["files"][name]))


@router.post(BASE + "/{identity}/audio/import")
def import_audio(identity: str, request: Request, payload: dict = Body(...)):
    return call(audio.import_audio, project(request, identity), str(payload.get("path") or ""),
                narration_text=payload.get("text", ""), kind=payload.get("kind", "narration"),
                provenance=payload.get("provenance", "用户导入"))


@router.post(BASE + "/{identity}/presenters/import")
def import_presenter(identity: str, request: Request, payload: dict = Body(...)):
    return call(presenter.import_presenter, project(request, identity), payload)


@router.post(BASE + "/{identity}/layout/prepare")
def prepare_layout(identity: str, request: Request, payload: dict = Body(...)):
    return call(layout.prepare, project(request, identity), payload)


@router.post(BASE + "/{identity}/layout/apply")
def apply_layout(identity: str, request: Request, payload: dict = Body(...)):
    root,_=runtime(request)
    return call(layout.apply,identity,payload,projects_root=root)


@router.get(BASE + "/{identity}/layout/plan")
def layout_plan(identity: str, request: Request):
    result=call(commentary.compile_timeline,project(request,identity),call(commentary.read,identity)['payload'])
    return {'layouts':[{'segment_id':s['id'],**s['layout_plan']} for s in result['segments'] if 'layout_plan' in s],
        'warnings':result['warnings']}


@router.get(BASE + "/{identity}/layout/tasks/{task_id}")
def layout_task(identity: str, task_id: str, request: Request):
    return call(layout.read_task, project(request, identity), task_id)


@router.get(BASE + "/{identity}/layout/tasks/{task_id}/media/{name}")
def layout_image(identity: str, task_id: str, name: str, request: Request):
    task=call(layout.read_task,project(request,identity),task_id)
    item=next((p for p in task['frames']+task['sheets'] if Path(p['path']).name==name),None)
    if not item: raise HTTPException(404,'空间判断图片不存在')
    from backlot.commentary_common import verified
    return FileResponse(call(verified,item['path'],item['sha256']))


@router.post(BASE + "/{identity}/layout/protection")
def layout_protection(identity: str, request: Request, payload: dict = Body(...)):
    return call(layout.submit_protection, project(request, identity), payload)


@router.post(BASE + "/{identity}/presenters/quote")
def quote_presenter(identity: str, request: Request, payload: dict = Body(...)):
    return call(presenter_job.quote, project(request, identity), payload)


@router.post(BASE + "/{identity}/presenters/generate")
def generate_presenter(identity: str, request: Request, payload: dict = Body(...)):
    _, queue = runtime(request)
    return call(presenter_job.submit, project(request, identity), payload, queue)


@router.get(BASE + "/{identity}/presenters/jobs/{generation_id}")
def presenter_status(identity: str, generation_id: str, request: Request):
    return call(presenter_job.inspect, project(request, identity), generation_id)


@router.get(BASE + "/{identity}/presenters/{asset_id}/media")
def presenter_file(identity: str, asset_id: str, request: Request):
    asset = call(presenter.read, project(request, identity), asset_id)
    return FileResponse(asset["path"], media_type="video/mp4")


@router.post(BASE + "/{identity}/audio/quote")
def quote(identity: str, request: Request, payload: dict = Body(...)):
    project(request, identity)
    return call(audio.quote, payload)


@router.post(BASE + "/{identity}/audio/alignment")
def import_alignment(identity: str, request: Request, payload: dict = Body(...)):
    return call(alignment.import_alignment, project(request, identity), payload)


@router.post(BASE + "/{identity}/audio/generate")
def generate(identity: str, request: Request, payload: dict = Body(...)):
    return call(audio.synthesize, project(request, identity), payload)


@router.get(BASE + "/{identity}/audio/{audio_id}/media")
def audio_file(identity: str, audio_id: str, request: Request):
    take = call(audio.read, project(request, identity), audio_id)
    return FileResponse(take["path"], media_type="audio/wav")


@router.get(BASE + "/{identity}/versions/{signature}/{name}")
def media(identity: str, signature: str, name: str, request: Request, download: bool = False):
    root, _ = runtime(request)
    path = call(commentary.output_path, identity, signature, projects_root=root, artifact=name)
    return FileResponse(path, media_type="video/mp4" if name.endswith("mp4") else "text/plain; charset=utf-8",
                        filename=f"{identity}-{signature[:8]}-{name}" if download else None)
