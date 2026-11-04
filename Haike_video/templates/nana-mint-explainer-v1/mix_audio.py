"""Local fixed-template music recipe. Invoke only inside the project queue stage."""
from pathlib import Path
import argparse,json,math,subprocess
from frozen_release import verify

HERE=Path(__file__).resolve().parent
def mix(voice,music,duration,output,ffmpeg,ffprobe):
    verify();profile=json.loads((HERE/'template-profile.json').read_bytes());a=profile['audio']
    if not math.isfinite(duration) or not 0<duration<=120:raise ValueError('请提供完整实际音轨时长，范围0–120秒。')
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('混音目标已有内容，请恢复原任务，不覆盖。')
    output.mkdir(parents=True,exist_ok=True)
    probe=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-show_format','-of','json',str(music)],creationflags=0x08000000))
    length=float(probe['format']['duration']);cross=a['crossfade_seconds']
    if length<=cross:raise ValueError('音乐太短，不能按定稿交叉淡化衔接。')
    count=max(1,math.ceil((duration-cross)/(length-cross)))
    def run(*args):
        p=subprocess.run([str(ffmpeg),'-nostdin','-hide_banner','-v','error','-y',*map(str,args)],capture_output=True,timeout=180,creationflags=0x08000000)
        if p.returncode:raise RuntimeError(p.stderr.decode('utf-8',errors='replace')[-2400:])
    if count==1:graph='[0:a]aresample=48000[loop]'
    else:
        graph=f'[0:a]aresample=48000,asplit={count}'+''.join(f'[a{i}]' for i in range(count))+';'
        previous='a0'
        for i in range(1,count):
            label='loop' if i==count-1 else f'join{i}'
            graph+=f'[{previous}][a{i}]acrossfade=d={cross}:c1=qsin:c2=qsin[{label}];';previous=label
        graph=graph.rstrip(';')
    graph+=f";[loop]atrim=duration={duration},asetpts=PTS-STARTPTS,highpass=f={a['highpass_hz']},equalizer=f={a['presence_eq_hz']}:t=q:w=1:g={a['presence_eq_gain_db']},volume={a['music_base_gain_db']}dB,afade=t=in:st=0:d={a['fade_in_seconds']},afade=t=out:st={max(0,duration-a['fade_out_seconds'])}:d={min(duration,a['fade_out_seconds'])}[music]"
    run('-i',music,'-filter_complex',graph,'-map','[music]','-ac',2,'-ar',48000,'-c:a','pcm_f32le',output/'music-shaped.wav')
    run('-i',voice,'-af',f"volume={a['speech_gain_db']}dB,aresample=48000,apad=whole_dur={duration},atrim=duration={duration}",'-ac',2,'-ar',48000,'-c:a','pcm_f32le',output/'speech-stem.wav')
    sc=a['sidechain'];graph=f"[0:a][1:a]sidechaincompress=threshold={sc['threshold']}:ratio={sc['ratio']}:attack={sc['attack_ms']}:release={sc['release_ms']}:mix={sc['mix']}[bed]"
    run('-i',output/'music-shaped.wav','-i',output/'speech-stem.wav','-filter_complex',graph,'-map','[bed]','-t',duration,'-ac',2,'-ar',48000,'-c:a','pcm_f32le',output/'music-ducked-base.wav')
    previous=output/'music-ducked-base.wav'
    for i,gain in enumerate(a['post_duck_gain_stages_db']):
        target=output/f'music-gain-{i}.wav';run('-i',previous,'-af',f'volume={gain}dB','-c:a','pcm_f32le',target);previous=target
    limiter=a['limiter'];graph=f"[0:a][1:a]amix=inputs=2:duration=first:normalize=0,aresample={limiter['oversample_hz']},alimiter=limit={limiter['linear_limit']}:attack={limiter['attack_ms']}:release={limiter['release_ms']}:level=false:latency=true,aresample=48000[out]"
    run('-i',output/'speech-stem.wav','-i',previous,'-filter_complex',graph,'-map','[out]','-t',duration,'-ac',2,'-ar',48000,'-c:a','pcm_s16le',output/'mix.wav')
    (output/'recipe.json').write_text(json.dumps({'template_id':profile['template_id'],'template_version':profile['version'],'voice':str(Path(voice).resolve()),'music':str(Path(music).resolve()),'duration':duration,'music_passes':count,'audio':a,'new_paid_calls':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return output/'mix.wav'
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--voice',type=Path,required=True);p.add_argument('--music',type=Path,required=True);p.add_argument('--duration',type=float,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ffmpeg',required=True);p.add_argument('--ffprobe',required=True);args=p.parse_args()
    print(mix(args.voice,args.music,args.duration,args.output,args.ffmpeg,args.ffprobe))
