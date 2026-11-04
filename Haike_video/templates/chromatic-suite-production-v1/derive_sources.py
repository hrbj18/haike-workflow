"""Author independent copies of task-owned source functions; never edit freezes.

Only media-clock ownership and entry exports change here. All source geometry,
paths, layout formulas, easing and original small labels stay in derived files.
The production root provides new headlines/captions and real semantic events.
"""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BATCH=ROOT/'Haike_video/templates/chromatic-six-video-batch-v1'


def replace_function(source,start,end,new):
 a=source.index(start);b=source.index(end,a);return source[:a]+new+'\n'+source[b:]


def derive():
 records=[]
 for letter in ('a','b','c'):
  path=BATCH/f'window-{letter}/Scene.tsx';s=path.read_text('utf-8')
  s=s.replace("import {AbsoluteFill,Sequence,Video,useCurrentFrame} from 'remotion';", "import {AbsoluteFill,Sequence,Video} from 'remotion';\nimport {useCurrentFrame,useGlobalFrame,useScene,Media} from './Runtime';")
  s=s.replace("import {AbsoluteFill, Sequence, Video, useCurrentFrame} from 'remotion';", "import {AbsoluteFill,Sequence,Video} from 'remotion';\nimport {useCurrentFrame,useGlobalFrame,useScene,Media} from './Runtime';")
  s=re.sub(r"import type \{Episode(?: as BaseEpisode)?\} from '[^']+';",'type Episode=any; type BaseEpisode=any;',s)
  if letter=='a':
   s=s.replace("export {Template06} from '../../chromatic-06-video-v1/Scene';",'')
   s=s.replace('type Episode=any; type BaseEpisode=any;','type BaseEpisode=any;')
   s=replace_function(s,'function Material(','function Presenter(',"function Material({n}:{episode:Episode;n:number}){return <Media id={String(n)}/>;}")
   s=s[:s.index('export function Template07')]
   # The measured robot/hand track follows actual source frames and only its
   # original measured extent. Stroke timing follows semantic motion separately.
   s=s.replace('const f=useCurrentFrame();let k=0;while',
     'const draw=useCurrentFrame()-420,f=useGlobalFrame()-useScene().from;if(f>164)return null;let k=0;while')
   s=s.replace('<Mark f={f}', '<Mark f={draw}')
   s+='\nexport {StickerMaterial};\n'
  elif letter=='b':
   s=replace_function(s,'function Clip(','function Material(',"function Clip({id,style=fit}:{episode:Episode;id:string;style?:React.CSSProperties}){return <Media id={id} style={style}/>;}")
   a=s.index('export function Template08');b=s.index('function FoldCover',a);s=s[:a]+s[b:]
   s=s[:s.index('export function Template09')]
   s+='\nexport {Orbit,Gallery,TiltRecord,FoldCover,ParkJournal,ExposeVideo,Desk};\n'
  else:
   s=replace_function(s,'function Material(','function Presenter(',"function Material({slot}:{episode:Episode;slot:string}){return <Media id={slot}/>;}")
   a=s.index('export function Template10');b=s.index('// Route world',a);s=s[:a]+s[b:]
   s=s[:s.index('export function Template11')]
   s=s.replace('<div style={{...box(48,950,624,98)', '<div data-native-note="assemble" style={{...box(48,950,624,98)')
   s+='\nexport {Impact,Filmstrip,Assemble,PosterRecap,RouteWorld,StepLine,Callout};\n'
  header='// Independent semantic HD derivative; original source identity is in SOURCE_MAP.json.\n'
  target=HERE/f'Derived-{letter.upper()}.tsx';target.write_text(header+s,encoding='utf-8')
  records.append({'source':path.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
    'derived':target.relative_to(ROOT).as_posix(),'derived_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
    'changes':'real-video Media helper; motion-only context; root removed;07 tracking respects actual measured source extent; geometry/formulas retained'})
 (HERE/'SOURCE_MAP.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('three independent derived source files authored; original source bytes untouched')
if __name__=='__main__':derive()
