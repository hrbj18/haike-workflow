import {useEffect,useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import './hallmark-directions.css';

export function HallmarkDirections({draft,onSelect}){
  const [catalog,setCatalog]=useState(null),[error,setError]=useState('');
  const [query,setQuery]=useState(''),[genre,setGenre]=useState(''),[slug,setSlug]=useState('hum');
  useEffect(()=>{api('/api/studio/motiongit/art-directions').then(setCatalog).catch(e=>setError(e.message));},[]);
  useEffect(()=>{if(draft?.art_direction?.theme_slug)setSlug(draft.art_direction.theme_slug);},[draft?.id,draft?.art_direction?.theme_slug]);
  const selected=catalog?.themes.find(t=>t.slug===slug);
  const visible=(catalog?.themes||[]).filter(t=>(!genre||t.genre===genre)&&(!query||`${t.name} ${t.name_zh} ${t.summary_zh} ${t.video_use_zh}`.toLowerCase().includes(query.toLowerCase())));
  return <details className="hallmark-directions">
    <summary>Hallmark 视觉参考库 · {catalog?.themes.length||'…'}种风格{draft?.art_direction?.theme_slug?` · 本草稿：${catalog?.themes.find(t=>t.slug===draft.art_direction.theme_slug)?.name_zh||draft.art_direction.theme_slug}`:''}</summary>
    <p>选择配色、字体与材质方向，交给 Agent 按本期素材适配。这里展示原作者的网页参考图；视频动效沿用所选模板，画面仍需实际预览。</p>
    <Notice message={error}/>{!catalog&&!error&&<p role="status">正在读取风格目录…</p>}
    {catalog&&<><div className="hm-filters"><label>查找风格<input type="search" placeholder="例如：亲子、科技、纸感" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>风格类别<select value={genre} onChange={e=>setGenre(e.target.value)}><option value="">全部类别</option>{[...new Map(catalog.themes.map(t=>[t.genre,t.genre_zh]))].map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label><span role="status">{visible.length}种</span></div>
    <div className="hm-browser"><div className="hm-grid">{visible.map(t=><button type="button" key={t.slug} aria-pressed={slug===t.slug} onClick={()=>setSlug(t.slug)}><img src={t.image_url} alt={`${t.name_zh}网页风格参考`} loading="lazy" width="320" height="200"/><strong>{t.name} · {t.name_zh}</strong><span>{t.summary_zh}</span></button>)}{!visible.length&&<p>没有匹配风格，试试其他关键词。</p>}</div>
    {selected&&<aside className="hm-detail"><a className="hm-full-reference" href={selected.image_url} target="_blank" rel="noreferrer"><img src={selected.image_url} alt={`${selected.name}原作者网页示例，点击查看完整参考图`} width="600" height="375"/></a><h4>{selected.name} · {selected.name_zh}</h4><p>{selected.summary_zh}</p><p>视频场景建议：{selected.video_use_zh}</p><p>原版标题字体：{selected.display.face}。中文字体需另行匹配并检查实际字形。</p><div className="mg-actions"><a href={selected.reference_url} target="_blank" rel="noreferrer">原版设计说明</a><a href={`/api/studio/motiongit/art-directions/${selected.slug}/video-brief`} target="_blank" rel="noreferrer">视频适配计划</a></div><Button disabled={!draft} onClick={()=>onSelect({theme_slug:selected.slug,source_commit:catalog.source_commit})}>用于当前草稿的视觉方向</Button>{draft?.art_direction?.theme_slug&&<Button onClick={()=>onSelect({})}>清除草稿风格方向</Button>}<p>{draft?'选择后点击下方“保存草稿”，复制新视频时一并保留。':'选择或新建一份视频草稿后，可以保存风格方向。'}</p><small>风格选择仅保存参考方向，不会自动改写模板参数；原图中的照片与英文文案属于示例内容。</small></aside>}
    </div></>}
  </details>;
}
