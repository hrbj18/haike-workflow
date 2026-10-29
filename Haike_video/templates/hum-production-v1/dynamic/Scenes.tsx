import React,{useEffect,useMemo} from 'react';
import {AbsoluteFill,Audio,Img,OffthreadVideo,Sequence,staticFile,useCurrentFrame} from 'remotion';
import type {Media,Props,Scene} from '../types';
import layout from './layout.json';
import {buildMotion,type Action} from './motion';
import {buildItems,computeItemBaseRotation} from './vendor/layouts';
import {gsap} from 'gsap';
const box=(b:number[]):React.CSSProperties=>({position:'absolute',left:b[0],top:b[1],width:b[2],height:b[3]});
const family='HaikeProductionBody';
export const dynamicPalette=(p:Props)=>p.visualStyle==='playroom'?layout.playroom:layout.archive;
const Surface:React.FC<{m:Media;live?:boolean;ink:string}>=({m,live=false,ink})=><div style={{position:'absolute',inset:0,overflow:'hidden',backgroundColor:ink}}>{live&&m.kind!=='image'?<OffthreadVideo src={staticFile(m.src)} startFrom={Math.round(m.offset*30)} muted style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',objectPosition:m.objectPosition||'50% 50%'}}/>:<Img src={staticFile(m.kind==='image'?m.src:m.thumbnail)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>}</div>;
const Panel:React.FC<{p:Props;m:Media;live:boolean;label?:boolean}>=({p,m,live,label=true})=>{const t=dynamicPalette(p),play=p.visualStyle==='playroom';return <div style={{position:'absolute',inset:0,border:play?`5px solid ${t.ink}`:`2px solid ${t.line}`,borderRadius:play?25:7,background:t.paper,overflow:'hidden',boxShadow:play?`8px 9px 0 ${t.ink}`:'0 12px 30px #24445920'}}><div style={{position:'absolute',inset:play?10:8,bottom:label?56:8,overflow:'hidden',borderRadius:play?13:1}}><Surface m={m} live={live} ink={play?'#19285A':'#18333F'}/></div>{label&&<div style={{position:'absolute',bottom:8,left:18,right:18,height:35,color:t.ink,fontFamily:family,fontSize:25,display:'flex',alignItems:'center',justifyContent:'space-between'}}><span>{m.label||'门店活动记录'}</span>{live&&<span style={{fontSize:19,color:t.muted}}>实拍</span>}</div>}</div>};
const Cursor:React.FC<{state:{x:number;y:number;opacity:number;press:number};color:string}>=({state:s,color})=><div style={{position:'absolute',left:s.x,top:s.y,opacity:s.opacity,zIndex:80,transform:`scale(${1-s.press*.14})`,transformOrigin:'0 0'}}><svg width="57" height="76" viewBox="0 0 57 76"><path d="M5 3 L5 59 L20 45 L32 70 L43 65 L31 42 L52 42Z" fill="white" stroke={color} strokeWidth="4"/></svg><div style={{position:'absolute',left:-31,top:-31,width:64,height:64,border:`5px solid ${color}`,borderRadius:'50%',opacity:s.press,transform:`scale(${1+s.press*.6})`}}/></div>;
const Statement:React.FC<{p:Props;s:Scene}>=({p,s})=>{const f=useCurrentFrame(),t=dynamicPalette(p),play=p.visualStyle==='playroom';const motion=useMemo(()=>{const lines=s.title.split('\n').map(()=>({y:65,opacity:0})),note={y:20,opacity:0};const tl=gsap.timeline({paused:true});lines.forEach((v,i)=>tl.to(v,{y:0,opacity:1,duration:.75,ease:'power3.out'},i*.12));tl.to(note,{y:0,opacity:1,duration:.7,ease:'power2.out'},.35);tl.pause(0);gsap.ticker.sleep();return {lines,note,tl}},[s.id,s.title]);useEffect(()=>()=>{motion.tl.kill()},[motion]);motion.tl.time(f/30,false);return <><div style={{position:'absolute',left:88,top:400,width:1264,color:t.ink,fontFamily:'HaikeProductionDisplay',fontSize:112,lineHeight:1.25}}>{s.title.split('\n').map((line,i)=><div key={i} style={{opacity:motion.lines[i].opacity,transform:`translateY(${motion.lines[i].y}px)`}}>{line}</div>)}</div>{s.subtitle&&<div style={{position:'absolute',left:92,top:850,width:1250,color:t.muted,fontSize:44,lineHeight:1.6,whiteSpace:'pre-wrap',opacity:motion.note.opacity,transform:`translateY(${motion.note.y}px)`}}>{s.subtitle}</div>}<div style={{position:'absolute',left:88,top:1190,width:play?800:450,height:play?18:3,background:t.accent,opacity:motion.note.opacity}}/></>};
export const DynamicScene:React.FC<{p:Props;s:Scene}>=({p,s})=>{
 const f=useCurrentFrame(),t=dynamicPalette(p),play=p.visualStyle==='playroom';
 const pool=s.wallMediaIds!.map(id=>p.media.find(m=>m.id===id)!),main=pool.find(m=>m.id===s.mediaId)!,selected=pool.indexOf(main);
 const items=pool.map(m=>({id:m.id,img:m.thumbnail,width:m.orientation==='portrait'?9:16,height:m.orientation==='portrait'?16:9}));
 const key=JSON.stringify([s.motion,s.frames,items,selected,play]);
 const motion=useMemo(()=>buildMotion(s.motion as Action,items,selected,s.frames,play),[key]);
 useEffect(()=>()=>{motion.timeline.kill()},[motion]);motion.timeline.time(f/30,false);
 const dome=useMemo(()=>buildItems(pool.map(m=>({src:m.thumbnail,alt:m.label||''})),14),[key]);
 const rotations=dome.map(it=>computeItemBaseRotation(it.x,it.y,it.sizeX,it.sizeY,14));
 const signed=(v:number)=>((v+180)%360+360)%360-180;
 const front=rotations.reduce((best,r,i)=>Math.abs(signed(r.rotateY+24))+Math.abs(r.rotateX)*2<Math.abs(signed(rotations[best].rotateY+24))+Math.abs(rotations[best].rotateX)*2?i:best,0);
 return <><div data-element="dynamic-heading" style={{...box(layout.title),fontFamily:'HaikeProductionDisplay',fontSize:layout.titleSize,lineHeight:1.12,color:t.ink,fontWeight:play?800:500,whiteSpace:'pre'}}>{s.title}</div>
 {s.subtitle&&<div style={{...box(layout.subtitle),color:t.muted,fontSize:layout.subtitleSize,fontFamily:family}}>{s.subtitle}</div>}
 <div data-element="dynamic-stage" data-motion={s.motion} style={{...box(layout.stage),overflow:'hidden',borderRadius:play?24:3}}>
 {s.motion==='spatial-gallery'?<><div style={{position:'absolute',inset:0,perspective:2600,perspectiveOrigin:'50% 50%',background:play?t.card:'#C8D9E5'}}><div style={{position:'absolute',left:'50%',top:'50%',width:0,height:0,transformStyle:'preserve-3d',transform:`translateZ(-1300px) rotateX(${motion.camera.x}deg) rotateY(${motion.camera.y}deg) scale(${motion.camera.zoom})`}}>{dome.map((it,i)=>{const r=rotations[i],m=i===front?main:pool.find(x=>x.thumbnail===it.src)!;return <div key={i} style={{position:'absolute',left:-292,top:-292,width:584,height:584,transformStyle:'preserve-3d',backfaceVisibility:'hidden',transform:`rotateY(${r.rotateY}deg) rotateX(${r.rotateX}deg) translateZ(1300px)`}}><div style={{position:'absolute',inset:12}}><Panel p={p} m={m} live={i===front}/></div></div>})}</div></div><div style={{position:'absolute',inset:0,pointerEvents:'none',boxShadow:`inset 0 0 90px 25px ${play?'#172A6535':'#335F7244'}`}}/></>:
 <>{motion.states.map((v,i)=><div key={pool[i].id} data-media-id={pool[i].id} data-main={i===selected} style={{position:'absolute',left:v.x,top:v.y,width:v.w,height:v.h,opacity:v.opacity,transform:`scale(${v.scale}) rotate(${v.rotation}deg)`,zIndex:i===selected?30:i+1,transformOrigin:'50% 50%'}}><Panel p={p} m={pool[i]} live={i===selected}/></div>)}{s.motion==='click-open'&&<Cursor state={motion.cursor} color={t.accent}/>}</>}
 </div></>;
};
export const DynamicContent:React.FC<Props&{presenterLayer?:React.ReactNode}>=p=>{
 const f=useCurrentFrame(),t=dynamicPalette(p),play=p.visualStyle==='playroom',cue=p.captions.find(c=>f/30*1000>=c.startMs&&f/30*1000<c.endMs);
 return <AbsoluteFill style={{backgroundColor:t.bg,fontFamily:family,overflow:'hidden'}}>
 {play?<><div style={{position:'absolute',right:-120,top:-160,width:420,height:420,border:`32px solid ${t.ink}`,borderRadius:'50%'}}/><div style={{position:'absolute',left:-90,top:730,width:170,height:280,background:t.accent,transform:'rotate(-16deg)'}}/></>:<><div style={{position:'absolute',left:88,right:88,top:172,height:1,background:t.line}}/><div style={{position:'absolute',right:70,top:212,width:12,height:170,background:t.accent}}/></>}
 <div style={{position:'absolute',left:88,top:62,right:88,display:'flex',justifyContent:'space-between',alignItems:'center',color:t.ink,fontSize:32}}><span>{p.brand}</span><span style={{fontSize:24,border:play?`3px solid ${t.ink}`:undefined,borderRadius:24,padding:'4px 14px',background:play?t.paper:undefined}}>{play?'亲手体验':'社区日常'}</span></div>
 <div style={{position:'absolute',left:88,top:122,color:t.muted,fontSize:24}}>{p.footer}</div>
 {p.scenes.map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={30}><AbsoluteFill>{s.module==='dynamic'?<DynamicScene p={p} s={s}/>:<Statement p={p} s={s}/>}</AbsoluteFill></Sequence>)}
 {p.presenterLayer}
 <div style={{position:'absolute',left:88,right:88,top:1450,height:158,borderTop:`2px solid ${t.line}`,display:'flex',alignItems:'center',justifyContent:'center',color:t.ink,fontSize:76,lineHeight:1.2,textAlign:'center'}}>{cue?.text||''}</div>
 <div style={{position:'absolute',left:88,bottom:75,color:t.muted,fontSize:24}}>陈家林路63号 · 未来汇一楼</div>
 {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill>;
};
