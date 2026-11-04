// Independent full-speech candidate. Original 06 source and freeze stay intact.
import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Composition,OffthreadVideo,Sequence,continueRender,delayRender,cancelRender,registerRoot,staticFile,useCurrentFrame} from 'remotion';

export type Event={from:number;to:number;anchor:{kind:'word'|'cue';index:number;boundary:'start'|'end'};offsetFrames:number;meaning:string};
export type Scene={id:string;actionId:string;from:number;to:number;title:string;note:string;label:string;
  events:Record<string,Event>;disclosure?:string;medical?:boolean};
export type Shot={id:string;src:string;from:number;to:number;sourceFrom:number;objectPosition:string;description:string};
export type Props={templateId:string;version:string;durationInFrames:number;fps:number;scenes:Scene[];shots:Shot[];
 captions:{from:number;to:number;text:string}[];presenters:{src:string;from:number;to:number;sourceFrom:number}[];
 font:string;brand:string;medicalOverlay:string};
const blue='#1635F2',orange='#FF6B1A',cream='#FFF1C9';
const b=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const q=(f:number,a:number,z:number)=>Math.max(0,Math.min(1,(f-a)/(z-a)));
const smooth=(v:number)=>v*v*(3-2*v),out=(v:number)=>1-Math.pow(1-v,4),lerp=(a:number,z:number,v:number)=>a+(z-a)*v;
export const eventProgress=(f:number,s:Scene,key:string)=>{const e=s.events[key];if(!e)throw Error('Missing semantic internal event: '+key);return q(f,e.from,e.to);};
const progress=eventProgress;

function Footage({p}:{p:Props}) {
 return <>{p.shots.map(shot=><Sequence key={shot.id} from={shot.from} durationInFrames={shot.to-shot.from} layout="none">
   <OffthreadVideo data-role="main-video" data-shot={shot.id} data-global-from={shot.from} data-source-from={shot.sourceFrom}
     src={staticFile(shot.src)} startFrom={shot.sourceFrom} endAt={shot.sourceFrom+shot.to-shot.from}
     muted volume={0} playbackRate={1} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:shot.objectPosition}}/>
  </Sequence>)}</>;
}
function Wipe({f,s}:{f:number;s:Scene}) {
 const e=s.events.wipe;
 return <div style={{...b(0,270,720,554),overflow:'hidden',pointerEvents:'none',zIndex:25}}>{['#FFBE8C','#FF914F',orange].map((c,i)=>{
  const t=q(f,e.from+i*2,e.to+i*2),v=t<.5?Math.pow(t*2,5)/2:1-Math.pow((1-t)*2,5)/2;
  return <div key={c} style={{position:'absolute',left:'-80%',top:'-15%',height:'130%',width:'260%',background:c,
    transform:`translateX(${lerp(-75,75,v)}%) skewX(-12deg) scaleX(${1+.22*(1-Math.abs(t*2-1))})`}}/>;
 })}</div>;
}
function CutOpen({p,s,f}:{p:Props;s:Scene;f:number}) {
 const opening=smooth(progress(f,s,'aperture'));
 return <><div style={{...b(0,270,720,554),background:orange}}/><div data-element="hero-video" style={{...b(0,270,720,554),
   clipPath:`polygon(${49-opening*49}% 0,${51+opening*49}% 0,${67+opening*33}% 100%,${33-opening*33}% 100%)`,overflow:'hidden'}}><Footage p={p}/></div><Wipe f={f} s={s}/></>;
}
function PushNear({p,s,f}:{p:Props;s:Scene;f:number}) {
 const a=progress(f,s,'push'),cross=smooth(progress(f,s,'crossfade')),settle=out(progress(f,s,'settle'));
 // Same source window is sampled once. The explicit event changes camera focus;
 // editorial shot cuts remain in their independently validated global windows.
 const scale=lerp(1+.35*a*a*a,lerp(1.18,1.03,settle),cross);
 return <div data-element="push-camera" style={{...b(0,284,720,536),overflow:'hidden',clipPath:'polygon(0 0,100% 0,100% 88%,88% 100%,0 100%)'}}>
  <div style={{position:'absolute',inset:0,transform:`scale(${scale})`,filter:`blur(${lerp(a*6,6*(1-settle),cross)}px)`}}><Footage p={p}/></div>
 </div>;
}
function ObserveColour({p,s,f}:{p:Props;s:Scene;f:number}) {
 let edge=lerp(1,.5,smooth(progress(f,s,'splitHalf')));edge=lerp(edge,.12,smooth(progress(f,s,'splitEdge')));edge=lerp(edge,.5,smooth(progress(f,s,'splitReturn')));
 return <div style={{...b(0,284,720,536),overflow:'hidden'}}><Footage p={p}/>
  <div data-element="same-frame-grayscale" style={{position:'absolute',inset:0,clipPath:`inset(0 ${(1-edge)*100}% 0 0)`,backdropFilter:'grayscale(1)'}}/>
  <div data-element="split-divider" style={{...b(edge*720-3,0,6,536),background:orange}}><span style={{...b(-27,240,60,60),borderRadius:'50%',background:cream,color:blue,fontSize:31,fontWeight:900,textAlign:'center',lineHeight:'60px'}}>↔</span></div>
  <span style={{...b(44,32,190,40),background:blue,color:cream,padding:7,fontSize:21,fontWeight:800,visibility:edge>=.4?'visible':'hidden'}}>看见互动</span>
  <span style={{...b(500,32,176,40),background:orange,color:'#23180C',padding:7,fontSize:21,fontWeight:800,visibility:edge<=.6?'visible':'hidden'}}>感受快乐</span>
 </div>;
}
function CutClose({p,s,f}:{p:Props;s:Scene;f:number}) {
 return <><div style={{...b(0,284,720,536),overflow:'hidden',clipPath:'polygon(0 0,88% 0,100% 16%,100% 100%,0 100%)'}}><Footage p={p}/></div><Wipe f={f} s={s}/></>;
}

