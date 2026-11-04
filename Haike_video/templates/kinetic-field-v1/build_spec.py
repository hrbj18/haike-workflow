"""Build a bounded implementation specification for the 16-second visual test."""
import copy
import importlib.util
import json
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
plan=json.loads((HERE/'layout.json').read_bytes())
spec=json.loads((HERE.parent/'animation-signatures-v2/specs/phone-portal.json').read_bytes())
spec.update(template_id='kinetic-field-v1',template_version=plan['version'],stage='specification')
spec['authority']={'runbook':'README.md','implementation_paths':['index.tsx','layout.json','render.cjs','prepare.py','../../scripts/kinetic_field_preview.py'],'parameter_source':'layout.json owns scene/action/global clock; index.tsx owns per-object geometry and local interpolation. Source and assets frozen by queue.'}
spec['canvas'].update(width=540,height=960,fps=24,duration_seconds=16,clock='Original mix14.8..30.8 at original speed;384frames;270x480 test output.')
spec['narrative']={'purpose':'Real media participates in staged motion; reference-led richness test.','information_hierarchy':['Real subject','Persistent short topic','Sequential emphasis','Quiet supporting texture'],'structure':[s['id'] for s in plan['scenes']]}
prototype=copy.deepcopy(spec['elements'][0]);spec['elements']=[]
rows=[('background','background',0,16,'Persistent halftone/cobalt/coral geometry'),('title','text',0,16,'Permanent six-character topic')]
rows += [(r['id'],'media',r['from'],r['until'],r['purpose']) for r in plan['scenes']]
for key,kind,start,end,purpose in rows:
    e=copy.deepcopy(prototype);e.update(id=key,type=kind,role=purpose,z_index=100 if key=='title' else 2)
    e['content'].update(description=purpose,mode='editable' if key=='title' else 'generated',binding='topic' if key=='title' else None)
    e['layout']['style']={'authority':'index.tsx scene function '+key};e['timing'].update(start=start,end=end)
    if key=='title':
        e['replaceable']=['layout.title']
        e['layout']['style'].update(font='Haike Sans/local Noto SC',font_size=25,max_lines=1,overflow='Shorten topic before rendering; never shrink to unreadable size.')
    e['states']=[{'id':'active','visible':True,'description':'Exact child objects, masks and states in index.tsx; no empty scene first frame.'}]
    e['acceptance']=[{'check':'actual-scene','method':'Source-bound entry/middle/exit images and encoded output','pass_condition':'Real main subject is clear; no verbal sentences; meaning of emphasis visible; no accidental mask gaps.'}]
    spec['elements'].append(e)
