"""Review provenance regressions; isolated files do not assert real visual QA."""
import pytest
from pathlib import Path

from backlot import studio_motion_console as console
from backlot.work_catalog import WorkError,read_json,sha
from backlot.studio import atomic_private


def test_media_slots_follow_selected_native_actions():
    assert console.media_windows({},[{'recipe':'keyword-slam','durationFrames':216}])==[]
    media={'wall':[{'at':i,'source':{'path':f'{i}.mp4'}} for i in range(6)]}
    windows=console.media_windows(media,[{'recipe':'works-fan','durationFrames':324}])
    assert len(windows)==6 and all(w[3]==5.4 for w in windows)
    with pytest.raises(WorkError,match='实拍窗口'):
        console.media_windows(media,[{'recipe':'result-inspector','durationFrames':300}])
    media['lens']={'offset':2,'source':{'path':'lens.mp4'}}
    assert console.media_windows(media,[{'recipe':'result-inspector','durationFrames':300}])[0][2:]==(2,5)


def test_real_media_requires_review_of_full_used_interval(tmp_path,monkeypatch):
    video=tmp_path/'source.mp4';video.write_bytes(b'isolated video identity')
    image=tmp_path/'review.jpg';image.write_bytes(b'isolated representative pixels')
    row={'source':console.bound(video),'at':2}
    material={'source_sha256':sha(video),'source_start_seconds':1,'source_end_seconds':3,
              'actual_images_viewed':[console.bound(image)]}
    review={'status':'pass','materials':[material]}
    monkeypatch.setattr(console,'_probe',lambda *args:{'streams':[{'codec_type':'video'}],'format':{'duration':'8'}})
    windows=[('wall.0',row,2,5.4)]
    with pytest.raises(WorkError,match='完整使用区间'):console.review_media(windows,review,{})
    material['source_end_seconds']=7.4
    console.review_media(windows,review,{})
    with pytest.raises(WorkError,match='区间不足'):console.review_media([('wall.0',row,3,5.4)],review,{})
    with pytest.raises(WorkError,match='入点'):console.review_media([('wall.0',row,float('nan'),5.4)],review,{})


def test_review_rejects_repeating_one_image_as_five_frames(tmp_path):
    image=tmp_path/'one.jpg';image.write_bytes(b'isolated image fixture')
    row=console.bound(image)
    with pytest.raises(WorkError,match='重复图片'):
        console.reviewed_images([row]*5,{str(image.resolve()):row['sha256']},minimum=5)


def test_review_rejects_other_stage_and_changed_image(tmp_path):
    image=tmp_path/'one.jpg';image.write_bytes(b'isolated image fixture')
    row=console.bound(image)
    with pytest.raises(WorkError,match='当前阶段'):
        console.reviewed_images([row],{})
    image.write_bytes(b'changed fixture')
    with pytest.raises(WorkError,match='身份已变化'):
        console.reviewed_images([row],{str(image.resolve()):row['sha256']})


def test_review_requires_distinct_current_files(tmp_path):
    rows=[]
    for i in range(5):
        path=tmp_path/f'{i}.jpg';path.write_bytes(f'fixture {i}'.encode());rows.append(console.bound(path))
    allowed={row['path']:row['sha256'] for row in rows}
    assert len(console.reviewed_images(rows,allowed,minimum=5))==5
    with pytest.raises(WorkError,match='证据不足'):
        console.reviewed_images(rows[:4],allowed,minimum=5)


def test_official_preparation_cannot_export_full_movie():
    with pytest.raises(WorkError,match='统一队列'):
        console.official({},'render')


def test_native_groups_follow_real_sentence_gaps():
    caps=[{'t0':.76,'t1':1.92},{'t0':2.16,'t1':3.48},{'t0':3.64,'t1':5.76}]
    console.sentence_boundaries(caps,[{'durationFrames':216},{'durationFrames':144}])
    with pytest.raises(WorkError,match='切断真实字幕句'):
        console.sentence_boundaries(caps,[{'durationFrames':288},{'durationFrames':72}])


