import {useEffect,useState} from 'react';
import {Layers} from 'lucide-react';
import {Button,Dialog,Field,Notice} from './ui.jsx';
import {TEMPLATES} from './generator-model.js';
import {api} from './studio-api.js';
import {TemplateLibrary} from './TemplateLibrary.jsx';
import {TemplatePreview,TemplateSampleDialog} from './TemplatePreview.jsx';

export function AvatarTemplatePicker({templateId,motion,onChoose}) {
  const [open,setOpen]=useState(false),[catalog,setCatalog]=useState(null),[layout,setLayout]=useState(motion?.layout||'portrait'),[error,setError]=useState('');
  const [view,setView]=useState('library');
  const [detail,setDetail]=useState(null),[sample,setSample]=useState(null);
  useEffect(()=>{if(!open)return;let live=true;setCatalog(null);setError('');api(`/api/studio/motion/catalog?layout=${layout}`).then(v=>live&&setCatalog(v)).catch(e=>live&&setError(e.message));return()=>{live=false;};},[open,layout]);
  const selected=TEMPLATES.find(t=>t.id===templateId);
  const templates=[...TEMPLATES].sort((a,b)=>Number(!!b.featured)-Number(!!a.featured));
  return <><div className="avatar-template-choice"><div><strong>{motion?`${motion.style} · 动效口播`:selected?.name}</strong><p className="helper">{motion?(motion.layout==='portrait'?'9:16':'16:9'):selected?.ratio} · 文案、声音与素材在切换时保留</p></div><Button onClick={()=>{setDetail(null);setOpen(true);}}><Layers size={17}/>选择模板</Button></div>
    {open&&<Dialog title={detail?detail.name:'选择视频模板'} description={detail?`${detail.ratio} · ${detail.kind}`:'浏览已保存的视觉模板，或选择可直接制作的基础与动效模板。'} wide onClose={()=>{setOpen(false);setDetail(null);}} footer={detail&&<><Button onClick={()=>setDetail(null)}>返回模板列表</Button><Button variant="primary" onClick={()=>{onChoose({templateId:detail.id,motion:null});setOpen(false);setDetail(null);}}>使用此模板</Button></>}>
      {!detail&&<div className="template-browser-tabs"><Button variant={view==='library'?'primary':undefined} onClick={()=>setView('library')}>视觉模板库</Button><Button variant={view==='direct'?'primary':undefined} onClick={()=>setView('direct')}>基础与动效 · 直接制作</Button></div>}
      {!detail&&view==='library'?<TemplateLibrary/>:detail?<div className="template-detail"><TemplatePreview template={detail} onPlay={()=>setSample(detail)}/><p className="template-detail-note">{detail.sampleNote || detail.previewNote}</p><p className="helper">可更换人物、声音、标题与画面素材。选择模板后，在“画面安排”中设置四种画面模式。</p></div>:<><h3>基础口播</h3><div className="template-grid">{templates.map(t=><button key={t.id} className={`template-tile ${!motion&&t.id===templateId?'selected':''}`} onClick={()=>{if(t.previews){setDetail(t);return;}onChoose({templateId:t.id,motion:null});setOpen(false);}}><div className="template-cover"><img src={`${import.meta.env.BASE_URL}assets/${t.poster}`} alt={`${t.name}模板参考`}/></div><div className="template-copy"><strong>{t.name}</strong><p>{t.ratio} · {t.description}</p>{t.previews&&<small>{t.sample?'查看四种画面与样片':'查看四种画面示意'}</small>}</div></button>)}</div>
      <div className="ai-template-heading"><h3>动效口播</h3><Field label="画幅"><select value={layout} onChange={e=>setLayout(e.target.value)}><option value="portrait">竖屏 9:16</option><option value="landscape">横屏 16:9</option></select></Field></div><Notice message={error} error/><div className="ai-style-grid">{catalog?.styles.filter(s=>s.supported).map(s=><button key={s.id} className={`template-tile ${motion?.style===s.id&&motion?.layout===layout?'selected':''}`} onClick={()=>{onChoose({templateId:'avatar-safe-circle-v1',motion:{style:s.id,layout}});setOpen(false);}}>{s.preview&&<img src={s.preview} alt="上游风格参考"/>}<div><strong>{s.id} · {s.name}</strong><p>{s.groups.length}个镜头组 · {s.status==='stable'?'稳定组':s.id==='quick'?'轻量组合':'候选组，成片待审'}</p></div></button>)}</div>{!catalog&&!error&&<p className="helper" role="status">正在读取模板库…</p>}<p className="helper">AI按实际声音安排动作。完整模板需要的素材或动作时长不足时会保留母版并提示复核。专业编辑仍可手动调整完整镜头组。</p>
    </> }</Dialog>}{sample&&<TemplateSampleDialog template={sample} onClose={()=>setSample(null)}/>}</>;
}
