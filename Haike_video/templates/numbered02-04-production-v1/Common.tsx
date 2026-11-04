import React,{createContext,useContext,useEffect,useState} from 'react';
import {AbsoluteFill,Audio,cancelRender,continueRender,delayRender,OffthreadVideo,Sequence,staticFile,useCurrentFrame} from 'remotion';
import type {Clip,Episode} from './types';
export const CurrentEpisode=createContext<Episode>(null as any);
export const AbsoluteFrame=createContext(0);
export function FontGate({children}:{children:React.ReactNode}){
 const e=useContext(CurrentEpisode),[handle]=useState(()=>delayRender('Full motion local font'));
 useEffect(()=>{Promise.all(['Haike Sans','Haike Nana Local','Haike Full Motion'].map(async name=>{const face=await new FontFace(name,`url(${staticFile(e.font)})`,{weight:'100 950'}).load();document.fonts.add(face)})).then(()=>continueRender(handle)).catch(cancelRender)},[e.font,handle]);
 return <>{children}</>;
}
/** Geometry may use a frozen reference pose; source media always uses the
 * enclosing production's true clock. Sequence translation removes the ancestor
 * clock origin without changing source playback speed or repeating a frame. */
export function VideoImage({src,style,clips}:{src?:string;style?:React.CSSProperties;clips?:Clip[]}){
 const e=useContext(CurrentEpisode),global=useContext(AbsoluteFrame),local=useCurrentFrame();
 const name=decodeURIComponent((src||'').split('/').pop()||'');
 const playlist=clips||e.media[name];if(!playlist)throw Error('Unbound real-video slot: '+name);
 const active=playlist.filter(c=>global>=c.from&&global<c.to);
 return <>{active.map(c=><Sequence key={c.file+c.from} from={c.from-(global-local)} durationInFrames={c.to-c.from} layout="none">
  <OffthreadVideo src={staticFile(c.file)} trimBefore={c.sourceStartFrame} muted style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:c.position||'50% 35%',...style}}/>
 </Sequence>)}</>;
}
export function Presenter({box,label=true}:{box:number[];label?:boolean}){
 const e=useContext(CurrentEpisode),f=useContext(AbsoluteFrame);if(!e.presenters.some(c=>c.from<=f&&f<c.to))return null;
 return <div data-role="same-source-presenter" style={{position:'absolute',left:box[0],top:box[1],width:box[2],height:box[3],borderRadius:'95px 95px 8px 8px',overflow:'hidden',border:'3px solid #124a49',background:'#fff'}}><VideoImage clips={e.presenters}/>{label&&<div style={{position:'absolute',left:0,right:0,bottom:0,padding:7,fontSize:16,fontWeight:800,textAlign:'center',background:'#124a49',color:'#fff'}}>侯总 · AI数字人</div>}</div>;
}
export function Caption({landscape=false,kinetic=false}:{landscape?:boolean;kinetic?:boolean}){
 const e=useContext(CurrentEpisode),f=useContext(AbsoluteFrame);const cue=e.captions.find(c=>c.startMs<=f/e.fps*1000&&f/e.fps*1000<c.endMs);
 const y=landscape?990:kinetic?1800:1710,w=landscape?1780:936,x=landscape?70:72;
 return <><div data-role="medical-boundary" style={{position:'absolute',left:x,top:landscape?952:kinetic?1738:1634,width:w,height:landscape?32:kinetic?54:68,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',whiteSpace:'pre-line',fontFamily:'Haike Full Motion',fontSize:landscape?25:kinetic?23:27,fontWeight:800,color:kinetic?'#fff':'#124a49',lineHeight:1.18}}>AI体质检测：非医疗诊断。{landscape?' ':'\n'}不看病不卖药，给您个参考。</div>
 <div data-role="full-source-caption" style={{position:'absolute',left:x,top:y,width:w,minHeight:landscape?70:kinetic?108:114,padding:'12px 20px',display:'flex',alignItems:'center',justifyContent:'center',fontSize:landscape?36:39,fontFamily:'Haike Full Motion',fontWeight:800,lineHeight:1.2,textAlign:'center',color:'#fff',background:'#124a49',visibility:cue?'visible':'hidden'}}>{cue?.text}</div></>;
}
export function ProductionRoot({episode,children}:{episode:Episode;children:React.ReactNode}){
 const f=useCurrentFrame();return <CurrentEpisode.Provider value={episode}><AbsoluteFrame.Provider value={f}><FontGate><AbsoluteFill style={{background:episode.template_id==='kinetic-field-v1'?'#151D22':'#F4F1E9',overflow:'hidden'}}>{children}<Audio src={staticFile(episode.audio)}/></AbsoluteFill></FontGate></AbsoluteFrame.Provider></CurrentEpisode.Provider>;
}
