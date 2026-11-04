import React,{useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Player,type PlayerRef} from '@remotion/player';
import {catalogue,Demo} from './Demo';

class PreviewError extends React.Component<{children:React.ReactNode},{message:string}>{
  state={message:''};static getDerivedStateFromError(error:Error){return {message:error.message}}
  render(){return this.state.message?<div className="preview-error" role="alert">这个效果暂时无法播放：{this.state.message}</div>:this.props.children}
}
function App(){
  const params=new URLSearchParams(location.search);
  const initial=params.get('component')||location.hash.slice(1)||'phone-frame';
  const [selected,setSelected]=useState(catalogue.some(d=>d.id===initial)?initial:'phone-frame');
  const [query,setQuery]=useState('');const [category,setCategory]=useState('全部');
  const [autoNext,setAutoNext]=useState(false);const [posters,setPosters]=useState<string[]>([]);
  const [copied,setCopied]=useState(false);const [playing,setPlaying]=useState(false);
  const player=useRef<PlayerRef>(null);
  const active=catalogue.find(d=>d.id===selected)!;
  const categories=['全部',...new Set(catalogue.map(d=>d.category))];
  const filtered=useMemo(()=>catalogue.filter(d=>(category==='全部'||category===d.category)&&`${d.name} ${d.id} ${d.description}`.toLowerCase().includes(query.toLowerCase())),[query,category]);
  const choose=(id:string,scroll=false)=>{setSelected(id);setCopied(false);setPlaying(false);history.replaceState(null,'','#'+id);if(scroll)document.getElementById('preview')?.scrollIntoView({behavior:'smooth',block:'start'})};
  const move=(direction:number)=>{const rows=filtered.length?filtered:catalogue;const index=rows.findIndex(d=>d.id===selected);choose(rows[(Math.max(index,0)+direction+rows.length)%rows.length].id)};
  useEffect(()=>{fetch('preview-index.json').then(r=>r.ok?r.json():[]).then(setPosters).catch(()=>setPosters([]))},[]);
  useEffect(()=>{
    const ref=player.current;if(!ref)return;
    const end=()=>{setPlaying(false);if(autoNext)move(1)};
    const play=()=>setPlaying(true);const pause=()=>setPlaying(false);
    ref.addEventListener('ended',end);ref.addEventListener('play',play);ref.addEventListener('pause',pause);
    return()=>{ref.removeEventListener('ended',end);ref.removeEventListener('play',play);ref.removeEventListener('pause',pause)};
  },[selected,autoNext,filtered]);
  const instruction=`我要使用动效组件：${active.id}（${active.name}）。请结合我的文案、本地素材和数字人，按已选模板风格编排。`;
  const copy=async()=>{try{await navigator.clipboard.writeText(instruction);setCopied(true)}catch{setCopied(true)}};
  return <main>
    <header className="header"><div><div className="eyebrow">海客 · 动效积木</div><h1>先看效果，再挑喜欢的</h1><p>53 个免费动效已收入本地。每次只播放一个，支持拖动进度；有素材窗口的效果优先放入本地实拍。</p></div><span className="total">53<span>个效果</span></span></header>
    <section className="preview" id="preview" aria-label="当前动效预览">
      <div className="stage" data-testid="preview-stage" data-component={active.id}>
        <PreviewError key={selected}><Player key={selected} ref={player} component={Demo} inputProps={{id:selected}} durationInFrames={active.config.durationInFrames} fps={active.config.fps} compositionWidth={active.config.compositionWidth} compositionHeight={active.config.compositionHeight} initialFrame={Math.min(Number(params.get('frame')||0),active.config.durationInFrames-1)} controls loop={!autoNext} autoPlay={autoNext} acknowledgeRemotionLicense style={{width:'100%'}}/></PreviewError>
      </div>
      <aside><div className="badges"><span>{active.category}</span><span className={active.localMedia?'local':'text'}>{active.localMedia?'本地实拍演示':'中文内容演示'}</span></div><h2 data-testid="active-name">{active.name}</h2><code>{active.id}</code><p>{active.description}</p><div className="duration">{(active.config.durationInFrames/active.config.fps).toFixed(1)} 秒 · 原生动作节奏 · 静音预览</div>
      <div className="nav"><button onClick={()=>move(-1)} aria-label="上一个效果">← 上一个</button><button onClick={()=>move(1)} aria-label="下一个效果">下一个 →</button></div>
      <button className="primary" onClick={()=>{player.current?.seekTo(0);player.current?.play()}}>重新播放</button>
      <label className="autoplay"><input type="checkbox" checked={autoNext} onChange={e=>setAutoNext(e.target.checked)}/> 按目录自动连播</label>
      <button className="copy" onClick={copy}>{copied?'已显示调用语句':'复制给 Agent'}</button>{copied&&<p className="instruction">{instruction}</p>}
      <p className="note">字幕和数据使用示意内容；字体效果保留少量英文以看清字形。这里用于挑选动效，完整口播模板另行组合。</p><output className="sr-only" data-testid="play-status">{playing?'播放中':'已暂停'}</output></aside>
    </section>
    <section className="library" aria-label="全部动效目录"><div className="library-head"><h2>动效目录 <span>{filtered.length} 个</span></h2><input aria-label="搜索动效" placeholder="搜索：手机、照片、字幕…" value={query} onChange={e=>setQuery(e.target.value)}/></div>
    <nav className="categories" aria-label="动效分类">{categories.map(c=><button key={c} className={category===c?'active':''} onClick={()=>setCategory(c)}>{c}</button>)}</nav>
    <div className="grid">{filtered.map(d=><button key={d.id} className={'card '+(d.id===selected?'selected':'')} onClick={()=>choose(d.id,true)} data-testid={'card-'+d.id}><div className="poster">{posters.includes(d.id)?<img loading="lazy" src={`posters/${d.id}.jpg`} alt={d.name+'效果画面'}/>:<div className={'placeholder cat-'+categories.indexOf(d.category)}><strong>{d.name}</strong><span>点击预览 ↗</span></div>}<span className="seconds">{(d.config.durationInFrames/d.config.fps).toFixed(1)}s</span></div><div className="card-body"><div className="card-top"><strong>{d.name}</strong><span>{d.localMedia?'本地实拍':'中文示例'}</span></div><p>{d.description}</p><code>{d.id}</code></div></button>)}</div>{!filtered.length&&<p className="empty">没有找到，试试“图片”“手机”或“文字”。</p>}</section>
    <footer>全部效果使用固定版本的 Snapcn 免费源码。个人实拍只在本机加载；无新增配音、数字人生成或公开上传。<br/>组件目录供挑选与复用，实际模板仍需根据台词、画幅和素材进行编排与验收。</footer>
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
