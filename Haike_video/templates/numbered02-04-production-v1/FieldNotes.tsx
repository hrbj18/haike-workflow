// Generated additive adaptation; see build_sources.py and derivation.json.
import React,{useMemo} from 'react';
import {AbsoluteFill,Video,Sequence,Freeze,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {Media,TextEffect} from './FieldMedia';
import originalRecipes from '../chromatic-motion-lab-v1/recipes.json';
const recipes=originalRecipes.recipes;type Episode=any;
import {VideoImage as Img,Presenter} from './Common';
import {activeIndex,activeAndNext} from '../chromatic-motion-lab-v1/runtime';
import recipe from '../chromatic-motion-lab-v1/custom-recipes/field-notes.json';

export {recipe as customRecipe};
const box=([left,top,width,height]:number[]):React.CSSProperties=>({position:'absolute',left,top,width,height});
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const progress=(f:number,a:number,b:number)=>interpolate(f,[a,b],[0,1],clamp);

function Stage({episode,index}:{episode:Episode;index:number}){
 const f=useCurrentFrame(),{fps}=useVideoConfig(),s={...recipe.stages[index],...episode.stages[index].text},t={...recipe.timing,...episode.stages[index].timing},p=recipe.palette;
 const segment=episode.segments![index],chapterFrames=segment.to-segment.from;
 const media=box(recipe.layout.media),w=recipe.layout.media[2],h=recipe.layout.media[3];
 const photo=(i:number)=>episode.photos[s.photoOrder[i]%episode.photos.length];
 const reveal=progress(f,t.mediaFrom,t.mediaFrom+t.actionFrames);
 const actionFrame=Math.min(t.actionFrames,Math.max(0,f-t.mediaFrom));
 const r=useMemo(()=>({...recipes.find(x=>x.id===recipe.baseVariant)!,mediaEffect:s.effect,mediaBox:[0,0,w,h],photos:[1,2,3]}),[s,w,h]);
 const pe=useMemo(()=>({...episode,photos:s.photoOrder.map(i=>episode.photos[i%episode.photos.length])}),[episode,s]);
 return <AbsoluteFill data-stage={s.id} data-layout={s.layout} data-effect={s.effect} data-local-frame={f}>
   <div style={{...box([48,91,624,22]),fontSize:18,letterSpacing:3,fontWeight:700}}>{s.label}</div>
   <div style={{...box(recipe.layout.title),fontSize:76,fontWeight:900,lineHeight:1.06}}>
    {(segment.headline||'走进现场\n看见新鲜').split('\n').map((line,i)=><div key={i} style={{position:'relative',height:86}}><Sequence from={i*5} layout="none"><div style={{opacity:progress(f,i*5,t.titleFrames),transform:`translateY(${(1-progress(f,i*5,t.titleFrames))*14}px)`}}>{line}</div></Sequence></div>)}
   </div>
   <div style={{position:'absolute',left:48,top:326,width:624,height:2,background:p.ink,opacity:.25}}/>
   {s.layout==='hero'&&<div style={{...media,overflow:'hidden',background:p.ink,border:`2px solid ${p.ink}`}}>
    <Img src={photo(0)} style={{width:'100%',height:'100%',objectFit:'cover',opacity:.75}}/>
    <Sequence from={t.mediaFrom} layout="none"><div style={{position:'absolute',inset:0}}><FrozenMedia r={r} p={p} episode={pe} frames={t.actionFrames} frame={actionFrame}/></div></Sequence>
    <span style={{position:'absolute',bottom:20,left:20,padding:'8px 14px',background:p.accent,fontSize:22,fontWeight:800}}>现场，是最好的开场 ↗</span>
   </div>}
   {s.layout==='duet'&&<div style={{...media,display:'flex',gap:16}}>{[0,1].map((n)=><div key={n} style={{position:'relative',width:(w-16)/2,height:h,overflow:'hidden',background:p.paper,border:`2px solid ${p.ink}`,transform:`translateY(${(1-reveal)*(n===0?20:-20)}px)`}}>
    <Img src={photo(n)} style={{width:'100%',height:h-58,objectFit:'cover',clipPath:`inset(0 ${(1-reveal)*100}% 0 0)`}}/>
    <div style={{position:'absolute',bottom:0,width:'100%',height:58,padding:'13px 16px',background:n?p.accent:p.ink,color:n?p.ink:p.bg,fontSize:23,fontWeight:800}}>{s.tags?.[n]}</div>
   </div>)}</div>}
   {s.layout==='cards'&&<div style={{...media,overflow:'hidden',background:p.paper,border:`2px solid ${p.ink}`}}>
    <Img src={photo(0)} style={{width:'100%',height:'100%',objectFit:'cover',opacity:1-reveal}}/>
    <Sequence from={t.mediaFrom} layout="none"><FrozenMedia r={r} p={p} episode={pe} frames={t.actionFrames} frame={actionFrame}/></Sequence>
   </div>}
   {s.layout==='summary'&&<div style={{...media,display:'flex',gap:24}}>
    <div style={{width:208,height:h,overflow:'hidden',border:`2px solid ${p.ink}`}}><Img src={photo(0)} style={{width:'100%',height:'100%',objectFit:'cover'}}/></div>
    <div style={{flex:1,paddingTop:18}}>{s.summary?.map((line,i)=><div key={line} style={{height:136,borderBottom:`1px solid ${p.ink}44`,display:'flex',alignItems:'center',gap:14}}><span style={{color:p.accent,fontSize:24}}>0{i+1}</span><span style={{fontSize:35,fontWeight:900,opacity:interpolate(f,[t.mediaFrom+i*14,t.mediaFrom+16+i*14],[.35,1],clamp)}}>{line}</span></div>)}</div>
   </div>}
   <div style={{...box(recipe.layout.note),fontSize:33,lineHeight:1.3,fontWeight:800,whiteSpace:'pre-line',opacity:progress(f,t.noteFrom,t.noteFrom+t.noteFrames)}}>
    {s.layout==='summary'?<Sequence from={t.noteFrom} layout="none"><TextEffect id="highlight" text={s.note} p={{...p,id:'custom'} as any} size={31} fontFamily={episode.fontFamily}/></Sequence>:<><span style={{display:'block',width:42,height:6,background:p.accent,marginBottom:16}}/>{s.note}</>}
   </div>
 </AbsoluteFill>;
}

// Reflow reaches its final pose once, then stays readable for the rest of the scene.
function FrozenMedia({r,p,episode,frames,frame}:any){
 return <Sequence layout="none"><MediaAtFrame r={r} p={p} episode={episode} frames={frames} frame={frame}/></Sequence>;
}
function MediaAtFrame({r,p,episode,frames,frame}:any){return <Freeze frame={frame}><Media r={r} p={{...p,id:'custom'}} e={episode} frames={frames}/></Freeze>}

export function RecipeStage({episode}:{episode:Episode}){
 const f=useCurrentFrame(),{fps}=useVideoConfig(),p=recipe.palette,segments=episode.segments!;
 const index=activeIndex(segments,f),cue=episode.captions[activeIndex(episode.captions,f)];
 if(index<0||segments.length!==recipe.stages.length)throw Error('定制配方需四段连续内容，请按样板重新准备');
 return <AbsoluteFill style={{background:p.bg,color:p.ink,fontFamily:episode.fontFamily,overflow:'hidden'}}>
  <div style={{...box([48,42,624,26]),fontSize:17,letterSpacing:2,display:'flex',justifyContent:'space-between'}}><b>{episode.brand}</b><span>VOL. 01</span></div>
  <div style={{...box([0,0,10,1280]),background:p.accent}}/>
  <Sequence key={index} from={segments[index].from} durationInFrames={segments[index].to-segments[index].from} layout="none"><Stage episode={episode} index={index}/></Sequence>
  <Presenter box={recipe.layout.presenter}/>
  <div style={{...box([48,1226,624,22]),fontSize:16,display:'flex',justifyContent:'space-between'}}><span>{episode.address}</span><span>{String(index+1).padStart(2,'0')} / 04</span></div>
  <div style={{position:'absolute',left:48,bottom:32,width:624,height:3,background:p.ink,opacity:.15}}/><div style={{position:'absolute',left:48,bottom:32,width:624*(f+1)/(episode.durationInFrames||720),height:3,background:p.accent}}/>
 </AbsoluteFill>;
}
