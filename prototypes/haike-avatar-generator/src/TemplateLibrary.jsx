import {useEffect,useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import './template-library.css';
import {MotionGitLibrary} from './MotionGitLibrary.jsx';

export function TemplateLibrary(){
  const [mode,setMode]=useState('saved');
  return <><div className="library-filters" role="group" aria-label="模板来源"><button aria-pressed={mode==='saved'} onClick={()=>setMode('saved')}>已保存模板</button><button aria-pressed={mode==='motiongit'} onClick={()=>setMode('motiongit')}>MotionGit 导入与编辑</button><a href="/motiongit">打开独立编辑页</a></div>{mode==='motiongit'?<MotionGitLibrary/>:<SavedTemplateLibrary/>}</>;
}

function SavedTemplateLibrary(){
  const [items,setItems]=useState(null),[error,setError]=useState(''),[group,setGroup]=useState('全部'),[query,setQuery]=useState(''),[detail,setDetail]=useState(null),[guide,setGuide]=useState(null),[notice,setNotice]=useState('');
  useEffect(()=>{let live=true;api('/api/studio/template-library').then(v=>live&&setItems(v.templates)).catch(e=>live&&setError(e.message));return()=>{live=false;};},[]);
  useEffect(()=>{setGuide(null);setNotice('');},[detail]);
  const groups=['全部','店长账号','招商广告','基础口播','图文视频'];
  const visible=(items||[]).filter(t=>(group==='全部'||t.group===group)&&`${t.name} ${t.status} ${t.avatar} ${t.description}`.includes(query.trim()));
  async function copy(){
    const prompt=`使用模板“${detail.name}”（${detail.id}）。先读 START_HERE.md、Haike_video/AGENT_GUIDE.md 和 ${detail.runbook}${detail.spec?`，并核对规格 ${detail.spec}`:''}。按原生制作入口冻结本期已批准音频和素材，保持模板视觉、字幕、BGM及音效规则。${detail.avatar}。${detail.id==='store-footage-20'||detail.id==='store-footage-21'?'只在介绍店长的一句插入高质量数字人；按本期ASR重算时间，只替换主窗，完整配音连续、副窗继续实拍。':''} 按手册验收并交付；新素材先复验，不把历史样片当本期已通过。`;
    try{await navigator.clipboard.writeText(prompt);setNotice('制作指令已复制，可粘贴到新的Agent窗口。');}catch{setNotice(prompt);}
  }
  if(detail)return <section className="visual-library">
    <Button onClick={()=>setDetail(null)}>返回全部模板</Button>
    <div className="library-detail">
      <div className="library-player">{detail.sample?<video key={detail.id} controls preload="metadata" poster={detail.poster||undefined} src={detail.sample}/>:detail.poster?<img src={detail.poster} alt={detail.name}/>:<div className="library-empty">本机暂无样片预览<br/>可查看视觉手册</div>}</div>
      <div className="library-description"><span className="library-status">{detail.status}</span><h3>{detail.name}</h3><p>{detail.description}</p><dl><dt>画幅 / 参考时长</dt><dd>{detail.ratio} / {detail.duration}</dd><dt>人物安排</dt><dd>{detail.avatar}</dd><dt>复刻方式</dt><dd>{detail.href?'独立图文制作页面':'Agent按已保存Runbook制作'}</dd></dl>
      <p className="helper">{detail.status==='短样测试'?'此版本只完成短样测试，制作完整视频需按手册补验。':'样片用于查看版式；换文案、素材或音频后按手册重新验收。'}</p>
      <div className="library-actions"><Button variant="primary" onClick={copy}>复制制作指令</Button>{detail.href&&<a href={detail.href}>打开制作页面</a>}{detail.guide&&<Button onClick={async()=>{try{setGuide((await api(detail.guide)).text);}catch(e){setNotice(e.message);}}}>查看视觉Runbook</Button>}</div><Notice message={notice}/>
      </div>
    </div>{guide!==null&&<div className="library-guide"><h4>视觉与制作手册</h4><pre>{guide}</pre></div>}
  </section>;
  return <section className="visual-library">
    <div className="library-heading"><div><h3>已保存的视觉模板</h3><p>先看版式与完整样片，再把制作指令交给Agent。</p></div><label>搜索模板<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="编号、颜色或纯实拍"/></label></div>
    <div className="library-filters" role="group" aria-label="模板用途">{groups.map(g=><button key={g} aria-pressed={group===g} onClick={()=>setGroup(g)}>{g}</button>)}<span>{visible.length}个版本</span></div>
    <Notice message={error} error/>{!items&&!error&&<p role="status">正在读取已保存模板…</p>}
    <div className="library-grid">{visible.map(t=><button className="library-card" key={t.id} onClick={()=>setDetail(t)}><div className="library-cover">{t.poster?<img loading="lazy" src={t.poster} alt={`${t.name}实际样片`}/>:<div className="library-empty">{t.name.split(' · ')[1]||t.name}<small>视觉手册 · 暂无本机预览</small></div>}<span className="library-status">{t.status}</span></div><div className="library-card-copy"><strong>{t.name}</strong><p>{t.ratio} / {t.duration}</p><small>{t.avatar}</small></div></button>)}</div>
    {items&&!visible.length&&<p>没有匹配模板，试试编号或切换用途。</p>}
  </section>;
}
