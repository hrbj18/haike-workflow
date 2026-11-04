"""Index local motion sources without importing components or running providers."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / 'Haike_video/motion-components/catalogue.json'
TALKCRAFT_CONFIG = ROOT / '.local/talkcraft-integration/state/config.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontmatter(path):
    text = path.read_text('utf-8')
    block = text.split('---', 2)[1] if text.startswith('---') else ''
    return dict(re.findall(r'^([^:\n]+):\s*(.*)$', block, re.M))


def build(config_path=TALKCRAFT_CONFIG):
    entries = []
    snap = ROOT / 'Haike_video/motion-components/snapcn'
    names = json.loads((snap / 'catalogue.json').read_text('utf-8'))
    registry = json.loads((snap / 'upstream/registry/snap-cn/registry.json').read_text('utf-8'))
    for item in registry['items']:
        slug = item['name']; source = snap / 'upstream/registry/snap-cn' / slug / 'index.tsx'
        entries.append({'id':'snapcn:'+slug,'origin':'snapcn','name':names[slug][0],
            'category':names[slug][1],'purpose':names[slug][2],
            'source':source.relative_to(ROOT).as_posix(),'source_sha256':digest(source),
            'runtime_modes':{'haike-remotion':'direct','design-only':'reference'},
            'validation':'existing-gallery-scope; new content/layout needs checking'})
    upstream = Path(json.loads(Path(config_path).read_text('utf-8'))['upstream'])
    for source in sorted((upstream / 'template/cards').glob('*.tsx')):
        slug=source.stem; doc=upstream/'references/cards'/f'{slug}.md'; meta=frontmatter(doc)
        text=source.read_text('utf-8')
        native={key:int(value) for key,value in re.findall(r'\b(width|height|fps|durationInFrames):\s*(\d+)\b',text[:1800])}
        entries.append({'id':'talkcraft:'+slug,'origin':'talkcraft','name':meta.get('标题',slug),
            'category':meta.get('类别','unclassified'),'purpose':meta.get('适用',''),
            'input_kind':meta.get('输入','unknown'),'semantics':meta.get('语义','unknown'),
            'source':'talkcraft://template/cards/'+source.name,'source_sha256':digest(source),
            'reference':'talkcraft://references/cards/'+slug+'.md','reference_sha256':digest(doc),
            'native':native,'runtime_modes':{'talkcraft-native':'direct','haike-remotion':'adapt','design-only':'reference'},
            'license':'upstream private installation; noncommercial research scope; no source redistributed',
            'validation':'catalogued; native prior checks and new host adaptation are separate'})
    remocn=ROOT/'Haike_video/templates/hum-production-v1/vendor/remocn'
    for source in sorted(remocn.glob('*.tsx')):
        entries.append({'id':'remocn:'+source.stem,'origin':'remocn','name':source.stem,
            'category':'material-or-transition','purpose':'inspect local source and template adapter',
            'source':source.relative_to(ROOT).as_posix(),'source_sha256':digest(source),
            'runtime_modes':{'haike-remotion':'direct','design-only':'reference'},'validation':'per-template evidence'})
    source=ROOT/'Haike_video/templates/hum-production-v1/dynamic/motion.ts'
    for slug in ['waterfall','reflow','click-open','spatial-gallery']:
        entries.append({'id':'haike:'+slug,'origin':'haike','name':slug,'category':'material',
            'purpose':'existing deterministic media choreography','source':source.relative_to(ROOT).as_posix(),
            'source_sha256':digest(source),'runtime_modes':{'haike-remotion':'direct','design-only':'reference'},
            'validation':'existing dynamic/Chromatic adapters; new layout needs checking'})
    return {'schema':'haike.motion-catalogue/1','revision':'2026-11-03.1',
        'counting':'unique origin-qualified component/action IDs; presets/backgrounds/SFX/grammar references not added',
        'counts':dict(Counter(e['origin'] for e in entries)),'total':len(entries),'entries':entries}


def query(catalogue, text='', runtime='haike-remotion', mode=None):
    return [dict(e, use_mode=e['runtime_modes'].get(runtime,'reference')) for e in catalogue['entries']
            if (not text or text.casefold() in json.dumps(e,ensure_ascii=False).casefold())
            and (not mode or e['runtime_modes'].get(runtime,'reference')==mode)]


def validate_selection(plan, catalogue, root=ROOT):
    if type(plan.get('minReadingFrames')) is not int or plan['minReadingFrames']<=0 or type(plan.get('durationInFrames')) is not int or plan['durationInFrames']<=0:
        raise ValueError('positive integer reading budget and episode duration required')
    index={e['id']:e for e in catalogue['entries']}
    seen=set()
    for scene in plan['scenes']:
        if any(type(scene.get(k)) is not int for k in ('from','to','stableFrom')) or not 0<=scene['from']<=scene['stableFrom']<scene['to']:
            raise ValueError('invalid scene clock or stable interval')
        if not scene.get('purpose') or not scene.get('subject') or not scene.get('handoff'):
            raise ValueError('scene needs purpose, subject and handoff')
        if scene['from'] in seen:raise ValueError('duplicate scene start')
        seen.add(scene['from'])
        if scene['to']-scene['stableFrom']<plan['minReadingFrames']:
            raise ValueError('reading hold is too short')
        if not any(s['mode'] in {'direct','adapt'} for s in scene['selections']):
            raise ValueError('reference alone is not an implemented motion')
        for selection in scene['selections']:
            entry=index.get(selection['id'])
            if entry is None:raise ValueError('unknown motion ID: '+selection['id'])
            expected=entry['runtime_modes'].get(plan['runtime'],'reference')
            if selection['mode'] not in {'direct','adapt','reference'}:raise ValueError('unknown use mode')
            if selection['mode']=='direct' and expected!='direct':raise ValueError('cross-runtime component requires adaptation')
            if not selection.get('reason') or not selection.get('verification'):raise ValueError('missing selection rationale/evidence criteria')
            if selection.get('source_sha256')!=entry['source_sha256']:raise ValueError('selection source revision changed')
            if selection['mode']!='reference':
                implementation=(root/selection.get('implementation','')).resolve()
                if not implementation.is_relative_to(root.resolve()) or not implementation.is_file():raise ValueError('implementation is missing or outside repository')
            if selection['mode']=='adapt' and not selection.get('changes'):raise ValueError('adaptation changes are missing')
        for alternative in scene.get('alternatives',[]):
            if alternative['id'] not in index or not alternative.get('reason'):raise ValueError('invalid alternative')
    scenes=plan['scenes']
    if not scenes or scenes[0]['from']!=0 or scenes[-1]['to']!=plan['durationInFrames'] or any(a['to']!=b['from'] for a,b in zip(scenes,scenes[1:])):
        raise ValueError('scenes must cover the exact episode clock')
    return {'valid':True,'scenes':len(scenes),'implemented':sorted({s['id'] for c in scenes for s in c['selections'] if s['mode']!='reference'}),
            'references':sorted({s['id'] for c in scenes for s in c['selections'] if s['mode']=='reference'})}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['refresh','list','check'])
    p.add_argument('--query',default='');p.add_argument('--runtime',default='haike-remotion');p.add_argument('--mode',choices=['direct','adapt','reference'])
    p.add_argument('--plan',type=Path);p.add_argument('--talkcraft-config',type=Path,default=TALKCRAFT_CONFIG)
    a=p.parse_args()
    if a.action=='refresh':
        result=build(a.talkcraft_config);CATALOGUE.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'total':result['total'],'counts':result['counts']},ensure_ascii=False));return
    c=json.loads(CATALOGUE.read_text('utf-8'))
    if a.action=='check' and a.plan is None:p.error('check requires --plan')
    result=validate_selection(json.loads(a.plan.read_text('utf-8')),c) if a.action=='check' else query(c,a.query,a.runtime,a.mode)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
