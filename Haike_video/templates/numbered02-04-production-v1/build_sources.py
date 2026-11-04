"""Deterministic, additive adaptations of frozen2/3/4 source; never edits parents."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
records=[]


def source(relative):
    path=ROOT/relative
    records.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return path.read_text(encoding='utf-8-sig')


def replace(text,old,new,count=1):
    actual=text.count(old)
    if actual!=count:raise ValueError(f'Frozen source changed: expected{count}, found{actual}: {old[:70]}')
    return text.replace(old,new)


def emit(name,text):
    path=HERE/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('// Generated additive adaptation; see build_sources.py and derivation.json.\n'+text,encoding='utf-8',newline='\n')


def kinetic():
    text=source('Haike_video/templates/kinetic-field-v1/index.tsx')
    text=replace(text,'import plan from \'./layout.json\';',"import plan from '../kinetic-field-v1/layout.json';")
    text=replace(text,"import defaultContent from './content.json';","import defaultContent from '../kinetic-field-v1/content.json';\nimport {CurrentEpisode,AbsoluteFrame,VideoImage as Img,VideoImage} from './Common';\nimport type {Episode} from './types';")
    text=replace(text,'Composition, Img, OffthreadVideo,','Composition, OffthreadVideo,')
    a=text.index('function Clip(');b=text.index('\nfunction Burst(',a)
    text=text[:a]+'''function Clip({name,position}:{name:string;at?:number;offset?:number;position?:string}){
 return <VideoImage src={name} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:position||'50% 50%'}}/>;
}
function useActionWindows(){const episode=React.useContext(CurrentEpisode);return(name:string,end=false)=>{const event=episode.actions['haike.kinetic-field-v1.video.'+name];if(!event)throw Error('Unknown executed kinetic action '+name);return (end?event.to:event.from)/episode.fps;};}
''' + text[b:]
    # Each actual effect reads its own semantic action window; no whole-piece time stretch.
    windows=[('1.5,2.15','split-divider-morph'),('3.2,3.65','footage-iris'),('4.6,5.25','detail-loupe'),('3.8,4.25','short-marker'),('5.6,6.05','hand-drawn-arrow'),('7.4,8.3','stack-to-location'),('9.3,9.85','floor-strip'),('10.7,11.2','location-focus'),('12,12.55','portrait-disc'),('13.65,14.2','photo-fan')]
    for old,name in windows:text=replace(text,'tween(t,'+old,"tween(t,at('"+name+"'),at('"+name+"',true)")
    for old,name in [('pop(t,0,.5)',"pop(t,at('angled-panel-settle'),.5)"),('pop(t,.65,.5)',"pop(t,at('keyword-assemble'),.5)"),('pop(t,1.0,.5)',"pop(t,at('keyword-assemble')+.35,.5)"),('from={2.4}',"from={at('tape-reveal')}"),('pop(t,5.6,.45)',"pop(t,at('hand-drawn-arrow'),.45)"),('tween(t,5.9,6.05)',"tween(t,at('hand-drawn-arrow')+.3,at('hand-drawn-arrow',true))"),('tween(t,3.2,6.6)',"tween(t,at('footage-iris'),at('detail-loupe',true)+1)"),('tween(t,6.6+i*.16,7+i*.16)',"tween(t,at('photo-cascade')+i*.16,at('photo-cascade',true)+i*.16)"),('pop(t,7.3,.4)',"pop(t,at('photo-cascade')+.54,.4)"),('pop(t,8.5,.55)',"pop(t,at('pin-pop'),.55)"),('pop(t,14.4,.45)',"pop(t,at('invitation-stamp'),.45)")]:text=replace(text,old,name)
    text=replace(text,'{t>=8?',"{t>=React.useContext(CurrentEpisode).presenters[0].from/useVideoConfig().fps?")
    text=replace(text,'{t>=12.7?',"{t>=at('headline-assemble')?")
    text=replace(text,'Math.round(12.7*24)',"Math.round(at('headline-assemble')*24)")
    text=replace(text,'const c=useContent();','const c=useContent(),at=useActionWindows();',6)
    start=text.index('export function KineticField(')
    body=text[start:]
    body=body[:body.index('\nregisterRoot(')]
    body=replace(body,'export function KineticField({content=defaultContent}:{content?:typeof defaultContent}){const t=time();',"export function KineticProduction({episode}:{episode:Episode}){const t=time(),f=React.useContext(AbsoluteFrame),content=episode.content,s=episode.stages;")
    body=replace(body,'{t<3.65?<Duo/>:null}{t>=3.2&&t<6.6?<Hands/>:null}{t>=6.6&&t<8.3?<Collage/>:null}{t>=7.4&&t<12?<Location/>:null}{t>=12?<Invitation/>:null}',"{f<s[0].to?<Duo/>:null}{f>=s[1].from&&f<s[1].to?<Hands/>:null}{f>=s[2].from&&f<s[2].to?<Collage/>:null}{f>=s[3].from&&f<s[3].to?<Location/>:null}{f>=s[4].from?<Invitation/>:null}")
    body=replace(body,"<Audio src={staticFile('sample.wav')} volume={plan.audio.gain}/>",'')
    text=text[:start]+body
    emit('Kinetic.tsx',text)


def field_notes():
    avatar=source('Haike_video/templates/chromatic-motion-lab-v1/AvatarScene.tsx')
    imports=avatar[:avatar.index('export {activeIndex}')]
    imports=replace(imports,'AbsoluteFill,Img,Video,','AbsoluteFill,Video,')
    imports=replace(imports,"import palettes from './palettes.json';","import palettes from '../chromatic-motion-lab-v1/palettes.json';")
    imports=replace(imports,"import recipeBook from './recipes.json';","import recipeBook from '../chromatic-motion-lab-v1/recipes.json';")
    imports=replace(imports,"import {activeIndex,activeAndNext} from './runtime';","import {VideoImage as Img} from './Common';")
    chunk=avatar[avatar.index("const font='Haike Preview';"):avatar.index('function Decoration(')]
    emit('FieldMedia.tsx',imports+'\ntype Recipe=any;type Palette=any;type Episode=any;\n'+chunk)
    text=source('Haike_video/templates/chromatic-motion-lab-v1/RecipeStage.tsx')
    text=replace(text,'AbsoluteFill,Img,Video,','AbsoluteFill,Video,')
    text=replace(text,"import {Media,TextEffect,recipes,type Episode} from './AvatarScene';","import {Media,TextEffect} from './FieldMedia';\nimport originalRecipes from '../chromatic-motion-lab-v1/recipes.json';\nconst recipes=originalRecipes.recipes;type Episode=any;\nimport {VideoImage as Img,Presenter} from './Common';")
    text=replace(text,"from './runtime'","from '../chromatic-motion-lab-v1/runtime'")
    text=replace(text,"from './custom-recipes/field-notes.json'","from '../chromatic-motion-lab-v1/custom-recipes/field-notes.json'")
    text=replace(text,'s=recipe.stages[index],t=recipe.timing,p=recipe.palette;',"s={...recipe.stages[index],...episode.stages[index].text},t={...recipe.timing,...episode.stages[index].timing},p=recipe.palette;")
    text=replace(text,'{recipe.brand}','{episode.brand}')
    a=text.index('  <div data-role="presenter"');b=text.index('  <div style={{...box([48,1226',a)
    text=text[:a]+'  <Presenter box={recipe.layout.presenter}/>\n'+text[b:]
    text=replace(text,'把好奇，留给真实的现场。','{episode.address}')
    # The caption is now the shared full-source caption below the legal overlay.
    emit('FieldNotes.tsx',text)


def nana():
    base='Haike_video/templates/nana-mint-explainer-v1/'
    text=source(base+'shared.tsx')
    text=replace(text,"from '../../motion-components/","from '../../../motion-components/",2)
    text=replace(text,'AbsoluteFill, cancelRender,','AbsoluteFill, cancelRender,')
    text=text.replace("import type {Episode, Media, Scene} from './types';","import type {Episode, Media, Scene} from './types';\nimport {VideoImage,CurrentEpisode,AbsoluteFrame} from '../Common';")
    a=text.index('export function Presenter(');b=text.index('export function MediaWindow(',a)
    original=text[a:b]
    original=replace(original,'  if (!media) return null;',"  const global=React.useContext(AbsoluteFrame),episode=React.useContext(CurrentEpisode);\n  if (!media || (media.role==='avatar' && !episode.presenters.some(c=>c.from<=global&&global<c.to))) return null;")
    a2=original.index("    {media.kind === 'image'");b2=original.index('\n  </div>;',a2)
    original=original[:a2]+'''    <VideoImage src={media.file} style={{width:'100%',height:'100%',objectFit:'cover'}}/>
    <span style={{position:'absolute',bottom:0,left:0,right:0,padding:7,fontSize:14,fontWeight:800,textAlign:'center',background:'#124a49',color:'#fff'}}>{media.role==='avatar'?'侯总 · AI数字人':'门店实拍'}</span>'''+original[b2:]
    text=text[:a]+original+text[b:]
    emit('nana/shared.tsx',text)
    types=source(base+'types.ts').replace("kind?: 'image' | 'video'","kind?: 'image' | 'video';role?:'avatar'|'footage'")
    emit('nana/types.ts',types)
    substitutions={
        'Workflow.tsx':[("'上传素材'", "'看清现场'"),("'描述需求'","'测完看报告'"),("'打开可视窗口'","'不看病不卖药'"),("'查看剪辑结果'","'自己判断'"),('placeholder="描述你想做的视频"','placeholder="先把话说明白"'),("chips={['时长', '风格', '给谁看']}","chips={['报告', '参考', '自己定']}"),('typeDuration={2.4}','typeDuration={1.1}'),('cursorAt={3.4} clickAt={4.1}','cursorAt={1.8} clickAt={2.1}'),('query="开始剪辑"','query="到店了解"'),("running: '读取素材', done: '素材就绪'","running: '查看报告', done: '给您参考'"),("running: '编排镜头', done: '镜头已编排'","running: '了解边界', done: '不看病卖药'"),("running: '合成字幕与声音', done: '合成完成'","running: '自己判断', done: '选择由您'"),('result="打开预览窗口"','result="不是医疗诊断"')],
        'Argument.tsx':[('>以前</div>','>想法</div>'),('>交给 AI</div>','>说明白</div>'),('>回到人的价值</div>','>决定在您</div>'),('>水平差别依然可以非常大</div>','>买不买，自己定</div>'),("'理解结果' : '人工判断'","'日常用品' : '免费参考'")],
        'Resources.tsx':[('>几个月的探索</div>','>在店里，自己看</div>'),('highlight="全套教程"','highlight="按需要选"'),('headline="提示词 | 方法 · Skill | 案例样片" capturing="整理案例" copied="形成可复用方法"','headline="看现场 | 看报告 | 自己判断" capturing="了解现场" copied="给您个参考"'),('>评论区打字</div>','>陈家林路63号</div>'),("scene.labels?.[0] || '剪辑'","scene.labels?.[0] || '您自己定'"),("scene.labels?.[1] || '全套教程，我发给你'","scene.labels?.[1] || '未来汇一楼'")]
    }
    for name in ['Introduction.tsx','Workflow.tsx','Argument.tsx','Resources.tsx']:
        text=source(base+'scenes/'+name).replace("../../../motion-components/","../../../../motion-components/")
        if name=='Resources.tsx':text=replace(text,"from '../../../../motion-components/snapcn/upstream/registry/snap-cn/capture-reveal'","from '../CaptureReveal'")
        for old,new in substitutions.get(name,[]):text=replace(text,old,new)
        if name=='Workflow.tsx':text=replace(text,"done: '不看病卖药'","done: '不看病不卖药'")
        if name=='Introduction.tsx':
            text=replace(text,'Math.round(2.1 * fps)',"Math.round((scene.cues?.presenter ?? 2.1) * fps)")
            text=replace(text,'(.25 + i * .82)',"((scene.cues?.labelStart ?? .25) + i * (scene.cues?.labelStagger ?? .82))")
        emit('nana/scenes/'+name,text)
    text=source(base+'index.tsx')
    text=text[:text.index('export function NanaReference(')]
    text=text.replace("../../motion-components/","../../../motion-components/")
    # Shared caption below the composition has the exact complete source words.
    start=text.index('        <WordCaptions ');end=text.index('\n      </SnapCnUIProvider>',start)
    text=text[:start]+text[end:]
    text=replace(text,'    <Audio src={file(episode.voice)} premountFor={fps}/>','')
    emit('nana/index.tsx',text)
    # Preserve native capture window/toast/cursor equations, use live video inside it.
    text=source('Haike_video/motion-components/snapcn/upstream/registry/snap-cn/capture-reveal/index.tsx')
    text=text.replace('"use client";','"use client";\nimport {VideoImage} from "../Common";')
    a=text.index('function useAspect(');b=text.index('\n}',a)+2
    text=text[:a]+'function useAspect(src:string):number|null { return 16/9; }'+text[b:]
    text=replace(text,'"https://cdn.jsdelivr.net/npm/@fontsource-variable/dm-sans@5.3.0/files/dm-sans-latin-opsz-normal.woff2"','staticFile("font.ttf")')
    old='''              <image
                href={image}
                x={WIN.x}
                y={WIN.y}
                width={WIN.w}
                height={winH}
                preserveAspectRatio="xMidYMin slice"
              />'''
    text=replace(text,old,'''              <foreignObject x={WIN.x} y={WIN.y} width={WIN.w} height={winH}>
                <VideoImage src={image} style={{width:'100%',height:'100%',objectFit:'cover'}}/>
              </foreignObject>''')
    emit('nana/CaptureReveal.tsx',text)


def main():
    kinetic();field_notes();nana()
    document={'schema':'haike.numbered-motion-source-derivation/1','sources':records,
        'generated':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(HERE.rglob('*.tsx')) if p.name not in {'Common.tsx','index.tsx'}],
        'scope':'Retain original geometry/equations/native components; parameterize true semantic event instants and live source playback. No original source edits.'}
    (HERE/'derivation.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
