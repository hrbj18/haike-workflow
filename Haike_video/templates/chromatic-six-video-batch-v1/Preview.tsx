import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Player,type PlayerRef} from '@remotion/player';
import {Template06,Template07} from './window-a/Scene';
import {Template08,Template09} from './window-b/Scene';
import {Template10,Template11} from './window-c/Scene';
import catalogue from './catalogue.json';

const components={'06':Template06,'07':Template07,'08':Template08,'09':Template09,'10':Template10,'11':Template11};
const episodes:Record<string,any>={};
function Review(){
 const params=new URLSearchParams(location.search),initial=params.get('template')||'06';
 const [id,setId]=useState(initial in components?initial:'06'),[frame,setFrame]=useState(Math.max(0,Math.min(719,Number(params.get('frame'))||120))),[playing,setPlaying]=useState(false),[rate,setRate]=useState(1),[naturalEndFrame,setNaturalEndFrame]=useState<number|null>(null),player=useRef<PlayerRef>(null);
 const entry=catalogue.templates.find(x=>x.id===id)!;
 useEffect(()=>{const p=player.current!;const tick=(e:any)=>setFrame(e.detail.frame),play=()=>{setNaturalEndFrame(null);setPlaying(true)},pause=()=>setPlaying(false),ended=()=>{setNaturalEndFrame(p.getCurrentFrame());setPlaying(false)};p.addEventListener('frameupdate',tick);p.addEventListener('play',play);p.addEventListener('pause',pause);p.addEventListener('ended',ended);return()=>{p.removeEventListener('frameupdate',tick);p.removeEventListener('play',play);p.removeEventListener('pause',pause);p.removeEventListener('ended',ended)}},[id]);
 const seek=(f:number)=>{player.current?.pause();player.current?.seekTo(f);setNaturalEndFrame(null);setFrame(f);setPlaying(false)};
 const select=(next:string)=>{player.current?.pause();setPlaying(false);setNaturalEndFrame(null);setFrame(120);setId(next)};
 return <main data-template={id} data-current-frame={frame} data-playing={playing} data-natural-end-frame={naturalEndFrame}>
  <section className="stage"><Player key={id} ref={p=>{player.current=p}} component={components[id as keyof typeof components]} inputProps={{episode:episodes[id]}} compositionWidth={720} compositionHeight={1280} fps={30} durationInFrames={720} initialFrame={frame} initiallyMuted playbackRate={rate} controls={false} loop={false} moveToBeginningWhenEnded={false} style={{width:'100%',height:'100%'}} acknowledgeRemotionLicense/></section>
  <aside><span className="eyebrow">CHROMATIC MOTION / REAL VIDEO</span><h1>六种编排，真实现场</h1><p>主素材改为真实视频。文字与版式可停留供阅读，现场人物、设备和互动继续播放。</p>
   <div className="active-label"><b>{entry.id} · {entry.name}</b><span>24秒低清静音 · 视频候选</span></div>
   <nav>{catalogue.templates.map(t=><button key={t.id} aria-pressed={id===t.id} onClick={()=>select(t.id)} style={{borderTop:`7px solid ${t.accent}`}}><b>{t.id} · {t.name}</b><small>{t.shape}</small></button>)}</nav>
   <p role="status">{playing?'正在播放：现场素材内容持续运动':naturalEndFrame!==null?'本片播放结束，可从头重播':'已暂停，点击播放查看视频内容运动'}</p>
   <div className="transport"><button onClick={()=>player.current?.toggle()}>{playing?'暂停':'播放视频预览'}</button><button onClick={()=>{seek(0);player.current?.play()}}>从头重播</button><select aria-label="播放速度" value={rate} onChange={e=>setRate(Number(e.target.value))}><option value={1}>1×</option><option value={.5}>0.5×</option></select></div>
   <input aria-label="预览时间轴" type="range" min={0} max={719} value={frame} onChange={e=>seek(Number(e.target.value))}/><label className="frame-control">定位帧 <input aria-label="定位帧" type="number" min={0} max={719} value={frame} onChange={e=>seek(Math.max(0,Math.min(719,Number(e.target.value))))}/><span> / 719</span></label>
   <p><a href="http://127.0.0.1:14949/" target="_blank">查看保留的照片设计基线</a></p><p className="foot">逐次只播放一套。字幕为静音布局示意；用户确认、正式有声、高清与生产接入分别验收。</p>
  </aside>
 </main>;
}
async function boot(){
 const binding=await fetch('/input-bindings.json').then(r=>{if(!r.ok)throw Error('视频输入未准备');return r.json()});
 const font=new FontFace('Haike Six Video',`url('${binding.fontUrl}')`);await font.load();document.fonts.add(font);await document.fonts.ready;
 await Promise.all(catalogue.templates.map(async e=>{const r=await fetch('/episodes/'+e.id+'.json');if(!r.ok)throw Error('本套素材未准备：'+e.id);episodes[e.id]=await r.json();if(episodes[e.id].durationInFrames!==720)throw Error('仅接受24秒输入');episodes[e.id].fontFamily='Haike Six Video';}));
 createRoot(document.getElementById('root')!).render(<Review/>);
}
boot().catch(e=>document.getElementById('root')!.textContent=e.message);
