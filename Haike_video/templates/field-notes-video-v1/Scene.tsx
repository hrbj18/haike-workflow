import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Audio,cancelRender,continueRender,delayRender,OffthreadVideo,Sequence,staticFile,useCurrentFrame} from 'remotion';

export type Clip={file:string;from:number;to:number;sourceStartFrame:number;position?:string};
export type SceneSpec={id:string;actionId:string;from:number;to:number;headline:string;note:string;kicker:string;events:Record<string,number>;media:Clip[][];labels?:string[]};
export type Episode={template_id:string;version:string;fps:30;durationFrames:number;brand:string;title:string;scenes:SceneSpec[];captions:{text:string;startMs:number;endMs:number}[];presenters:Clip[];audio:string;font:string;requiredOverlay:string;address:string;sourceText:string};
const P={bg:'#F4F1E9',ink:'#124A49',accent:'#EC795E',paper:'#FFFFFF'};
const box=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const p=(f:number,a:number,b:number)=>Math.max(0,Math.min(1,(f-a)/Math.max(1,b-a)));
const ease=(t:number)=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const textStyle:React.CSSProperties={fontWeight:900,lineHeight:1.08,whiteSpace:'pre-line'};

function FontGate({font,children}:{font:string;children:React.ReactNode}){
 const [handle]=useState(()=>delayRender('Field Notes local font'));
 useEffect(()=>{const face=new FontFace('Field Notes Formal',`url(${staticFile(font)})`);face.load().then(f=>{document.fonts.add(f);continueRender(handle)}).catch(e=>cancelRender(e));},[font,handle]);
 return <>{children}</>;
}
/** Every occurrence has an absolute window and a real source offset at1x.
 * Scene/camera motion can settle while the underlying video keeps playing.
 */
