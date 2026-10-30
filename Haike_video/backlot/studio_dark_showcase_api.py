"""Read-only comparison page. Only five server-registered, hashed MP4s can play."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backlot.studio_dark_full_api import catalog as full_catalog
from backlot.work_catalog import sha

router=APIRouter()
ROOT=Path(__file__).resolve().parents[2]
TASK_ROOT=ROOT/'.local/motion-full-20261028'
PAGE=ROOT/'Haike_video/templates/motion-showcase-page/index.html'
MEDIA={
    'reference':('官方完整参考','16:9'),
    'native':('本次完整原生复刻','16:9'),
    'editable':('项目可编辑完整重建','16:9'),
    'elder':('长者账号成片','4:5'),
    'child':('亲子账号成片','4:5'),
}
DEFAULT_NOTE='原版内嵌素材缺失处，以同规格自制图形替代。请结合完整动作、构图和声音观看比较。'


def read_manifest(name):
    try:return json.loads((TASK_ROOT/name).read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {}


def safe_text(value,fallback,maximum=180):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:return fallback
    if re.search(r'[A-Za-z]:[\\/]|(?:^|\s)/(?:[^/\s]+/)+|(?i:api[_ -]?key|bearer\s)',value):return fallback
    return value.strip()


@lru_cache(maxsize=32)
def digest_matches(path,size,mtime_ns,ctime_ns,expected):
    # mtime/ctime and size are part of the key; replacing a registered file must
    # trigger a new hash check before a range or complete response is returned.
    try:return sha(Path(path))==expected
    except OSError:return False


def registered(media_id,manifest=None):
    if media_id not in MEDIA:raise HTTPException(404,'对照媒体不存在')
    manifest=manifest if manifest is not None else read_manifest('showcase.json')
    slots=manifest.get('media',{}) if isinstance(manifest,dict) else {}
    entry=slots.get(media_id,{}) if isinstance(slots,dict) else {}
    entry=entry if isinstance(entry,dict) else {}
    label,aspect=MEDIA[media_id]
    item={'id':media_id,'label':safe_text(entry.get('label'),label,80),'aspect':aspect,'ready':False,'status':'pending','status_label':'待生成或登记','url':None}
    expected=entry.get('sha256');raw=entry.get('path')
    if not isinstance(raw,str) or not isinstance(expected,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected):return item,None
    try:
        path=Path(raw)
        if not path.is_absolute() or path.suffix.lower()!='.mp4' or not path.is_file() or path.is_symlink():return item,None
        path=path.resolve();stat=path.stat()
        if not digest_matches(str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,expected.lower()):
            item.update(status='invalid',status_label='版本待核对');return item,None
    except OSError:return item,None
    item.update(ready=True,status='ready',status_label='已就绪',url=f'/api/studio/motion-showcase/media/{media_id}')
    return item,path


@router.get('/motiongit-showcase')
def page():
    return FileResponse(PAGE,media_type='text/html; charset=utf-8',headers={'Cache-Control':'no-cache'})


@router.get('/api/studio/motion-showcase')
def showcase():
    manifest=read_manifest('showcase.json');manifest=manifest if isinstance(manifest,dict) else {}
    media={identity:registered(identity,manifest)[0] for identity in MEDIA}
    groups=[];cursor=0
    for item in full_catalog()['groups']:
        duration=item['source']['end']-item['source']['start']
        groups.append({'id':item['id'],'number':item['number'],'name':item['title'],'score':item['score'],
                       'start':round(cursor,3),'end':round(cursor+duration,3),'preview_url':item.get('preview'),
                       'preview_kind':item.get('preview_kind','image'),'preview_label':item.get('preview_label','预览待绑定')})
        cursor+=duration
    workbench={}
    live=read_manifest('workbench-live-result.json')
    for identity in ['elder','child']:
        films=live.get('films',{}) if isinstance(live,dict) else {}
        item=films.get(identity,{}) if isinstance(films,dict) else {}
        draft=item.get('draft_id') if isinstance(item,dict) else None
        workbench[identity]='/motiongit?section=dark-full'+('&dark_draft='+draft if isinstance(draft,str) and re.fullmatch(r'studio-[0-9a-f]{16}',draft) else '')
    return {'page_url':'/motiongit-showcase','title':safe_text(manifest.get('title'),'完整复刻与成片对照',80),
            'notes':safe_text(manifest.get('notes'),DEFAULT_NOTE,400),'media':media,'groups':groups,
            'total_seconds':round(cursor,3),'workbench':workbench,'read_only':True}


@router.get('/api/studio/motion-showcase/media/{media_id}')
def media(media_id:str):
    item,path=registered(media_id)
    if path is None:raise HTTPException(409 if item['status']=='invalid' else 404,item['status_label'])
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'no-cache'})
