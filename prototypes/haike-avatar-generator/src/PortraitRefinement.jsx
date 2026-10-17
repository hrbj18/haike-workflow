import {useEffect, useState} from 'react';
import {api} from './studio-api.js';
import {Button, Notice} from './ui.jsx';
import {refinementError} from './portrait-refinement-model.js';

const ROOT='/api/studio/refinement';
const money=value=>(Number(value||0)/1000000).toFixed(6).replace(/0+$/,'').replace(/\.$/,'');

export function PortraitRefinement({draftId,portrait,onAdopt,onPending}) {
  const [task,setTask]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [generation,setGeneration]=useState(0);
  const sourceId=portrait?.id;
  useEffect(()=>{const changed=()=>setGeneration(v=>v+1);window.addEventListener('haike:gateway-changed',changed);return()=>window.removeEventListener('haike:gateway-changed',changed);},[]);
  useEffect(()=>{
    let live=true;
    setTask(null);setError('');setBusy(false);
    if(!draftId||!sourceId||portrait.refined){onPending(false);return;}
    onPending(true);
    api(`${ROOT}/prepare`,{draft_id:draftId,asset_id:sourceId}).then(value=>{if(live)setTask(value);}).catch(e=>{if(live){setError(refinementError(e,{preparing:true}));onPending(false);}});
    return()=>{live=false;};
  },[draftId,sourceId,portrait?.refined,generation]);
  useEffect(()=>{if(task)onPending(!task.decision);},[task?.id,task?.decision]);
  useEffect(()=>{
    if(!task||!['submitting','queued','running','submission_unknown'].includes(task.status)||task.decision)return;
    let live=true;
    const timer=setInterval(()=>api(`${ROOT}/tasks/${task.id}`).then(value=>{if(live){setTask(value);setError('');}}).catch(e=>{if(live)setError(refinementError(e));}),4000);
    return()=>{live=false;clearInterval(timer);};
  },[task?.id,task?.status,task?.decision]);
  if(!portrait)return null;
  if(portrait.refined)return <p className="helper">已采用预设优化图 · 1024 × 1280，原图仍保留在项目素材中。</p>;
  async function submit(){
    setBusy(true);setError('');
    try{setTask(await api(`${ROOT}/tasks/${task.id}/submit`,{confirmed:true,max_charge_micros:task.maximum||task.quote.max_charge_micros}));}
    catch(e){setError(refinementError(e));}
    finally{setBusy(false);}
  }
  async function decide(use_refined){
    setBusy(true);setError('');
    try{const value=await api(`${ROOT}/tasks/${task.id}/decision`,{use_refined});setTask(value.task);onPending(false);if(use_refined)onAdopt(value.draft,sourceId);}
    catch(e){setError(refinementError(e));}
    finally{setBusy(false);}
  }
  async function renew(){setBusy(true);setError('');try{setTask(await api(`${ROOT}/tasks/${task.id}/renew`,{confirmed:true}));}catch(e){setError(refinementError(e));}finally{setBusy(false);}}
  return <div className="portrait-refinement" aria-label="人物图片预设优化">
    <p className="helper">人物优化为可选操作，也可直接使用上传的原图。默认坐姿人像预设保留人物身份与服装、自然肤质并整理背景，输出4:5竖图；确认本次费用后才开始优化。</p>
    <Notice message={error} error/>
    {error&&!task&&sourceId&&<Button disabled={busy} onClick={()=>setGeneration(v=>v+1)}>重新检查精修服务</Button>}
    {!sourceId&&<p className="helper">图片上传到项目后将自动准备优化报价。</p>}
    {task&&<>
      <details><summary>查看默认提示词</summary><p className="helper" style={{whiteSpace:'pre-wrap'}}>{task.prompt}</p></details>
      {task.status==='quoted'&&!task.decision&&<><p>海客人物精修 · GPT Image 2 · 本次费用上限 ¥{money(task.quote.max_charge_micros)}</p><Button disabled={busy} onClick={submit}>确认费用并优化图片</Button><Button disabled={busy} onClick={renew}>延长原报价有效期</Button></>}
      {['submitting','queued','running'].includes(task.status)&&!task.decision&&<p role="status">正在优化图片，完成后可对比并确认采用。</p>}
      {task.status==='submission_unknown'&&!task.decision&&<><p role="status">结果暂不确定，正在查询原任务。请勿重新提交修图。</p><Button disabled={busy} onClick={submit}>恢复原操作</Button></>}
      {task.status==='failed'&&<p role="status">本次优化未完成，原图已保留。{task.error}</p>}
      {task.result?.image_url&&!task.decision&&<><div className="layout-fields"><figure><img src={task.source_url} alt="优化前原图" style={{width:'100%',maxHeight:320,objectFit:'contain'}}/><figcaption>原图</figcaption></figure><figure><img src={task.result.image_url} alt="预设优化候选图" style={{width:'100%',maxHeight:320,objectFit:'contain'}}/><figcaption>优化候选</figcaption></figure></div><Button variant="primary" disabled={busy} onClick={()=>decide(true)}>确认采用优化图</Button></>}
      {!task.decision&&<Button disabled={busy} onClick={()=>decide(false)}>使用原图继续</Button>}
      {task.decision==='original'&&<p className="helper">已选择使用原图，优化结果不会自动替换。</p>}
    </>}
  </div>;
}
