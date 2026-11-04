"""Read-only scoped structural checks for the six delivered video revisions."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def collect():
    standard=load('scoped_video_standard',ROOT/'Haike-Videohub/verify/check_template_standards.py')
    motions=load('video_motion_catalogue',ROOT/'Haike_video/scripts/motion_catalogue.py')
    catalogue=json.loads((ROOT/'Haike_video/motion-components/catalogue.json').read_text('utf-8'))
    result=[]
    for window,numbers in [('a',{6,7}),('b',{8,9}),('c',{10,11})]:
        handoff=json.loads((HERE/f'window-{window}/HANDOFF.json').read_text('utf-8'))
        if {int(t['number']) for t in handoff['templates']}!=numbers:raise ValueError('Wrong handoff numbers')
        for template in handoff['templates']:
            spec_file=ROOT/template['spec'];selection_file=ROOT/template['selection'];source=ROOT/template['source']
            spec=json.loads(spec_file.read_text('utf-8'));selection=json.loads(selection_file.read_text('utf-8'))
            errors=standard.check_spec(spec,spec_file.parent)
            if errors:raise ValueError((template['number'],errors))
            if spec['template_id']!=template['templateId'] or spec['template_version']!=template['version']:raise ValueError('Spec identity mismatch')
            checked=motions.validate_selection(selection,catalogue)
            result.append(dict(number=int(template['number']),templateId=template['templateId'],version=template['version'],source=source.relative_to(ROOT).as_posix(),sourceSha256=sha(source),spec=spec_file.relative_to(ROOT).as_posix(),specSha256=sha(spec_file),selection=selection_file.relative_to(ROOT).as_posix(),selectionSha256=sha(selection_file),selection_check=checked))
    directory=ROOT/'.local/chromatic-six-video-batch-review';directory.mkdir(parents=True,exist_ok=True)
    (directory/'structural-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dict(valid=True,scoped_specs=len(result),selections=len(result))

if __name__=='__main__':print(json.dumps(collect(),ensure_ascii=False))
