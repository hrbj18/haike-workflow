"""Source-aware placement exercised through the public editor and queue."""
import copy
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from tests.backlot.test_commentary_editorial import editor, plan
from lib.ffmpeg_locator import resolve_ffmpeg_pair
from backlot import material_commentary as flow
from backlot.production_queue_worker import ProductionQueueWorker


@pytest.fixture
def layout_editor(editor, tmp_path):
    client, base, draft, ev, media_id, projects, queue = editor
    voice = tmp_path / 'layout-voice.wav'
    with wave.open(str(voice), 'wb') as out:
        out.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        out.writeframes((np.sin(np.arange(96000)*2*np.pi*220/48000)*5000).astype('<i2').tobytes())
    take = client.post(base+'/audio/import', json={'path': str(voice), 'text': '看这个动作'}).json()
    avatar = tmp_path/'red-avatar.mp4'
    subprocess.run([resolve_ffmpeg_pair()[0], '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=red:size=320x400:rate=25:duration=2', '-c:v', 'libx264', '-threads', '2', str(avatar)], check=True, capture_output=True)
    asset = client.post(base+'/presenters/import', json={'path': str(avatar), 'audio_id': take['id'],
        'name': '测试主持人', 'provenance': '合成红色视频，配音同源'}).json()
    payload = plan(draft, ev, media_id); payload['payload'].pop('editorial')
    payload['payload']['format'] = 'landscape'
    row = payload['payload']['segments'][0]; row.pop('event_id')
    row.update(mode='narration', text=take['text'], audio_id=take['id'], subtitle_mode='none',
        presenter={'asset_id': asset['id'], 'x': .63, 'y': .05, 'diameter': .35, 'layout_review': '空间测试'},
        presenter_layout={'mode': 'auto', 'protection_ids': [], 'locks': []})
    return client, base, payload, ev, projects, queue


def protect(client, base, ev, regions, *, start=2, end=4, coverage='complete', cuts=None):
    response = client.post(base+'/layout/prepare', json={'evidence_id': ev['id'], 'start': start, 'end': end,
        'model': 'test-ground-truth'})
    assert response.status_code == 200, response.text
    task = response.json()
    response = client.post(base+'/layout/protection', json={'task_id': task['id'], 'task_fingerprint': task['fingerprint'],
        'reviewed_frame_ids': [f['id'] for f in task['frames']], 'coverage': coverage,
        'regions': regions, 'cuts': cuts or [], 'rationale': '合成夹具的已知空间真值；非现实人物判断'})
    assert response.status_code == 200, response.text
    return response.json()


def test_right_subject_selects_left_at_accepted_size(layout_editor):
    client, base, payload, ev, *_ = layout_editor
    record = protect(client, base, ev, [{'kind': 'person', 'label': '互动人物与手臂',
        'box': {'x': .60, 'y': 0, 'w': .40, 'h': .65}, 'start': 2, 'end': 4}])
    payload['payload']['segments'][0]['presenter_layout']['protection_ids'] = [record['id']]
    saved = client.put(base, json=payload)
    assert saved.status_code == 200, saved.text
    response = client.post(base+'/preflight', json={'revision': saved.json()['revision']})
    assert response.status_code == 200, response.text
    shot = response.json()['layouts'][0]['shots'][0]
    assert shot['position'] == 'left' and shot['geometry']['size'] == 448
    assert shot['geometry']['x'] == 38
    assert '互动人物与手臂' in ' '.join(shot['reasons'])