def test_new_person_calibration_replans_and_requires_review_of_diagnostics(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from backlot import studio_motion_console_session as session, studio_motion_face_crop as face
    input_path=tmp_path/'input.json'
    atomic_private(input_path,{'console':{'cropCalibrationRequired':'new-person'},
                             'avatar':{'sha256':'new-person'},'tools':{}})
    build=tmp_path/'build.json';atomic_private(build,{'fixture':True})
    calibrated=tmp_path/'calibration.json';atomic_private(calibrated,{'crop':{'cx':.51,'cy':.4,'h':.38}})
    value={'revision':3,'status':'plan_review','input':{'console':{'presenterCrop':{'cx':.2,'cy':.2,'h':.2}}},
           'build':console.bound(build),'plan':{'token':'current-plan','images':[{'id':'actually-viewed-source'}]}}
    monkeypatch.setattr(console,'load',lambda path:{'input_path':str(input_path),'frames':1800})
    imports=[]
    def imported(path,review,times,**kw):
        assert read_json(review)['actual_plan_inspected']
        assert kw=={'calibration_import':True} and len(times)==5
        imports.append(path);return {'project':str(tmp_path/'official')}
    monkeypatch.setattr(console,'prepare_and_preview',imported)
    monkeypatch.setattr(face,'calibrate',lambda *a:console.bound(calibrated))
    def prepare(store,updated,queue):
        assert updated['revision']==4 and updated['status']=='ready_to_prepare'
        assert 'build' not in updated and 'plan' not in updated
        assert updated['input']['console']['presenterCrop']=={'cx':.51,'cy':.4,'h':.38}
        assert updated['input']['console']['cropCalibration']==console.bound(calibrated)
        return {'status':'plan_review','revision':5}
    monkeypatch.setattr(session,'prepare',prepare)
    store=SimpleNamespace(put=lambda v,revision:{**v,'revision':revision+1})
    assert session.approve_plan(store,value,'current-plan',[0])=={'status':'plan_review','revision':5}
    assert len(imports)==1


@pytest.mark.parametrize('same_sources',[True,False])
def test_plan_retry_only_preserves_already_bound_acknowledgement(tmp_path,monkeypatch,same_sources):
    from backlot import studio_motion_console_session as session
    build=tmp_path/'build.json';atomic_private(build,{'fixture':True})
    instance=tmp_path/'instance';(instance/'plan').mkdir(parents=True)
    plan_path=instance/'plan/plan.json';atomic_private(plan_path,{'reviewed':True})
    input_path=tmp_path/'input.json';atomic_private(input_path,{'console':{'segments':[{'durationFrames':1800}]}})
    images=[{'path':'actual-reviewed-image','sha256':'bound-image'}]
    prior={'status':'pass','actual_plan_inspected':True,'plan_sha256':'original-token',
           'reviewed_plan_sha256':sha(plan_path),'actual_source_images_viewed':images if same_sources else []}
    atomic_private(tmp_path/'web-plan-review.json',prior)
    value={'status':'plan_review','build':console.bound(build),'layout':'landscape',
           'plan':{'token':'original-token','images':images}}
    monkeypatch.setattr(console,'load',lambda path:{'instance':str(instance),'input_path':str(input_path)})
    def check_proof(path,review,times):
        assert ('reviewed_plan_sha256' in read_json(review)) is same_sources
        raise WorkError('stop after checking proof')
    monkeypatch.setattr(console,'prepare_and_preview',check_proof)
    with pytest.raises(WorkError,match='checking proof'):
        session.approve_plan(None,value,'original-token',[0])


def test_duration_follows_real_speech_without_moving_native_anchors():
    segments=[{'recipe':'opening','durationFrames':180,'anchors':{'title':.4}},
              {'recipe':'ending','durationFrames':240,'anchors':{'title':.2}}]
    groups={'opening':{'minFrames':120,'maxHoldFrames':180,'minFollowingFrames':54},
            'ending':{'minFrames':150,'maxHoldFrames':300,'minFollowingFrames':0}}
    caps=[{'t0':.5,'t1':2.9},{'t0':3.1,'t1':5.5},{'t0':5.9,'t1':7.9}]
    fitted=console.fit_segments(segments,caps,8,groups)
    assert sum(s['durationFrames'] for s in fitted)==480
    assert fitted[0]['anchors']==segments[0]['anchors'] and segments[0]['durationFrames']==180
    console.sentence_boundaries(caps,fitted)
    with pytest.raises(WorkError,match='无法适配'):
        console.fit_segments(segments,[{'t0':0,'t1':8}],8,groups)


def test_native_exit_tail_cannot_be_silently_truncated():
    groups={'follow':{'minFollowingFrames':78},'terminal':{'minFollowingFrames':0}}
    with pytest.raises(WorkError,match='退场需要后续帧'):
        console.following_frames([{'recipe':'follow','durationFrames':450}],groups)
    console.following_frames([{'recipe':'follow','durationFrames':450},{'recipe':'terminal','durationFrames':180}],groups)


def test_real_plan_envelope_requires_nested_native_acceptance():
    from copy import deepcopy
    report={'status':'ready-for-review','mode':'native','layout':'landscape','fps':60,
            'total_frames':1836,'problems':[],'whole_sentence_crossings':[],
            'native_contract':{'ready':True,'status':'ready','blocking':[],'missing':[],
                               'durationFrames':1836,'selectedScenes':['fan','terminal']}}
    console.plan_facts(report,1836,['fan','terminal'])
    for path,value in [('ready',False),('durationFrames',1835),('blocking',['missing-video'])]:
        changed=deepcopy(report);changed['native_contract'][path]=value
        with pytest.raises(WorkError,match='官方计划未通过'):console.plan_facts(changed,1836,['fan','terminal'])
    report['whole_sentence_crossings']=[{'sentence':3}]
    with pytest.raises(WorkError,match='官方计划未通过'):console.plan_facts(report,1836,['fan','terminal'])


def test_public_native_review_and_preview_can_resume_without_rebuilding(tmp_path,monkeypatch):
    """Fake files test acknowledgement/recovery, never actual artistic approval."""
    inst=tmp_path/'instance';plan=inst/'plan';plan.mkdir(parents=True)
    body={'status':'ready-for-review','reviewed':False,'mode':'native','layout':'landscape','fps':60,
          'total_frames':600,'problems':[],'whole_sentence_crossings':[],
          'native_contract':{'ready':True,'status':'ready','blocking':[],'missing':[],
                             'durationFrames':600,'selectedScenes':['fan']},'sourceParameterSha256':'bound-fixture'}
    atomic_private(plan/'plan.json',body)
    atomic_private(plan/'review.json',{'schema':'fixture','planBodySha256':'preserve-this-original-binding'})
    image=tmp_path/'source.jpg';image.write_bytes(b'fixture source pixels');row=console.bound(image)
    atomic_private(tmp_path/'sources.json',{'materials':[{'actual_images_viewed':[row]}]})
    atomic_private(tmp_path/'input.json',{'source_review':console.bound(tmp_path/'sources.json')})
    b={'instance':str(inst),'input_path':str(tmp_path/'input.json'),'frames':600,'recipes':['fan']}
    monkeypatch.setattr(console,'load',lambda p:b)
    review_path=tmp_path/'review.json'
    atomic_private(review_path,{'status':'pass','actual_plan_inspected':True,
        'plan_sha256':sha(plan/'plan.json'),'actual_source_images_viewed':[row]})
    times=[.2,1,2,3,4];calls=[]
    def fake_official(build,op,args):
        calls.append(op);project=inst/'project'
        if op=='prepare':
            assert read_json(plan/'plan.json')['reviewed'] is True
            project.mkdir();atomic_private(project/'parameters.json',{'fixture':'not-real-movie'})
            atomic_private(project/'instance.json',{'sourceLockSha256':'fixture-lock'})
        elif op=='preview':
            stills=[]
            for i in range(5):
                path=project/f'frame-{i}.png';path.write_bytes(f'fixture {i}'.encode())
                stills.append({'path':path.name,'sha256':sha(path)})
            atomic_private(project/'preview.json',{'schema':'motiongit-preview/1','times_s':times,'stills':stills,
                'parameterSha256':sha(project/'parameters.json'),'sourceLockSha256':'fixture-lock'})
    monkeypatch.setattr(console,'official',fake_official)
    first=console.prepare_and_preview(tmp_path/'build.json',review_path,times)
    assert first==console.prepare_and_preview(tmp_path/'build.json',review_path,times)
    assert calls==['prepare','preview']
    assert read_json(plan/'review.json')['planBodySha256']=='preserve-this-original-binding'
    preview=read_json(inst/'project/preview.json');preview['stills'][0]['path']='../escaped.png'
    with pytest.raises(WorkError,match='路径无效'):console.preview_images(preview,inst/'project')
    preview=read_json(inst/'project/preview.json');preview['sourceLockSha256']='another-package'
    with pytest.raises(WorkError,match='本期准备工程'):console.preview_images(preview,inst/'project')


def test_nested_review_acknowledges_only_identical_viewed_pixels(tmp_path):
    project=tmp_path/'prepared';inner=project/'project';inner.mkdir(parents=True)
    image=inner/'frame.png';image.write_bytes(b'isolated fixture pixels');actual=[console.bound(image)]
    source=inner/'config.json';atomic_private(source,{'fixture':'opaque source identity'})
    atomic_private(project/'preview.json',{'sourceLockSha256':'same-source'})
    receipt={'schema':'motiongit-preview/1','reviewed':False,'sourceBinding':{'sourceLockSha256':'same-source'},
             'stills':{'frame.png':sha(image)},'projectHashes':{'config.json':sha(source)},
             'projectHashesSha256':'do-not-rewrite-binding'}
    atomic_private(inner/'preview.json',receipt)
    result=console.acknowledge_nested_preview(project,actual)
    reviewed=read_json(result['path'])
    assert reviewed['reviewed'] is True and reviewed['projectHashesSha256']=='do-not-rewrite-binding'
    with pytest.raises(WorkError,match='同一批'):console.acknowledge_nested_preview(project,[])
    source.write_bytes(b'changed fixture input')
    with pytest.raises(WorkError,match='身份已变化'):console.acknowledge_nested_preview(project,actual)
