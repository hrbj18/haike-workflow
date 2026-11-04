import React from 'react';
import {AbsoluteFill,Freeze,Img,Sequence,useCurrentFrame,Video} from 'remotion';
import GridToHero from 'talkcraft-private:grid-to-hero';
import type {Episode} from '../chromatic-motion-lab-v1/AvatarScene';
import plan from './selection.json';

const P=plan.palette;
const box=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const p=(f:number,a:number,b:number)=>Math.max(0,Math.min(1,(f-a)/(b-a)));
const ease=(t:number)=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const imageStyle:React.CSSProperties={width:'100%',height:'100%',objectFit:'cover'};

function Title({text,demote=false}:{text:string;demote?:boolean}){
 const f=useCurrentFrame(),t=demote?ease(p(f,39,63)):0;
 return <div data-element="headline" style={{...box(48,demote?mix(348,136,t):136,624,210),fontSize:demote?mix(80,38,t):76,fontWeight:900,lineHeight:1.08,whiteSpace:'pre-line',opacity:p(f,0,12),transformOrigin:'top left'}}>{text}</div>;
}
function Arrive({episode}:{episode:Episode}){
 const f=useCurrentFrame();
 return <><Title text={episode.segments![0].headline!} demote/>
 <div data-element="material" style={{...box(48,272,624,514),border:`2px solid ${P.ink}`,overflow:'hidden',opacity:p(f,51,75),clipPath:`inset(0 ${(1-ease(p(f,51,87)))*100}% 0 0)`}}>
  <Img src={episode.photos[0]} style={imageStyle}/><span style={{position:'absolute',bottom:0,left:0,right:0,padding:'20px 24px',fontSize:28,fontWeight:800,background:P.ink,color:P.bg}}>现场，是最好的开场 ↗</span>
 </div></>;
}
function Compare({episode}:{episode:Episode}){
 const f=useCurrentFrame();
 return <><Title text={episode.segments![1].headline!}/>
 <div data-element="material" className="native-grid" style={{...box(48,362,624,351),overflow:'hidden'}}>
  <div style={{width:960,height:540,transform:'scale(.65)',transformOrigin:'top left',position:'relative'}}>
   <Freeze frame={Math.min(f,202)}><GridToHero srcs={[0,2,4,6].map(i=>episode.photos[i])} labels={['','','','']} heroIdx={2}/></Freeze>
  </div>
 </div>
 <div style={{...box(48,758,624,70),fontSize:28,fontWeight:800,textAlign:'center',opacity:p(f,38,48)}}>并列 → 聚焦 → 回到全景</div></>;
}
function Connect({episode}:{episode:Episode}){
 const f=useCurrentFrame(),draw=p(f,18,52);
 return <><Title text={episode.segments![2].headline!}/>
 <svg data-element="handoff-line" width={720} height={840} style={{position:'absolute',inset:0,overflow:'visible'}}>
  <path d="M48 326 H146 Q168 326 168 348 V378 Q168 400 190 400 H648 Q672 400 672 424 V768 Q672 792 648 792 H72 Q48 792 48 768 V424 Q48 400 72 400 H190" pathLength={1} fill="none" stroke={P.accent} strokeWidth={6} strokeDasharray={1} strokeDashoffset={1-draw}/>
 </svg>
 <div data-element="material" style={{...box(72,424,576,344),overflow:'hidden',opacity:p(f,53,68),transform:`translateY(${(1-ease(p(f,53,77)))*18}px)`}}><Img src={episode.photos[2]} style={imageStyle}/>
  <span style={{position:'absolute',left:0,bottom:0,right:0,padding:'14px 18px',background:P.ink,color:P.bg,fontSize:28,fontWeight:800}}>看到 → 参与 → 理解</span>
 </div></>;
}
function Converge({episode}:{episode:Episode}){
 const f=useCurrentFrame(),travel=ease(p(f,42,82)),labels=['走进现场','亲手体验','看见细节'],origins=[[56,388],[394,388],[225,536]];
 return <><Title text={episode.segments![3].headline!}/>
 <svg data-element="source-paths" width={720} height={820} style={{position:'absolute',inset:0,opacity:1-p(f,82,94)}}>
  {origins.map(([x,y],i)=><path key={i} d={`M${x+135} ${y+46} Q${i===0?176:i===1?548:360} 650 360 694`} pathLength={1} fill="none" stroke={P.accent} strokeWidth={4} strokeDasharray={1} strokeDashoffset={1-p(f,30,42)}/>)}</svg>
 {origins.map(([x,y],i)=>{
  // Quadratic paths match the SVG paths; labels shrink only after most travel is complete.
  const a=1-travel,cx=i===0?176:i===1?548:360;
  const px=a*a*(x+135)+2*a*travel*cx+travel*travel*360,py=a*a*(y+46)+2*a*travel*650+travel*travel*694;
  return <div data-element={`source-${i}`} key={i} style={{...box(px-135,py-46,270,92),display:'flex',alignItems:'center',gap:14,padding:10,background:P.paper,border:`2px solid ${P.ink}`,borderRadius:8,fontSize:28,fontWeight:800,opacity:1-p(f,77,83),transform:`scale(${1-.9*p(travel,.75,1)})`}}><Img src={episode.photos[[0,4,2][i]]} style={{width:66,height:66,objectFit:'cover',borderRadius:3}}/>{labels[i]}</div>;
 })}
 <div data-element="conclusion" style={{...box(48,mix(621,380,ease(p(f,83,107))),624,mix(146,410,ease(p(f,83,107)))),overflow:'hidden',background:P.ink,color:P.bg,fontSize:36,fontWeight:900,border:`2px solid ${P.ink}`,borderBottom:`9px solid ${P.accent}`,opacity:p(f,83,99)}}><Img src={episode.photos[4]} style={imageStyle}/><span style={{position:'absolute',left:0,right:0,bottom:0,padding:'24px 18px',textAlign:'center',background:'linear-gradient(transparent,#124A49 35%)'}}>把体验连成新发现</span></div>
 </>;
}
const parts=[Arrive,Compare,Connect,Converge];
function Stage({episode,index}:{episode:Episode;index:number}){
 const f=useCurrentFrame(),Part=parts[index],s=plan.scenes[index],localStable=s.stableFrom-s.from;
 return <AbsoluteFill data-stage={s.id} data-layout={s.id} data-effect={s.selections[0].id} data-local-frame={f} data-reading={f>=localStable}>
  <div style={{...box(48,92,624,24),fontSize:18,letterSpacing:3,fontWeight:700}}>{s.kicker}</div>
  <Part episode={episode}/>
  <div data-element="note" style={{...box(48,884,410,164),fontSize:33,lineHeight:1.3,fontWeight:800,whiteSpace:'pre-line',opacity:p(f,s.noteFrom,s.noteFrom+14)}}><span style={{display:'block',width:42,height:6,background:P.accent,marginBottom:16}}/>{s.note}</div>
 </AbsoluteFill>;
}
export function CandidateScene({episode}:{episode:Episode}){
 const f=useCurrentFrame(),i=plan.scenes.findIndex(s=>f>=s.from&&f<s.to),s=plan.scenes[i];
 if(!s)throw Error('Frame outside candidate clock');
 return <AbsoluteFill data-template="field-notes-v2-candidate" style={{background:P.bg,color:P.ink,fontFamily:episode.fontFamily,overflow:'hidden'}}>
  <div style={{...box(0,0,10,1280),background:P.accent}}/>
  <div style={{...box(48,42,624,26),fontSize:17,letterSpacing:2,display:'flex',justifyContent:'space-between'}}><b>FIELD NOTES / 现场笔记</b><span>VOL. 02</span></div>
  <Sequence key={s.id} from={s.from} durationInFrames={s.to-s.from} layout="none"><Stage episode={episode} index={i}/></Sequence>
  <div data-role="presenter" style={{...box(486,850,186,232),borderRadius:'95px 95px 8px 8px',overflow:'hidden',border:`3px solid ${P.ink}`,background:P.paper}}>
   <Video data-avatar="true" src={episode.presenterClips![0].src} muted volume={0} pauseWhenBuffering style={{...imageStyle,objectPosition:'50% 35%'}}/>
   <span style={{position:'absolute',left:0,right:0,bottom:0,padding:7,textAlign:'center',fontSize:16,fontWeight:800,background:P.ink,color:P.bg}}>{episode.presenterName} · AI数字人</span>
  </div>
  <div data-element="caption" style={{...box(48,1110,624,88),background:P.ink,color:P.bg,padding:'12px 18px',fontSize:27,fontWeight:700,lineHeight:1.2,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center'}}>{episode.captions[i].text}</div>
  <div style={{...box(48,1226,624,22),fontSize:16,display:'flex',justifyContent:'space-between'}}><span>把好奇，留给真实的现场。</span><span>{String(i+1).padStart(2,'0')} / 04</span></div>
  <div style={{...box(48,1245,624,3),background:P.ink,opacity:.15}}/><div style={{...box(48,1245,624*(f+1)/720,3),background:P.accent}}/>
 </AbsoluteFill>;
}