def test_auto_placement_renders_left_and_moves_large_captions(layout_editor):
    client, base, payload, ev, projects, queue = layout_editor
    record = protect(client,base,ev,[{'kind':'person','label':'右侧人物',
        'box':{'x':.60,'y':0,'w':.40,'h':.55},'start':2,'end':4}])
    row=payload['payload']['segments'][0]
    row['presenter_layout']['protection_ids']=[record['id']]
    row.update(subtitle_mode='timed',subtitle_position='top',subtitles=[{'start':.1,'end':1.9,'text':'看这个动作'}])
    payload['payload']['subtitle_style']={'font_size':64}
    saved=client.put(base,json=payload).json()
    job=client.post(base+'/render',json={'revision':saved['revision']})
    assert job.status_code==200,job.text
    result=ProductionQueueWorker(queue,projects).run_once()
    assert result['status']=='completed',result
    version=client.get(base).json()['versions'][0]
    assert version['layouts'][0]['shots'][0]['position']=='left'
    frame=subprocess.run([resolve_ffmpeg_pair()[0],'-v','error','-ss','0.5','-i',
        str(flow.output_path(payload['id'],job.json()['parent_job_id'],projects_root=projects)),
        '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True)
    pixels=np.frombuffer(frame.stdout,np.uint8).reshape(720,1280,3)
    assert pixels[260,262,0]>180 and pixels[260,262,1]<70
    assert version['layouts'][0]['shots'][0]['subtitle_layout']['y']>.18


@pytest.mark.parametrize('scenario',['occupied','uncertain','partial'])
def test_unsafe_or_ununderstood_shot_hides_presenter_and_flags_review(layout_editor,scenario):
    client,base,payload,ev,*_=layout_editor
    regions=[{'kind':'action','label':'跨画面的关键动作','box':{'x':0,'y':0,'w':1,'h':.8},'start':2,'end':4}]
    if scenario=='partial': regions[0]['end']=3
    record=protect(client,base,ev,regions,end=3 if scenario=='partial' else 4,
        coverage='uncertain' if scenario=='uncertain' else 'complete')
    payload['payload']['segments'][0]['presenter_layout']['protection_ids']=[record['id']]
    saved=client.put(base,json=payload).json()
    checked=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    assert checked['status']=='ready'
    assert checked['layouts'][0]['shots'][0]['position']=='hidden'
    assert any('隐藏' in warning for warning in checked['warnings'])


def test_position_changes_only_at_confirmed_cut_and_uses_whole_movement_window(layout_editor):
    client,base,payload,ev,projects,queue=layout_editor
    regions=[{'kind':'person','label':'右侧人物','box':{'x':.60,'y':0,'w':.4,'h':.65},'start':2,'end':3},
        {'kind':'action','label':'左侧动作','box':{'x':0,'y':0,'w':.40,'h':.65},'start':3,'end':4}]
    continuous=protect(client,base,ev,regions)
    config=payload['payload']['segments'][0]['presenter_layout']
    config['protection_ids']=[continuous['id']]
    saved=client.put(base,json=payload).json()
    response=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    assert [s['position'] for s in response['layouts'][0]['shots']]==['hidden']
    cut=protect(client,base,ev,regions,cuts=[3])
    saved['payload']['segments'][0]['presenter_layout']['protection_ids']=[cut['id']]
    saved=client.put(base,json=saved).json()
    job=client.post(base+'/render',json={'revision':saved['revision']})
    assert job.status_code==200,job.text
    assert ProductionQueueWorker(queue,projects).run_once()['status']=='completed'
    version=client.get(base).json()['versions'][0]
    shots=version['layouts'][0]['shots']
    assert [(s['position'],s['start_frame'],s['end_frame']) for s in shots]==[('left',0,30),('right',30,60)]
    path=flow.output_path(payload['id'],job.json()['parent_job_id'],projects_root=projects)
    for stamp,x in [(.5,262),(1.5,1017)]:
        raw=subprocess.run([resolve_ffmpeg_pair()[0],'-v','error','-ss',str(stamp),'-i',str(path),
            '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
        pixels=np.frombuffer(raw,np.uint8).reshape(720,1280,3)
        assert pixels[260,x,0]>180 and pixels[260,x,1]<70


def test_automatic_application_preserves_manual_lock_and_rejects_changed_locked_source(layout_editor):
    client,base,payload,ev,*_=layout_editor
    protect(client,base,ev,[{'kind':'person','label':'右侧人物','box':{'x':.6,'y':0,'w':.4,'h':.7},'start':2,'end':4}])
    saved=client.put(base,json=payload).json()
    response=client.post(base+'/layout/apply',json={'revision':saved['revision']})
    assert response.status_code==200,response.text
    auto=response.json()
    assert auto['layouts'][0]['shots'][0]['position']=='left'
    locked=auto['draft']; locked['payload']['segments'][0]['presenter_layout']['locks']=[{'shot_index':0,'position':'right'}]
    locked=client.put(base,json=locked).json()
    again=client.post(base+'/layout/apply',json={'revision':locked['revision']}).json()
    assert again['layouts'][0]['shots'][0]['position']=='right'
    assert again['layouts'][0]['shots'][0]['locked'] is True
    assert any('手动锁定' in w for w in again['warnings'])
    repeated=client.post(base+'/layout/apply',json={'revision':again['draft']['revision']}).json()
    assert repeated['draft']['revision']==again['draft']['revision']
    changed=copy.deepcopy(repeated['draft']); changed['payload']['segments'][0]['shots'][0]['start']=2.1
    assert client.put(base,json=changed).status_code==422


def test_spatial_task_images_are_available_and_incomplete_review_is_rejected(layout_editor):
    client,base,_,ev,*_=layout_editor
    task=client.post(base+'/layout/prepare',json={'evidence_id':ev['id'],'start':2,'end':4,'model':'test-ground-truth'}).json()
    image=client.get(base+'/layout/tasks/'+task['id']+'/media/frame-000.png')
    assert image.status_code==200 and image.content.startswith(b'\x89PNG'),image.text
    response=client.post(base+'/layout/protection',json={**task['submission_template'],
        'reviewed_frame_ids':[task['frames'][0]['id']],'coverage':'complete','regions':[],'rationale':'只查看了首帧'})
    assert response.status_code==422 and '全部帧' in response.text


def test_source_boxes_are_mapped_through_portrait_letterboxing(layout_editor):
    client,base,payload,ev,*_=layout_editor
    record=protect(client,base,ev,[{'kind':'person','label':'源图右侧人物',
        'box':{'x':.6,'y':0,'w':.4,'h':.65},'start':2,'end':4}])
    payload['payload']['format']='portrait'
    payload['payload']['segments'][0]['presenter_layout']['protection_ids']=[record['id']]
    saved=client.put(base,json=payload).json()
    checked=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    shot=checked['layouts'][0]['shots'][0]
    assert shot['position']=='right'
    assert shot['protected_regions'][0]['box']['y']==434


def test_changed_task_source_and_nonexistent_cut_lock_are_rejected(layout_editor):
    client,base,payload,ev,*_=layout_editor
    task=client.post(base+'/layout/prepare',json={'evidence_id':ev['id'],'start':2,'end':4}).json()
    path=Path(task['frames'][0]['path']).parent/'task.json'
    changed=copy.deepcopy(task); changed['crop']['x']=.1
    path.write_text(json.dumps(changed),encoding='utf-8')
    response=client.get(base+'/layout/tasks/'+task['id'])
    assert response.status_code==422 and '指纹' in response.text
    path.write_text(json.dumps(task),encoding='utf-8')
    payload['payload']['segments'][0]['presenter_layout']['locks']=[{'shot_index':0,'cut_index':1,'position':'left'}]
    saved=client.put(base,json=payload).json()
    response=client.post(base+'/preflight',json={'revision':saved['revision']})
    assert response.status_code==422 and '锁定' in response.text


def test_contiguous_source_entries_do_not_create_a_position_switch(layout_editor):
    client,base,payload,ev,*_=layout_editor
    regions=[{'kind':'person','label':'右侧人物','box':{'x':.6,'y':0,'w':.4,'h':.65},'start':2,'end':3},
        {'kind':'action','label':'移动到左侧','box':{'x':0,'y':0,'w':.4,'h':.65},'start':3,'end':4}]
    record=protect(client,base,ev,regions)
    row=payload['payload']['segments'][0]
    row['shots']=[{'evidence_id':ev['id'],'start':2,'end':3},{'evidence_id':ev['id'],'start':3,'end':4}]
    row['presenter_layout']['protection_ids']=[record['id']]
    saved=client.put(base,json=payload).json()
    checked=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    assert [p['position'] for p in checked['layouts'][0]['shots']]==['hidden','hidden']
    saved['payload']['segments'][0]['presenter_layout']['locks']=[{'shot_index':0,'position':'left'}]
    saved=client.put(base,json=saved).json()
    checked=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    assert [p['position'] for p in checked['layouts'][0]['shots']]==['left','left']
    assert any('手动锁定' in w for w in checked['warnings'])
    cut=protect(client,base,ev,regions,cuts=[3])
    saved['payload']['segments'][0]['presenter_layout']['locks']=[]
    saved['payload']['segments'][0]['presenter_layout']['protection_ids']=[cut['id']]
    saved=client.put(base,json=saved).json()
    checked=client.post(base+'/preflight',json={'revision':saved['revision']}).json()
    assert [p['position'] for p in checked['layouts'][0]['shots']]==['left','right']
