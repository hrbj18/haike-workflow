export const TASK_CENTER_API = '/api/task-center';
export const TASK_PLATFORMS = [{id:'douyin',name:'抖音'},{id:'kuaishou',name:'快手'},{id:'shipinhao',name:'视频号'}];
export const DAILY_TEMPLATES = [
  {id:'avatar-safe-circle-v1',name:'模板1 · 圆框口播'},
  {id:'avatar-full-width-v2',name:'模板2 · 全宽讲解'},
  {id:'avatar-template3-card-3x4-v001',name:'模板3 · 卡片讲解'},
  {id:'avatar-deepblue-n1-v1',name:'深蓝视窗 N1'},
];
const STATUS = {
  planned:'待开始',queued:'排队中',pending:'等待中',running:'执行中',processing:'执行中',
  awaiting_human:'等待处理',awaiting_input:'等待补充',ambiguous:'结果待核对',blocked:'遇到阻碍',
  uncertain:'结果待核对',
  completed:'制作完成',succeeded:'已完成',ready:'已就绪',review_ready:'待审成片已就绪',
  failed:'执行失败',error:'发生错误',cancelled:'已取消',canceled:'已取消',paused:'已暂停',skipped:'已跳过',
  awaiting_verification:'已提交 · 待核验',ready_for_review:'成片已完成 · 待检查',waiting_publish:'等待发布',
  needs_attention:'需要处理',fully_verified:'全部已核验',source_unknown:'状态暂不可读',
};
export function taskStatusLabel(value) {return STATUS[value] || '状态待确认';}
export function taskTone(value) {
  if(['failed','error','blocked','needs_attention'].includes(value))return 'error';
  if(['completed','succeeded','ready','review_ready','fully_verified'].includes(value))return 'success';
  if(['running','processing'].includes(value))return 'active';
  if(['awaiting_human','awaiting_input','ambiguous','uncertain','awaiting_verification','ready_for_review','waiting_publish','source_unknown'].includes(value))return 'waiting';
  return 'neutral';
}
export function productionKindLabel(kind) {
  return {studio_graphic:'图文视频',studio_avatar:'数字人口播',studio_motion:'动效口播',review_preview:'审核预览',
    avatar_review_preview:'数字人审核预览',full_preview:'全片合成',material_selection:'素材选择',
    published_remix:'成片二剪',material_commentary:'素材解说',commentary_presenter:'解说口播',
    commentary_presenter_consumer_v1:'解说口播'}[kind] || '制作任务';
}
export function productionJobs(value) {
  if(!Array.isArray(value?.tasks))throw new Error('制作队列返回格式不正确，暂时保留上次记录。');
  return value.tasks;
}
export function formatTaskTime(value) {
  if(!value)return '尚未记录';
  const date=new Date(value);
  if(!Number.isFinite(date.getTime()))return '时间待确认';
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);
}
function microsNumber(value) {
  if(value===null||value===undefined||value==='')return null;
  if(typeof value!=='number'&&!(typeof value==='string'&&/^\d+$/.test(value)))return null;
  const number=Number(value);
  return Number.isSafeInteger(number)&&number>=0?number:null;
}
export function formatTaskMoney(value) {
  const number=microsNumber(value);
  return number===null?'尚未确认':`¥${(number/1000000).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:6})}`;
}
export function microsInput(value) {
  const number=microsNumber(value);
  return number===null?'':(number/1000000).toFixed(6).replace(/\.?0+$/,'');
}
export function parseBudget(value) {
  if(!/^\d+(?:\.\d{1,6})?$/.test(String(value)))throw new Error('预算需为非负金额，最多保留六位小数。');
  const [whole,fraction='']=String(value).split('.');
  const amount=BigInt(whole)*1000000n+BigInt(fraction.padEnd(6,'0'));
  if(amount>BigInt(Number.MAX_SAFE_INTEGER))throw new Error('预算金额过大。');
  return Number(amount);
}
export function safeTaskHref(value) {
  if(typeof value!=='string'||!value||/[\u0000-\u0020\\]/.test(value))return null;
  if(value.startsWith('/'))return /^\/(?:api\/(?:works|task-center)\/|api\/studio\/(?:assets|materials)\/|p\/|projects(?:[?#]|$)|calendar(?:[?#]|$)|material-library(?:[?#]|$))/.test(value)?value:null;
  try {const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
export function taskCenterHref({id,queueJob,projectId}={}) {
  const query=new URLSearchParams();
  if(id)query.set('task',id);
  if(queueJob)query.set('queue_job',queueJob);
  if(projectId)query.set('project',projectId);
  return `/task-center${query.size?'?'+query:''}`;
}
export function mergeTaskChanges(previous,changes) {
  if(!Array.isArray(changes))throw new Error('任务状态返回格式不正确，请重新读取。');
  const tasks=new Map(previous.map(item=>[item.id,item]));
  for(const item of changes) {
    if(!item||typeof item.id!=='string'||!Number.isInteger(item.revision)||item.revision<0)throw new Error('任务状态缺少有效版本，请重新读取。');
    if(!tasks.has(item.id)||tasks.get(item.id).revision<=item.revision)tasks.set(item.id,item);
  }
  return [...tasks.values()].sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||''))||a.id.localeCompare(b.id));
}
export function mergeTaskEvents(previous=[],changes=[]) {
  return [...new Map([...previous,...changes].map(item=>[item.id,item])).values()].sort((a,b)=>b.id-a.id);
}
export function taskGroups(tasks) {
  const groups=new Map();
  for(const task of tasks) {
    const id=task.batch_id||'independent';
    if(!groups.has(id))groups.set(id,{id,title:task.batch_id?`批次 ${task.batch_id}`:'独立任务',tasks:[]});
    groups.get(id).tasks.push(task);
  }
  return [...groups.values()];
}
export function applyTaskSummary(previous,value,{cursor=0,reset=false}={}) {
  if(!Number.isSafeInteger(value?.next_cursor)||value.next_cursor<cursor||typeof value.has_more!=='boolean'
    ||(value.has_more&&value.next_cursor===cursor))throw new Error('任务记录版本已变化，请点击刷新重新读取。');
  return {tasks:mergeTaskChanges(reset?[]:previous,value.changes),cursor:value.next_cursor};
}
export function reportWaiting(command) {return command?.kind==='report_now'&&command.status==='requested';}
export function nextReportClientId(previous,commands,createId) {
  const existing=commands.find(item=>item.client_id===previous);
  return previous&&(!existing||reportWaiting(existing))?previous:createId();
}
export function commandLabel(command) {
  return {requested:'请求已接收，等待响应',acknowledged:'汇报已响应',running:'正在整理汇报',
    completed:'汇报已完成',succeeded:'汇报已完成',failed:'汇报失败',rejected:'请求未获执行',cancelled:'请求已取消'}[command?.status]||'请求状态待确认';
}
export function publicationRows(task) {
  const attempts=[...(Array.isArray(task?.sources?.work?.attempts)?task.sources.work.attempts:[]),
    ...(Array.isArray(task?.sources?.calendar?.attempts)?task.sources.calendar.attempts:[])];
  const expected=task?.expected_targets?.length?task.expected_targets:TASK_PLATFORMS;
  return expected.map(target=>{
    const platform=TASK_PLATFORMS.find(p=>p.id===(target.platform||target.id));
    const matches=attempts.filter(item=>item.platform===platform.id&&(!target.account_id||item.account_id===target.account_id));
    const row=matches.sort((a,b)=>String(a.synced_at||a.at||'').localeCompare(String(b.synced_at||b.at||''))).at(-1);
    const unavailable=task?.sources?.work?.availability==='unavailable'||task?.sources?.calendar?.availability==='unavailable';
    if(!row)return {platform:platform.id,name:platform.name,status:unavailable?'unavailable':'not_recorded',label:unavailable?'发布状态暂不可读':'尚无发布记录',account_id:target.account_id||null,error:'',href:null};
    let label={pending:'等待提交',scheduled:'已排期',running:'发布中',publishing:'发布中',failed:'发布失败',
      error:'发生错误',uncertain:'结果待核对',canceled:'已取消',cancelled:'已取消'}[row.status]||'平台状态待确认';
    if(['done','completed','published'].includes(row.status))label=row.public_visible===true?'已核验公开可见':'已提交，公开状态待核验';
    if(['done','completed','published'].includes(row.status)&&row.public_visible!==true&&row.acceptance_status==='verified'&&row.identity_verified===true)label='已提交并核验';
    if(row.status==='pending'&&row.next_allowed_at)label=`等待发布间隔，最早 ${formatTaskTime(row.next_allowed_at)}`;
    if(row.status==='blocked')label='发布受阻，保留原任务';
    return {...row,name:platform.name,label,href:safeTaskHref(row.work_url||row.result_url)};
  });
}

export function taskPresentation(task) {
  const queue=task.sources?.queue,rows=publicationRows(task);
  let status=task.status,stage=task.stage||'尚未记录';
  const unavailable=[queue,task.sources?.work,task.sources?.calendar].some(s=>['unavailable','missing'].includes(s?.availability));
  if(unavailable){status='source_unknown';stage='来源状态暂不可读，保留上次记录';}
  else if(rows.some(r=>['failed','error','blocked','uncertain','submission_unknown'].includes(r.status))){status='needs_attention';stage='部分平台需要处理，其他平台结果分别保留';}
  else if(queue?.status==='failed'){status='needs_attention';stage=queue.stage||'制作失败，恢复原任务';}
  else if(rows.length&&rows.every(r=>['done','completed','published'].includes(r.status))){
    const verified=rows.every(r=>r.acceptance_status==='verified'&&r.identity_verified===true);
    status=verified?'fully_verified':'awaiting_verification';stage=verified?'全部目标平台已提交并核验':'全部目标平台已提交，等待最终核验';
  }else if(rows.some(r=>['publishing','running','submitting'].includes(r.status))){status='running';stage='正在提交平台，按原任务核对';}
  else if(rows.some(r=>['pending','scheduled'].includes(r.status))){status='waiting_publish';stage='等待原发布任务执行';}
  else if(['queued','running'].includes(queue?.status)){status=queue.status;stage=queue.stage||stage;}
  else if(queue?.status==='completed'&&!['cancelled','canceled','paused','uncertain','ambiguous','awaiting_human','blocked'].includes(task.status)){status='ready_for_review';stage='成片已完成，等待质量检查或发布';}
  return {status,stage,label:taskStatusLabel(status)};
}

export function taskCounts(tasks) {
  const states=tasks.map(t=>taskPresentation(t).status);
  return {all:tasks.length,active:states.filter(s=>['running','processing','queued','planned'].includes(s)).length,
    waiting:states.filter(s=>['waiting_publish','awaiting_verification','ready_for_review','source_unknown','awaiting_human','needs_attention','ambiguous','blocked','failed','uncertain'].includes(s)).length,
    completed:states.filter(s=>['fully_verified','completed','succeeded'].includes(s)).length};
}

export function executorPresence(task,now=Date.now()) {
  const stamp=Date.parse(task.heartbeat_at),age=now-stamp;
  return Number.isFinite(stamp)&&age>=0&&age<=120000?'最近2分钟收到执行者心跳':'执行者在线状态未确认';
}
export function dailyPlanDraft(plan) {
  const slots=Array.isArray(plan?.slots)&&plan.slots.length?plan.slots:DAILY_TEMPLATES.slice(0,3).map(item=>({template_id:item.id,accounts:[],topic:'最新科技新闻',budget_limit_micros:null}));
  return {revision:Number.isInteger(plan?.revision)?plan.revision:0,start_time:plan?.start_time||'02:00',
    slots:slots.map(slot=>({...slot,accounts:Array.isArray(slot.accounts)?slot.accounts.map(item=>({...item})):[],budget:microsInput(slot.budget_limit_micros)}))};
}
export function dailyPlanPayload(draft) {
  if(!Number.isInteger(draft.revision)||draft.revision<0)throw new Error('请先重新读取每日方案。');
  if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(draft.start_time))throw new Error('请选择有效的每日开始时间。');
  if(!Array.isArray(draft.slots)||draft.slots.length!==3)throw new Error('每日方案需要三个视频槽位。');
  return {expected_revision:draft.revision,enabled:false,timezone:'Asia/Shanghai',start_time:draft.start_time,
    slots:draft.slots.map((slot,index)=>{
      if(!DAILY_TEMPLATES.some(item=>item.id===slot.template_id))throw new Error(`第${index+1}条的模板需要重新选择。`);
      const topic=String(slot.topic||'').trim();
      if(!topic||topic.length>500)throw new Error(`第${index+1}条选题方向需为1至500字。`);
      const accounts=slot.accounts.filter(item=>item.account_id!==''&&item.account_id!=null).map(item=>({platform:item.platform,account_id:Number(item.account_id)}));
      if(accounts.some(item=>!TASK_PLATFORMS.some(p=>p.id===item.platform)||!Number.isSafeInteger(item.account_id)||item.account_id<1)
        ||new Set(accounts.map(item=>item.platform)).size!==accounts.length)throw new Error(`第${index+1}条的平台账号绑定无效。`);
      return {template_id:slot.template_id,topic,accounts,budget_limit_micros:parseBudget(slot.budget)};
    })};
}
export async function taskCenterRequest(path,{body,method='POST',signal,fetchImpl=fetch}={}) {
  const response=await fetchImpl(`${TASK_CENTER_API}${path}`,{signal,...(body===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  let value;
  try {value=await response.json();}catch{throw new Error('任务服务没有返回有效状态，请稍后重新读取。');}
  if(!response.ok)throw Object.assign(new Error(typeof value?.detail==='string'?value.detail:'任务操作未完成，请重新读取后再试。'),{status:response.status});
  return value;
}
