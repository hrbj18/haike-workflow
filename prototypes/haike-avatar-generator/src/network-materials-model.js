export const DOWNLOAD_SESSIONS_API='/api/studio/download-sessions';
export const NETWORK_DOWNLOAD_API='/api/studio/network-download';
export const DOWNLOAD_PLATFORMS=[
  {id:'douyin',name:'抖音'},
  {id:'kuaishou',name:'快手'},
  {id:'shipinhao',name:'视频号'},
  {id:'xhs',name:'小红书'},
];
const SCOPE_STATES=new Set(['available','unconfirmed','login_required','network_error']);
export const scopeState=value=>SCOPE_STATES.has(value)?value:'unconfirmed';
export const scopeLabel=value=>({available:'可用',unconfirmed:'待确认',login_required:'需要登录',network_error:'网络异常'})[scopeState(value)];
// 八小时仅用于展示最近检查结果，不代表 Cookie 寿命，也不用于放行搜索或发布。
export const SESSION_CHECK_DISPLAY_MS=8*60*60*1000;
export function accountScopeView(status,{supported=true,saved=false,checkedAt,now=Date.now()}={}) {
  if(!supported)return {label:'仅链接下载',tone:'neutral'};
  if(status==='available') {
    const checked=typeof checkedAt==='string'?Date.parse(checkedAt):NaN,age=now-checked;
    if(!Number.isFinite(age)||age<0||age>SESSION_CHECK_DISPLAY_MS)status='unconfirmed';
  }
  return {available:{label:'最近检查正常',tone:'ready'},login_required:{label:'需要登录',tone:'danger'},network_error:{label:'检查失败',tone:'warning'},unknown:{label:'状态未知',tone:'neutral'}}[status]||{label:saved?'已保存 · 待检查':'待检查',tone:'neutral'};
}
export const platformLabel=value=>DOWNLOAD_PLATFORMS.find(item=>item.id===value)?.name||'其他平台';
const sessionTime=value=>typeof value==='string'&&Number.isFinite(new Date(value).getTime())?value:null;
const sessionNumber=value=>typeof value==='number'&&Number.isFinite(value)?value:null;
export function sessionObservability(value) {
  const source=value&&typeof value==='object'?value:{},policy=source.keepalive&&typeof source.keepalive==='object'?source.keepalive:{};
  const choices=(value,list)=>list.includes(value)?value:null;
  return {checkpoint_at:sessionTime(source.checkpoint_at),background_health_checked_at:sessionTime(source.background_health_checked_at),
    account_last_active_at:sessionTime(source.account_last_active_at),
    background_health_outcome:choices(source.background_health_outcome,['verified','login_required','unconfirmed']),
    background_health_trigger:choices(source.background_health_trigger,['keepalive','auth_recheck']),
    keepalive:{configured:typeof policy.configured==='boolean'?policy.configured:null,
      engine_running:typeof policy.engine_running==='boolean'?policy.engine_running:null,
      mode:choices(policy.mode,['keepalive','auth_recheck']),idle_hours:sessionNumber(policy.idle_hours),
      check_interval_seconds:sessionNumber(policy.check_interval_seconds),jitter_ratio:sessionNumber(policy.jitter_ratio),
      next_eligible_at:sessionTime(policy.next_eligible_at),schedule_status:choices(policy.schedule_status,['unknown','disabled','engine_stopped','no_saved_session','waiting','due'])||'unknown'}};
}

export function normalizeDownloadSessions(value) {
  if(value?.available===false)throw new Error('账号服务暂时不可用，请稍后重新读取。');
  if(!Array.isArray(value?.items))throw new Error('账号状态返回不完整，请稍后重新读取。');
  return value.items.filter(item=>Number.isSafeInteger(Number(item.id))&&Number(item.id)>0).map(item=>({
    id:Number(item.id),platform:String(item.platform||''),nickname:String(item.nickname||item.name||'未命名账号'),
    download_status:scopeState(item.download_status),publish_status:scopeState(item.publish_status),
    download_check_status:scopeState(Object.hasOwn(item,'download_check_status')?item.download_check_status:item.download_status),
    download_checked_at:sessionTime(Object.hasOwn(item,'download_checked_at')?item.download_checked_at:item.last_checked_at),
    publish_check_status:scopeState(Object.hasOwn(item,'publish_check_status')?item.publish_check_status:item.publish_status),
    selected:item.selected===true,search_supported:item.search_supported===true,
    search_status:['available','unconfirmed','login_required','network_error','unknown','unsupported'].includes(item.search_status)?item.search_status:'unknown',
    search_checked_at:sessionTime(item.search_checked_at),
    saved_at:item.saved_at||null,last_checked_at:item.last_checked_at||null,
    publish_checked_at:sessionTime(item.publish_checked_at),login_record_saved:item.login_record_saved===true,
    download_saved:item.download_saved===true||item.download_status==='stored_unverified',
    publish_saved:item.publish_saved===true||item.publish_status==='stored_unverified',
    observability:sessionObservability(item.observability),
    message:typeof item.message==='string'?item.message:'',
  }));
}