spec['scenes']=[{'id':r['id'],'start':r['from'],'end':r['until'],'purpose':r['purpose'],'element_ids':['background','title',r['id']],'variant':r['id']} for r in plan['scenes']]
spec['assets'][0]['source']='Private episode.json verifies six video proxies, four actual photos and original local mix14.8..30.8.'
spec['evidence']=[{'id':'design','source_kind':'design','source':'User asks a single test after rejecting sparse moving frames. Actual reference21..36 observed separately in private evidence.','locator':'layout.json/reference and index.tsx','method':'Reference-led portrait art direction; source-bound actual keyframe review.','file':'layout.json','sha256':None}]
for name,row in spec['validation'].items():row.update(status='pending',note='This16-second sample only; separate technical, actual visual, user aesthetic, listening, phone and production statuses.')
spec['extensions']['avatar']={'face_crop':'Location lower window and final oval; source original background retained, anchor50%28%/25%.','synchronization':'Output8..12 host-close(source22.8..26.8),12..16 host-open(source26.8..30.8);audio source14.8..30.8. No loop or stretch.'}
spec['extensions']['material_edit']={'source_ranges':'index.tsx Clip calls own exact source clocks:robot/dog0..3.65;children3..6.4;store2..6.6;photos actual1s source; avatar exact paired intervals.','cut_policy':'Real subject maintained on both sides of iris/wipe. Photos only for B-roll. No blank scene or raw speech text.'}
spec['extensions']['motion_language']={'contract':'kinetic-field-test-v1','rules':['Sequential primary actions; paired labels count as one reveal group.','Actual reference action mapping required; no same-container repetition as richness proof.'],'taste_profile':plan['taste_profile'],'actions':plan['primary_actions']}
spec['operations']=[{'id':'prepare','entrypoint':'prepare.py --source <verified> --data <private> --ffmpeg <runtime>','input':'Verified local source manifest.','action':'Copy media and trim full-sentence16s audio.','output':'episode/public','completion':'SHA and exact source clocks valid; zero provider calls.','recovery':'Keep originals and existing paid assets.'},{'id':'stills','entrypoint':'../../scripts/kinetic_field_preview.py --phase stills --install-root <install> --data <private>','input':'Source/schema/assets/bundle.','action':'Owned unified queue renders critical states.','output':'stills-job and actual PNGs','completion':'Actual review of images, source-bound design-review.','recovery':'Fix source then refreeze.'},{'id':'video','entrypoint':'../../scripts/kinetic_field_preview.py --phase video --install-root <install> --data <private>','input':'Matching source-bound actual image review.','action':'Owned queue renders one16s test.','output':'MP4/proofs and local comparison page','completion':'Decode, critical frames, audio metrics; subjective acceptance remains separate.','recovery':'Read original queue/output before retry.'}]
# The approved design is ready for this bounded16-second input contract only.
contract=json.loads((HERE/'input-contract.json').read_bytes())
spec['authority']['implementation_paths']+=['content.json','input-contract.json','content-contract.cjs','prepare_inputs.py','verify-release.cjs']
spec['authority']['parameter_source']='layout.json'
spec['canvas']['clock']='16-second whole-utterance audio,24fps; source media remains original speed. Outputs8..12 and12..16 use matching presenter intervals.'
spec['narrative']['purpose']='动效模板2 · 活力现场：用户已确认五段撞色编排，按每期独立输入受控复用。'
spec['assets'][0]['source']='Private episode.json binds input-contract.json media slots bySHA; new files never alter the template.'
spec['assets'][1]['source']='Private public/sample.wav:16-second full-utterance mix, original speed, gain from layout.json.'
spec['slots']=[]
title=next(e for e in spec['elements'] if e['id']=='title');title['replaceable']=['content.topic'];title['content']['binding']='topic'
text_rows={'topic':('title',0,16,25),'brand':('brand',0,16,17),'upperLabel':('duo',.65,3.65,34),'lowerLabel':('duo',1,3.65,34),'tape':('duo',2.4,3.65,24),'detailTitle':('hands',3.8,6.6,62),'detailLabel':('hands',5.6,6.6,35),'collageLabel':('collage',7.3,8.3,34),'venue':('location',9.3,12,45),'floor':('location',9.3,12,45),'address':('location',7.4,12,23),'closingTitle':('invitation',12.7,16,66),'stamp':('invitation',14.4,16,38)}
for key,(scene,start,end,size) in text_rows.items():
    eid='title' if key=='topic' else 'copy-'+key
    if key!='topic':
        e=copy.deepcopy(title);e.update(id=eid,role=key);e['content'].update(binding=key,description='episode.content.'+key);e['replaceable']=['content.'+key];e['layout']['style'].update(font_size=size,authority='index.tsx '+scene);e['timing'].update(start=start,end=end);spec['elements'].append(e)
        for s in spec['scenes']:
            if scene=='brand' or s['id']==scene:s['element_ids'].append(eid)
    spec['slots'].append({'id':key,'element_id':eid,'property':'content.'+key,'value_type':'string','required':True,'limits':{'max_chinese_equivalent_chars':contract['text_limits'][key]},'missing':'New episodes must provide every short label; no inherited old address.','overflow':'Reject and shorten copy; no raw spoken sentences or tiny font.'})
