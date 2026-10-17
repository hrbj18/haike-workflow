/** Framework-neutral UI. Keep supplier/service credentials in the host backend.
 * submit(file,{confirmed}) -> job; get(id) -> job; file(id,kind) -> Blob.
 * onAdopt({jobId, sourceFile, resultBlob, presetVersion}) must copy the result
 * into host storage and CAS-check the original asset ID/revision before adoption.
 * restore(job, sourceFile) resumes a host-persisted task without submitting.
 */
export function mountRefinement(container, {submit, get, file, onAdopt, onOriginal}) {
  let epoch=0, job=null, source=null, result=null, timer=null;
  const urls=[];
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const root=node('section');root.setAttribute('aria-label','图片预设优化');
  const input=node('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.setAttribute('aria-label','上传原图');
  const description=node('p','上传后使用服务端预设优化。确认费用后开始，结果对比后采用；原图保留。');
  const status=node('p');status.setAttribute('role','status');
  const compare=node('div');compare.style.cssText='display:flex;gap:16px;flex-wrap:wrap';
  const original=node('img'), candidate=node('img');original.alt='原图';candidate.alt='优化候选';
  for(const img of [original,candidate]){img.style.cssText='max-width:100%;width:240px;object-fit:contain';compare.append(img);}
  const start=node('button','确认费用并优化'), refresh=node('button','查询原任务'), adopt=node('button','采用优化图'), keep=node('button','使用原图');
  root.append(input,description,status,compare,start,refresh,adopt,keep);container.append(root);
  const objectUrl=blob=>{const url=URL.createObjectURL(blob);urls.push(url);return url;};
  function resetUrls(){while(urls.length)URL.revokeObjectURL(urls.pop());original.removeAttribute('src');candidate.removeAttribute('src');}
  function update(){start.disabled=!source||!!job;refresh.disabled=!job;adopt.disabled=!result;keep.disabled=!source;}
  function later(ticket){clearTimeout(timer);timer=setTimeout(()=>poll(ticket),2500);}
  async function poll(ticket){
    if(ticket!==epoch||!job)return;
    try{
      const next=await get(job.id);if(ticket!==epoch)return;job=next;
      if(job.status==='succeeded'){
        const blob=await file(job.id,'result');if(ticket!==epoch)return;
        result=blob;candidate.src=objectUrl(blob);status.textContent=job.metadata?.warning||'优化完成，请对比后采用。';
      }else if(job.status==='ambiguous')status.textContent='结果或扣费未知。请先核对上游，勿重新提交；可使用原图。';
      else if(job.status==='failed')status.textContent=job.error||'优化失败，原图保留。';
      else{status.textContent='正在优化…';later(ticket);}
    }catch{if(ticket===epoch)status.textContent='查询失败，请点“查询原任务”；不会重发修图。';}
    if(ticket===epoch)update();
  }
  input.onchange=()=>{epoch++;clearTimeout(timer);resetUrls();source=input.files?.[0]||null;job=null;result=null;if(source)original.src=objectUrl(source);status.textContent='已选择原图。确认费用后使用预设优化。';update();};
  start.onclick=async()=>{
    if(!source||job)return;const ticket=epoch;start.disabled=true;
    try{const value=await submit(source,{confirmed:true});if(ticket!==epoch)return;job=value;status.textContent='原图已提交，正在优化…';update();await poll(ticket);}
    catch{if(ticket===epoch){status.textContent='提交结果未知，请从项目已保存的任务编号恢复；不要重复点击提交。';start.disabled=true;}}
  };
  refresh.onclick=()=>poll(epoch);
  adopt.onclick=async()=>{if(!job||!result)return;const ticket=epoch;adopt.disabled=true;try{await onAdopt({jobId:job.id,sourceFile:source,resultBlob:result,presetVersion:job.config?.preset_version});if(ticket!==epoch)return;status.textContent='已采用优化图，原图保留。';epoch++;clearTimeout(timer);}catch{if(ticket===epoch){status.textContent='采用未完成，请检查原图版本及保存状态。';update();}}};
  keep.onclick=async()=>{const ticket=epoch;try{await onOriginal({jobId:job?.id,sourceFile:source});if(ticket!==epoch)return;epoch++;clearTimeout(timer);status.textContent='已选择原图。';start.disabled=true;adopt.disabled=true;refresh.disabled=true;}catch{if(ticket===epoch)status.textContent='原图选择未保存，请重试。';}};
  update();
  return {
    restore(savedJob,sourceFile){epoch++;clearTimeout(timer);resetUrls();job=savedJob;source=sourceFile;result=null;if(source)original.src=objectUrl(source);update();poll(epoch);},
    destroy(){epoch++;clearTimeout(timer);resetUrls();root.remove();},
  };
}
