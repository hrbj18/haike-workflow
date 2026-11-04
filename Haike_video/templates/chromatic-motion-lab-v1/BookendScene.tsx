import React,{useMemo} from 'react';
import {AbsoluteFill,Audio,Img,Sequence,Video,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {SnapCnUIProvider} from '../../motion-components/snapcn/upstream/registry/snap-cn-ui/core';
import {MondrianSplit} from '../hum-production-v1/vendor/remocn/mondrian-split';
import {Media,TextEffect,recipes,palettes,type Episode,type Segment,type Recipe,type Palette} from './AvatarScene';
import {activeIndex,activeAndNext} from './runtime';
const rect=([x,y,width,height]:number[]):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});

function MaterialScene({s,e,p,base,index}:{s:Segment;e:Episode;p:Palette;base:Recipe;index:number}){
 const f=useCurrentFrame(),{fps}=useVideoConfig();
 const motion=s.motions!['03'],kind=s.composition||'gallery',focus=kind==='focus';
 const box=focus?[0,140,720,910]:[36,340,648,708];
 const r=useMemo(()=>({...base,...motion,photos:[1,2,3],mediaBox:[0,0,box[2],box[3]]}),[base,motion,kind]);
 const ep=useMemo(()=>({...e,photos:s.photos.map(i=>e.photos[i])}),[e,s]);
 const pair=useMemo(()=>({...r,mediaEffect:'parallax',mediaBox:[0,0,312,670]}),[r]);
 const pairEpisodes=useMemo(()=>[0,1].map(i=>({...ep,photos:[ep.photos[i%ep.photos.length]]})),[ep]);
 const headline=(s.headline||'看见现场').split('\n'),labels=s.labels||['现场','互动'];
 return <AbsoluteFill data-role="material-scene" style={{overflow:'hidden'}}>
  {focus&&<Img src={ep.photos[index%ep.photos.length]} style={{...rect(box),objectFit:'cover',opacity:.3}}/>}
  <div data-role="media" style={{...rect(box),zIndex:0,overflow:'hidden',background:p.paper,border:focus?0:`2px solid ${p.ink}33`}}>
   <Img src={ep.photos[0]} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',opacity:interpolate(f,[18,36],[1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}/>
   {kind==='duet'?<div style={{display:'flex',gap:20,height:'100%'}}>{[0,1].map(i=><div key={i} style={{position:'relative',width:312,height:670,top:i?28:0}}><Sequence from={i*8} layout="none" premountFor={fps}><Media r={pair} p={p} e={pairEpisodes[i]} frames={s.to-s.from-i*8}/></Sequence><div style={{position:'absolute',bottom:26,left:18,right:18,padding:16,background:p.ink,color:p.bg,fontSize:30,fontWeight:800}}>{labels[i]}</div></div>)}</div>:<Media r={r} p={p} e={ep} frames={s.to-s.from} selected={index%3}/>}
   {kind==='orbit'&&<Img src={ep.photos[0]} style={{...rect([174,180,300,390]),objectFit:'cover',border:`8px solid ${p.paper}`,transform:`rotate(${interpolate(f,[0,24],[-8,0],{extrapolateRight:'clamp'})}deg)`}}/>}
  </div>
  <div data-role="headline" style={{...rect([36,focus?158:130,648,190]),background:focus?p.bg:undefined,padding:focus?'12px 18px':0,fontWeight:900,lineHeight:1.1}}>{headline.map((t,i)=><div key={i} style={{position:'relative',height:88}}><Sequence from={i*7} layout="none" premountFor={fps}><TextEffect id={motion.headlineEffect} text={t} p={p} size={76} fontFamily={e.fontFamily}/></Sequence></div>)}</div>
  {s.conclusion&&<div data-role="conclusion" style={{...rect([52,focus?950:978,616,84]),padding:10,background:p.bg,borderLeft:`8px solid ${p.accent}`}}><Sequence from={Math.min(Math.round(1.8*fps),Math.floor((s.to-s.from)/3))} layout="none" premountFor={fps}><TextEffect id={motion.conclusionEffect} text={s.conclusion} p={p} size={32} fontFamily={e.fontFamily}/></Sequence></div>}
  {index===1&&f<18&&<AbsoluteFill style={{pointerEvents:'none',opacity:interpolate(f,[6,18],[1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}><MondrianSplit seed={37} splits={5} speed={2} redColor={p.accent} yellowColor={p.bg} blueColor={p.ink} fieldColor={p.bg} lineColor={p.ink} lineWeight={4}/></AbsoluteFill>}
 </AbsoluteFill>;
}

function PresenterScene({s,e,p}:{s:Segment;e:Episode;p:Palette}){
 const f=useCurrentFrame(),{fps}=useVideoConfig();const end=s.role==='outro';
 return <AbsoluteFill>
  <div style={{...rect([end?350:36,370,end?330:240,650]),background:p.accent,rotate:end?'5deg':'-5deg'}}/>
  <Img src={e.photos[end?e.photos.length-1:0]} style={{...rect([end?380:36,400,end?300:280,570]),objectFit:'cover',opacity:.82,transform:`translateY(${interpolate(f,[0,30],[45,0],{extrapolateRight:'clamp'})}px)`}}/>
  <div data-role="headline" style={{...rect([36,135,648,200]),fontWeight:900,lineHeight:1.1}}>{(s.headline||'走进现场').split('\n').map((t,i)=><div key={i} style={{position:'relative',height:90}}><Sequence from={i*7} layout="none" premountFor={fps}><TextEffect id={end?'build':'reveal'} text={t} p={p} size={80} fontFamily={e.fontFamily}/></Sequence></div>)}</div>
  <div style={{...rect([36,1060,648,34]),fontSize:24,fontWeight:800,color:p.ink}}>{s.conclusion||'先体验，再理解。'}</div>
 </AbsoluteFill>;
}

export function BookendScene({episode:e,previewMuted=false}:{episode:Episode;variant?:string;previewMuted?:boolean}){
 const f=useCurrentFrame(),{fps}=useVideoConfig();
 const base=recipes.find(r=>r.id==='03')!,p=palettes.find(p=>p.id==='03')!;
 const index=activeIndex(e.segments||[],f),s=e.segments?.[index];
 if(!s||!s.role)throw Error('缺少首尾出镜场景计划，请重新准备');
 const host=s.role==='intro'||s.role==='outro',box=s.role==='intro'?[210,345,468,705]:[36,350,414,705];
 const clips=host?activeAndNext(e.presenterClips||[],f,fps):[];
 const cue=e.captions[activeIndex(e.captions,f)],family=e.fontFamily||'Haike Preview';
 return <AbsoluteFill data-recipe="03" data-segment={index} data-scene-role={s.role} data-composition={s.composition} data-motion-media={s.motions?.['03'].mediaEffect} style={{background:p.bg,color:p.ink,fontFamily:family,overflow:'hidden',isolation:'isolate'}}>
  <style>{`@font-face{font-family:'${family}';src:url('${e.fontSrc||'/assets/font.ttf'}')}*,*:before,*:after{box-sizing:border-box}`}</style>
  <SnapCnUIProvider theme={{background:p.bg,foreground:p.ink,primary:p.accent,fontFamily:family}}>
   <Sequence key={s.from} from={s.from} durationInFrames={s.to-s.from} layout="none">{host?<PresenterScene s={s} e={e} p={p}/>:<MaterialScene s={s} e={e} p={p} base={base} index={index}/>}</Sequence>
   {host&&<div data-role="presenter" style={{...rect(box),overflow:'hidden',border:`5px solid ${p.accent}`,borderRadius:28,background:p.paper,zIndex:10}}>{clips.map(c=><Sequence key={c.from} from={c.from} durationInFrames={c.to-c.from} layout="none" premountFor={fps}><Video data-avatar="true" data-clip-from={c.from} src={c.src} muted volume={0} pauseWhenBuffering style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/></Sequence>)}<div style={{position:'absolute',bottom:0,left:0,right:0,padding:'30px 10px 18px',textAlign:'center',fontWeight:800,fontSize:22,background:`linear-gradient(transparent,${p.bg})`}}>{e.presenterName} · AI 数字人</div></div>}
   <div style={{...rect([36,38,648,40]),fontSize:18,display:'flex',justifyContent:'space-between'}}><span>海客 · 现场观察</span><span>{host?s.role==='intro'?'从好奇开始':'把体验带走':'看见 · 理解 · 体验'}</span></div>
   <div data-role="caption" style={{...rect([36,1100,648,94]),display:'flex',alignItems:'center',justifyContent:'center',whiteSpace:'pre-line',textAlign:'center',fontSize:28,lineHeight:1.2,fontWeight:700,padding:'8px 16px',background:p.ink,color:p.bg,borderLeft:`8px solid ${p.accent}`,visibility:cue?'visible':'hidden'}}>{cue?.lines?.join('\n')||cue?.text||''}</div>
   <div style={{...rect([36,1220,648,24]),fontSize:16,display:'flex',justifyContent:'space-between',opacity:.7}}><span>先体验，再理解。</span><span>{String(index+1).padStart(2,'0')} / {e.segments?.length}</span></div>
   {e.audio&&<Audio src={e.audio} muted={previewMuted} volume={previewMuted?0:1} pauseWhenBuffering/>}
  </SnapCnUIProvider>
 </AbsoluteFill>;
}
