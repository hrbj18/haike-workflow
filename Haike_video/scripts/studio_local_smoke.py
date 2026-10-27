"""Isolated native studio composition smoke; existing local media, zero cloud calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.studio_render import run_graphic
from backlot.studio_composition import compose_avatar
from lib.ffmpeg_locator import resolve_ffmpeg_pair

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--media',type=Path,required=True);p.add_argument('--portrait',type=Path,required=True);a=p.parse_args()
    s=Studio(a.root/'projects')
    d=s.save_draft({'template_id':'graphic-news-v2','title':'图文模板技术验收','input':{'headlines':['海客科技','让创作更简单','图文视频工作流'],'conclusion':'三个画面 · 一个观点','details':[['模板验收','标题与详情清晰','每景三秒']]*3}})
    material=s.save_asset(d['id'],'presenter.png','image',a.portrait.read_bytes())
    d=s.save_draft({**d,'input':{**d['input'],'materials':[material]*3}})
    folder=s.projects_root/d['id'];(folder/'project.json').write_text(json.dumps({'title':d['title']}))
    g=run_graphic(folder,{'draft':d,'render_id':'local-smoke'})
    ffmpeg,_=resolve_ffmpeg_pair();source=a.root/'avatar-3s.mp4';audio=a.root/'audio-3s.wav'
    for target,options in [(source,['-an','-c:v','libx264']),(audio,['-vn','-ac','1','-ar','24000','-c:a','pcm_s16le'])]:
        subprocess.run([ffmpeg,'-v','error','-y','-i',str(a.media),'-t','3',*options,str(target)],check=True)
    rows=[]
    for name in ['avatar-safe-circle-v1','avatar-full-width-v2','avatar-template3-card-3x4-v001']:
        render=a.root/name;render.mkdir(exist_ok=True)
        draft={'template_id':name,'title':'海客科技','text':'海客科技，让创作更简单。一个接口，连接配音、数字人和创作工作流。','layout':{'title_size':60,'accent':'#316dd6'}}
        output=compose_avatar(render,draft,source,audio,3,[{'startMs':0,'endMs':3000,'text':'海客科技，让创作更简单'}])
        rows.append({'template':name,'output':str(output)})
        print(name,'local composition passed',flush=True)
    atomic_private(a.root/'summary.json',{'graphic':g,'avatar':rows,'paid_calls':0,'external_publishes':0})
if __name__=='__main__':main()
