import React,{useRef,useState,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {Player,type PlayerRef} from '@remotion/player';
import {RecipeStage,customRecipe} from './RecipeStage';
import type {Episode} from './AvatarScene';
let episode:Episode;
function Preview(){
 const total=episode.durationInFrames!,capture=new URLSearchParams(location.search).has('capture');
 const initial=Math.max(0,Math.min(total-1,Number(new URLSearchParams(location.search).get('frame'))||0));
 const ref=useRef<PlayerRef>(null),[frame,setFrame]=useState(initial),[playing,setPlaying]=useState(false),[rate,setRate]=useState(1);
 useEffect(()=>{const player=ref.current;if(!player)return;const tick=(e:any)=>setFrame(e.detail.frame),play=()=>setPlaying(true),pause=()=>setPlaying(false);player.addEventListener('frameupdate',tick);player.addEventListener('play',play);player.addEventListener('pause',pause);player.addEventListener('ended',pause);return()=>{player.removeEventListener('frameupdate',tick);player.removeEventListener('play',play);player.removeEventListener('pause',pause);player.removeEventListener('ended',pause)}},[]);
 return <main data-current-frame={frame} data-playing={playing} className={capture?'capture':''}><section className="stage"><Player ref={p=>{ref.current=p;if(p){(window as any).preview=p;}}} component={RecipeStage} inputProps={{episode}} durationInFrames={total} fps={30} compositionWidth={720} compositionHeight={1280} initialFrame={initial} initiallyMuted playbackRate={rate} style={{width:'100%',height:'100%'}} controls={false} autoPlay={false} loop={false} moveToBeginningWhenEnded={false} acknowledgeRemotionLicense/></section>
 {!capture&&<aside><span className="eyebrow">CUSTOM MOTION / 01</span><h1>{customRecipe.name}</h1><p>同一风格，四段编排。先展示现场，再对照、接力，最后停下来收束。</p><span className="badge">24秒 · 低清素材 · 30fps · 静音示意</span><nav>{customRecipe.stages.map((s,i)=><button key={s.id} onClick={()=>{ref.current?.pause();ref.current?.seekTo(episode.segments![i].from);setFrame(episode.segments![i].from);setPlaying(false)}}><b>0{i+1}</b><span>{s.purpose}<small>{s.layout==='hero'?'纵深展示':s.layout==='duet'?'双图展开':s.layout==='cards'?'卡片重排':'划线收束'}</small></span></button>)}</nav><div className="transport"><button onClick={()=>ref.current?.toggle()}>{playing?'暂停':'播放预览'}</button><button onClick={()=>{ref.current?.seekTo(0);ref.current?.play();setPlaying(true)}}>从头重播</button><select aria-label="播放速度" value={rate} onChange={e=>setRate(Number(e.target.value))}><option value={1}>1×</option><option value={.5}>0.5×</option></select></div><input aria-label="预览时间轴" type="range" min={0} max={total-1} value={frame} onChange={e=>{const f=Number(e.target.value);ref.current?.pause();ref.current?.seekTo(f);setFrame(f);setPlaying(false)}}/><p className="foot">复用已有数字人与图片。字幕为布局示意。配方、代码及素材身份随构建记录，当前用于快速看动作和构图。</p></aside>}
 </main>;
}
async function boot(){
 const response=await fetch('/episode.json');if(!response.ok)throw Error('请先准备素材');episode=await response.json();
 if(episode.mode!=='visual-preview')throw Error('本样板仅接受静音布局预览');
 if(episode.segments?.length!==customRecipe.stages.length)throw Error('内容必须为四段');
 for(const s of episode.segments){if(s.to-s.from-customRecipe.timing.noteFrom-customRecipe.timing.noteFrames<customRecipe.timing.minHoldFrames)throw Error('阅读停留不足，请增加章节时长');}
 episode.fontSrc='/assets/font.ttf';episode.fontFamily='Haike Custom Field Notes';
 const font=new FontFace(episode.fontFamily,"url('/assets/font.ttf')");await font.load();document.fonts.add(font);await document.fonts.ready;
 createRoot(document.getElementById('root')!).render(<Preview/>);
 (window as any).customRecipe=customRecipe;
}
boot().catch(e=>document.getElementById('root')!.textContent=e.message);
