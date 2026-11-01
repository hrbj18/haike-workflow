"""Layout/timing gates and an independent numerical test of the drawing model."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
from backlot import studio_chalkboard as board
from backlot.work_catalog import WorkError


def props():
    return {'width':1440,'height':1800,'fps':60,'durationFrames':600,
        'chapters':[{'id':'one','start':0,'end':10,'title':'同一个球','kind':'orbit','annotation':['连续运动']}],
        'phaseKeys':[[0,0],[10,6.28]],'nodeKeys':[[0,1.57],[10,1.57]],
        'captions':[{'start':1,'end':4,'text':'同一个对象不在换句时重置'}],
        'model':{'orbitRadius':60.3,'bodyRadius':.273,'occluderRadius':1,'sourceRadius':109.2,
                 'sourceDistance':23455,'inclinationDegrees':5.1,'displayInclinationDegrees':20}}


def test_two_real_canvases_and_full_clock():
    p=props()
    assert board.validate(p)==10
    p.update(width=1080,height=1920)
    assert board.validate(p)==10
    p['width']=1920
    with pytest.raises(WorkError,match='画幅'):board.validate(p)


def test_reject_rushed_group_gap_bad_model_and_uncovered_motion():
    for mutation in [
        lambda p:p['chapters'][0].update(end=7),
        lambda p:p['chapters'][0].update(start=.2),
        lambda p:p.update(phaseKeys=[[0,0],[5,2]]),
        lambda p:p['model'].update(bodyRadius=70),
        lambda p:p['captions'][0].update(text='很'*60),
    ]:
        p=props();mutation(p)
        with pytest.raises(WorkError):board.validate(p)


def test_caption_patch_only_reuses_identical_picture_and_measured_clock():
    a=props();b=deepcopy(a);b['captions'][0]['text']='修正转写文字'
    assert board.caption_patch_frames(a,b)==[60,239]
    for mutate in [lambda p:p.update(width=1080),lambda p:p['captions'][0].update(start=1.1),
                   lambda p:p['model'].update(inclinationDegrees=0),lambda p:p.update(audio='different.wav')]:
        c=deepcopy(b);mutate(c)
        with pytest.raises(WorkError):board.caption_patch_frames(a,c)


def test_caption_patch_keeps_full_frame_clock_and_encoded_audio(tmp_path):
    import shutil
    ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('local FFmpeg pair required')
    base,segment,target=[tmp_path/n for n in ['base.mp4','patch.mp4','final.mp4']]
    subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=red:s=64x64:r=30:d=2',
        '-f','lavfi','-i','sine=frequency=1000:duration=2','-c:v','libx264','-pix_fmt','yuv420p',
        '-c:a','aac',str(base)],check=True)
    subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=blue:s=64x64:r=30:d=0.5',
        '-c:v','libx264','-pix_fmt','yuv420p',str(segment)],check=True)
    board.merge_caption_patch(ffmpeg,base,segment,target,[15,29],60,30)
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(target)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert video['nb_frames']=='60' and video['avg_frame_rate']=='30/1'
    def packets(p):
        result=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','a',
            '-show_packets','-show_data_hash','sha256','-of','json',str(p)]))
        return [r['data_hash'] for r in result['packets']]
    assert packets(base)==packets(target)
    raw=subprocess.check_output([ffmpeg,'-nostdin','-v','error','-i',str(target),'-vf','select=eq(n\\,0)+eq(n\\,20)+eq(n\\,59)',
        '-fps_mode','vfr','-pix_fmt','rgb24','-f','rawvideo','-'])
    center=lambda i:raw[i*64*64*3+(32*64+32)*3:i*64*64*3+(32*64+32)*3+3]
    assert center(0)[0]>200 and center(1)[2]>200 and center(2)[0]>200


def test_color_conversion_only_runs_during_encoding_not_stream_copy():
    code="""
