// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {AbsoluteFill, Audio, Composition, OffthreadVideo, Sequence, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {SnapCnUIProvider} from '../../motion-components/snapcn/upstream/registry/snap-cn-ui/core';
import {TextReveal} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-reveal';
import {Font} from '../animation-signatures-v2/shared';
import plan from '../kinetic-field-v1/layout.json';
import defaultContent from '../kinetic-field-v1/content.json';
import {CurrentEpisode,AbsoluteFrame,VideoImage as Img,VideoImage} from './Common';
import type {Episode} from './types';

const Content=React.createContext(defaultContent);
const useContent=()=>React.useContext(Content);

const P=plan.palette;
const clamp=(p:number)=>Math.max(0,Math.min(1,p));
const smooth=(p:number)=>{p=clamp(p);return p*p*(3-2*p);};
const tween=(t:number,a:number,b:number,x=0,y=1)=>x+(y-x)*smooth((t-a)/(b-a));
const pop=(t:number,start:number,d=.5)=>{const p=clamp((t-start)/d);return 1-Math.pow(1-p,3)*Math.cos(p*Math.PI*2);};
const box=(x:number,y:number,w:number,h:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width:w,height:h});
const time=()=>useCurrentFrame()/useVideoConfig().fps;

function Clip({name,position}:{name:string;at?:number;offset?:number;position?:string}){
 return <VideoImage src={name} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:position||'50% 50%'}}/>;
}
function useActionWindows(){const episode=React.useContext(CurrentEpisode);return(name:string,end=false)=>{const event=episode.actions['haike.kinetic-field-v1.video.'+name];if(!event)throw Error('Unknown executed kinetic action '+name);return (end?event.to:event.from)/episode.fps;};}

