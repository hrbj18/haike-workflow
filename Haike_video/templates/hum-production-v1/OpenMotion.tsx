import React from 'react';
import {AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {ClothReveal} from './vendor/remocn/cloth-reveal';
import {MondrianSplit} from './vendor/remocn/mondrian-split';
import {ParallaxDepth} from './vendor/remocn/parallax-depth';
import {EffectVideo} from './OpenEffects';
import type {Props,Scene} from './types';

const DARK='#17221f', AMBER='#dab981', WHITE='#faf6ed', RED='#ec422c', YELLOW='#ffdf3e', BLUE='#173caf';
const font='HaikeProductionDisplay';
const at=(left:number,top:number,width:number,height?:number):React.CSSProperties=>({position:'absolute',left,top,width,height,boxSizing:'border-box'});
const Title:React.FC<{s:Scene;child:boolean;focus:boolean;landscape:boolean}>=({s,child,focus,landscape})=>{
 const side=focus&&!landscape;
 return <div style={{...at(side?(child?900:92):90,side?430:180,side?420:1260),zIndex:8,color:child?WHITE:AMBER}}>
  <div style={{fontFamily:font,fontSize:side?96:112,lineHeight:1.24,whiteSpace:'pre-wrap'}}>{s.title}</div>
  {s.subtitle&&<div style={{fontSize:32,lineHeight:1.6,marginTop:38,color:child?WHITE:'#bec6bd',whiteSpace:'pre-wrap'}}>{s.subtitle}</div>}
 </div>;
};

const Frame:React.FC<{p:Props;s:Scene;index:number}>=({p,s,index})=>{
 const child=p.visualStyle==='carnival',f=useCurrentFrame();
 const m=p.media.find(x=>x.id===s.mediaId),landscape=m?.orientation==='landscape';
 const bg=child?(index%3===0?RED:index%3===1?BLUE:'#e24429'):DARK;
 const presenter=p.presenterModes?.some(x=>x.mode!=='hidden'&&s.from+x.frames>0&&s.from+f>=x.from&&s.from+f<x.from+x.frames);
 const video=m?<div style={{...at(landscape?70:child?90:580,landscape?540:280,landscape?1300:720,landscape?735:1180),overflow:'hidden',background:child?BLUE:'#0b1410'}}>
   <EffectVideo media={m} width={landscape?1300:720} height={landscape?735:1180} effect={s.motion==='pixi-shock'?'shock':'warm'} transition={s.motion==='gl-film'?'FilmBurn':s.motion==='gl-circle'?'CircleOpen':undefined} background={bg}/>
  </div>:null;
 const scene=<AbsoluteFill style={{backgroundColor:bg}}>
  {child?<><div style={{...at(0,0,1440,118),background:YELLOW}}/><div style={{...at(1322,118,118,1440),background:index%2?YELLOW:BLUE}}/><div style={{...at(0,1490,1440,310),background:YELLOW}}/>
   {!m&&<><div style={{...at(75,440,presenter?470:1290,840),background:WHITE,transform:'rotate(-3deg)'}}/><div style={{...at(95,460,presenter?420:1240,800),background:BLUE}}/></>}
  </>:<><div style={{...at(80,125,1280,2),background:'#64756a'}}/><div style={{...at(80,1478,1280,2),background:'#64756a'}}/>{!m&&<div style={{...at(90,420,presenter?430:1260,890),borderLeft:'2px solid #dab981',borderBottom:'2px solid #43594c'}}/>}</>}
  {video}
  {m?<Title s={s} child={child} focus landscape={!!landscape}/>:<div style={{...at(presenter?90:150,presenter?490:565,presenter?440:1140),zIndex:4,color:child?YELLOW:WHITE}}>
   <div style={{fontFamily:font,fontSize:presenter?92:132,lineHeight:1.33,whiteSpace:'pre-wrap'}}>{s.title}</div>
   {s.subtitle&&<div style={{marginTop:66,fontSize:presenter?32:42,lineHeight:1.65,whiteSpace:'pre-wrap',color:child?WHITE:AMBER}}>{s.subtitle}</div>}
  </div>}
  <div style={{...at(92,1390,380),fontSize:26,color:child?WHITE:'#b7c2b7'}}>{m?'门店真实活动记录':'海客 AI 社区服务店'}</div>
 </AbsoluteFill>;
 if(s.motion==='cloth'&&f<36)return <ClothReveal clothColor={AMBER} undersideColor="#796341" background={DARK} direction="up" delay={2} seed={8} speed={1.15}>{scene}</ClothReveal>;
 if(s.motion==='mondrian')return <AbsoluteFill style={{backgroundColor:YELLOW}}><MondrianSplit seed={17} splits={5} speed={1.8} lineWeight={10} redColor={RED} yellowColor={YELLOW} blueColor={BLUE} fieldColor={RED}>{scene}</MondrianSplit></AbsoluteFill>;
 if(s.motion==='parallax')return <ParallaxDepth skyColor={DARK} distance={.075} push={.025} speed={60/s.frames} layers={[{depth:5,content:scene},{depth:1.5,content:<div style={{...at(80,1360,120,3),background:AMBER}}/>}]}/>;
 return scene;
};

const Presenter:React.FC<{p:Props}>=({p})=>{
 const frame=useCurrentFrame(),mode=p.presenterModes?.find(x=>frame>=x.from&&frame<x.from+x.frames);
 if(!mode||mode.mode==='hidden')return null;
 const clip=p.presenterClips!.find(x=>x.id===mode.clipId)!,child=p.visualStyle==='carnival',large=mode.mode==='large';
 return <div style={{...at(large?650:1000,large?300:970,large?660:300,large?1130:510),zIndex:30,background:child?YELLOW:'#405446',padding:large?10:5}}>
  <Sequence from={clip.from} durationInFrames={clip.frames} layout="none"><OffthreadVideo src={staticFile(clip.src)} startFrom={Math.round(clip.offset*30)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>
  <div style={{position:'absolute',bottom:18,left:18,fontSize:large?24:18,padding:'6px 10px',color:WHITE,background:DARK}}>AI数字人演绎</div>
 </div>;
};
export const OpenMotionContent:React.FC<Props>=p=>{
 const f=useCurrentFrame(),child=p.visualStyle==='carnival',cue=p.captions.find(c=>f/30*1000>=c.startMs&&f/30*1000<c.endMs);
 return <AbsoluteFill style={{fontFamily:'HaikeProductionBody',backgroundColor:child?RED:DARK,overflow:'hidden'}}>
  {p.scenes.map((s,index)=><Sequence key={s.id} from={s.from} durationInFrames={s.frames}><Frame p={p} s={s} index={index}/></Sequence>)}
  <Presenter p={p}/>
  {child&&<><div style={{...at(0,0,1440,118),background:YELLOW,zIndex:35}}/><div style={{...at(0,1490,1440,310),background:YELLOW,zIndex:35}}/></>}
  <div style={{...at(90,48,1260),zIndex:40,display:'flex',justifyContent:'space-between',fontSize:30,color:child?DARK:WHITE}}><span>{p.brand}</span><span>{child?'亲子探索':'社区日常'}</span></div>
  {cue&&<div style={{...at(88,1528,1264,145),display:'flex',alignItems:'center',justifyContent:'center',fontSize:76,lineHeight:1.3,color:child?DARK:WHITE,zIndex:50,textAlign:'center',whiteSpace:'pre'}}>{cue.text}</div>}
  <div style={{...at(90,1730,1260),fontSize:25,color:child?DARK:'#b7c2b7',zIndex:50}}>{p.footer}</div>
  {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill>;
};
