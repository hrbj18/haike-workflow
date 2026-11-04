import {useEffect,useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import {productionInstruction} from './motion-preferred-model.js';

export function useProductionCard(selection){
 const [card,setCard]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let live=true;setCard(null);setError('');if(selection)api('/api/studio/template-library').then(v=>{if(live){const row=v.templates.find(t=>t.id===selection.gallery_id);if(row)setCard(row);else setError('原样式暂不可用，草稿选择与素材已保留。');}}).catch(()=>live&&setError('模板入口暂时无法读取，草稿与素材保留。'));return()=>{live=false;};},[selection?.gallery_id]);
 return {card,error};
}
export function MotionProductionSelection({selection,card,error,onSave}){
 const [notice,setNotice]=useState(''),[result,setResult]=useState(null),[busy,setBusy]=useState(false);
 const current=card?.preferred_production;
 const historical=current&&current.version!==selection.version;
 async function copy(){setBusy(true);try{const draft=await onSave();await navigator.clipboard.writeText(productionInstruction({...card,preferred_production:{...current,version:selection.version,production_contract:selection.production_contract||current.production_contract,...(historical?{prepare_endpoint:'/api/studio/motion-replay/prepare'}:{})}},draft.id));setNotice('草稿与已有素材已保存，制作指令已复制。交给当前Agent继续准备。');}catch(e){setNotice(e.message);}finally{setBusy(false);}}
 async function prepare(file){if(!file)return;setBusy(true);setNotice('');try{if(file.size>2*1024*1024)throw Error('本期输入JSON最多2MB。');const v=JSON.parse(await file.text());setResult(await api(current.prepare_endpoint,{request:v.request||v}));}catch(e){setNotice(e.message);}finally{setBusy(false);}}
 return <section className="motion-production-selection" aria-label="所选动效制作入口"><h3>{card?.name||'已选动效模板'}</h3><p>已有文案、声音、人物与素材继续保留。由当前Agent补齐真实时钟和本期编排，再沿所选模板制作。</p><Notice error message={error}/>{historical&&<Notice message="此草稿保留原精确版本；不会随首选版本自动升级。请交Agent按原身份继续。"/>}
 {card&&<><p className="helper">待准备：{current.required_inputs.map(x=>x.label).join('、')}。已有素材可直接复用，准备不会提交付费或渲染任务。</p><Button disabled={busy} onClick={copy}>保存草稿并复制制作指令</Button><details><summary>检查Agent已准备的本期输入</summary><p className="helper">这里只检查输入与来源，不生成新片。实际制作继续使用原队列与审核记录。</p><label>载入本期输入JSON<input type="file" accept="application/json,.json" disabled={busy||historical} onChange={e=>{prepare(e.target.files[0]);e.target.value='';}}/></label><small>精确版本：{selection.version}</small>{result&&<><p role="status">{result.status==='prepared'?'输入已核对，可交Agent沿固定入口继续制作。':result.blockers?.join('；')||'请补齐本期输入。'}</p><details><summary>查看准备回执</summary><textarea readOnly aria-label="只读准备回执" rows={6} value={JSON.stringify(result,null,2)}/></details></>}</details></>}
 <Notice message={notice}/></section>;
}