export function sourceLink(value) {
  const match=String(value||'').trim().match(/https?:\/\/[^\s<>]+/i);
  if(!match)throw new Error('请粘贴完整的视频分享链接。');
  const candidate=match[0].replace(/[，。；！？”’」』）]+$/u,'');
  let parsed;try{parsed=new URL(candidate);}catch{throw new Error('链接格式不正确，请重新复制视频分享链接。');}
  if(!['http:','https:'].includes(parsed.protocol)||parsed.username||parsed.password)throw new Error('请使用不含账号密码的视频分享链接。');
  return parsed.href;
}

export function sourcePlatform(value) {
  let host;try{host=new URL(sourceLink(value)).hostname.toLowerCase();}catch{return '';}
  const at=domain=>host===domain||host.endsWith(`.${domain}`);
  if(at('douyin.com')||at('iesdouyin.com'))return 'douyin';
  if(at('kuaishou.com'))return 'kuaishou';
  if(at('xiaohongshu.com')||at('xhslink.com'))return 'xhs';
  if(at('weixin.qq.com')||at('finder.video.qq.com'))return 'shipinhao';
  return '';
}

export function networkDownloadPayload({url,accountId,rightsConfirmed,quality='highest',clientRequestId},accounts) {
  const link=sourceLink(url),id=Number(accountId),account=accounts.find(item=>item.id===id);
  if(!account)throw new Error('请选择下载账号；没有账号时先扫码登录。');
  const platform=sourcePlatform(link);
  if(platform&&platform!==account.platform)throw new Error('分享链接与所选账号的平台不一致，请重新选择账号。');
  if(account.download_status!=='available')throw new Error('下载登录尚未确认可用，请检查登录或重新扫码。');
  if(rightsConfirmed!==true)throw new Error('请确认你有权下载并使用这份素材。');
  if(!['highest','1080p','720p'].includes(quality))throw new Error('请选择支持的下载清晰度。');
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(clientRequestId||''))throw new Error('下载任务编号不完整，请重新打开网络素材。');
  return {url:link,account_id:id,quality,rights_confirmed:true,client_request_id:clientRequestId};
}

const FINISHED_DOWNLOADS=new Set(['completed','succeeded','failed','cancelled','canceled','login_required']);
const RUNNING_DOWNLOADS=new Set(['queued','pending','running','processing','downloading','registering']);
export function downloadJob(value) {
  const job=value?.job&&typeof value.job==='object'?value.job:value;
  const id=job?.id||job?.job_id;
  if(!id)throw new Error('下载结果缺少任务编号，请先刷新任务记录，避免重复提交。');
  const status=String(job.status||'unconfirmed');
  return {id:String(id),status,message:typeof job.message==='string'?job.message:'',
    error:typeof job.error==='string'?job.error:'',result:job.result&&typeof job.result==='object'?job.result:null,
    active:RUNNING_DOWNLOADS.has(status),terminal:FINISHED_DOWNLOADS.has(status),
    completed:['completed','succeeded'].includes(status)};
}
export const downloadStatusLabel=value=>({submitting:'正在提交下载',queued:'等待下载',pending:'等待下载',running:'正在下载',processing:'正在处理',downloading:'正在下载',registering:'正在加入素材库',completed:'下载完成',succeeded:'下载完成',failed:'下载失败',cancelled:'已取消',canceled:'已取消',login_required:'请重新登录',unconfirmed:'结果待确认',submission_unknown:'结果待核对'})[value]||'结果待确认';
export function registeredMediaCount(job) {
  const result=job?.result;
  if(Number.isSafeInteger(result?.media_count)&&result.media_count>=0)return result.media_count;
  if(Array.isArray(result?.items))return result.items.length;
  if(Array.isArray(result?.media_ids))return result.media_ids.length;
  if(Number.isSafeInteger(result?.registered)&&result.registered>=0)return result.registered;
  return null;
}
export function savedNetworkJob(search='') {return new URLSearchParams(search).get('network_job')||'';}
export function networkJobUrl(location,id) {
  const url=new URL(location.href);if(id)url.searchParams.set('network_job',id);else url.searchParams.delete('network_job');
  return `${url.pathname}${url.search}${url.hash}`;
}

export function loginPreviewImage(task,revision=0) {
  if(!['opening','waiting','verification'].includes(task?.status))return '';
  if(!/^[0-9a-f]{32}$/i.test(task?.task_id||''))return '';
  const expected=`${DOWNLOAD_SESSIONS_API}/login/${task.task_id}/preview.png`;
  if(task.preview_url!==expected)return '';
  return `${expected}?_preview=${Number.isSafeInteger(revision)&&revision>=0?revision:0}`;
}
export const LOGIN_PREVIEW_RETRY_LIMIT=20;
export function loginPreviewRetryDelay(task,{failures=0,waitingForImage=false}={}) {
  if(!loginPreviewImage(task)||waitingForImage||!Number.isSafeInteger(failures)||failures<0||failures>=LOGIN_PREVIEW_RETRY_LIMIT)return null;
  return 3000;
}
