import {useState} from 'react';
import {Layers} from 'lucide-react';
import {Button,Dialog} from './ui.jsx';
import {TEMPLATES} from './generator-model.js';
import {TemplateLibrary} from './TemplateLibrary.jsx';
import {TemplatePreview,TemplateSampleDialog} from './TemplatePreview.jsx';
import {motionSelection} from './motion-preferred-model.js';

export function AvatarTemplatePicker({templateId,motion,motionProduction,onChoose}) {
  const [open,setOpen]=useState(false),[detail,setDetail]=useState(null),[sample,setSample]=useState(null);
  const selected=TEMPLATES.find(t=>t.id===templateId);
  const choose=t=>{onChoose({templateId:t.id,motion:null,motion_production:null});setOpen(false);setDetail(null);};
  return <><div className="avatar-template-choice"><div><strong>{motionProduction?'已选动效模板':motion?`${motion.style} · 动效口播`:selected?.name}</strong><p className="helper">{motionProduction?'按所选样式制作':motion?(motion.layout==='portrait'?'9:16':'16:9'):selected?.ratio} · 文案、声音与素材在切换时保留</p></div><Button onClick={()=>{setDetail(null);setOpen(true);}}><Layers size={17}/>选择模板</Button></div>
    {open&&<Dialog title={detail?detail.name:'选择视频模板'} description={detail?`${detail.ratio} · ${detail.kind}`:'固定模板与动效模板，每套都有样式封面。'} wide onClose={()=>{setOpen(false);setDetail(null);}} footer={detail&&<><Button onClick={()=>setDetail(null)}>返回模板列表</Button><Button variant="primary" onClick={()=>choose(detail)}>使用此模板</Button></>}>
      {detail?<div className="template-detail"><TemplatePreview template={detail} onPlay={()=>setSample(detail)}/><p className="template-detail-note">{detail.sampleNote||detail.previewNote}</p></div>:<TemplateLibrary directTemplates={TEMPLATES} onSelectProduction={t=>{onChoose({motion_production:motionSelection(t),motion:null});setOpen(false);setDetail(null);}} onSelectDirect={t=>{const original=TEMPLATES.find(item=>item.id===t.id);if(original?.previews)setDetail(original);else if(original)choose(original);}}/>}
    </Dialog>}{sample&&<TemplateSampleDialog template={sample} onClose={()=>setSample(null)}/>}</>;
}
