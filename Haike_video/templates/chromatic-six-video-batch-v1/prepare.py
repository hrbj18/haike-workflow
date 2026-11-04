"""Aggregate completed window handoffs and exact video inputs; no media providers."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent

def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()

def local(value):
    file=(ROOT/value).resolve()
    if not file.is_relative_to(ROOT) or not file.exists():raise ValueError('Missing/external input: '+str(value))
    return file

def prepare(output):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT/'.local'):raise ValueError('Private .local output required')
    staged=[];seen=set()
    for window,numbers in [('a',{6,7}),('b',{8,9}),('c',{10,11})]:
        handoff=HERE/f'window-{window}/HANDOFF.json'
        data=json.loads(handoff.read_text('utf-8'))
        if data['schema']!='haike.video-window-handoff/1' or data['windowId']!=window:raise ValueError('Window handoff identity mismatch')
        if 'complete' not in data['status']:raise ValueError('Window not complete: '+window)
        if {int(t['number']) for t in data['templates']}!=numbers:raise ValueError('Two expected templates required')
        preview=local(data['previewDirectory']);manifest_file=local(data['buildManifest'])
        manifest=json.loads(manifest_file.read_text('utf-8'))
        for group in ('sources','inputs','assets','outputs'):
            for item in manifest.get(group,[]):
                if item.get('virtual'):continue
                file=Path(item['path']) if group in ('sources','inputs') else preview/item['path']
                if not file.is_file() or sha(file)!=item['sha256']:raise ValueError('Window identity changed: '+str(file))
        assets=preview/'assets'/window
        if not assets.is_dir():raise ValueError('Prefixed assets required: '+window)
        for template in data['templates']:
            number=int(template['number'])
            if number in seen:raise ValueError('Duplicate template number')
            seen.add(number)
            source=local(template['source']);episode_file=local(template['episode'])
            episode=json.loads(episode_file.read_text('utf-8'))
            if episode.get('durationInFrames')!=720:raise ValueError('720-frame input required')
            staged.append((window,template,source,episode_file,preview,assets,manifest_file,handoff,data['fontUrl']))
    output.mkdir(parents=True,exist_ok=True);(output/'episodes').mkdir(exist_ok=True)
    rows=[];asset_records={}
    for window,t,source,episode_file,preview,assets,manifest,handoff,font in staged:
        shutil.copytree(assets,output/'assets'/window,dirs_exist_ok=True)
        target=f'episodes/{int(t["number"]):02d}.json';shutil.copyfile(episode_file,output/target)
        rows.append(dict(number=int(t['number']),templateId=t['templateId'],version=t['version'],source=str(source),sourceSha256=sha(source),episode=str(episode_file),episodeSha256=sha(episode_file),target=target,manifest=str(manifest),manifestSha256=sha(manifest),handoff=str(handoff),handoffSha256=sha(handoff)))
        for file in assets.rglob('*'):
            if file.is_file():
                rel='assets/'+window+'/'+file.relative_to(assets).as_posix();asset_records[rel]=dict(path=rel,sha256=sha(file))
    font_url=staged[0][-1]
    if not font_url.startswith('/assets/a/') or not (output/font_url.lstrip('/')).is_file():raise ValueError('Actual loaded font missing')
    bindings=dict(schema='haike.six-real-video-inputs/1',fontUrl=font_url,templates=rows)
    (output/'input-bindings.json').write_text(json.dumps(bindings,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'assets-manifest.json').write_text(json.dumps(list(asset_records.values()),indent=2)+'\n',encoding='utf-8')
    return dict(output=str(output),templates=len(rows),assets=len(asset_records))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'.local/chromatic-six-video-batch')
    print(json.dumps(prepare(p.parse_args().output),ensure_ascii=False))
