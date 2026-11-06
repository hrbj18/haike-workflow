import {useEffect, useState} from 'react';
import {CheckCircle2, Circle, LoaderCircle, Sparkles} from 'lucide-react';
import {api} from './studio-api.js';
import {Button, Notice} from './ui.jsx';
import './one-stop.css';

const ROOT='/api/studio/one-stop';
const statusLabel={queued:'已准备',running:'正在制作',waiting:'云端处理中',awaiting_agent:'Agent处理中',awaiting_input:'等待本次素材',paused:'待恢复',stopped:'已停止',completed:'已成片'};

export function OneStopPanel(){
  const [items,setItems]=useState([]),[selected,setSelected]=useState(()=>new URLSearchParams(location.search).get('one_stop')||'');
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[generation,setGeneration]=useState(0);
  useEffect(()=>{const changed=()=>{setItems([]);setSelected('');setError('');setGeneration(n=>n+1);};window.addEventListener('haike:gateway-changed',changed);return()=>window.removeEventListener('haike:gateway-changed',changed);},[]);
  useEffect(()=>{
    let live=true,timer;
    async function refresh(){try{const value=await api(`${ROOT}/jobs`);if(live){setItems(value.items||[]);setError('');}}catch(e){if(live)setError(e.message);}finally{if(live)timer=setTimeout(refresh,5000);}}
    void refresh();
    return()=>{live=false;clearTimeout(timer);};
  },[generation]);
  const task=items.find(row=>row.id===selected)||items[0];
  async function resume(){setBusy(true);setError('');try{await api(`${ROOT}/jobs/${task.id}/advance`,{});setGeneration(n=>n+1);}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <section className="one-stop-panel" aria-label="Agent一条龙制作">
    <div className="one-stop-heading"><div><h2><Sparkles size={18} aria-hidden="true"/>Agent一条龙制作</h2><p>在对话里提供人物图片和声音样本，说“使用一条龙视频生成流程”，进度和成片会显示在这里。</p></div>{task&&<span className={`one-stop-status ${task.status==='completed'?'complete':''}`}>{statusLabel[task.status]||'处理中'}</span>}</div>
    {!task&&!error&&<p className="helper">默认动效模板11 · 自动精修、克隆声音、校准语速、挑选素材与合成。高质量数字人每片累计上限2000 RH币。</p>}
    <Notice message={error} error/>
    {task&&<>
      {items.length>1&&<label className="one-stop-select">制作记录<select value={task.id} onChange={e=>setSelected(e.target.value)}>{items.map(row=><option key={row.id} value={row.id}>{row.title}{row.rate!=null?` · ${row.rate.toFixed(2)}倍速`:''} · {statusLabel[row.status]||'处理中'}</option>)}</select></label>}
      {task.revision_of&&<p className="helper">语速修订版，沿用本次人物与音色；原版与累计费用记录已保留。</p>}
      <p className="one-stop-title"><strong>{task.title}</strong><span>{task.template_name}{task.rate!=null?` · ${task.rate.toFixed(2)}倍速`:''}</span></p>
      {task.pace?.full_characters_per_five_seconds!=null?<p className="helper">整稿实测：每5秒 {task.pace.full_characters_per_five_seconds.toFixed(2)} 字{task.pace.target?`，目标 ${task.pace.target.minimum}～${task.pace.target.maximum} 字`:''}。{task.pace.full_text_accepted?'已达标。':''}</p>:task.pace?.test_characters_per_five_seconds!=null&&<p className="helper">{task.pace.calibration_mode==='fixed_text_baseline'?'固定文案1.00倍':'试听'}实测：每5秒 {task.pace.test_characters_per_five_seconds.toFixed(2)} 字。{task.pace.test_cache_hit?'已复用测速结果。':''}整稿语速待验收。</p>}
      <ol className="one-stop-stages">{task.stages.map(stage=><li key={stage.id} className={stage.status} aria-current={task.stage===stage.id?'step':undefined}>{stage.status==='succeeded'?<CheckCircle2 size={16} aria-hidden="true"/>:stage.status==='running'?<LoaderCircle size={16} className="spinner" aria-hidden="true"/>:<Circle size={16} aria-hidden="true"/>}<span>{stage.label}</span></li>)}</ol>
      <p className="helper" role="status">{task.message||task.stage_label}</p>
      {task.status==='paused'&&<Button loading={busy} onClick={resume}>恢复原任务</Button>}
      {task.media&&<details className="one-stop-record"><summary>查看本次人物与声音</summary><div className="one-stop-inputs"><figure><img src={task.media.source} alt="本次人物原图" loading="lazy"/><figcaption>人物原图</figcaption></figure>{task.media.refined&&<figure><img src={task.media.refined} alt="本次已检查的精修图" loading="lazy"/><figcaption>精修结果</figcaption></figure>}<div className="one-stop-audios"><label>声音样本<audio controls preload="metadata" src={task.media.sample}/></label>{task.media.audition&&<label>语速测量试听<audio controls preload="metadata" src={task.media.audition}/></label>}{task.media.narration&&<label>完整配音<audio controls preload="metadata" src={task.media.narration}/></label>}</div></div></details>}
      {task.result&&<div className="one-stop-output"><video controls preload="metadata" src={task.result.video_url} poster={task.result.cover_url} aria-label="一条龙实际成片"/><div><Button href={task.result.video_url} download>{task.result.review_status==='pending'?'下载合成预览':'下载成片'}</Button><Button href={task.result.cover_url} download>下载封面</Button></div></div>}
      <details className="one-stop-record"><summary>制作与费用记录</summary><p className="helper">任务 {task.id} · 已保存全部步骤，刷新页面后继续查看。</p><p className="helper">高质量数字人累计上限 {task.budget_rh_coins} RH币{task.avatar_reserved_rh_coins!=null?`，预留 ${task.avatar_reserved_rh_coins} RH币`:''}{task.avatar_usage_rh_coins!=null?`，已记录用量 ${task.avatar_usage_rh_coins} RH币`:''}。</p>{task.charges?.map(row=><p className="helper" key={row.stage}>{({clone:'克隆声音',audition:'语速试听',narration:'完整配音',asr:'字幕识别'})[row.stage]||(row.stage.startsWith('narration-adjust-')?'完整配音语速校准':row.stage)}：报价预留 ¥{(Number(row.estimated_micros)/1000000).toFixed(6)}，实际费用待供应商回执。</p>)}</details>
    </>}
  </section>;
}
