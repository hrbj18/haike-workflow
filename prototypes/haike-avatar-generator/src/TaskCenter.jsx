import {useCallback,useEffect,useRef,useState} from 'react';
import {Activity,ArrowUpRight,CalendarClock,Clock3,FileText,ListTodo,RefreshCw,Send,Settings2,Wallet} from 'lucide-react';
import {Button,Dialog,EmptyState,Field,Heading,Notice} from './ui.jsx';
import {api} from './studio-api.js';
import {DAILY_TEMPLATES,TASK_PLATFORMS,applyTaskSummary,commandLabel,dailyPlanDraft,dailyPlanPayload,formatTaskMoney,
  formatTaskTime,mergeTaskEvents,nextReportClientId,publicationRows,reportWaiting,safeTaskHref,taskCenterHref,taskCenterRequest,taskGroups,taskStatusLabel,taskTone,taskPresentation,taskCounts,executorPresence} from './task-center-model.js';
import './task-center.css';

function Badge({status,children}) {return <span className={`task-badge ${taskTone(status)}`}>{children||taskStatusLabel(status)}</span>;}
function navigateTask(id) {history.pushState({},'',taskCenterHref({id}));window.dispatchEvent(new Event('haike:navigate'));}
function closeTask() {history.replaceState({},'','/task-center');window.dispatchEvent(new Event('haike:navigate'));}

export function TaskBudget({budget={}}) {
  return <dl className="task-budget" aria-label="费用记录">
    {[
      ['实际已结算',budget.actual_micros],['当前预留',budget.reserved_micros],
      ['预计费用',budget.estimated_micros],['费用上限',budget.limit_micros],
    ].map(([name,value])=><div key={name}><dt>{name}</dt><dd>{budget.currency&&budget.currency!=='CNY'?'币种待确认':formatTaskMoney(value)}</dd></div>)}
  </dl>;
}

