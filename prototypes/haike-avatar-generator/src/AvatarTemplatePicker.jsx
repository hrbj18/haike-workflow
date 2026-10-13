import {useEffect,useState} from 'react';
import {Layers} from 'lucide-react';
import {Button,Dialog,Field,Notice} from './ui.jsx';
import {TEMPLATES} from './generator-model.js';
import {api} from './studio-api.js';

export function AvatarTemplatePicker({templateId,motion,onChoose}) {
  const [open,setOpen]=useState(false),[catalog,setCatalog]=useState(null),[layout,setLayout]=useState(motion?.layout||'portrait'),[error,setError]=useState('');
  useEffect(()=>{if(!open)return;let live=true;setCatalog(null);setError('');api(`/api/studio/motion/catalog?layout=${layout}`).then(v=>live&&setCatalog(v)).catch(e=>live&&setError(e.message));return()=>{live=false;};},[open,layout]);
  const selected=TEMPLATES.find(t=>t.id===templateId);
  return <><div className="avatar-template-choice"><div><strong>{motion?`${motion.style} · 动效口播`:selected?.name}</strong><p className="helper">{motion?(motion.layout==='portrait'?'9:16':'16:9'):selected?.ratio} · 文案、声音与素材在切换时保留</p></div><Button onClick={()=>setOpen(true)}><Layers size={17}/>选择模板</Button></div>
    {open&&<Dialog title="选择口播模板" description="基础口播与动效模板共用一套制作内容。" wide onClose={()=>setOpen(false)}><h3>基础口播</h3><div className="template-grid">{TEMPLATES.map(t=><button key={t.id} className={`template-tile ${!motion&&t.id===templateId?'selected':''}`} onClick={()=>{onChoose({templateId:t.id,motion:null});setOpen(false);}}><div className="template-cover"><img src={`${import.meta.env.BASE_URL}assets/${t.poster}`} alt="模板参考"/></div><div className="template-copy"><strong>{t.name}</strong><p>{t.ratio} · {t.description}</p></div></button>)}</div>
      <div className="ai-template-heading"><h3>动效口播</h3><Field label="画幅"><select value={layout} onChange={e=>setLayout(e.target.value)}><option value="portrait">竖屏 9:16</option><option value="landscape">横屏 16:9</option></select></Field></div><Notice message={error} error/><div className="ai-style-grid">{catalog?.styles.filter(s=>s.supported).map(s=><button key={s.id} className={`template-tile ${motion?.style===s.id&&motion?.layout===layout?'selected':''}`} onClick={()=>{onChoose({templateId:'avatar-safe-circle-v1',motion:{style:s.id,layout}});setOpen(false);}}>{s.preview&&<img src={s.preview} alt="上游风格参考"/>}<div><strong>{s.id} · {s.name}</strong><p>{s.groups.length}个镜头组 · {s.status==='stable'?'稳定组':s.id==='quick'?'轻量组合':'候选组，成片待审'}</p></div></button>)}</div>{!catalog&&!error&&<p className="helper" role="status">正在读取模板库…</p>}<p className="helper">AI按实际声音安排动作。完整模板需要的素材或动作时长不足时会保留母版并提示复核。专业编辑仍可手动调整完整镜头组。</p>
    </Dialog>}</>;
}
