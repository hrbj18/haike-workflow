"""Read-only comparison registry: IDs, byte identity, ranges and safe metadata."""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backlot import studio_dark_showcase_api as web
from backlot.work_catalog import sha


@pytest.fixture
def page(tmp_path,monkeypatch):
    monkeypatch.setattr(web,'TASK_ROOT',tmp_path);web.digest_matches.cache_clear()
    app=FastAPI();app.include_router(web.router)
    return TestClient(app),tmp_path


def register(root,**entries):
    (root/'showcase.json').write_text(json.dumps({'schema':'haike-motion-showcase/1','media':entries}),encoding='utf-8')


def movie(root,name='registered.mp4',content=b'\x00\x00\x00\x18ftypisom'+b'x'*120):
    p=root/name;p.write_bytes(content);return p


def test_missing_manifest_is_explicit_and_ten_group_clock_uses_full_movie(page):
    client,_=page;response=client.get('/api/studio/motion-showcase');assert response.status_code==200
    value=response.json();assert value['read_only'] is True and value['page_url']=='/motiongit-showcase'
    assert len(value['media'])==5 and all(not m['ready'] and m['url'] is None for m in value['media'].values())
    assert len(value['groups'])==10 and value['groups'][-1]['start']==108.4 and value['total_seconds']==122.4
    html=client.get('/motiongit-showcase');assert html.status_code==200 and '同步播放与定位' in html.text and '单独全屏' in html.text


def test_only_registered_ids_are_served_and_paths_never_reach_metadata(page):
    client,root=page;p=movie(root)
    register(root,native={'path':str(p),'sha256':sha(p),'api_key':'do-not-show'},private={'path':str(p),'sha256':sha(p)})
    details=client.get('/api/studio/motion-showcase');assert str(root) not in details.text and 'do-not-show' not in details.text
    item=details.json()['media']['native'];assert item['ready'] and item['url']=='/api/studio/motion-showcase/media/native'
    assert client.get('/api/studio/motion-showcase/media/private').status_code==404
    actual=client.get(item['url']+'?path=C:/not-registered.mp4');assert actual.status_code==200 and actual.content==p.read_bytes()
    assert client.post('/api/studio/motion-showcase/media/native',json={'path':'C:/any.mp4'}).status_code==405


def test_byte_ranges_and_mtime_cache_revalidate_changed_media(page,monkeypatch):
    client,root=page;p=movie(root);register(root,reference={'path':str(p),'sha256':sha(p)})
    real=web.sha;calls=[]
    monkeypatch.setattr(web,'sha',lambda path:calls.append(path) or real(path))
    response=client.get('/api/studio/motion-showcase/media/reference',headers={'Range':'bytes=0-15'})
    assert response.status_code==206 and response.content==p.read_bytes()[:16] and response.headers['Content-Range'].startswith('bytes 0-15/')
    assert client.get('/api/studio/motion-showcase/media/reference').status_code==200 and len(calls)==1
    p.write_bytes(b'changed-file-version')
    invalid=client.get('/api/studio/motion-showcase/media/reference');assert invalid.status_code==409 and len(calls)==2
    assert client.get('/api/studio/motion-showcase').json()['media']['reference']['status']=='invalid'


def test_incomplete_invalid_registry_and_raw_motion_package_remain_unavailable(page):
    client,root=page;p=movie(root,'private.motion')
    register(root,native={'path':str(p),'sha256':sha(p)},editable={'path':str(root/'missing.mp4'),'sha256':'a'*64},elder={'path':str(root/'not-yet.mp4')})
    value=client.get('/api/studio/motion-showcase').json();assert all(not value['media'][k]['ready'] for k in ['native','editable','elder'])
    assert client.get('/api/studio/motion-showcase/media/native').status_code==404
    (root/'showcase.json').write_text('{bad json',encoding='utf-8')
    assert client.get('/api/studio/motion-showcase').status_code==200


def test_workbench_links_only_use_valid_registered_draft_identity(page):
    client,root=page
    (root/'workbench-live-result.json').write_text(json.dumps({'films':{'elder':{'draft_id':'studio-1234567890abcdef','page_url':'https://not-allowed.invalid'},'child':{'draft_id':'../../escape'}}}),encoding='utf-8')
    links=client.get('/api/studio/motion-showcase').json()['workbench']
    assert links['elder']=='/motiongit?section=dark-full&dark_draft=studio-1234567890abcdef'
    assert links['child']=='/motiongit?section=dark-full'