export function PlatformResults({task}) {
  const unavailable=[task.sources?.work,task.sources?.calendar].some(item=>item?.availability==='unavailable');
  return <section className="task-platforms"><h3>平台发布</h3>{unavailable&&<p className="task-warning">发布数据暂时无法更新，已有回执仅供核对上次记录。</p>}<div className="task-platform-grid">
    {publicationRows(task).map(item=><article key={`${item.platform}-${item.account_id||'unknown'}`}>
      <header><strong>{item.name}</strong><span>{item.account_id?`账号 #${item.account_id}`:'尚未返回账号'}</span></header>
      <p className={['failed','error','uncertain'].includes(item.status)?'task-error-text':''}>{item.label}</p>
      {item.acceptance_status==='verified'&&<small>{item.identity_verified===true?'作品验收已核对，公开可见性单独确认。':'平台受理已核验，公开可见状态单独确认。'}</small>}
      {item.task_id&&<small>发布任务 #{item.task_id}</small>}
      {item.platform_work_id&&<small>作品编号：{item.platform_work_id}</small>}
      {item.error&&<p className="task-platform-error" role="alert">{item.error}</p>}
      {item.href&&<a className="text-button" href={item.href} target="_blank" rel="noopener noreferrer">{item.public_visible===true?'查看公开作品':'查看平台结果链接'}<ArrowUpRight size={14}/></a>}
    </article>)}
  </div></section>;
}

export function QueueState({task}) {
  const queue=task.sources?.queue;
  if(!queue)return <p className="helper">尚未关联制作队列。</p>;
  if(queue.availability==='unavailable')return <p className="task-warning">实际制作队列暂时不可读取，总控上报不能代替队列结果。</p>;
  if(queue.availability==='missing')return <p className="task-warning">关联的制作队列记录未找到，请核对原任务。</p>;
  const error=typeof queue.error==='string'?queue.error:queue.error?.message;
  return <div className="task-queue-state"><div><strong>实际制作队列</strong><Badge status={queue.status}/></div>
    <p>{queue.status==='completed'?'本地制作已完成，平台结果单独核对。':queue.stage||'尚未记录阶段'}</p><small>制作记录更新：{formatTaskTime(queue.updated_at)}</small>
    {error&&<p className="task-error-text" role="alert">{error}</p>}</div>;
}

export function TaskCard({task,onOpen}) {
  const view=taskPresentation(task),busy=['running','processing'].includes(view.status),workId=task.links?.work_id||task.sources?.work?.id;
  return <article className="surface task-card">
    <header><span className="task-card-id">{task.id}</span><Badge status={view.status}>{view.label}</Badge></header>
    <h3>{task.title||'未命名视频任务'}</h3>
    <p className="task-stage"><Activity size={16}/>总控阶段：{view.stage}</p>
    {task.summary&&<p className="task-summary">{task.summary}</p>}
    <dl className="task-freshness"><div><dt>最后进展</dt><dd>{formatTaskTime(task.last_progress_at)}</dd></div>
      <div><dt>运行心跳</dt><dd>{task.heartbeat_at?formatTaskTime(task.heartbeat_at):busy?'尚未收到心跳':'尚未记录'}</dd></div></dl><p className="helper">{executorPresence(task)}</p>
    <QueueState task={task}/>
    <TaskBudget budget={task.budget}/>
    <div className="task-platform-summary">{publicationRows(task).filter(r=>r.status!=='not_recorded').map(r=><span key={`${r.platform}-${r.account_id}`}>{r.name}：{r.status==='done'&&r.acceptance_status==='verified'?'已提交并核验':r.label}</span>)}</div>
    <footer><small>{task.pending_commands_count>0?`${task.pending_commands_count} 条请求等待响应`:'查看阶段记录与平台结果'}</small>
      {workId&&<Button href={`/projects?work=${encodeURIComponent(workId)}`}>查看成片</Button>}<Button onClick={()=>onOpen(task.id)}>查看任务与结果<ArrowUpRight size={15}/></Button></footer>
  </article>;
}

export function TaskArtifacts({task}) {
  const result=task.sources?.work?.result,video=safeTaskHref(result?.video_url),cover=safeTaskHref(result?.cover_url);
  if(!video)return null;
  return <section className="task-results"><h3>成片与发布资料</h3><div className="task-results-media"><video controls preload="none" src={video} poster={cover||undefined} aria-label="本条最终成片"/>
    {cover&&<a href={cover} target="_blank" rel="noopener noreferrer"><img src={cover} alt="本条发布封面"/>打开封面</a>}</div>
    <strong>{result.title||task.title}</strong>{result.desc&&<p className="task-publish-description">{result.desc}</p>}{result.topics&&<p className="helper">话题：{result.topics}</p>}</section>;
}

export function TaskMaterialResult({task}) {
  const result=task.sources?.material_result||task.material_result||task.sources?.work?.material_result||task.sources?.queue?.material_result;
  if(!result||typeof result!=='object')return null;
  const items=Array.isArray(result.items)?result.items:[],count=Number.isSafeInteger(result.used_count)&&result.used_count>=0?result.used_count:null;
  const selectedCount=Number.isSafeInteger(result.selected_count)&&result.selected_count>=0?result.selected_count:items.length;
  const blocked=['blocked','failed','not_found','no_materials','login_required','awaiting_input','awaiting_human'].includes(result.status);
  const awaitingAgent=result.status==='awaiting_agent';
  const adopted=result.enabled===true&&['completed','used','succeeded'].includes(result.status)&&count>0,selected=result.enabled===true&&result.status==='ready'&&selectedCount>0;
  const label=result.enabled===false?'未开启联网素材':awaitingAgent?'待当前Agent分析':result.status==='login_required'?'等待账号登录':blocked?'等待补充素材':adopted?'已采用联网画面':selected?'已选画面 · 待合成':result.status==='checking_login'?'正在检查登录':['searching','running','pending','queued'].includes(result.status)?'正在查找素材':'素材结果待确认';
  return <section className="task-material-result" aria-label="本次画面素材"><div className="task-section-heading"><h3>画面素材</h3><span className={`task-badge ${blocked||selected||awaitingAgent?'waiting':adopted?'success':'neutral'}`}>{label}</span></div>
    <p>{result.message||(result.enabled===false?'本任务沿用原来的画面参数。':awaitingAgent?'素材与音轨已保留，等待当前Agent完成分析后恢复原任务。':blocked?'没有找到合适且可采用的素材，请检查登录或补充素材后恢复原任务。':'实际采用的画面与来源以本任务记录为准。')}{adopted?` · 已采用 ${count} 段画面素材`:selected?` · 已选 ${selectedCount} 段待合成`:''}</p>
    {items.length>0&&<details className="task-material-items"><summary>查看{adopted?'实际采用':selected?'已选':''}画面与来源（{items.length}）</summary><ul>{items.map((item,index)=>{
      const source=safeTaskHref(item.source_url),preview=safeTaskHref(item.preview_url),kind={video:'视频',image:'图片',screenshot:'截图'}[item.kind]||'画面素材';
      return <li key={`${item.asset_id||index}-${index}`}>{preview&&<a href={preview} target="_blank" rel="noopener noreferrer">{item.kind==='image'||item.kind==='screenshot'?<img src={preview} alt={`${item.name||item.label||'采用画面'}缩略图`} loading="lazy"/>:<span className="task-material-preview"><FileText size={19}/>打开画面</span>}</a>}<div><strong>{item.name||item.label||`画面 ${index+1}`}</strong><small>{kind} · {item.source||'来源待确认'}</small>{source&&<a href={source} target="_blank" rel="noopener noreferrer">查看来源<ArrowUpRight size={13}/></a>}</div></li>;
    })}</ul></details>}
  </section>;
}

function useTaskSummary() {
  const [tasks,setTasks]=useState([]),[meta,setMeta]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const [syncedAt,setSyncedAt]=useState(null),items=useRef([]),cursor=useRef(0),active=useRef(null),mounted=useRef(false);
  const refresh=useCallback(async(reset=false)=>{
    if(active.current)return;
    const controller=new AbortController();active.current=controller;setLoading(true);
    try {
      const previousCursor=reset?0:cursor.current;
      const value=await taskCenterRequest(`/summary?cursor=${previousCursor}&limit=100`,{signal:controller.signal});
      const next=applyTaskSummary(items.current,value,{cursor:previousCursor,reset});
      if(!mounted.current||controller.signal.aborted)return;
      items.current=next.tasks;cursor.current=next.cursor;setTasks(next.tasks);setMeta(value);setSyncedAt(new Date().toISOString());setError('');
    }catch(e){if(mounted.current&&!controller.signal.aborted)setError(e.message||'任务状态暂时无法更新。');}
    finally {if(active.current===controller){active.current=null;if(mounted.current)setLoading(false);}}
  },[]);
  useEffect(()=>{mounted.current=true;void refresh();const timer=setInterval(()=>void refresh(),5000);return()=>{mounted.current=false;clearInterval(timer);active.current?.abort();active.current=null;};},[refresh]);
  useEffect(()=>{if(meta?.has_more){const timer=setTimeout(()=>void refresh(),0);return()=>clearTimeout(timer);}},[meta,refresh]);
  return {tasks,meta,loading,error,syncedAt,refresh};
}

export function TaskDetailContent({task,events=task.events||[],reporting=false,onReport,reportUnknown=false}) {
  const workId=task.links?.work_id||task.sources?.work?.id,projectId=task.sources?.queue?.project_id;
  const timeline=mergeTaskEvents([],events).filter(item=>item.kind!=='heartbeat');
  const commands=Array.isArray(task.commands)?task.commands:[];
  const waiting=commands.some(reportWaiting);
  const view=taskPresentation(task);
  return <div className="task-detail">
    <section className="task-detail-overview" aria-label="当前阶段与摘要"><div className="task-section-heading"><Badge status={view.status}>{view.label}</Badge><span className="helper">{task.id}</span></div>
      <p className="helper">当前阶段与摘要</p>
      <h3>{view.stage}</h3>{task.summary&&<p>{task.summary}</p>}
      <dl className="task-freshness"><div><dt>最后进展</dt><dd>{formatTaskTime(task.last_progress_at)}</dd></div><div><dt>运行心跳</dt><dd>{formatTaskTime(task.heartbeat_at)}</dd></div></dl>
      <p className="helper">{executorPresence(task)}。界面同步不代表执行者在线；阶段变化和新产物才是新的制作进展。</p>
      <QueueState task={task}/>
      <div className="task-artifact-links">{workId&&<Button href={`/projects?work=${encodeURIComponent(workId)}`}><FileText size={16}/>查看作品</Button>}
        {projectId&&<Button href={`/p/${encodeURIComponent(projectId)}`}>项目工作台<ArrowUpRight size={15}/></Button>}
        {task.links?.calendar_id&&<Button href="/calendar">查看发布日历</Button>}</div>
    </section>
    <TaskArtifacts task={task}/>
    <TaskMaterialResult task={task}/>
    <section><div className="task-section-heading"><h3>费用记录</h3><Wallet size={18}/></div><TaskBudget budget={task.budget}/><p className="helper">预留与估算不计为实际结算；尚未返回金额时保留“尚未确认”。</p></section>
    <PlatformResults task={task}/>
    <section><details className="task-history"><summary><h3>阶段时间线 · 历史记录（最新在前）</h3><Clock3 size={18}/></summary>
      <p className="helper">历史记录不代表当前仍有阻碍，当前进展以顶部的当前阶段与摘要为准。</p>
      {timeline.length?<ol className="task-timeline">{timeline.map(event=><li key={event.id}><span className="task-timeline-dot"/><div><header><strong>{event.stage||({report:'任务汇报',fact:'状态记录',note:'任务备注'}[event.kind])||'任务进展'}</strong><time>{formatTaskTime(event.created_at)}</time></header><p>{event.message||'该事件没有附带说明。'}</p>{event.facts?.status&&<small>当时状态：{taskStatusLabel(event.facts.status)}</small>}</div></li>)}</ol>:<p className="task-placeholder">尚无阶段事件记录，当前阶段以任务状态为准。</p>}
    </details></section>
    <section><h3>证据与产物</h3>{task.evidence?.length?<ul className="task-evidence">{task.evidence.map((item,index)=>{
      const href=safeTaskHref(item.ref);return <li key={`${item.label}-${index}`}><FileText size={16}/>{href?<a href={href} target="_blank" rel="noopener noreferrer">{item.label||'查看记录'}<ArrowUpRight size={14}/></a>:<span>{item.label||'任务证据'}<small>已保存引用，当前没有可打开的链接。</small></span>}</li>;
    })}</ul>:<p className="task-placeholder">尚无可展示的证据与产物。</p>}</section>
    <section><div className="task-section-heading"><h3>请求任务汇报</h3><Button loading={reporting} disabled={waiting} onClick={onReport}><Send size={15}/>{waiting?'等待汇报响应':reportUnknown?'用原编号重试请求':'请求汇报'}</Button></div>
      <p className="helper">请求会持久保存，收到实际响应后再更新。请求汇报不会暂停或重启制作。</p>
      {commands.length>0&&<ul className="task-command-list">{commands.map(command=><li key={command.id}><div><strong>{command.kind==='report_now'?commandLabel(command):'控制请求记录'}</strong><small>{formatTaskTime(command.created_at)}</small></div>{typeof command.result==='string'?<p>{command.result}</p>:typeof command.result?.summary==='string'&&<p>{command.result.summary}</p>}</li>)}</ul>}
    </section>
  </div>;
}

function TaskDetail({id,onClose,onUpdated}) {
  const [task,setTask]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[reporting,setReporting]=useState(false),[unknown,setUnknown]=useState(false);
  const [history,setHistory]=useState([]),[historyCursor,setHistoryCursor]=useState(0),[historyMore,setHistoryMore]=useState(true),[historyLoading,setHistoryLoading]=useState(false);
  const reportId=useRef(null),mounted=useRef(false),inFlight=useRef(null);
  const refresh=useCallback(async()=>{
    if(inFlight.current)return;
    const controller=new AbortController();inFlight.current=controller;
    try {const value=await taskCenterRequest(`/tasks/${encodeURIComponent(id)}`,{signal:controller.signal});
      if(!value||value.id!==id)throw new Error('任务详情返回不完整，请重新读取。');
      if(mounted.current&&!controller.signal.aborted){setTask(value);setError('');}
    }catch(e){if(mounted.current&&!controller.signal.aborted)setError(e.message||'无法读取任务详情。');}
    finally {if(inFlight.current===controller){inFlight.current=null;if(mounted.current)setLoading(false);}}
  },[id]);
  useEffect(()=>{mounted.current=true;void refresh();const timer=setInterval(()=>void refresh(),5000);return()=>{mounted.current=false;clearInterval(timer);inFlight.current?.abort();inFlight.current=null;};},[refresh]);
  async function report() {
    if(reporting)return;
    reportId.current=nextReportClientId(reportId.current,task?.commands||[],()=>crypto.randomUUID());setReporting(true);setNotice('');
    try {
      const command=await taskCenterRequest(`/tasks/${encodeURIComponent(id)}/commands`,{body:{client_id:reportId.current,kind:'report_now'}});
      if(!command?.id||command.task_id!==id)throw new Error('请求回执未确认，请保留原请求重试。');
      if(mounted.current){setUnknown(false);setNotice(commandLabel(command));setTask(current=>current?{...current,commands:[...(current.commands||[]).filter(item=>item.id!==command.id),command]}:current);void refresh();onUpdated();}
    }catch(e){if(mounted.current){setUnknown(true);setNotice('');setError(`${e.message} 再次请求会复用原编号。`);}}
    finally {if(mounted.current)setReporting(false);}
  }
  async function readHistory() {
    setHistoryLoading(true);
    try {const value=await taskCenterRequest(`/tasks/${encodeURIComponent(id)}/events?cursor=${historyCursor}&limit=50`);
      if(!Array.isArray(value.items)||!Number.isInteger(value.next_cursor))throw new Error('历史记录返回格式不正确。');
      if(mounted.current){setHistory(current=>mergeTaskEvents(current,value.items));setHistoryCursor(value.next_cursor);setHistoryMore(value.has_more===true);}
    }catch(e){if(mounted.current)setError(e.message);}finally {if(mounted.current)setHistoryLoading(false);}
  }
  const events=mergeTaskEvents(history,task?.events||[]);
  return <Dialog title={task?.title||'视频任务详情'} wide onClose={onClose} busy={reporting} footer={<><span className="helper">详情每5秒同步；更新失败时保留上次记录。</span><Button onClick={onClose}>关闭</Button><Button disabled={loading} onClick={refresh}><RefreshCw size={15}/>刷新详情</Button></>}>
    <Notice message={error} error/><Notice message={notice}/>
    {task?<><TaskDetailContent task={task} events={events} reporting={reporting} onReport={report} reportUnknown={unknown}/>
      {task.events_has_more&&historyMore&&<Button loading={historyLoading} onClick={readHistory}>补充历史时间线</Button>}</>:
      <EmptyState title={loading?'正在读取任务详情':'暂时无法读取任务'}>{loading?'正在查询后台保存的状态。':'请重新读取；当前没有把未知状态标记为成功。'}</EmptyState>}
  </Dialog>;
}

export function DailyPlanFields({draft,setDraft,accounts=[],disabled=false}) {
  const patch=(index,value)=>setDraft(current=>({...current,slots:current.slots.map((slot,i)=>i===index?{...slot,...value}:slot)}));
  function bind(index,platform,value) {patch(index,{accounts:[...draft.slots[index].accounts.filter(item=>item.platform!==platform),...(value?[{platform,account_id:Number(value)}]:[])]});}
  return <div className="daily-plan-fields"><div className="daily-plan-clock"><Field label="每天开始时间" hint="北京时间 · Asia/Shanghai"><input type="time" value={draft.start_time} disabled={disabled} onChange={event=>setDraft(current=>({...current,start_time:event.target.value}))}/></Field><p>每日三个视频槽位。方案保存与自动执行分别记录。</p></div>
    {draft.slots.map((slot,index)=><fieldset key={index} className="daily-plan-slot"><legend>第 {index+1} 条视频</legend>
      <div className="daily-plan-slot-main"><Field label="视频模板"><select value={slot.template_id} disabled={disabled} onChange={event=>patch(index,{template_id:event.target.value})}>{DAILY_TEMPLATES.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <Field label="本条费用上限（元）" hint="最多六位小数；保存方案不产生费用。"><input inputMode="decimal" value={slot.budget} disabled={disabled} placeholder="填写本条预算" onChange={event=>patch(index,{budget:event.target.value})}/></Field></div>
      <Field label="选题方向"><input value={slot.topic} maxLength={500} disabled={disabled} onChange={event=>patch(index,{topic:event.target.value})}/></Field>
      <div className="daily-plan-accounts">{TASK_PLATFORMS.map(platform=>{
        const selected=slot.accounts.find(item=>item.platform===platform.id)?.account_id||'';
        const choices=accounts.filter(item=>item.platform===platform.id);
        return <Field key={platform.id} label={`${platform.name}账号`}><select value={selected} disabled={disabled} onChange={event=>bind(index,platform.id,event.target.value)}><option value="">暂不绑定</option>{choices.map(item=><option key={item.id} value={item.id}>#{item.id} · {item.name||'未命名账号'}</option>)}{selected&&!choices.some(item=>Number(item.id)===Number(selected))&&<option value={selected}>已保存账号 #{selected}（待核对）</option>}</select></Field>;
      })}</div>
    </fieldset>)}
    <p className="helper">账号列表为本机已保存的记录，执行前仍需检查平台登录。未绑定账号的槽位可以保存为方案。</p>
  </div>;
}

function DailyPlan({onClose}) {
  const [plan,setPlan]=useState(null),[draft,setDraft]=useState(null),[accounts,setAccounts]=useState([]),[loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[accountWarning,setAccountWarning]=useState('');
  const mounted=useRef(false);
  useEffect(()=>{mounted.current=true;const controller=new AbortController();
    taskCenterRequest('/plan',{signal:controller.signal}).then(value=>{if(mounted.current){setPlan(value);setDraft(dailyPlanDraft(value));}}).catch(e=>{if(mounted.current&&!controller.signal.aborted)setError(e.message);}).finally(()=>{if(mounted.current)setLoading(false);});
    api('/api/studio/publishing').then(value=>{if(mounted.current){setAccounts(Array.isArray(value.accounts)?value.accounts:[]);if(!value.available)setAccountWarning('账号服务暂时不可读取；已保存的绑定会保留。');}}).catch(()=>{if(mounted.current)setAccountWarning('暂时无法读取账号列表；已保存的绑定会保留。');});
    return()=>{mounted.current=false;controller.abort();};
  },[]);
  async function save(event) {
    event.preventDefault();setError('');setNotice('');
    let body;try {body=dailyPlanPayload(draft);}catch(e){setError(e.message);return;}
    setSaving(true);
    try {const value=await taskCenterRequest('/plan',{body,method:'PUT'});if(mounted.current){setPlan(value);setDraft(dailyPlanDraft(value));setNotice('每日方案已保存，自动执行未启用。本次没有创建制作或发布任务。');}}
    catch(e){if(mounted.current)setError(e.status===409?'方案已被其他窗口更新，请关闭后重新打开；当前编辑内容仍保留。':e.message);}
    finally {if(mounted.current)setSaving(false);}
  }
  return <Dialog title="每日制作方案" description="保存开始时间、模板、账号与预算，后续从同一方案建立任务。" wide onClose={onClose} busy={saving}
    footer={<><Button disabled={saving} onClick={onClose}>关闭</Button><Button type="submit" form="daily-task-plan" variant="primary" loading={saving} disabled={loading||!draft}>保存未启用的方案</Button></>}>
    <div className="task-plan-status"><CalendarClock size={20}/><div><strong>自动执行未启用</strong><p className="helper">{plan?.worker_available?'当前只保存未启用的方案，不会自动开始制作。':'自动执行器尚未接通；保存方案不会自动生成视频或公开发布。'}</p></div></div>
    <Notice message={error} error/><Notice message={notice}/>{accountWarning&&<p className="task-warning" role="status">{accountWarning}</p>}
    {draft?<form id="daily-task-plan" onSubmit={save}><DailyPlanFields draft={draft} setDraft={setDraft} accounts={accounts} disabled={saving}/></form>:
      <EmptyState title={loading?'正在读取每日方案':'每日方案暂时不可读取'}>{loading?'正在查询后台保存的配置。':'请稍后重新打开；读取失败时不会覆盖已有方案。'}</EmptyState>}
  </Dialog>;
}

export function TaskCenter({search=''}) {
  const {tasks,meta,loading,error,syncedAt,refresh}=useTaskSummary();
  const [planOpen,setPlanOpen]=useState(false),[filter,setFilter]=useState('all');
  const query=new URLSearchParams(search),taskId=query.get('task'),queueJob=query.get('queue_job'),projectId=query.get('project');
  const matching=queueJob?tasks.filter(item=>item.links?.queue_job_id===queueJob):tasks;
  const shown=matching.filter(item=>{const state=taskPresentation(item).status;return filter==='all'||(filter==='active'?['planned','queued','running'].includes(state):filter==='attention'?['failed','awaiting_human','ambiguous','blocked','uncertain','awaiting_verification','waiting_publish','ready_for_review','needs_attention','source_unknown'].includes(state):['completed','fully_verified','cancelled'].includes(state));});
  const groups=taskGroups(shown);
  const counts=taskCounts(tasks);
  return <main className="workspace task-center"><Heading title="任务总览" helper="每条视频的进展、费用和平台结果，在这里汇合。"><div className="task-heading-actions"><Button onClick={()=>setPlanOpen(true)}><Settings2 size={16}/>每日方案</Button><Button disabled={loading} onClick={()=>refresh(true)}><RefreshCw size={16} className={loading?'spinner':''}/>刷新</Button></div></Heading>
    <section className="surface task-sync-bar"><span><Activity size={17}/>{loading?'正在同步任务记录':syncedAt?`界面同步于 ${formatTaskTime(syncedAt)}`:'等待读取任务记录'}</span><small>每5秒同步 · 不读取聊天上下文</small></section>
    <Notice message={error?`更新失败：${error}${syncedAt?' 当前保留上次成功读取的记录。':''}`:''} error/>
    {meta?.worker_available===false&&<p className="task-warning"><Clock3 size={16}/>任务由 Codex 按批次推进；每日定时执行尚未启用。汇报请求会在执行者读取后更新。</p>}
    <section className="task-overview" aria-label="当前任务计数">{[
      ['全部任务',counts.all],['待开始与执行',counts.active],
      ['待核验与处理',counts.waiting],['全部已核验',counts.completed],
    ].map(([label,value])=><div key={label}><span>{label}</span><strong>{meta?value:'—'}</strong></div>)}</section>
    <div className="task-filter-bar" aria-label="任务筛选">{[['all','全部'],['active','待开始与执行中'],['attention','待核验与处理'],['completed','已完成与取消']].map(([id,label])=><button key={id} type="button" aria-pressed={filter===id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{label}</button>)}</div>
    {meta?.has_more&&<p className="helper">仍有更多记录正在同步，当前计数仅包含已读取任务。</p>}
    {queueJob&&meta&&!meta.has_more&&!matching.length&&<section className="surface task-unlinked"><h2>该制作任务尚未关联任务总账</h2><p>原队列任务仍保留，不会因此重新提交制作。</p>{projectId?<Button href={`/p/${encodeURIComponent(projectId)}`}>查看原项目</Button>:<Button href="/projects">返回我的作品</Button>}</section>}
    {groups.map(group=><section className="task-batch" key={group.id}><header><div><ListTodo size={19}/><h2>{group.title}</h2></div><span>{group.tasks.length} 条任务</span></header><div className="task-card-grid">{group.tasks.map(task=><TaskCard key={task.id} task={task} onOpen={navigateTask}/>)}</div></section>)}
    {!groups.length&&!error&&(!queueJob||matching.length>0)&&<section className="surface"><EmptyState icon={ListTodo} title={!meta?'正在读取任务':tasks.length?'当前筛选没有任务':'还没有任务记录'}>{!meta?'正在查询后台保存的状态。':tasks.length?'调整筛选后查看其他任务。':'每日方案和实际执行分开记录；任务建立后才会出现在这里。'}</EmptyState></section>}
    {taskId&&<TaskDetail key={taskId} id={taskId} onClose={closeTask} onUpdated={()=>refresh()}/>}
    {planOpen&&<DailyPlan onClose={()=>setPlanOpen(false)}/>}
  </main>;
}
