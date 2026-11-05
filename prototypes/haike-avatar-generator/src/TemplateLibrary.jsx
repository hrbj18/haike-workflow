import {useEffect,useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import './template-library.css';
import {productionInstruction} from './motion-preferred-model.js';

export function TemplateLibrary({directTemplates=[],onSelectDirect,onSelectProduction}){
return <SavedTemplateLibrary directTemplates={directTemplates} onSelectDirect={onSelectDirect} onSelectProduction={onSelectProduction}/>;
}

function creationMethod(template){
  if(template.preferred_production)return '已绑定完整生产入口；准备本期输入后沿统一队列制作';
  if(template.package_installed===false)return '导入原包后按开放能力制作';
  if(template.source_kind==='imported-motion')return `${template.capability_status} · 本机原包参数编辑`;
  return template.href?'可编辑制作页面':'Agent按已保存Runbook制作';
}

function SavedTemplateLibrary({directTemplates,onSelectDirect,onSelectProduction}){
  const [items,setItems]=useState(null),[error,setError]=useState(''),[group,setGroup]=useState('动效模板'),[query,setQuery]=useState(''),[detail,setDetail]=useState(null),[guide,setGuide]=useState(null),[notice,setNotice]=useState(''),[attempt,setAttempt]=useState(0);
  useEffect(()=>{let live=true;setError('');api('/api/studio/template-library').then(v=>live&&setItems(v.templates)).catch(()=>live&&setError('模板库暂时无法连接，请确认工作台服务已启动后重试。'));return()=>{live=false;};},[attempt]);
  useEffect(()=>{setGuide(null);setNotice('');},[detail]);
  const groups=['固定模板','动效模板'];
  const all=[...directTemplates.map(t=>({...t,category:'固定模板',direct:true,poster:`${import.meta.env.BASE_URL}assets/${t.poster}`,duration:'支持直接制作',avatar:'人物与声音可替换'})),...(items||[])].sort((a,b)=>Number(!!b.release)-Number(!!a.release));
  const category=t=>t.category||(t.group==='动画模板'||t.source_kind==='imported-motion'?'动效模板':'固定模板');
  const visible=all.filter(t=>category(t)===group&&`${t.name} ${t.status||''} ${t.avatar||''} ${t.description||''}`.includes(query.trim()));
  async function copy(){
    if(detail.preferred_production){try{await navigator.clipboard.writeText(productionInstruction(detail));setNotice('已复制所选精确生产版本的制作指令。');}catch{setNotice(productionInstruction(detail));}return;}
    const replay=detail.replay?`先读 Haike_video/docs/MOTION_REPLAY_STANDARD.md，使用精确身份 ${detail.replay.template_id}@${detail.replay.version} 的统一复刻合同。通过 Haike_video/scripts/motion_replay.py catalog 核对开放能力，再用 prepare 准备本期输入；核对源SHA与真实动作绑定，保留原布局和运动公式。只使用已开放槽，缺原包、素材、未知动作或不支持的换稿能力先报告具体阻断，不把准备成功当作已完成视频。`:'';
    const prompt=`使用模板“${detail.name}”（${detail.id}）。先读 START_HERE.md、Haike_video/AGENT_GUIDE.md 和 ${detail.runbook}${detail.spec?`，并核对规格 ${detail.spec}`:''}。${replay}${detail.release?`正式配置：${detail.release}。按此精确版本声明的画幅和帧率输出高清有声正式版；完整口播连续，BGM及音效按混音规则；回链高清原片，不使用低清预览代理作为正式源。`:''}按原生制作入口冻结本期已批准音频和素材，保持模板视觉、字幕、BGM及音效规则。${detail.avatar}。${detail.id==='store-footage-20'||detail.id==='store-footage-21'?'只在介绍店长的一句插入高质量数字人；按本期ASR重算时间，只替换主窗，完整配音连续、副窗继续实拍。':''} 按手册验收并交付；新素材先复验，不把历史样片当本期已通过。`;
    try{await navigator.clipboard.writeText(prompt);setNotice('制作指令已复制，可粘贴到新的Agent窗口。');}catch{setNotice(prompt);}
  }
  if(detail)return <section className="visual-library">
    <Button onClick={()=>setDetail(null)}>返回模板列表</Button>
    <div className="library-detail">
      <div className="library-player">{detail.sample||detail.reference_preview?<video key={detail.id} controls preload="metadata" poster={detail.poster||undefined} src={detail.sample||detail.reference_preview}/>:detail.poster?<img src={detail.poster} alt={detail.name}/>:<div className="library-empty">原封面待找回<br/>可查看视觉手册</div>}</div>
      <div className="library-description"><span className="library-status">{detail.status}</span><h3>{detail.name}</h3><p>{detail.description}</p><dl><dt>画幅 / 参考时长</dt><dd>{detail.ratio} / {detail.duration}</dd><dt>人物安排</dt><dd>{detail.avatar}</dd><dt>制作方式</dt><dd>{creationMethod(detail)}</dd></dl>
      <p className="helper">{detail.status==='短样测试'?'此版本只完成短样测试，制作完整视频需按手册补验。':'样片用于查看版式；换文案、素材或音频后按手册重新验收。'}</p>
      {detail.replay&&<p className="helper">{detail.preferred_production?'沿已登记的精确生产入口准备，已有素材与声音可复用。':detail.package_installed===false?'导入匹配原包后，再核对它的开放能力和本期素材。':detail.replay.renderer.execution!=='supported'?'当前保留原包检查与编辑能力，视频制作需先完成适配。':detail.replay.capabilities.native_parameter_editor_only?'原包目前支持参数编辑；已登记的独立项目路线按各自制作条件复用。':'可按已开放的内容与制作方式复用；开始前核对本机素材和制作条件。'}</p>}{detail.replay_notice&&<Notice message={detail.replay_notice} error/>}
      <div className="library-actions">{detail.preferred_production&&onSelectProduction&&<Button variant="primary" onClick={()=>onSelectProduction(detail)}>使用此模板</Button>}<Button variant="primary" onClick={copy}>复制制作指令</Button>{detail.original_poster&&<a href={detail.original_poster} target="_blank" rel="noreferrer">查看本机原封面</a>}{detail.href&&<a href={detail.href}>打开制作页面</a>}{detail.source_kind==='imported-motion'&&detail.capability_status==='开放制作接口'&&<a href="/motiongit?section=studio">进入视频制作</a>}{detail.guide&&<Button onClick={async()=>{try{setGuide((await api(detail.guide)).text);}catch(e){setNotice(e.message);}}}>查看视觉Runbook</Button>}</div><Notice message={notice}/>{detail.preferred_production&&<details><summary>精确生产版本与历史记录</summary><p>新任务：{detail.preferred_production.version} · 完整声音与真实素材</p><p>保留版本：{detail.preferred_production.historical_versions.join("、")}</p><p>样片与原封面保留作风格参考，连续听看如实按实际记录说明。</p></details>}
      </div>
    </div>{guide!==null&&<div className="library-guide"><h4>视觉与制作手册</h4><pre>{guide}</pre></div>}
  </section>;
  return <section className="visual-library">
    <div className="library-heading"><div><h3>选择你想要的画面样式</h3><p>先看封面，再查看样片与制作说明。</p></div><label>搜索模板<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="编号、颜色或名称"/></label></div>
    <div className="library-filters" role="group" aria-label="模板分类">{groups.map(g=><button key={g} aria-pressed={group===g} onClick={()=>setGroup(g)}>{g} · {all.filter(t=>category(t)===g).length}</button>)}<span>{visible.length}个样式</span></div>
    <Notice message={error} error/>{error&&<Button onClick={()=>setAttempt(n=>n+1)}>重新加载模板</Button>}{!items&&!error&&<p role="status">正在读取模板…</p>}
    <div className="library-grid">{visible.map(t=><button className="library-card" key={t.id} onClick={()=>t.direct?onSelectDirect?.(t):setDetail(t)}><div className="library-cover">{t.poster?<img loading="lazy" src={t.poster} alt={`${t.name}样式封面`}/>:t.reference_preview?<video aria-label={`${t.name}原版参考封面`} src={t.reference_preview} preload="metadata" muted playsInline onLoadedMetadata={e=>{const v=e.currentTarget;if(Number.isFinite(v.duration))v.currentTime=Math.min(3,v.duration/2);}}/>:<div className="library-empty">{t.name.split(' · ')[1]||t.name}<small>原封面待找回</small></div>}<span className="library-status">{t.status||'基础模板'}</span></div><div className="library-card-copy"><strong>{t.name}</strong><p>{t.ratio} / {t.duration}</p><small>{t.cover_note||t.avatar}</small></div></button>)}</div>
    {items&&!visible.length&&<p>没有匹配模板，试试编号或切换用途。</p>}
  </section>;
}
