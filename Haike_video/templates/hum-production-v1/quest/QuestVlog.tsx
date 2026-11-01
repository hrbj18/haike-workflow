import React from 'react';
import {AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import type {Box, Media, Props, Scene} from '../types';
import layout from './layout.json';
import {ExtraGraphics,PersistentPath,PhotoConstellation,SceneTransition} from './Mechanisms';

// Independent implementation from observed reference behavior. No MotionGit core code.
const color = layout.palette;
const clamp = {extrapolateLeft:'clamp', extrapolateRight:'clamp'} as const;
const ramp = (f:number,a:number,b:number) => {const t=interpolate(f,[a,b],[0,1],clamp);return t*t*(3-2*t);};
const mix = (a:number,b:number,t:number) => a+(b-a)*t;
const box = (b:number[]):React.CSSProperties => ({position:'absolute',left:b[0],top:b[1],width:b[2],height:b[3],boxSizing:'border-box'});
const display='HaikeProductionDisplay', body='HaikeProductionBody';
const Live:React.FC<{m:Media;frames:number}>=({m,frames}) => m.kind==='image'
  ? <Img src={staticFile(m.src)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>
  : <Sequence durationInFrames={frames} layout="none"><OffthreadVideo src={staticFile(m.src)} startFrom={Math.round(m.offset*30)} muted style={{width:'100%',height:'100%',objectFit:'contain',objectPosition:m.objectPosition||'50% 50%'}}/></Sequence>;

const Graphics:React.FC<{p:Props;s:Scene;portrait:boolean}>=({p,s,portrait})=>{
  const f=useCurrentFrame(), q=s.quest!, W=portrait?936:1210;
  const dark=s.theme==='dark'||q.kind==='boot'||q.kind==='books'||q.kind==='radar';
  const blue=q.kind==='world';
  const ink=dark||blue?'#fff':color.ink;
  const entry=ramp(f,0,15), exit=1-ramp(f,s.frames-10,s.frames);
  const items=q.items, cues=q.cues;
  const m=p.media.find(x=>x.id===s.mediaId);
  const narrowMedia=!portrait&&m?.orientation==='portrait';
  const headlineHeight=portrait?(q.presenter==='card'?480:560):(s.title.includes('\n')?300:420);
  const heading=<div style={{fontFamily:display,fontWeight:700,fontSize:portrait?110:104,lineHeight:1.12,whiteSpace:'pre-wrap',letterSpacing:-3,transform:`translateY(${(1-entry)*50}px)`,opacity:entry}}>{s.title.split('\n').map((line,i)=><div key={i} style={{color:i===1&&!dark&&!blue?color.accent:ink}}>{line}</div>)}</div>;
  const label:React.CSSProperties={fontSize:portrait?50:46,fontFamily:body,lineHeight:1.35};
  const reveal=(i:number)=>ramp(f,cues[i],cues[i]+15);
  return <AbsoluteFill style={{opacity:exit,color:ink}}>
    <div style={{fontSize:22,letterSpacing:4,opacity:.55,marginBottom:26}}>{q.chapter||'AI · COMMUNITY'}</div>
    {heading}
    <ExtraGraphics p={p} s={s} portrait={portrait} frame={f}/>
    {q.kind==='path'&&portrait&&m&&<div data-element="quest-path-evidence" style={{...box(layout.portrait.pathMedia),padding:8,background:'#fff',borderRadius:14,boxShadow:'0 14px 35px #0003',opacity:entry,transform:`translateY(${(1-entry)*45}px)`}}><Live m={m} frames={s.frames}/></div>}
    {q.kind==='boot'&&<div style={{marginTop:100,fontFamily:'monospace'}}>
      <div style={{fontSize:32,opacity:.7}}>INITIALIZING YOUR NEXT QUEST</div>
      <div style={{marginTop:36,fontSize:120,color:color.good}}>{Math.floor(ramp(f,0,s.frames-25)*100)}%</div>
      <div style={{display:'flex',gap:10,marginTop:24}}>{Array.from({length:16},(_,i)=><div key={i} style={{width:W/16-10,height:34,background:f>i*(s.frames-25)/16?color.accent:'#282B33'}}/>)}</div>
    </div>}
    {q.kind==='headline'&&m?.orientation==='portrait'?<div data-element="quest-headline-media" style={{display:'flex',alignItems:'center',gap:56,marginTop:38,height:headlineHeight}}>
      <div style={{flexShrink:0,width:headlineHeight*9/16,height:headlineHeight,boxSizing:'border-box',background:'#080A10',border:'8px solid #fff',boxShadow:'12px 18px 0 #1455FF20',transform:`rotate(${mix(-5,-2,entry)}deg)`}}><Live m={m} frames={s.frames}/></div>
      <div style={{maxWidth:W-headlineHeight*9/16-56,boxSizing:'border-box',background:color.accent,color:'#fff',padding:'12px 24px',fontSize:44,lineHeight:1.35,overflowWrap:'anywhere',transform:`rotate(-3deg) scale(${.85+.15*entry})`}}>{q.accent}</div>
    </div>:q.kind==='headline'&&<>
      <div style={{display:'inline-block',marginTop:38,background:color.accent,color:'#fff',padding:'12px 24px',fontSize:44,transform:`rotate(-3deg) scale(${.85+.15*entry})`}}>{q.accent}</div>
      {m&&<div style={{marginTop:42,width:W*.85,height:portrait?380:s.title.includes('\n')?200:270,boxSizing:'border-box',background:'#080A10',border:'8px solid #fff',boxShadow:'12px 18px 0 #1455FF20',transform:`rotate(${mix(-5,-2,entry)}deg)`}}><Live m={m} frames={s.frames}/></div>}
    </>}
    {q.kind==='versus'&&!q.variant&&<div style={{display:'flex',gap:24,marginTop:70}}>{items.map((x,i)=><div key={i} style={{flex:1,transform:`translateY(${(1-reveal(i))*100}px) rotate(${i?-2:2}deg)`,opacity:reveal(i),border:`4px solid ${i?color.accent:color.bad}`,padding:28,background:dark?'#191B24':'#F5F6FA'}}>
      <div style={{fontSize:24,letterSpacing:3,color:i?color.accent:color.bad}}>PLAYER 0{i+1}</div>
      <div style={{...label,marginTop:35,minHeight:120}}>{x}</div>
      <div style={{height:22,background:'#DFE2E9',marginTop:30}}><div style={{height:'100%',width:`${i?100:100-75*ramp(f,cues[1],cues[1]+30)}%`,background:i?color.accent:color.bad}}/></div>
      <div style={{fontSize:25,marginTop:14,opacity:.6}}>{i?'READY TO TRY':'WATCHING'}</div>
    </div>)}</div>}
    {q.kind==='quests'&&<div style={{marginTop:50,display:'grid',gap:24}}>{items.map((x,i)=><div key={i} style={{display:'flex',alignItems:'center',gap:28,padding:'32px 28px',border:`2px solid ${dark?'#4C5263':'#D9DDE7'}`,borderRadius:22,opacity:reveal(i),transform:`translateX(${(1-reveal(i))*100}px)`,background:dark?'#161A25':'#F5F7FC'}}>
      <div style={{fontSize:25,color:color.accent,border:'2px solid',padding:12}}>QUEST<br/>0{i+1}</div><div style={label}>{x}</div>
    </div>)}</div>}
    {q.kind==='media'&&m&&<div style={{marginTop:42,width:portrait?420:narrowMedia?248:W,height:portrait?747:narrowMedia?440:360,borderRadius:26,overflow:'hidden',background:'#080A10',transform:`perspective(1400px) rotateY(${mix(12,0,entry)}deg) scale(${mix(.88,1,entry)})`,boxShadow:'0 20px 0 #1455FF20'}}><Live m={m} frames={s.frames}/></div>}
    {q.kind==='media'&&(portrait||narrowMedia)&&<div style={{position:'absolute',left:portrait?470:330,top:portrait?435:245,width:portrait?440:780}}>{items.map((x,i)=><div key={i} style={{fontFamily:display,fontSize:58,color:color.accent,padding:'38px 0',borderBottom:'3px solid #E3E8F3',opacity:reveal(i),transform:`translateX(${(1-reveal(i))*50}px)`}}><span style={{fontFamily:body,fontSize:23}}>0{i+1} / </span><br/>{x}</div>)}</div>}
    {q.kind==='unlock'&&!q.variant&&<div style={{marginTop:65,position:'relative'}}>
      <div style={{position:'absolute',left:33,top:25,width:4,height:items.length*130-75,background:dark?'#454B60':'#DDE2EF'}}/>
      {items.map((x,i)=><div key={i} style={{display:'flex',gap:34,alignItems:'center',height:130,position:'relative'}}>
        <div style={{width:70,height:70,borderRadius:18,display:'grid',placeItems:'center',background:reveal(i)>.5?color.accent:dark?'#303545':'#E8EBF3',color:reveal(i)>.5?'#fff':'#8B92A4',transform:`scale(${1+.13*Math.sin(Math.PI*reveal(i))})`,fontSize:35}}>{reveal(i)>.5?'✓':String(i+1).padStart(2,'0')}</div>
        <div style={{...label,color:reveal(i)>.5?dark?'#fff':color.ink:'#969EAE',transform:`translateX(${(1-reveal(i))*20}px)`}}>{x}</div>
      </div>)}
    </div>}
    {q.kind==='timeline'&&<div data-element="quest-timeline" style={{marginTop:portrait?50:38,position:'relative'}}>
      <div style={{height:5,background:color.accent,position:'absolute',top:portrait?32:28,left:34,width:W-70}}/>
      <div style={{display:'flex',justifyContent:'space-between'}}>{items.map((x,i)=><div key={i} style={{width:W/items.length,textAlign:'center',position:'relative',boxSizing:'border-box',padding:'0 8px'}}><div style={{margin:'0 auto',width:portrait?64:56,height:portrait?64:56,boxSizing:'border-box',borderRadius:'50%',background:reveal(i)>.5?color.accent:dark?'#444B5B':'#DCE1ED',border:'5px solid white',transform:`scale(${1+.2*Math.sin(Math.PI*reveal(i))})`}}/><div style={{fontSize:32,lineHeight:1.3,height:portrait?126:84,marginTop:portrait?20:18,overflowWrap:'anywhere'}}>{x}</div></div>)}</div>
      <div style={{fontFamily:display,fontSize:portrait?80:64,lineHeight:1.15,color:color.accent,marginTop:portrait?50:28}}>{q.accent}</div>
    </div>}
    {q.kind==='books'&&<div data-element="quest-books" style={{marginTop:45,position:'relative'}}>{items.map((x,i)=><div key={i} style={{height:portrait?96:64,boxSizing:'border-box',width:W*(.78+i*.045),marginLeft:i*18,marginTop:portrait?14:10,background:[color.accent,color.bad,'#F9C94D','#7BE69B'][i],color:'#101114',borderRadius:'6px 20px 20px 6px',padding:portrait?'12px 24px':'8px 24px',fontFamily:body,fontSize:portrait?42:34,lineHeight:1.35,opacity:reveal(i),transform:`translateX(${(1-reveal(i))*-200}px)`}}>{x}</div>)}</div>}
    {q.kind==='world'&&(narrowMedia?<div style={{marginTop:50,position:'relative',height:400}}>
      <div style={{width:225,height:400,overflow:'hidden',borderRadius:20,background:'#111',position:'relative'}}><Live m={m!} frames={s.frames}/><AbsoluteFill style={{background:'linear-gradient(0deg,#1455FF88,transparent)'}}/></div>
      <div style={{position:'absolute',left:300,top:30,right:0}}><div style={{fontSize:24,letterSpacing:4}}>WORLD EVENT</div><div style={{fontFamily:display,fontSize:60,whiteSpace:'pre-wrap',lineHeight:1.3,marginTop:24}}>{q.accent}</div><div style={{height:24,marginTop:40,background:'#FFFFFF33'}}><div style={{height:'100%',background:'#fff',width:`${ramp(f,15,s.frames-30)*100}%`}}/></div><div style={{fontSize:27,letterSpacing:4,marginTop:25}}>MEET AI IN REAL LIFE</div></div>
    </div>:<div style={{marginTop:50}}>
      {m&&<div style={{height:portrait?620:280,width:portrait?350:W,overflow:'hidden',borderRadius:20,background:'#111',position:'relative'}}><Live m={m} frames={s.frames}/><AbsoluteFill style={{background:'linear-gradient(0deg,#1455FF88,transparent)'}}/></div>}
      {portrait&&<div style={{position:'absolute',left:395,top:320,width:540,fontFamily:display,fontSize:68,lineHeight:1.3,whiteSpace:'pre-wrap',overflowWrap:'break-word',opacity:entry}}>{q.accent}<div style={{fontFamily:body,fontSize:27,letterSpacing:5,marginTop:45,opacity:.6}}>MEET AI<br/>IN REAL LIFE</div></div>}
      <div style={{fontSize:24,letterSpacing:4,marginTop:30}}>WORLD EVENT</div>
      <div style={{height:24,marginTop:20,background:'#FFFFFF33'}}><div style={{height:'100%',background:'#fff',width:`${ramp(f,15,s.frames-30)*100}%`}}/></div>
      <div style={{fontSize:44,marginTop:22}}>{q.accent}</div>
    </div>)}
    {q.kind==='clear'&&<div style={{marginTop:55}}><div style={{fontSize:24,letterSpacing:6,color:color.accent}}>STAGE CLEAR</div>{items.map((x,i)=><div key={i} style={{...label,marginTop:30,display:'flex',gap:22,opacity:reveal(i),transform:`translateY(${(1-reveal(i))*35}px)`}}><span style={{color:color.accent,fontSize:50}}>☑</span>{x}</div>)}<div style={{fontFamily:display,fontSize:52,color:color.accent,marginTop:45,transform:`rotate(-2deg)`}}>{q.accent}</div></div>}
    {portrait&&m&&['versus','quests','unlock','clear'].includes(q.kind)&&<div style={{position:'absolute',left:q.kind==='quests'?635:288,top:q.kind==='quests'?735:640,width:q.kind==='quests'?282:360,height:q.kind==='quests'?500:640,border:'8px solid white',borderRadius:22,overflow:'hidden',background:'#101114',boxShadow:'0 20px 45px #0002',transform:`rotate(${q.kind==='quests'?-5:3}deg) translateY(${(1-entry)*90}px)`,opacity:entry}}><Live m={m} frames={s.frames}/></div>}
    {s.subtitle&&<div style={{...label,fontSize:portrait?32:36,marginTop:38,opacity:entry*.75,whiteSpace:'pre-wrap'}}>{s.subtitle}</div>}
  </AbsoluteFill>;
};

// This single source node stays mounted through scene changes; its global clock never restarts.
const Presenter:React.FC<{p:Props;portrait:boolean;frame:number}>=({p,portrait,frame})=>{
  const index=p.scenes.findIndex(s=>frame>=s.from&&frame<s.from+s.frames), s=p.scenes[index];
  const mode=(p.presenterModes||[]).find(x=>frame>=x.from&&frame<x.from+x.frames);
  const clip=mode&&(p.presenterClips||[]).find(x=>x.id===mode.clipId);
  if(!clip||!s||mode?.mode==='hidden')return null;
  const target=(scene:Scene):number[]=>scene.quest?.presenter==='card'
    ? portrait?(scene.quest.kind==='path'?layout.portrait.pathPresenter:[340,1060,400,500]):[1410,240,390,570]
    : portrait?[370,1170,340,340]:[1500,555,280,280];
  const to=target(s), from=index?target(p.scenes[index-1]):to;
  const t=ramp(frame,s.from,s.from+18), b=from.map((x,i)=>mix(x,to[i],t));
  const circle=s.quest?.presenter!=='card', previous=index?p.scenes[index-1].quest?.presenter!=='card':circle;
  const radius=mix(previous?50:6,circle?50:6,t);
  const hidden=s.quest?.presenter==='hidden';
  const opacity=ramp(frame,clip.from,clip.from+10)*(1-ramp(frame,clip.from+clip.frames-8,clip.from+clip.frames));
  return <div data-element="quest-presenter" style={{...box(b),borderRadius:`${radius}%`,overflow:'hidden',border:'7px solid #fff',boxShadow:'0 14px 45px #0003',opacity:hidden?0:opacity,zIndex:20,background:'#E7EAF2'}}>
    <Sequence layout="none" from={clip.from} durationInFrames={clip.frames}><OffthreadVideo src={staticFile(clip.src)} startFrom={Math.round(clip.offset*30)} muted style={{width:'100%',height:'100%',objectFit:'contain',objectPosition:clip.objectPosition||'50% 50%'}}/></Sequence>
    <div style={{position:'absolute',bottom:'10%',left:0,right:0,textAlign:'center',fontSize:14,background:'#FFFFFFCC',color:'#303440'}}>AI数字人演绎</div>
  </div>;
};

export const QuestVlog:React.FC<Props>=p=>{
  const frame=useCurrentFrame(), width=p.width||1080,height=p.height||1920,portrait=height>width;
  const bw=portrait?1080:1920,bh=portrait?1920:1080, scale=width/bw, sy=height/bh;
  const s=p.scenes.find(x=>frame>=x.from&&frame<x.from+x.frames), q=s?.quest;
  const blue=q?.kind==='world', dark=s?.theme==='dark'||q?.kind==='boot'||q?.kind==='books'||q?.kind==='radar';
  const ink=dark||blue?'#fff':color.ink;
  const caption=p.captions.find(x=>frame*1000/30>=x.startMs&&frame*1000/30<x.endMs);
  const next=s&&p.scenes[p.scenes.indexOf(s)+1],transitioning=!!next?.quest?.transition&&frame>=s!.from+s!.frames-layout.timing.transitionFrames;
  const overlayInk=transitioning?'#fff':ink;
  const overlayShadow=transitioning?'0 2px 4px #101114,0 0 10px #101114':undefined;
  const geo=portrait?layout.portrait:layout.landscape;
  return <AbsoluteFill style={{backgroundColor:blue?color.accent:dark?color.ink:color.paper,fontFamily:body,overflow:'hidden'}}>
    <div style={{position:'absolute',width:bw,height:bh,transform:`scale(${scale},${sy})`,transformOrigin:'0 0',color:ink}}>
      <div style={{position:'absolute',left:portrait?72:100,right:portrait?72:100,top:70,display:'flex',justifyContent:'space-between',fontSize:23,letterSpacing:2,zIndex:40,color:overlayInk,textShadow:overlayShadow}}><span>{p.brand}</span><span>{String(p.scenes.indexOf(s!)+1).padStart(2,'0')} / {String(p.scenes.length).padStart(2,'0')}</span></div>
      {p.scenes.map(scene=><Sequence key={scene.id} from={scene.from} durationInFrames={scene.frames}><div style={box(geo.content)}><Graphics p={p} s={scene} portrait={portrait}/></div></Sequence>)}
      <PersistentPath p={p} portrait={portrait} frame={frame}/>
      {p.scenes.map(scene=><Sequence key={'photos-'+scene.id} from={scene.from} durationInFrames={scene.frames}><PhotoConstellation p={p} s={scene} portrait={portrait} frame={Math.max(0,frame-scene.from)}/></Sequence>)}
      <SceneTransition p={p} frame={frame}/>
      <Presenter p={p} portrait={portrait} frame={frame}/>
      {caption&&<div data-element="quest-caption" style={{...box(geo.caption),display:'flex',alignItems:'center',justifyContent:'center',fontSize:geo.captionSize,lineHeight:1.35,textAlign:'center',borderTop:`2px solid ${dark||blue?'#FFFFFF44':'#DCE0EB'}`,color:overlayInk,textShadow:overlayShadow,zIndex:40}}>{caption.text}</div>}
      <div style={{position:'absolute',left:portrait?72:100,right:portrait?72:100,bottom:portrait?105:38,display:'flex',alignItems:'center',gap:22,zIndex:40}}><span style={{fontSize:21,color:transitioning||blue?'#fff':color.accent,textShadow:overlayShadow}}>LV.{Math.min(99,p.scenes.indexOf(s!)+1)}</span><div style={{height:8,flex:1,background:dark||blue?'#FFFFFF33':'#E0E4EF'}}><div style={{height:'100%',background:transitioning||blue?'#fff':color.accent,width:`${frame/Math.max(1,p.durationFrames-1)*100}%`}}/></div></div>
      <div style={{position:'absolute',left:portrait?72:100,right:portrait?72:100,bottom:portrait?55:12,fontSize:portrait?20:17,opacity:.7,color:overlayInk,textShadow:overlayShadow,zIndex:40}}>{p.footer}</div>
    </div>
    {p.audio&&<Audio src={staticFile(p.audio)}/>}
  </AbsoluteFill>;
};