function Burst({x,y,size=180,color=P.lime,rotation=0}:{x:number;y:number;size?:number;color?:string;rotation?:number}){
 const points=Array.from({length:32},(_,i)=>{const a=i*Math.PI/16,r=i%2?37:50;return `${50+Math.cos(a)*r},${50+Math.sin(a)*r}`;}).join(' ');
 return <svg viewBox="0 0 100 100" style={{...box(x,y,size,size),transform:`rotate(${rotation}deg)`}}><polygon points={points} fill={color}/></svg>;
}
function Paper({color=P.lime}:{color?:string}){
 return <AbsoluteFill style={{background:color}}><div style={{position:'absolute',inset:0,opacity:.12,backgroundImage:'radial-gradient(#121418 1px, transparent 1.2px)',backgroundSize:'12px 12px'}}/><div style={{...box(-90,180,750,70),background:P.blue,transform:'rotate(-13deg)'}}/><div style={{...box(-70,810,750,90),background:P.coral,transform:'rotate(10deg)'}}/></AbsoluteFill>;
}
function Label({children,x,y,rotate=0,color=P.lime,ink=P.ink,scale=1,size=34}:{children:React.ReactNode;x:number;y:number;rotate?:number;color?:string;ink?:string;scale?:number;size?:number}){
 return <div style={{position:'absolute',left:x,top:y,background:color,color:ink,padding:'8px 15px',fontSize:size,fontWeight:900,lineHeight:1.15,whiteSpace:'nowrap',border:`3px solid ${P.ink}`,boxShadow:`6px 6px 0 ${P.ink}`,transform:`rotate(${rotate}deg) scale(${scale})`,transformOrigin:'left center'}}>{children}</div>;
}
function Tape({t,y,text,from=0,color=P.lime}:{t:number;y:number;text:string;from?:number;color?:string}){
 const a=tween(t,from,from+.45);
 return <div style={{...box(-50,y,700,50),background:color,color:P.ink,transform:`rotate(-4deg) scaleX(${a})`,overflow:'hidden',borderTop:`3px solid ${P.ink}`,borderBottom:`3px solid ${P.ink}`}}><div style={{fontSize:24,fontWeight:900,whiteSpace:'nowrap',transform:`translateX(${-((t-from)*22)%160}px)`,lineHeight:'44px'}}>{Array(6).fill(text+'  ↗  ').join('')}</div></div>;
}
function Shell(){const c=useContent(),at=useActionWindows();return <><div style={{...box(20,22,500,50),display:'flex',alignItems:'center',justifyContent:'space-between',zIndex:100}}><span style={{background:P.ink,color:P.lime,fontSize:25,padding:'7px 13px',fontWeight:850,border:'2px solid white'}}>{c.topic}</span><span style={{fontSize:17,color:P.ink,background:P.lime,padding:'6px 9px',fontWeight:800}}>{c.brand}</span></div></>;}
function Duo(){
 const c=useContent(),at=useActionWindows();
 const t=time();const divide=tween(t,at('split-divider-morph'),at('split-divider-morph',true),.72,.52),settle=pop(t,at('angled-panel-settle'),.5);
 return <AbsoluteFill><Paper/>
  <div style={{...box(12,105,516,737),transform:`rotate(${(1-settle)*-8-2}deg) scale(${.96+.04*settle})`,border:`7px solid ${P.ink}`,boxShadow:`12px 14px 0 ${P.blue}`,overflow:'hidden'}}>
   <div style={{position:'absolute',inset:0,clipPath:`polygon(0 0,100% 0,100% ${divide*100-5}%,0 ${divide*100+5}%)`}}><div style={{...box(0,0,516,(divide+.05)*737)}}><Clip name="robot.mp4" position="50% 76%"/></div></div>
   <div style={{position:'absolute',inset:0,clipPath:`polygon(0 ${divide*100+5}%,100% ${divide*100-5}%,100% 100%,0 100%)`}}><div style={{...box(0,(divide-.05)*737,516,(1-divide+.05)*737)}}><Clip name="dog.mp4" position="50% 62%"/></div></div>
   <svg viewBox="0 0 516 737" style={{position:'absolute',inset:0}}><line x1="0" y1={(divide+.05)*737} x2="516" y2={(divide-.05)*737} stroke={P.lime} strokeWidth="16"/></svg>
  </div>
  <Label x={34} y={132} rotate={-4} scale={Math.max(.01,pop(t,at('keyword-assemble'),.5))}>{c.upperLabel}</Label>
  <Label x={300} y={660} color={P.coral} rotate={5} scale={Math.max(.01,pop(t,at('keyword-assemble')+.35,.5))}>{c.lowerLabel}</Label>
  <Tape t={t} y={852} text={c.tape} from={at('tape-reveal')}/>
 </AbsoluteFill>;
}
function Hands(){
 const c=useContent(),at=useActionWindows();
 const t=time(),iris=tween(t,at('footage-iris'),at('footage-iris',true),0,145),focus=tween(t,at('detail-loupe'),at('detail-loupe',true));
 return <AbsoluteFill style={{clipPath:`circle(${iris}% at 50% 55%)`}}><Paper color={P.blue}/>
  <div style={{...box(17,108,506,744),overflow:'hidden',border:`6px solid ${P.ink}`,transform:'rotate(2deg)'}}><Clip name="children.mp4" at={3.2} offset={3}/></div>
  <div style={{...box(-20,84,580,120),background:P.lime,transform:'rotate(-4deg)',borderBottom:`7px solid ${P.ink}`}}><div style={{...box(48,18,460,90),fontSize:62,fontWeight:950,color:P.ink,clipPath:`inset(0 ${tween(t,at('short-marker'),at('short-marker',true),100,0)}% 0 0)`}}>{c.detailTitle}</div></div>
  <svg style={{position:'absolute',inset:0}} viewBox="0 0 540 960"><path d="M405 715 Q510 610 400 482" stroke={P.lime} strokeWidth="9" strokeLinecap="round" fill="none" pathLength="1" strokeDasharray="1" strokeDashoffset={1-tween(t,at('hand-drawn-arrow'),at('hand-drawn-arrow',true))}/><path d="M400 482 l-3 36 m3-36 l29 21" stroke={P.lime} strokeWidth="8" fill="none" opacity={tween(t,at('hand-drawn-arrow')+.3,at('hand-drawn-arrow',true))}/></svg>
  <div style={{...box(290,414,224,224),borderRadius:'50%',border:`9px solid ${P.lime}`,overflow:'hidden',boxShadow:`7px 9px 0 ${P.ink}`,transform:`scale(${focus})`,transformOrigin:'80% 90%'}}><div style={{position:'absolute',width:560,height:996,left:-110,top:-512}}><Clip name="children.mp4" at={3.2} offset={3} position="50% 50%"/></div></div>
  <Label x={35} y={784} color={P.coral} rotate={-3} size={35} scale={Math.max(.01,pop(t,at('hand-drawn-arrow'),.45))}>{c.detailLabel}</Label>
  <div style={{...box(32,900,480,20),background:P.lime,transform:`scaleX(${tween(t,at('footage-iris'),at('detail-loupe',true)+1)})`,transformOrigin:'left'}}/>
 </AbsoluteFill>;
}
function Collage(){
 const c=useContent(),at=useActionWindows();
 const t=time();const cards=[{src:'robot.jpg',x:20,y:140,r:-9},{src:'store.jpg',x:170,y:230,r:9},{src:'children.jpg',x:60,y:340,r:-3}];
 return <AbsoluteFill><Paper color={P.coral}/>{cards.map((c,i)=>{const p=i===0?1:tween(t,at('photo-cascade')+i*.16,at('photo-cascade',true)+i*.16);return <div key={c.src} style={{...box(c.x,c.y,330,430),background:'white',padding:8,border:`4px solid ${P.ink}`,transform:`translateY(${(1-p)*600}px) rotate(${c.r}deg)`,boxShadow:`8px 10px 0 ${P.ink}`}}><Img src={staticFile(c.src)} style={{width:'100%',height:'100%',objectFit:'cover'}}/></div>;})}<Label x={50} y={810} rotate={-4} scale={Math.max(.01,pop(t,at('photo-cascade')+.54,.4))}>{c.collageLabel}</Label></AbsoluteFill>;
}
function Location(){
 const c=useContent(),at=useActionWindows();
 const t=time(),reveal=tween(t,at('stack-to-location'),at('stack-to-location',true)),floor=tween(t,at('floor-strip'),at('floor-strip',true)),push=tween(t,at('location-focus'),at('location-focus',true));
 return <AbsoluteFill style={{clipPath:`inset(0 ${(1-reveal)*100}% 0 0)`}}><Paper/>
  <div style={{...box(14,100,512,420),border:`6px solid ${P.ink}`,overflow:'hidden',transform:`rotate(${-2+push*2}deg) scale(${1+push*.035})`,boxShadow:`9px 9px 0 ${P.blue}`}}><Clip name="store.mp4" at={7.4} offset={2}/></div>
  {t>=React.useContext(CurrentEpisode).presenters[0].from/useVideoConfig().fps?<div style={{...box(60,532,420,360),border:`6px solid ${P.ink}`,overflow:'hidden',transform:'rotate(2deg)',boxShadow:`12px 9px 0 ${P.coral}`}}><Clip name="host-close.mp4" at={8} position="50% 28%"/></div>:null}
  <div style={{...box(407,368,90,120),transform:`scale(${Math.max(.01,pop(t,at('pin-pop'),.55))})`}}><svg viewBox="0 0 100 130"><path d="M50 126 C44 108 8 71 8 46 A42 42 0 0 1 92 46 C92 71 56 108 50 126" fill={P.coral} stroke={P.ink} strokeWidth="5"/><circle cx="50" cy="45" r="15" fill={P.lime}/></svg></div>
  <div style={{...box(-20,474,580,85),background:P.blue,color:'white',border:`5px solid ${P.ink}`,transform:`rotate(-4deg) scaleX(${floor})`,overflow:'hidden'}}><div style={{fontSize:45,fontWeight:900,textAlign:'center',lineHeight:'75px'}}>{c.venue} <span style={{color:P.lime}}>{c.floor}</span></div></div>
  <div style={{...box(18,900,505,35),color:P.ink,fontWeight:800,fontSize:23,textAlign:'center'}}>{c.address}</div>
 </AbsoluteFill>;
}
function Invitation(){
 const c=useContent(),at=useActionWindows();
 const t=time(),settle=tween(t,at('portrait-disc'),at('portrait-disc',true)),fan=tween(t,at('photo-fan'),at('photo-fan',true));
 return <AbsoluteFill><Paper color={P.blue}/>
  <Burst x={-135} y={105} size={800} color={P.lime} rotation={20}/>
  <div style={{...box(23,210,494,610),background:P.ink,borderRadius:'48% 48% 43% 43%',padding:8,transform:`scale(${.88+.12*settle}) rotate(${(1-settle)*-8}deg)`,boxShadow:`14px 15px 0 ${P.coral}`}}><div style={{width:'100%',height:'100%',borderRadius:'inherit',overflow:'hidden'}}><Clip name="host-open.mp4" at={12} position="50% 25%"/></div></div>
  {t>=at('headline-assemble')?<div style={{...box(-5,84,550,135),color:P.lime,background:P.blue,border:`5px solid ${P.ink}`,transform:'rotate(-3deg)',overflow:'hidden'}}><Sequence from={Math.round(at('headline-assemble')*24)} layout="none"><TextReveal text={c.closingTitle} fontSize={66} fontWeight={950} fontFamily="Haike Sans" color={P.lime} initialScale={1.15} introDuration={3} holdDuration={3} recedeDuration={5} assembleDuration={9} wordDelay={2} wordStagger={3} wordDuration={6}/></Sequence></div>:null}
  {[['robot.jpg',-28,-12],['children.jpg',199,4],['dog.jpg',408,13]].map(([src,x,r],i)=><div key={String(src)} style={{...box(Number(x),765,162,165),border:`5px solid white`,background:P.ink,boxShadow:`5px 6px 0 ${P.ink}`,overflow:'hidden',transform:`translateY(${(1-fan)*220}px) rotate(${r}deg)`}}><Img src={staticFile(String(src))} style={{width:'100%',height:'100%',objectFit:'cover'}}/></div>)}
  <div style={{...box(357,650,160,94),transform:`rotate(9deg) scale(${Math.max(.01,pop(t,at('invitation-stamp'),.45))})`,border:`5px solid ${P.ink}`,background:P.coral,color:P.ink,display:'grid',placeItems:'center',fontSize:38,fontWeight:950,boxShadow:`6px 7px 0 ${P.lime}`}}>{c.stamp}</div>
 </AbsoluteFill>;
}
export function KineticProduction({episode}:{episode:Episode}){const t=time(),f=React.useContext(AbsoluteFrame),content=episode.content,s=episode.stages;return <Content.Provider value={content}><AbsoluteFill style={{fontFamily:'Haike Sans',overflow:'hidden',background:P.ink}}><Font/><style>{'*,*:before,*:after{box-sizing:border-box}'}</style><SnapCnUIProvider theme={{background:P.lime,foreground:P.ink,primary:P.coral,fontFamily:'Haike Sans'}}>
 {f<s[0].to?<Duo/>:null}{f>=s[1].from&&f<s[1].to?<Hands/>:null}{f>=s[2].from&&f<s[2].to?<Collage/>:null}{f>=s[3].from&&f<s[3].to?<Location/>:null}{f>=s[4].from?<Invitation/>:null}<Shell/>
 </SnapCnUIProvider></AbsoluteFill></Content.Provider>;}