const {encodingArgs}=require(process.argv[1]);
const copy=['-i','encoded.mp4','-c:v','copy','final.mp4'];
if(encodingArgs({type:'stitcher',args:copy})!==copy)throw Error('stitch-copy must remain untouched');
const original=['-i','-','-c:v','libx264','encoded.mp4'];
const encoded=encodingArgs({type:'pre-stitcher',args:original});
if(!encoded.includes('-vf')||!encoded.includes('21M')||encoded.at(-1)!=='encoded.mp4'||original.length!==5)throw Error('encoding arguments');
"""
    subprocess.run(['node','-e',code,str(board.DRIVER)],check=True,capture_output=True)


def test_source_audio_mux_preserves_video_and_aligns_decoded_pcm_at_zero(tmp_path):
    import shutil
    import numpy as np
    ffmpeg=shutil.which('ffmpeg');ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('local FFmpeg pair required')
    picture,audio,target=[tmp_path/n for n in ['picture.mp4','source.wav','final.mp4']]
    subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=red:s=64x64:r=30:d=2',
        '-c:v','libx264','-pix_fmt','yuv420p',str(picture)],check=True)
    subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i',
        'anoisesrc=sample_rate=48000:duration=2:color=pink:seed=1234','-ac','2','-c:a','pcm_s16le',str(audio)],check=True)
    board.mux_source_audio(ffmpeg,picture,audio,target,2)
    def packets(path):
        result=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v',
            '-show_packets','-show_data_hash','sha256','-of','json',str(path)]))
        return [(x['pts'],x['data_hash']) for x in result['packets']]
    assert packets(picture)==packets(target)
    def pcm(path):
        return np.frombuffer(subprocess.check_output([ffmpeg,'-nostdin','-v','error','-i',str(path),
            '-vn','-ar','8000','-ac','1','-f','f32le','-']),dtype='<f4').astype('float64')
    a,b=pcm(audio),pcm(target);n=min(len(a),len(b));a,b=a[:n],b[:n]
    assert np.dot(a,b)/np.sqrt(np.dot(a,a)*np.dot(b,b))>.98


def test_geometry_preserves_phase_and_shadow_as_distinct_causes(tmp_path):
    root=Path(__file__).resolve().parents[2]
    harness=tmp_path/'physics.cjs'
    harness.write_text("""
const fs=require('node:fs'),vm=require('node:vm');
const ts=require(process.argv[2]);
const file=process.argv[3];
const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const m={exports:{}};
vm.runInNewContext('(function(exports,module){'+code+'})')(m.exports,m);
const {state,track,overlap,annotationIndex}=m.exports;
const p=JSON.parse(process.argv[4]);
const half=state(p,Math.PI/2,0),full=state(p,Math.PI,0),miss=state(p,Math.PI,Math.PI/2);
if(Math.abs(half.lit-.5)>1e-10||full.blocked<.999||miss.blocked>1e-10)throw Error('phase/shadow coupling');
const keys=[[0,0],[1,.2],[2,4],[4,5]];
let last=-Infinity;
for(let t=0;t<=4;t+=.001){const v=track(keys,t);if(v<last-1e-8||v<0||v>5)throw Error('overshoot');last=v}
for(const k of keys)if(Math.abs(track(keys,k[0])-k[1])>1e-10)throw Error('key drift');
if(Math.abs(overlap(1,1,1)-(2*Math.PI/3-Math.sqrt(3)/2))>1e-10)throw Error('overlap');
const speech=[{start:1,end:2},{start:4,end:5}];
if(annotationIndex(speech,0,10,.5).index!==-1||annotationIndex(speech,0,10,3).index!==0||annotationIndex(speech,0,10,6).index!==1)throw Error('note resets during silence');
console.log('phase, true eclipse, tilted miss, monotone track and exact keys passed');
""",encoding='utf-8')
    result=subprocess.run(['node',str(harness),str(root/'remotion-composer/node_modules/typescript'),
        str(board.TEMPLATE/'physics.ts'),json.dumps(props()['model'])],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
