"""Targeted v002 schema, source syntax and exact color-role checks. No cloud/render."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
checker=REPO/'Haike-Videohub/verify/check_template_standards.py'
spec=importlib.util.spec_from_file_location('template_standard_check',checker)
checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
results=[]
for n in range(22,27):
    path=HERE/'variants'/str(n)/'video-template-spec.json'
    results.append({'style':n,'errors':checks.check_spec(load(path),path.parent)})

def light(values):
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(linear,[.2126,.7152,.0722]))

def contrast(a,b):
    a,b=light(a),light(b)
    return (max(a,b)+.05)/(min(a,b)+.05)

representation=[];pairs=[]
geo=load(HERE/'layout.json')
for style,roles in load(HERE/'tokens.json')['color'].items():
    for role,token in roles.items():
        value=token['$value']
        if any(abs(int(value['hex'][i*2+1:i*2+3],16)/255-value['components'][i])>1e-9 for i in range(3)):
            representation.append([style,role])
    assert roles['ground']['$value']['hex']==geo['states'][style]['a']
    assert roles['ink']['$value']['hex']==geo['states'][style]['b']
    values=lambda role:roles[role]['$value']['components']
    row={'style':int(style),'large_display_pair':round(contrast(values('ground'),values('ink')),3),
        'caption_pair':round(contrast(values('captionGround'),values('captionInk')),3),
        'location_pair':round(contrast(values('locationGround'),values('locationInk')),3)}
    assert row['large_display_pair']>=3, row
    assert row['caption_pair']>=4.5 and row['location_pair']>=4.5, row
    pairs.append(row)
code="const e=require('./prototypes/haike-avatar-generator/node_modules/esbuild');const fs=require('fs');const r=e.transformSync(fs.readFileSync('Haike_video/templates/store-opening-v1/index.tsx','utf8'),{loader:'tsx',format:'esm',target:'es2022'});console.log(JSON.stringify({warnings:r.warnings,compiled_bytes:r.code.length}));"
compiled=subprocess.run(['node','-e',code],cwd=REPO,capture_output=True,text=True,encoding='utf-8',check=True)
parsed=json.loads(compiled.stdout)
report={'scope':'Current v002 schemas, current source syntax and declared sRGB color roles only; no visual or video certification',
    'results':results,'tsx_syntax':parsed,'token_color_representation_errors':representation,
    'contrast_pairs':pairs,'source_sha256':hashlib.sha256((HERE/'index.tsx').read_bytes()).hexdigest(),
    'layout_sha256':hashlib.sha256((HERE/'layout.json').read_bytes()).hexdigest(),
    'contrast_scope':'23/24 color-on-color is large display only. Body roles checked separately. Encoded/native worst-frame review remains required.',
    'rendered_visual_review':'Not evaluated by this static checker; current actual native/375px author and root reviews are recorded separately. Old v001 is not inherited.'}
(HERE/'STATIC-REVIEW.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(HERE/'contrast-check.json').write_text(json.dumps({'method':'declared sRGB role swatches; not encoded-frame proof','pairs':pairs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not representation and not any(x['errors'] for x in results) and not parsed['warnings']
print(json.dumps(report,ensure_ascii=False))
