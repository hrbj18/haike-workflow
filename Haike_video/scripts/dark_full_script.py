"""Prepare a full-template input from script + reviewed material recipe.

This facade never renders or publishes. New speech/ASR needs quote then explicit
confirmation; resume uses the same durable operation. Run with the project venv.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backlot.studio import Studio
from backlot.studio_dark_full_script import ScriptFacade,read
from backlot.work_catalog import WorkError


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['check','quote','confirm','resume','plan','export'])
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--projects-root',type=Path,default=ROOT/'projects')
    p.add_argument('--request',type=Path,help='JSON with script, full material recipe and optional source-proof reuse')
    p.add_argument('--script-file',type=Path,help='UTF-8 text, or an original script JSON containing text')
    p.add_argument('--recipe',type=Path,help='reviewed full material recipe; plan binds a revision after measuring actual voice duration')
    p.add_argument('--reuse',type=Path,help='JSON with original script/voice_info/captions evidence paths')
    p.add_argument('--events',type=Path,help='JSON motion-to-SFX event list for a new narration clock')
    p.add_argument('--voice-performance',type=Path,help='Local delivery plan; unsupported provider controls are never injected')
    p.add_argument('--title',default='脚本与真实素材短片')
    p.add_argument('--stage',choices=['tts','asr'])
    p.add_argument('--max-charge-micros',type=int)
    p.add_argument('--project-max-micros',type=int,default=1000000)
    p.add_argument('--budget',type=Path)
    p.add_argument('--confirmed',action='store_true')
    a=p.parse_args()
    try:
        if a.request and a.script_file:p.error('--request and --script-file cannot be combined')
        request=read(a.request) if a.request else None
        if a.script_file:
            if not a.recipe:p.error('--script-file requires --recipe')
            script=read(a.script_file)['text'] if a.script_file.suffix.lower()=='.json' else a.script_file.read_text(encoding='utf-8-sig')
            request={'title':a.title,'script':script,'recipe':read(a.recipe)}
            for key,path in [('reuse',a.reuse),('motion_events',a.events),('voice_performance',a.voice_performance)]:
                if path:request[key]=read(path)
        facade=ScriptFacade(Studio(a.projects_root),a.directory,request)
        if a.command=='check':result=facade.inspect()
        elif a.command=='quote':result=facade.quote(a.stage)
        elif a.command=='confirm':
            if not a.budget or a.max_charge_micros is None:p.error('confirm requires --budget and --max-charge-micros')
            result=facade.confirm(a.stage,a.max_charge_micros,a.budget,confirmed=a.confirmed,project_maximum=a.project_max_micros)
        elif a.command=='resume':result=facade.resume(a.stage)
        elif a.command=='plan':
            if not a.recipe:p.error('plan requires --recipe')
            result=facade.bind_recipe(read(a.recipe))
        else:result=facade.export()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except WorkError as e:
        print(json.dumps({'status':'needs_review','message':str(e),'paid_retry_created':False},ensure_ascii=False))
        return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