function LiveVideo({clips}:{clips:Clip[]}){
 return <>{clips.map((clip,i)=><Sequence key={clip.file+clip.from+i} from={clip.from} durationInFrames={clip.to-clip.from} premountFor={30} layout="none">
  <OffthreadVideo src={staticFile(clip.file)} startFrom={clip.sourceStartFrame} muted style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:clip.position||'50% 35%'}}/>
 </Sequence>)}</>;
}
function Title({scene,f,demote=false}:{scene:SceneSpec;f:number;demote?:boolean}){
 const e=scene.events,t=demote?ease(p(f,e.titleDemoteStart,e.titleDemoteEnd)):1;
 return <div data-element="headline" style={{...box(48,demote?mix(348,136,t):136,624,210),...textStyle,fontSize:demote?mix(80,38,t):72,opacity:p(f,scene.from,scene.from+12),transformOrigin:'top left'}}>{scene.headline}</div>;
}
export function Arrive({scene,f}:{scene:SceneSpec;f:number}){
 const e=scene.events;
 return <><Title scene={scene} f={f} demote/>
 <div data-element="material" style={{...box(48,272,624,514),border:`2px solid ${P.ink}`,overflow:'hidden',opacity:p(f,e.mediaEnterStart,e.mediaEnterEnd),clipPath:`inset(0 ${(1-ease(p(f,e.mediaEnterStart,e.mediaEnterEnd)))*100}% 0 0)`}}>
  <LiveVideo clips={scene.media[0]}/><span style={{position:'absolute',bottom:0,left:0,right:0,padding:'20px 24px',fontSize:28,fontWeight:800,background:P.ink,color:P.bg}}>先把话说明白，再请您看现场 ↗</span>
 </div></>;
}
export function Compare({scene,f}:{scene:SceneSpec;f:number}){
 const e=scene.events,g=ease(p(f,e.focusStart,e.focusEnd))*(1-ease(p(f,e.returnStart,e.returnEnd)));
 const grid=[[0,0,304,167],[320,0,304,167],[0,184,304,167],[320,184,304,167]];
 let side=0;
 return <><Title scene={scene} f={f}/>
 <div data-element="material" style={box(48,362,624,351)}>
  {grid.map((origin,i)=>{const target=i===2?[0,20,440,310]:[464,(side++)*123,160,105];
   const [x,y,w,h]=origin.map((a,j)=>mix(a,target[j],g));
   return <div key={i} data-grid-slot={i} style={{...box(x,y,w,h),overflow:'hidden',border:'4px solid white',borderRadius:8,boxShadow:'0 7px 18px #124a4928'}}>
    <LiveVideo clips={scene.media[i]}/><span style={{position:'absolute',left:0,right:0,bottom:0,padding:'6px 8px',fontSize:i===2&&g>.5?22:16,fontWeight:800,color:P.bg,background:'#124a49dc'}}>{scene.labels?.[i]}</span>
   </div>})}
 </div>
 <div style={{...box(48,758,624,70),fontSize:28,fontWeight:800,textAlign:'center',opacity:p(f,scene.from+24,scene.from+42)}}>三件事，您到店亲自看</div></>;
}
export function Connect({scene,f}:{scene:SceneSpec;f:number}){
 const e=scene.events,draw=p(f,e.lineStart,e.lineEnd);
 return <><Title scene={scene} f={f}/>
 <svg data-element="handoff-line" width={720} height={840} style={{position:'absolute',inset:0,overflow:'visible'}}><path d="M48 326 H146 Q168 326 168 348 V378 Q168 400 190 400 H648 Q672 400 672 424 V768 Q672 792 648 792 H72 Q48 792 48 768 V424 Q48 400 72 400 H190" pathLength={1} fill="none" stroke={P.accent} strokeWidth={6} strokeDasharray={1} strokeDashoffset={1-draw}/></svg>
 <div data-element="material" style={{...box(72,424,576,344),overflow:'hidden',opacity:p(f,e.mediaEnterStart,e.mediaEnterEnd),transform:`translateY(${(1-ease(p(f,e.mediaEnterStart,e.mediaEnterEnd)))*18}px)`}}><LiveVideo clips={scene.media[0]}/><span style={{position:'absolute',left:0,right:0,bottom:0,padding:'14px 18px',background:P.ink,color:P.bg,fontSize:28,fontWeight:800}}>日常用品，按需要自由选</span></div>
 </>;
}
export function Converge({scene,f}:{scene:SceneSpec;f:number}){
 const e=scene.events,travel=ease(p(f,e.travelStart,e.travelEnd)),origins=[[56,388],[394,388],[225,536]];
 const reveal=ease(p(f,e.conclusionStart,e.conclusionEnd));
 return <><Title scene={scene} f={f}/>
 <svg data-element="source-paths" width={720} height={820} style={{position:'absolute',inset:0,opacity:1-p(f,e.travelEnd,e.travelEnd+12)}}>
 {origins.map(([x,y],i)=><path key={i} d={`M${x+135} ${y+46} Q${i===0?176:i===1?548:360} 650 360 694`} pathLength={1} fill="none" stroke={P.accent} strokeWidth={4} strokeDasharray={1} strokeDashoffset={1-p(f,e.pathStart,e.travelStart)}/>)}</svg>
 {origins.map(([x,y],i)=>{const a=1-travel,cx=i===0?176:i===1?548:360,px=a*a*(x+135)+2*a*travel*cx+travel*travel*360,py=a*a*(y+46)+2*a*travel*650+travel*travel*694;
  return <div key={i} data-element={`source-${i}`} style={{...box(px-135,py-46,270,92),display:'flex',alignItems:'center',gap:14,padding:10,background:P.paper,border:`2px solid ${P.ink}`,borderRadius:8,fontSize:26,fontWeight:800,opacity:1-p(f,e.travelEnd-5,e.conclusionStart),transform:`scale(${1-.9*p(travel,.75,1)})`}}><div style={{position:'relative',width:66,height:66,overflow:'hidden',borderRadius:3,flexShrink:0}}><LiveVideo clips={scene.media[i]}/></div>{scene.labels?.[i]}</div>;
 })}
 <div data-element="conclusion" style={{...box(48,mix(621,380,reveal),624,mix(146,410,reveal)),overflow:'hidden',background:P.ink,color:P.bg,fontSize:36,fontWeight:900,border:`2px solid ${P.ink}`,borderBottom:`9px solid ${P.accent}`,opacity:p(f,e.conclusionStart,e.conclusionEnd)}}><LiveVideo clips={scene.media[3]}/><span style={{position:'absolute',left:0,right:0,bottom:0,padding:'24px 18px',textAlign:'center',background:'linear-gradient(transparent,#124A49 35%)'}}>来不来，您自己定</span></div>
 </>;
}
export const ACTIONS={
 'haike.field-notes-v2.video.arrive':Arrive,
 'haike.field-notes-v2.video.compare':Compare,
 'haike.field-notes-v2.video.connect':Connect,
 'haike.field-notes-v2.video.converge':Converge,
};
export function FieldNotesVideo({episode}:{episode:Episode}){
 const f=useCurrentFrame(),scene=episode.scenes.find(s=>s.from<=f&&f<s.to);
 if(!scene)throw Error('Frame outside full measured narration clock');
 const Part=ACTIONS[scene.actionId as keyof typeof ACTIONS];if(!Part)throw Error('Unknown executable action ID');
 const cue=episode.captions.find(c=>c.startMs<=f/30*1000&&f/30*1000<c.endMs);
 const presenter=episode.presenters.some(c=>c.from<=f&&f<c.to);
 return <FontGate font={episode.font}><AbsoluteFill style={{background:P.bg,color:P.ink,fontFamily:'Field Notes Formal',overflow:'hidden'}}>
 <style>{'*,*:before,*:after{box-sizing:border-box}'}</style>
 <div style={{width:720,height:1280,position:'absolute',left:0,top:0,transform:'scale(1.5)',transformOrigin:'0 0'}}>
  <div style={{...box(0,0,10,1280),background:P.accent}}/>
  <div style={{...box(48,42,624,26),fontSize:17,letterSpacing:2,display:'flex',justifyContent:'space-between'}}><b>{episode.brand}</b><span>FIELD NOTES</span></div>
  <div data-stage={scene.id} data-action-id={scene.actionId}><div style={{...box(48,92,624,24),fontSize:18,letterSpacing:3,fontWeight:700}}>{scene.kicker}</div><Part scene={scene} f={f}/>
   <div data-element="note" style={{...box(48,884,410,150),fontSize:33,lineHeight:1.3,fontWeight:800,whiteSpace:'pre-line',opacity:p(f,scene.events.noteStart,scene.events.noteStart+14)}}><span style={{display:'block',width:42,height:6,background:P.accent,marginBottom:16}}/>{scene.note}</div>
  </div>
  {presenter&&<div data-role="presenter" style={{...box(486,850,186,210),borderRadius:'95px 95px 8px 8px',overflow:'hidden',border:`3px solid ${P.ink}`,background:P.paper}}><LiveVideo clips={episode.presenters}/><span style={{position:'absolute',left:0,right:0,bottom:0,padding:7,textAlign:'center',fontSize:15,fontWeight:800,background:P.ink,color:P.bg}}>侯总 · AI数字人</span></div>}
  <div data-element="medical-boundary" style={{...box(48,1068,624,52),fontSize:20,fontWeight:700,lineHeight:1.3,textAlign:'center',whiteSpace:'pre-line',color:P.ink}}>{episode.requiredOverlay}</div>
  <div data-element="caption" style={{...box(48,1128,624,100),padding:'12px 18px',fontSize:28,fontWeight:750,lineHeight:1.3,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',background:P.ink,color:P.bg,visibility:cue?'visible':'hidden'}}>{cue?.text}</div>
  <div style={{...box(48,1232,624,22),fontSize:15,display:'flex',justifyContent:'space-between'}}><span>{episode.address}</span><span>{String(episode.scenes.indexOf(scene)+1).padStart(2,'0')} / 04</span></div>
  <div style={{...box(48,1262,624,3),background:P.ink,opacity:.15}}/><div style={{...box(48,1262,624*(f+1)/episode.durationFrames,3),background:P.accent}}/>
 </div>
 <Audio src={staticFile(episode.audio)}/>
 </AbsoluteFill></FontGate>;
}
