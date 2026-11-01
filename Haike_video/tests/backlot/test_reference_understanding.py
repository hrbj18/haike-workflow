"""Native-frame extraction, same-source clocks and traceable interpretations."""
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from backlot import reference_understanding as ref
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def speech(source_sha='test'):
    return {'source_sha256':source_sha,'clock':'measured-seconds','segments':[
        {'id':'intro','start':.1,'end':.5,'text':'同一个球在运动',
         'words':[{'start':.1,'end':.25,'text':'同一个球'}, {'start':.3,'end':.5,'text':'在运动'}]}]}


def test_transcript_never_reuses_another_source_or_estimates_word_clock():
    with pytest.raises(ValueError,match='同一原视频'):
        ref.transcript(speech(),'other',1)
    bad=speech();bad['segments'][0]['words'][0]['end']=.8
    with pytest.raises(ValueError,match='词时间'):
        ref.transcript(bad,'test',1)
    sentence=speech();sentence['segments'][0].pop('words')
    rows=ref.transcript(sentence,'test',1)
    assert rows[0]['words']==[]
    assert ref.context_at(rows,.2)['word_ids']==[]
    assert ref.context_at(rows,.7)['text']==''


@pytest.mark.parametrize('value',['-1:2','0:3','0:1:0','nan:1','0:1:inf'])
def test_bad_ranges_rejected(value):
    with pytest.raises(ValueError):ref.ranges([value],2)


@pytest.fixture
def real_task(tmp_path):
    pair=resolve_ffmpeg_pair()
    if not pair:pytest.skip('FFmpeg/ffprobe unavailable')
    source=tmp_path/'source.mp4'
    process=subprocess.run([pair[0],'-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10',
        '-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(source)],capture_output=True)
    assert process.returncode==0,process.stderr.decode(errors='replace')
    transcript=tmp_path/'transcript.json';ref.write(transcript,speech(ref.sha(source)))
    result=ref.prepare(source,tmp_path/'evidence',ffmpeg=pair[0],ffprobe=pair[1],model='test-agent',
        selected_ranges=['0.2:0.6'],every_frame=True,transcript_path=transcript,cell_width=240)
    return Path(result['task']),pair


def test_every_frame_preserves_native_pts_and_spoken_context(real_task):
    path,_=real_task;task=ref.load(path)
    assert [round(r['at'],3) for r in task['frames']]==[.2,.3,.4,.5]
    assert task['frames'][0]['speech']['text']=='同一个球在运动'
    assert task['frames'][-1]['speech']['text']==''
    assert Path(task['grids'][0]['path']).is_file()
    Path(task['frames'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='证据图片变化'):ref.load(path)


def submission(task):
    return {'task_fingerprint':task['fingerprint'],
        'reviewed_grid_ids':[r['id'] for r in task['grids']],
        'whole_piece':'仅分析选定的0.2–0.6秒合成测试图，不声称全片听看。',
        'objects':[{'id':'ball','role':'运动主体','appearance':'测试图形','lifetime':[0,1]}],
        'events':[{'id':'move','object_id':'ball','purpose':'持续运动','start':.2,'end':.6,
            'trigger':{'kind':'speech','sentence_id':'intro','word_id':'intro:w1'},
            'phases':[{'state':'运动中','frame_ids':[task['frames'][0]['id']]}],
            'preserve':'对象连续','retiming':'本期词事件定位，运动速度独立'}],
        'unknowns':['没有声音，不证明音频可懂'],
        'continuous_watch':'pending','continuous_listen':'pending'}


def test_analysis_requires_real_clock_and_preserves_prior_conclusion(real_task,tmp_path):
    path,_=real_task;task=ref.load(path);value=submission(task)
    bad=deepcopy(value);bad['events'][0]['trigger']['word_id']='intro:invented'
    with pytest.raises(ValueError,match='臆造'):ref.validate_submission(task,bad)
    bad=deepcopy(value);bad['reviewed_grid_ids']=[]
    with pytest.raises(ValueError,match='所有宫格'):ref.validate_submission(task,bad)
    file=tmp_path/'submission.json';ref.write(file,value)
    result=ref.submit(path,file)
    assert not ref.read(result['analysis'])['production_ready']
    value['whole_piece']='different interpretation';ref.write(file,value)
    with pytest.raises(ValueError,match='已有不同分析'):ref.submit(path,file)


def test_comparison_binds_actual_evidence_and_is_not_a_quality_verdict(real_task,tmp_path):
    path,_=real_task;task=ref.load(path)
    mapping=tmp_path/'mapping.json'
    ref.write(mapping,[{'reference_frame':task['frames'][0]['id'],
        'target_frame':task['frames'][1]['id'],'reason':'同一动作的连续阶段；测试显式映射'}])
    result=ref.compare(path,path,mapping,tmp_path/'compare')
    saved=ref.read(result['comparison'])
    assert saved['visual_judgment']=='pending'
    assert not saved['production_ready']
    assert saved['identity']['pairs'][0]['target']['at']!=saved['identity']['pairs'][0]['reference']['at']


def test_exact_single_frame_windows_keep_fractional_seek_boundaries(tmp_path):
    pair=resolve_ffmpeg_pair()
    if not pair:pytest.skip('FFmpeg/ffprobe unavailable')
    source=tmp_path/'sixty.mp4'
    subprocess.run([pair[0],'-nostdin','-v','error','-f','lavfi','-i','color=s=96x160:r=60:d=1',
        '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    expected=[27,41,59]
    result=ref.prepare(source,tmp_path/'evidence',ffmpeg=pair[0],ffprobe=pair[1],model='test-agent',
        selected_ranges=[f'{f/60}:{(f+.9)/60}' for f in expected],every_frame=True,cell_width=240)
    task=ref.load(result['task'])
    assert len(task['frames'])==3
    assert all(abs(row['at']-f/60)<1e-5 for row,f in zip(task['frames'],expected))
    from PIL import Image
    with Image.open(task['grids'][0]['path']) as grid:
        assert grid.height>grid.width # portrait pictures get portrait cells
