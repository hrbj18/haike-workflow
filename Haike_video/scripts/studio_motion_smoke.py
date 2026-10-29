"""Run a supplied, already generated speech clip through the native motion queue.

No supplier/API call, no external publication, no final work confirmation.
This is a technical fixture: cue placement is explicitly recorded for test playback.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio, atomic_private
from backlot.studio_motion import TEMPLATE_ID, plan, freeze, narration_clock
from backlot.studio_render import media_probe
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from lib.checkpoint import init_project


def main():
    p = argparse.ArgumentParser(); p.add_argument('video', type=Path); p.add_argument('root', type=Path); p.add_argument('--plan-only', action='store_true'); p.add_argument('--quick', action='store_true'); p.add_argument('--quick-kind',choices=['hero','point','number','compare','steps','quote','demo','checklist','outro']);p.add_argument('--image',type=Path);p.add_argument('--audio-caption-fixture',action='store_true');a = p.parse_args()
    a.root = a.root.resolve(); a.video = a.video.resolve()
    a.root.mkdir(parents=True, exist_ok=True); projects = a.root / 'projects'; projects.mkdir(exist_ok=True)
    s = Studio(projects); text = '海客科技，让创作更简单。一个接口，连接配音、数字人和创作工作流。'
    d = s.save_draft({'template_id': TEMPLATE_ID, 'title': '海客动效口播·技术验收', 'text': text})
    asset = s.save_asset(d['id'], 'existing-narration.mp4', 'video', a.video.read_bytes()); duration = narration_clock(media_probe(a.video))['duration']
    d = s.save_draft({**d, 'input': {'source': asset, 'motionLayout': 'portrait', 'style': '01-D', 'music': {'mode': 'none'}, 'captions': [],
              'face': {'mode': 'fixed', 'cx': .5, 'cy': .4, 'h': .55},
              'segments': [{'group': '01-D:basic-keyword', 'text': text, 'end': duration, 'values': {'heading': '海客科技', 'body-0': '一个接口，连接配音、数字人和创作工作流。'}, 'anchors': {'entry': 0, 'reading': 1.4}}]}})
    if a.quick or a.quick_kind:
        from backlot.studio_motion_quick import DEFINITIONS
        kind=a.quick_kind or 'hero'
        fixtures={
            'hero':{'line1':'海客科技','line2':'连接创作','sub':'一个接口，连接配音、数字人与创作。'},
            'point':{'word1':'统一接入','word2':'创作工作流','cards':'配音\n数字人\n创作'},
            'number':{'label':'统一接入','value':1,'from':0,'unit':'个接口','sub':'一个接口，连接配音、数字人和创作工作流。'},
            'compare':{'leftTitle':'准备内容','rightTitle':'创作工作流','leftItems':'文案\n声音','rightItems':'配音\n数字人','stamp':'连接'},
            'steps':{'title':'创作流程','steps':'准备文案\n选择声音\n数字人口播'},
            'quote':{'lines':'海客科技\n让创作更简单','by':'海客科技'},
            'demo':{'title':'海客工作台','features':'选择模板\n安排分镜\n观看成片'},
            'checklist':{'title':'制作检查','items':'文案\n声音\n人物'},
            'outro':{'title':'海客科技','lines':'让创作更简单','prompt':'连接配音、数字人与创作工作流。'},
        }
        values=fixtures[kind]
        if kind=='demo':
            if not a.image:raise ValueError('--image is required for demo')
            values['image']={'asset':s.save_asset(d['id'],'owned-product.png','image',a.image.read_bytes())}
        anchors={r:0 if i==0 else 1.4+(i-1)*.5 for i,r in enumerate(DEFINITIONS[kind][1])}
        d=s.save_draft({**d,'input':{**d['input'],'motionLayout':'landscape','style':'quick','segments':[{'group':'quick:'+kind,'text':text,'end':duration,'values':values,'anchors':anchors}]}})
    if a.audio_caption_fixture:
        # A quiet locally synthesized QA tone, explicitly not a production score.
        import wave,math,struct
        tone=a.root/'qa-tone.wav'
        with wave.open(str(tone),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
            wav.writeframes(b''.join(struct.pack('<h',round(300*math.sin(2*math.pi*220*i/48000))) for i in range(round(duration*48000))))
        music=s.save_asset(d['id'],'qa-tone.wav','audio',tone.read_bytes())
        captions=[{'start':0,'end':1.4,'text':'海客科技，让创作更简单。','en':'Haike makes creation easier.'},
                  {'start':1.4,'end':duration,'text':'一个接口，连接配音、数字人和创作工作流。','en':'One interface for voice, avatars and creation.'}]
        d=s.save_draft({**d,'input':{**d['input'],'music':{'mode':'track','asset':music,'offset':0},'captions':captions,'subtitleBottom':.06}})
    result = plan(s,d); atomic_private(a.root/'plan-summary.json', result)
    print(json.dumps({'plan_ready':result['report']['ready'], 'status':result['report']['status'], 'draft':d['id'], 'details':str(a.root/'plan-summary.json')}, ensure_ascii=False),flush=True)
    if a.plan_only or not result['report']['ready']: return
    init_project(d['id'], title=d['title'], pipeline_type='animated-explainer', pipeline_dir=projects)
    q = ProductionQueue(a.root/'queue.sqlite3',projects)
    job = q.submit(project_id=d['id'],kind='studio_motion',source='workbench',priority='normal',parent_job_id='studio-'+str(d['revision']),idempotency_key=f"motion-smoke:{d['id']}:{d['revision']}",frozen_request=freeze(s,d,result['id'],True))
    worker = ProductionQueueWorker(q,projects); worker.run_once()
    job = q.get(job['job_id']); atomic_private(a.root/'summary.json',{'job':job,'paid_calls':0,'external_publishes':0,'human_review':'pending'})
    print(json.dumps({'status':job['status'],'stage':job['stage'],'summary':str(a.root/'summary.json')},ensure_ascii=False))


if __name__=='__main__': main()