export const ACTIONS={
 'haike.chromatic-06.cut-open':CutOpen,'haike.chromatic-06.push-near':PushNear,
 'haike.chromatic-06.observe-colour':ObserveColour,'haike.chromatic-06.cut-close':CutClose,
};
export function sceneAt(p:Props,f:number) {const s=p.scenes.find(v=>f>=v.from&&f<v.to);if(!s)throw Error('Speech timeline gap');return s;}
function Presenter({p,f}:{p:Props;f:number}) {
 const clip=p.presenters.find(c=>f>=c.from&&f<c.to);if(!clip)return null;
 return <div data-role="presenter" style={{...b(496,864,176,220),overflow:'hidden',border:`3px solid ${orange}`,borderRadius:'0 26px 0 0',zIndex:30}}>
  <Sequence from={clip.from} durationInFrames={clip.to-clip.from} layout="none"><OffthreadVideo src={staticFile(clip.src)} startFrom={clip.sourceFrom}
   endAt={clip.sourceFrom+clip.to-clip.from} muted volume={0} playbackRate={1} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/></Sequence>
  <div style={{position:'absolute',bottom:0,left:0,right:0,background:blue,color:cream,padding:6,fontSize:15,textAlign:'center',fontWeight:800}}>侯总 · AI数字人</div>
 </div>;
}
function Drawing(p:Props) {
 const f=useCurrentFrame(),s=sceneAt(p,f),Action=ACTIONS[s.actionId as keyof typeof ACTIONS];
 if(!Action||p.templateId!=='chromatic-06'||p.version!=='1.2.0-candidate.1')throw Error('Unknown motion contract identity');
 const caption=p.captions.find(c=>f>=c.from&&f<c.to);
 const active=s.events.note?out(progress(f,s,'note')):1;
 return <AbsoluteFill style={{background:blue,overflow:'hidden'}}><div data-template="chromatic-06" data-version={p.version} data-action={s.actionId}
   data-stage={s.id} style={{...b(0,0,720,1280),transform:'scale(1.5)',transformOrigin:'0 0',background:blue,color:cream,fontFamily:'HaikeChromaticHD',overflow:'hidden',boxSizing:'border-box'}}>
  <div style={{...b(44,40,632,28),fontSize:17,letterSpacing:2,display:'flex',justifyContent:'space-between'}}><b>{p.brand} / 现场体验</b><span>06 — VIDEO</span></div>
  <div style={{...b(44,94,70,8),background:orange}}/>
  <div data-role="headline" style={{...b(44,124,632,150),fontSize:61,fontWeight:900,lineHeight:1.08,whiteSpace:'pre-line'}}>{s.title}</div>
  <Action p={p} s={s} f={f}/>
  <div style={{...b(44,778,420,46),background:orange,color:'#201A10',fontSize:23,fontWeight:900,padding:'8px 16px',clipPath:'polygon(0 0,100% 0,94% 100%,0 100%)'}}>{s.label}</div>
  <div data-role="note" style={{...b(44,864,p.presenters.some(c=>f>=c.from&&f<c.to)?406:632,164),fontSize:s.medical?32:38,fontWeight:900,lineHeight:1.3,whiteSpace:'pre-line',opacity:active}}>{s.note}</div>
  {s.disclosure&&<div style={{...b(44,1042,632,35),fontSize:18,color:orange}}>{s.disclosure}</div>}
  {s.medical&&<div data-role="medical-disclaimer" style={{...b(44,986,632,104),padding:'12px 14px',background:'#0726C5',fontSize:22,fontWeight:800,lineHeight:1.5,whiteSpace:'pre-line'}}>{p.medicalOverlay}</div>}
  <Presenter p={p} f={f}/>
  <div data-role="caption" style={{...b(44,1110,632,88),background:cream,color:blue,fontSize:27,lineHeight:1.3,fontWeight:800,padding:'14px 18px',display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',whiteSpace:'pre-line'}}>{caption?.text||''}</div>
  <div style={{...b(44,1226,632,24),fontSize:16,display:'flex',justifyContent:'space-between'}}><span>先体验，再理解。</span><span>{p.scenes.indexOf(s)+1} / {p.scenes.length}</span></div>
  <div style={{...b(0,1270,720*(f+1)/p.durationInFrames,10),background:orange}}/>
 </div></AbsoluteFill>;
}
export function ChromaticProduction(p:Props) {
 const [hold]=useState(()=>delayRender('Loading bound HD font'));
 useEffect(()=>{new FontFace('HaikeChromaticHD',`url('${staticFile(p.font)}')`).load().then(face=>{document.fonts.add(face);continueRender(hold);}).catch(cancelRender);return()=>continueRender(hold);},[hold,p.font]);
 return <Drawing {...p}/>;
}
const EMPTY:any={};
function Root(){return <Composition id="Chromatic06Production" component={ChromaticProduction} width={1080} height={1920} fps={30} durationInFrames={1800}
 defaultProps={EMPTY} calculateMetadata={({props})=>({width:1080,height:1920,fps:30,durationInFrames:props.durationInFrames})}/>;}
registerRoot(Root);
