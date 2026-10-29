import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def writer(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/template_video/rewrite_923_projects.py'
    spec = importlib.util.spec_from_file_location('template_writeback_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORK = str(tmp_path)
    module.PROJECTS = str(tmp_path / 'projects')
    project = tmp_path / 'projects' / 'test-project'
    project.mkdir(parents=True)
    (tmp_path / 'video.mp4').write_bytes(b'fixture-video')
    clip = dict(scene_id='cue-001', asset_path='assets/video/clip.mp4', source_video_id='source', source_url='', source_title='title', original_delivery_path='delivery', source_in_seconds=0, source_out_seconds=3, caption_policy='crop', media_id='MAT-id', clip_id='CLIP-id', selection_id='SEL-id', grade='A', source_crop={'x':0,'y':0,'w':1,'h':1})
    (tmp_path / 'selection_t30.json').write_text(json.dumps(dict(selection_policy='frozen', rights_note='unknown', visual_review='reviewed', clips=[dict(clip,scene_id=f'cue-{i:03d}') for i in range(1,4)])))
    module.THEMES['t30'] = dict(project='test-project', final='video.mp4', final_dir=str(tmp_path), label='test', title='Test', editorial_status='fact_pending', qc_file=str(tmp_path/'qc.json'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    return module, tmp_path, project


@pytest.mark.parametrize('qc', [[], {}, [{'pass':False,'per_frame':[{}],'risks':['risk']}], [{'pass':True,'per_frame':[],'risks':[]}], [{'pass':True,'per_frame':[{}],'risks':['risk']}]])
def test_failed_qc_cannot_write_deliverable(writer, qc):
    module, work, project = writer
    (work/'qc.json').write_text(json.dumps(qc))
    with pytest.raises(ValueError, match='QC'):
        module.rewrite('t30')
    assert not (project/'renders/final.mp4').exists()


def test_pending_facts_and_stable_ids_survive_writeback(writer):
    module, work, project = writer
    frames=[dict(frame=i*0.5, text_risk=False, face_risk=False, dark_risk=False) for i in range(18)]
    (work/'qc.json').write_text(json.dumps([{'cue':'t30_9s','pass':True,'per_frame':frames,'risks':[]}]))
    module.rewrite('t30')
    report=json.loads((project/'artifacts/render_report.json').read_text(encoding='utf-8'))
    assert report['status']=='fact_pending'
    assert report['editorial_status']=='fact_pending'
    assets=json.loads((project/'artifacts/asset_manifest.json').read_text(encoding='utf-8'))['assets']
    assert len(assets)==3
    assert assets[0]['clip_id']=='CLIP-id'
    assert assets[0]['grade']=='A'
    assert (project/'artifacts/template_qc.json').exists()


@pytest.mark.parametrize('mismatch', ['wrong_topic', 'sampling_gap'])
def test_wrong_or_sparse_qc_cannot_be_reused(writer, mismatch):
    module, work, project = writer
    frames=[dict(frame=i*0.5,text_risk=False,face_risk=False,dark_risk=False) for i in range(18)]
    if mismatch=='sampling_gap':
        del frames[4]
    (work/'qc.json').write_text(json.dumps([{'cue':'t31_9s' if mismatch=='wrong_topic' else 't30_9s','pass':True,'per_frame':frames,'risks':[]}]))
    with pytest.raises(ValueError,match='QC'):
        module.rewrite('t30')
    assert not (project/'renders/final.mp4').exists()
