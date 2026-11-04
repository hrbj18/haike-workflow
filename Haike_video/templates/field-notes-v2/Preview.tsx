import React,{useRef,useState,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {Player,type PlayerRef} from '@remotion/player';
import {CandidateScene} from './Scene';
import {RecipeStage} from '../chromatic-motion-lab-v1/RecipeStage';
import type {Episode} from '../chromatic-motion-lab-v1/AvatarScene';
import plan from './selection.json';
let candidate:Episode,baseline:Episode;
function Preview(){
 const params=new URLSearchParams(location.search),capture=params.has('capture'),initial=Number(params.get('frame'))||0;
 const [version,setVersion]=useState(params.get('version')==='v1'?'v1':'v2'),[frame,setFrame]=useState(initial),[playing,setPlaying]=useState(false),[rate,setRate]=useState(1),ref=useRef<PlayerRef>(null);
 useEffect(()=>{const player=ref.current!;const tick=(e:any)=>setFrame(e.detail.frame),play=()=>setPlaying(true),pause=()=>setPlaying(false);player.addEventListener('frameupdate',tick);player.addEventListener('play',play);player.addEventListener('pause',pause);player.addEventListener('ended',pause);return()=>{player.removeEventListener('frameupdate',tick);player.removeEventListener('play',play);player.removeEventListener('pause',pause);player.removeEventListener('ended',pause)}},[version]);
 const jump=(f:number)=>{ref.current?.pause();ref.current?.seekTo(f);setFrame(f);setPlaying(false)};
 return <main className={capture?'capture':''} data-version={version} data-current-frame={frame} data-playing={playing}>
  <section className="stage"><Player key={version} ref={v=>{ref.current=v;if(v)(window as any).reviewPlayer=v}} component={version==='v2'?CandidateScene:RecipeStage} inputProps={{episode:version==='v2'?candidate:baseline}} durationInFrames={720} compositionWidth={720} compositionHeight={1280} fps={30} initialFrame={Math.min(719,Math.max(0,frame))} initiallyMuted playbackRate={rate} controls={false} loop={false} moveToBeginningWhenEnded={false} style={{width:'100%',height:'100%'}} acknowledgeRemotionLicense/></section>
  {!capture&&<aside><span className="eyebrow">FIELD NOTES / MOTION REVIEW</span><h1>青珊瑚现场笔记<br/>动效优化候选</h1><p>先让标题让位，再把视角聚成主角；用线条连接线索，最后把发现汇成结论。</p><span className="badge">24秒 · 复用低清素材 · 静音示意</span>
   <div className="versions"><button aria-pressed={version==='v2'} onClick={()=>{setVersion('v2');setPlaying(false)}}>v2 优化候选</button><button aria-pressed={version==='v1'} onClick={()=>{setVersion('v1');setPlaying(false)}}>v1 已定稿对照</button></div>
   <nav>{plan.scenes.map((s,i)=><button key={s.id} onClick={()=>jump(version==='v2'?s.from:i*180)}><b>0{i+1}</b><span>{s.label}<small>{s.short}</small></span></button>)}</nav>
   <div className="transport"><button onClick={()=>ref.current?.toggle()}>{playing?'暂停':'播放预览'}</button><button onClick={()=>{jump(0);ref.current?.play()}}>从头重播</button><select aria-label="播放速度" value={rate} onChange={e=>setRate(Number(e.target.value))}><option value={1}>1×</option><option value={.5}>0.5×</option></select></div>
   <input aria-label="预览时间轴" type="range" min={0} max={719} value={frame} onChange={e=>jump(Number(e.target.value))}/><label className="frame-control">定位帧 <input aria-label="定位帧" type="number" min={0} max={719} value={frame} onChange={e=>jump(Math.max(0,Math.min(719,Number(e.target.value))))}/><span> / 719</span></label><p className="foot">小窗数字人连续保留。候选版供本地看动作与构图，尚未替换正式模板4；字幕为布局示意。</p>
  </aside>}
 </main>;
}
async function boot(){
 [candidate,baseline]=await Promise.all(['/episode.json','/baseline.json'].map(async url=>{const r=await fetch(url);if(!r.ok)throw Error('素材未准备');return r.json()}));
 const font=new FontFace('Field Notes Review',"url('/assets/font.ttf')");await font.load();document.fonts.add(font);await document.fonts.ready;
 candidate.fontFamily=baseline.fontFamily='Field Notes Review';
 createRoot(document.getElementById('root')!).render(<Preview/>);
}
boot().catch(e=>document.getElementById('root')!.textContent=e.message);