for name,rule in contract['files'].items():
    spec['slots'].append({'id':'asset-'+name.replace('.','-'),'element_id':'global','property':'episode.files.'+name,'value_type':'asset','required':True,'limits':rule,'missing':'Reject before copying or rendering.','overflow':'Keep full speech; wrong duration needs separate adaptation, never automatic stretch.'})
# Child geometry/animation values have one authority: the corresponding JSX.
objects={'duo':['upper-video','lower-video','split-line','paper'], 'hands':['full-video','loupe','arrow','progress','paper'], 'collage':['robot-photo','store-photo','children-photo','paper'], 'location':['store-video','presenter-video','pin','floor-band','paper'], 'invitation':['burst','presenter-video','photo-fan','title-band','paper']}
for scene,names in objects.items():
    parent=next(e for e in spec['elements'] if e['id']==scene)
    for name in names:
        e=copy.deepcopy(parent);e.update(id=scene+'-'+name,parent_id=scene,role=name);e['layout']['coordinate_space']='parent';e['layout']['style']['authority']='index.tsx '+scene+'/'+name+' exact child geometry, inherited masks and global frame states';spec['elements'].append(e)
        next(s for s in spec['scenes'] if s['id']==scene)['element_ids'].append(e['id'])
spec['extensions']['avatar']['synchronization']='Per-episode master16s; host-close.mp4 locally0..4 maps8..12, host-open.mp4 locally0..4 maps12..16. Actual same-source sync reviewed each episode.'
spec['extensions']['material_edit']['cut_policy']+=' Approved store SHA may hold final photograph-like frame for~1.2s while avatar continues; all new store media require6.6s. See input-contract.json.'
spec['extensions']['reuse']={'contract':contract['contract'],'rules':['Geometry, palette, scene order and all action clocks are fixed atv1.0.0.','Per-episode content and media live outside the template.','Only16-second9:16 low-resolution route is ready; longer audio,1080p and new-phone delivery need separate adaptation/verification.','release.json hashes are checked by render.cjs; modifying design requires a new version.']}
spec['operations'][0].update(entrypoint='prepare_inputs.py --request <private-request.json> --data <new-private-directory> --ffprobe <runtime>',input='All13 copy slots and12 SHA-bound media/font/audio slots; same-source avatar intervals; rights.',action='Validate bounds/durations/identity before copying into new per-episode public folder.',completion='Private episode/public created without modifying template or original assets.',recovery='Existing output rejected; read episode and original queue before continuing.')
approval=HERE/'APPROVAL.json'
if approval.is_file():
    value=json.loads(approval.read_bytes());assert value['visual_regression']['status']=='pass'
    spec['stage']='ready'
    spec['evidence'].append({'id':'accepted-baseline','source_kind':'observation','source':'Actual accepted16-second output, encoded frames, pixel comparison and explicit user confirmation; scope inAPPROVAL.json.','locator':'APPROVAL.json; private paths relative to workspace recorded there','method':'Original full decode,29 source frames/24 encoded frames; current29-frame visual regression; user message.','file':'APPROVAL.json','sha256':hashlib.sha256(approval.read_bytes()).hexdigest()})
    for key in ('structure','technical','visual','user_review'):
        spec['validation'][key].update(status='pass',evidence_ids=['accepted-baseline'],note='Approved16-second low-resolution design and exact default-content regression only; new inputs require their own review.')
    for key in ('audio','platform','production'):
        spec['validation'][key].update(status='pending',evidence_ids=['accepted-baseline'],note='Audio subjective acceptance, actual target phone and general formal/full-HD production not inferred from visual approval. Gallery is visible; bounded CLI queue works.')
path=HERE/'video-template-spec.json';path.write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
checkerpath=HERE.parents[2]/'Haike-Videohub/verify/check_template_standards.py'
mod=importlib.util.spec_from_file_location('standard',checkerpath);checker=importlib.util.module_from_spec(mod);mod.loader.exec_module(checker)
errors=checker.check_spec(spec,HERE)
if errors:raise ValueError(errors)
print('Kinetic field specification: PASS')
