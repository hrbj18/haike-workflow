import React from 'react';
import {AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import geometry from './layout.json';
import type {Box, NarratedPilotProps, PilotGeometry, PilotScene} from './types';

// Hum material adapted for a source-bound video; all speech and selection clocks stay upstream.
export const HUM = {
  paper:'#F7F5EA', card:'#FCFAF1', fringe:'#FFFDF6', ink:'#17212B', muted:'#626976',
  pear:'#EACD38', pearEdge:'#B59A22', blue:'#3176BB', coral:'#F16D6D', mint:'#A9D9B7',
  mintDeep:'#55856B', sand:'#D8C29C', kraft:'#AD895B', sugar:'#DBE7EC', dark:'#151C25',
};
const g = geometry as PilotGeometry;
const clamp = {extrapolateLeft:'clamp' as const,extrapolateRight:'clamp' as const};
const curve = Easing.bezier(.18,.8,.16,1);
const ease = (f:number,a:number,b:number) => interpolate(f,[a,b],[0,1],{...clamp,easing:curve});
const linear = (f:number,a:number,b:number) => interpolate(f,[a,b],[0,1],clamp);
const boxStyle = (b:Box):React.CSSProperties => ({position:'absolute',left:b[0],top:b[1],width:b[2],height:b[3],boxSizing:'border-box'});
const mix = (a:Box,b:Box,t:number):Box => a.map((v,i)=>v+(b[i]-v)*t) as Box;
const display = (p:NarratedPilotProps) => p.fontAssets?'HaikeNarratedDisplay':'Microsoft YaHei, sans-serif';
const body = (p:NarratedPilotProps) => p.fontAssets?'HaikeNarratedBody':'Microsoft YaHei, sans-serif';
const grainSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><filter id="g"><feTurbulence type="fractalNoise" baseFrequency=".72" numOctaves="3" seed="13" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(#g)" opacity=".21"/></svg>`;
const fibreSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><filter id="f"><feTurbulence type="fractalNoise" baseFrequency=".012 .42" numOctaves="2" seed="7" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(#f)" opacity=".12"/></svg>`;
const grain = `url("data:image/svg+xml,${encodeURIComponent(grainSvg)}")`;
const fibre = `url("data:image/svg+xml,${encodeURIComponent(fibreSvg)}")`;

/** Stable roughness; no random/time-dependent browser state enters a rendered frame. */
export function tornEdge(seed:number,depth=1.3) {
  const pts=['0% 1%'];
  for(let i=1;i<=24;i++)pts.push(`${i*100/24}% ${.6+Math.abs(Math.sin(i*2.19+seed)*Math.cos(i*.79+seed))*depth}%`);
  pts.push('100% 98.7%');
  for(let i=24;i>=0;i--)pts.push(`${i*100/24}% ${99.4-Math.abs(Math.sin(i*1.93+seed))*depth}%`);
  return `polygon(${pts.join(',')})`;
}

const Grain:React.FC = () => <AbsoluteFill data-element="hum-fibre" style={{backgroundImage:`${grain},${fibre}`,backgroundSize:'200px 200px,240px 240px',opacity:.28,mixBlendMode:'multiply',pointerEvents:'none'}}/>;

const Sheet:React.FC<{children?:React.ReactNode;seed?:number;color?:string;style?:React.CSSProperties}> = ({children,seed=1,color=HUM.card,style}) => <div data-element="hum-paper-sheet" style={{position:'absolute',inset:0,filter:`drop-shadow(1px 3px 1px ${HUM.ink}20) drop-shadow(5px 13px 15px ${HUM.ink}1F)`,...style}}>
  <AbsoluteFill style={{backgroundColor:HUM.fringe,clipPath:tornEdge(seed),borderRadius:30}}/>
  <AbsoluteFill style={{inset:'3px 0 5px 0',backgroundColor:color,clipPath:tornEdge(seed+2),borderRadius:28,overflow:'hidden'}}><Grain/>{children}</AbsoluteFill>
</div>;

const Backdrop:React.FC<{dark?:boolean}> = ({dark=false}) => <AbsoluteFill data-element="hum-background" style={{backgroundColor:dark?HUM.dark:HUM.paper}}>
  <Grain/>
  <div style={{position:'absolute',left:-20,right:-20,top:1480,height:380,backgroundColor:dark?HUM.mintDeep:HUM.mint,clipPath:tornEdge(19,1.7),rotate:'-2deg'}}/>
  <div style={{position:'absolute',left:-20,right:-20,top:1695,height:140,backgroundColor:dark?HUM.kraft:HUM.sand,clipPath:tornEdge(28,2),rotate:'1deg'}}/>
</AbsoluteFill>;

const Title:React.FC<{p:NarratedPilotProps;scene:PilotScene;age:number;box?:Box;size?:number;center?:boolean}> = ({p,scene,age,box=g.sceneHeader.title,size=g.sceneHeader.titleSize,center=false}) => <div data-element="hum-title" style={{...boxStyle(box),color:scene.theme==='dark'?HUM.paper:HUM.ink,fontFamily:display(p),fontWeight:700,fontSize:size,lineHeight:1.16,letterSpacing:-1.4,textAlign:center?'center':'left',whiteSpace:'pre'}}>
  {scene.title.split('\n').map((text,i)=><div key={i} style={{overflow:'hidden',paddingBottom:4}}><div style={{translate:`0 ${(1-ease(age-i*2,0,10))*105}%`}}>{text}</div></div>)}
</div>;

const Header:React.FC<{p:NarratedPilotProps;scene:PilotScene;age:number}> = ({p,scene,age}) => <>
  <Title p={p} scene={scene} age={age}/>
  {scene.subtitle&&<div style={{...boxStyle(g.sceneHeader.subtitle),fontFamily:body(p),fontSize:44,color:HUM.muted,opacity:ease(age,7,18)}}>{scene.subtitle}</div>}
</>;

const HumWall:React.FC<{p:NarratedPilotProps;scene:PilotScene}> = ({p,scene}) => {
  const age=useCurrentFrame(), ids=scene.wallMediaIds||[];
  const timing=scene.selection!;
  const progress=ease(age,timing.expandFrom,timing.holdFrom);
  const selected=p.media.find(m=>m.id===scene.mediaId)!;
  const selectedIndex=ids.indexOf(selected.id);
  const origin:Box=[88+(selectedIndex%3)*432,520+Math.floor(selectedIndex/3)*405,400,365];
  const target=selected.orientation==='portrait'?g.select.portraitExpanded:g.select.expanded;
  const cursor=ease(age,timing.cursorFrom,timing.selectFrom-2);
  const cursorAlpha=age<timing.cursorFrom?0:1-linear(age,timing.expandFrom,timing.expandFrom+8);
  const chips=[HUM.pear,HUM.sugar,HUM.coral,HUM.mint];
  return <><Header p={p} scene={scene} age={age}/>
    <div data-element="hum-category-row" style={{position:'absolute',left:88,top:426,display:'flex',gap:14,fontSize:25,fontFamily:body(p),color:HUM.ink,opacity:1-progress}}>
      {(p.wallCategories||['全部素材','亲子体验','机器人现场','店内日常']).map((label,i)=><span key={label} style={{padding:'9px 23px',borderRadius:16,backgroundColor:chips[i%chips.length],boxShadow:`0 4px 0 ${i===0?HUM.pearEdge:HUM.sand}`,rotate:`${i%2?1:-1}deg`}}>{label}</span>)}
    </div>
    {ids.map((id,i)=>{
      const media=p.media.find(m=>m.id===id)!;
      const active=id===selected.id, enter=ease(age,i*3,i*3+18);
      const start:Box=[88+(i%3)*432,520+Math.floor(i/3)*405,400,365];
      const box=active?mix(start,target,progress):start;
      return <div key={id} data-element="hum-wall-card" data-media-id={id} data-selected={active} data-phase={active&&age>=timing.expandFrom?'expand':age>=timing.selectFrom&&active?'selected':'enter'} style={{...boxStyle(box),zIndex:active?5:1,opacity:enter*(active?1:1-progress),translate:`0 ${(1-enter)*64}px`,scale:.97+.03*enter,rotate:`${(i%2?1.2:-1.1)*(active?1-progress:1)}deg`}}>
        <div style={{position:'absolute',inset:-10,backgroundColor:active&&age>=timing.selectFrom?HUM.pear:HUM.sugar,borderRadius:30,rotate:`${active?-1.4:1.8}deg`,opacity:active?1:.8}}/>
        <Sheet seed={i+10}><div style={{position:'absolute',inset:'14px 14px 78px',borderRadius:18,overflow:'hidden',backgroundColor:HUM.paper}}>
          <Img src={staticFile(media.thumbnail)} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain'}}/>
          {active&&<Sequence layout="none" from={timing.expandFrom} durationInFrames={scene.frames-timing.expandFrom}><OffthreadVideo src={staticFile(media.src)} startFrom={Math.round(media.offset*g.fps)} muted style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>}
        </div><div style={{position:'absolute',left:22,right:22,bottom:12,height:58,display:'flex',alignItems:'center',gap:12,color:HUM.ink,fontFamily:body(p),fontSize:29+progress*9}}><span style={{width:14,height:24,borderRadius:4,backgroundColor:chips[i%chips.length]}}/>{media.label||p.brand}</div></Sheet>
      </div>;
    })}
    <div data-element="hum-selection-cursor" style={{position:'absolute',zIndex:10,left:1240+(origin[0]+origin[2]*.6-1240)*cursor,top:440+(origin[1]+origin[3]*.5-440)*cursor,opacity:cursorAlpha}}><svg width="52" height="62" viewBox="0 0 52 62"><path d="M4 3 L7 48 L19 37 L29 58 L39 53 L29 32 L46 31 Z" fill={HUM.ink} stroke={HUM.fringe} strokeWidth="3" strokeLinejoin="round"/></svg></div>
  </>;
};

const HumFocus:React.FC<{p:NarratedPilotProps;scene:PilotScene}> = ({p,scene}) => {
  const age=useCurrentFrame(),media=p.media.find(m=>m.id===scene.mediaId)!;
  const portrait=media.orientation==='portrait';
  const entry=portrait?g.focus.portraitEntry:g.focus.entry,target=portrait?g.focus.portraitExpanded:g.focus.expanded;
  const box=mix(entry,target,ease(age,0,Math.min(18,scene.frames-1)));
  const label=portrait?g.focus.portraitLabel:g.focus.label;
  return <><Header p={p} scene={scene} age={age}/><div data-element="hum-focus-window" data-media-id={media.id} style={{...boxStyle(box)}}>
    <div style={{position:'absolute',inset:-12,borderRadius:28,backgroundColor:HUM.sugar,rotate:'-1.2deg'}}/>
    <Sheet seed={22}><div style={{position:'absolute',inset:16,borderRadius:20,overflow:'hidden',backgroundColor:HUM.paper}}><OffthreadVideo src={staticFile(media.src)} startFrom={Math.round(media.offset*g.fps)} muted style={{width:'100%',height:'100%',objectFit:'contain',objectPosition:media.objectPosition||'50% 50%'}}/></div></Sheet>
    </div>{media.label&&<div data-element="hum-focus-label" style={{...boxStyle(label),fontFamily:body(p),fontSize:40,lineHeight:1.4,color:HUM.ink,opacity:ease(age,6,18)}}><span style={{backgroundColor:HUM.pear,borderRadius:12,padding:'5px 14px',boxDecorationBreak:'clone'}}>{media.label}</span></div>}</>;
};

type PresenterAt=(p:NarratedPilotProps,frame:number)=>null|{mode:string;large:number;box:Box;sourceSeconds:number};

export const HumScene:React.FC<{p:NarratedPilotProps;scene:PilotScene}> = ({p,scene}) => {
  const age=useCurrentFrame();
  return <AbsoluteFill data-scene-id={scene.id}><Backdrop dark={scene.theme==='dark'}/>{scene.module==='wall'?<HumWall p={p} scene={scene}/>:scene.module==='focus'?<HumFocus p={p} scene={scene}/>:<Title p={p} scene={scene} age={age} box={g.statement.title} size={g.statement.titleSize} center/>}</AbsoluteFill>;
};

const HumPresenter:React.FC<{p:NarratedPilotProps;presenterAt:PresenterAt}> = ({p,presenterAt}) => {
  const frame=useCurrentFrame(),state=presenterAt(p,frame),scene=p.scenes.find(s=>frame>=s.from&&frame<s.from+s.frames);
  if(!p.presenter||!state||!scene)return null;
  const titleBox=mix(g.statement.title,g.presenter.title,state.large);
  const size=g.statement.titleSize+(g.sceneHeader.titleSize-g.statement.titleSize)*state.large;
  return <AbsoluteFill data-element="hum-presenter" data-mode={state.mode} style={{zIndex:20}}><Backdrop dark={scene.theme==='dark'}/>
    <Title p={p} scene={scene} age={frame-scene.from} box={titleBox} size={size} center/>
    <Sequence layout="none" from={p.presenter.from} durationInFrames={p.presenter.frames}><div data-element="hum-presenter-window" style={{...boxStyle(state.box),opacity:ease(frame,p.presenter.from,p.presenter.from+6)}}><Sheet seed={31}><div style={{position:'absolute',inset:12,borderRadius:22,overflow:'hidden',backgroundColor:HUM.paper}}><OffthreadVideo src={staticFile(p.presenter.src)} startFrom={Math.round(p.presenter.offset*g.fps)} muted style={{width:'100%',height:'100%',objectFit:'contain',objectPosition:p.presenter.objectPosition||'50% 50%'}}/></div></Sheet></div></Sequence>
    {scene.subtitle&&<div style={{position:'absolute',left:88,top:1415,width:180,height:110,fontFamily:body(p),fontSize:34,lineHeight:1.4,color:HUM.paper}}>{scene.subtitle}</div>}
  </AbsoluteFill>;
};

export const HumContent:React.FC<NarratedPilotProps & {presenterAt:PresenterAt}> = p => {
  const frame=useCurrentFrame(),scene=p.scenes.find(s=>frame>=s.from&&frame<s.from+s.frames);
  const dark=scene?.theme==='dark';
  const caption=p.captions.find(c=>frame*1000/g.fps>=c.startMs&&frame*1000/g.fps<c.endMs);
  return <AbsoluteFill data-template="motiongit-narrated-pilot-v1" data-visual-style="hum" style={{fontFamily:body(p),fontSynthesis:'none',backgroundColor:HUM.paper,color:HUM.ink}}>
    {p.scenes.map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={g.fps} name={s.id}><HumScene p={p} scene={s}/></Sequence>)}
    <HumPresenter p={p} presenterAt={p.presenterAt}/>
    <div data-element="hum-brand" style={{...boxStyle(g.brand),zIndex:40,display:'flex',justifyContent:'space-between',alignItems:'center',fontSize:29,color:dark?HUM.paper:HUM.ink}}><span style={{padding:'8px 16px',borderRadius:12,backgroundColor:HUM.pear,color:HUM.ink,boxShadow:`0 4px 0 ${HUM.pearEdge}`}}>{p.brand}</span><span style={{fontSize:24}}>HAIKE AI</span></div>
    {caption&&<div data-element="hum-caption" style={{...boxStyle(g.captions),zIndex:50}}><Sheet seed={33}><div style={{position:'absolute',inset:0,display:'flex',alignItems:'center',justifyContent:'center',fontSize:g.captionSize,lineHeight:1.25,textAlign:'center',whiteSpace:'pre',color:HUM.ink}}>{caption.text}</div></Sheet></div>}
    <div style={{...boxStyle(g.footer),zIndex:40,color:dark?HUM.paper:HUM.muted,fontSize:25}}>{p.footer}</div>
    {p.audio&&<Audio src={staticFile(p.audio)}/>}
  </AbsoluteFill>;
};
