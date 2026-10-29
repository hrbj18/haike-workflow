import {useState} from 'react';
import {api} from './studio-api.js';
import {Button,Dialog,Notice} from './ui.jsx';
import {NetworkMaterials} from './NetworkMaterials.jsx';
import {resumeDouyinJob} from './douyin-recovery-model.js';

export function DouyinRecovery({job,onJob}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[items,setItems]=useState(null),[selected,setSelected]=useState(''),[rights,setRights]=useState(false);
  if(job?.status!=='failed'||!/抖音/.test(job.stage))return null;
  async function task(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
  return <div className="douyin-recovery"><p className="helper">先在统一账号窗口选择抖音下载账号并检查登录，再恢复原任务；已生成的声音与素材保留。</p><NetworkMaterials/><div className="action-buttons"><Button disabled={busy} onClick={()=>task(async()=>{onJob(await resumeDouyinJob(api,job.job_id));})}>检查下载登录并继续</Button><Button disabled={busy} onClick={()=>task(async()=>{const r=await api(`/api/studio/ai/jobs/${job.job_id}/douyin-candidates`);setItems(r.items);setSelected('');setRights(false);})}>查看候选素材</Button></div><Notice message={error} error/>
    {items&&<Dialog title="确认抖音素材使用权" description="采集工具的授权不代表第三方视频的使用权。选择你有权使用的素材。" busy={busy} onClose={()=>setItems(null)} footer={<><Button disabled={busy} onClick={()=>setItems(null)}>返回</Button><Button variant="primary" disabled={busy||!selected||!rights} onClick={()=>task(async()=>{onJob(await api(`/api/studio/ai/jobs/${job.job_id}/authorize-douyin`,{video_id:selected,rights_confirmed:true}));setItems(null);})}>确认使用并恢复任务</Button></>}>
      {items.length?items.map((item,i)=><article key={`${item.id}-${i}`} className="ai-material-item"><label className="checkbox-row"><input type="radio" name="douyin-candidate" value={item.id} checked={selected===item.id} onChange={()=>{setSelected(item.id);setRights(false);}}/>{item.title}</label><p className="helper">{item.author}</p><Button href={`https://www.douyin.com/video/${encodeURIComponent(item.id)}`} target="_blank" rel="noreferrer">查看原视频</Button></article>):<p className="helper">还没有候选素材。先完成登录并恢复搜索，也可以跳过抖音使用Pexels。</p>}
      {selected&&<label className="checkbox-row"><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/>我确认有权将该视频用于本次制作</label>}
    </Dialog>}
  </div>;
}
