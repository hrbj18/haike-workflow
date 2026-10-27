import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Download,ExternalLink,LogIn,RefreshCw,UserRound} from 'lucide-react';
import {api} from './studio-api.js';
import {Button,Dialog,EmptyState,Field,Notice} from './ui.jsx';
import {DOWNLOAD_PLATFORMS,DOWNLOAD_SESSIONS_API,LOGIN_PREVIEW_RETRY_LIMIT,NETWORK_DOWNLOAD_API,accountScopeView,downloadJob,downloadStatusLabel,loginPreviewImage,loginPreviewRetryDelay,networkDownloadPayload,networkJobUrl,normalizeDownloadSessions,platformLabel,registeredMediaCount,savedNetworkJob,scopeLabel,sessionObservability,sourcePlatform} from './network-materials-model.js';
import './network-materials.css';

const loginFinished=status=>['done','confirmed','completed','succeeded'].includes(status);
const loginFailed=status=>['error','expired','failed','cancelled','canceled'].includes(status);
const loginLabel=status=>({opening:'正在打开浏览器',waiting:'等待扫码登录',verification:'请在浏览器完成验证',done:'登录流程已完成',confirmed:'登录流程已完成',completed:'登录流程已完成',error:'登录未完成',expired:'登录已超时',failed:'登录未完成'})[status]||'正在等待登录结果';
const timestamp=value=>{if(!value)return '尚无记录';const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'尚无记录';};
const scopeBadge=(label,status,saved,checkedAt)=>{const view=accountScopeView(status,{saved,checkedAt});return <span className={`download-scope ${{ready:'available',danger:'login_required',warning:'network_error'}[view.tone]||'unconfirmed'}`}><span>{label}</span><strong>{view.label}</strong></span>;};

export function SessionMaintenance({item}) {
  const data=sessionObservability(item.observability),policy=data.keepalive;
  const outcome=data.background_health_checked_at?{verified:'后台检查通过',login_required:'平台要求重新登录',unconfirmed:'未能确认，待复查'}[data.background_health_outcome]:null;
  const seconds=policy.check_interval_seconds,interval=seconds>0?(seconds%60===0?`${seconds/60}分钟`:`${seconds}秒`):null;
  const next=policy.schedule_status==='disabled'?'后台检查已关闭':policy.schedule_status==='engine_stopped'?'后台引擎未运行':policy.schedule_status==='no_saved_session'?'尚无可复用登录记录':
    policy.schedule_status==='due'?'已到检查窗口，等待后台调度':policy.schedule_status==='waiting'&&policy.next_eligible_at?timestamp(policy.next_eligible_at):'尚无可计算的计划';
  return <section className="download-maintenance" aria-label="登录维护记录">
    <div className="download-maintenance-heading"><strong>登录维护</strong><span>{item.login_record_saved?'本机登录记录已保存':'登录记录保存情况待确认'}</span></div>
    <dl className="download-account-times"><div><dt>会话检查点</dt><dd>{timestamp(data.checkpoint_at)}</dd></div>
      <div><dt>最近后台检查</dt><dd>{timestamp(data.background_health_checked_at)}{outcome&&<small>{outcome}</small>}</dd></div>
      <div><dt>最近账号活跃</dt><dd>{timestamp(data.account_last_active_at)}</dd></div>
      <div><dt>最早检查窗口</dt><dd>{next}</dd></div></dl>
    {interval&&<p className="helper">当前配置：{policy.mode==='auth_recheck'?`登录失效复检间隔${interval}。`:`后台每${interval}检查一次调度${policy.idle_hours!==null&&policy.idle_hours>0?`，闲置${policy.idle_hours}小时后可检查`:''}${policy.jitter_ratio!==null&&policy.jitter_ratio>0?`，最多${Math.round(Math.min(1,policy.jitter_ratio)*100)}%错峰`:''}。`}</p>}
    <p className="helper">检查窗口可能因任务占用或风控延后；保存会话不代表登录已验证，也不能延长平台有效期。</p>
  </section>;
}

export function DownloadSessionsList({items=[],loading=false,loadError=false,busy=false,onRetry,onCheck,onLogin,onSelect}) {
  if(loadError)return <EmptyState title="暂时无法读取账号状态" action={<Button onClick={onRetry}><RefreshCw size={16}/>重新读取</Button>}>连接恢复后再检查，当前无法确认登录是否可用。</EmptyState>;
  if(loading&&!items.length)return <p className="helper" role="status">正在读取账号与登录状态…</p>;
  if(!items.length)return <EmptyState icon={UserRound} title="还没有平台账号">选择下方平台并扫码登录，登录记录保存在这台电脑。</EmptyState>;
  return <div className="download-accounts">{items.map(item=>{
    const downloadStatus=item.download_check_status??item.download_status,publishStatus=item.publish_check_status??item.publish_status,
      downloadCheckedAt=Object.hasOwn(item,'download_checked_at')?item.download_checked_at:item.last_checked_at;
    const pending=[accountScopeView(downloadStatus,{checkedAt:downloadCheckedAt}),accountScopeView(publishStatus,{checkedAt:item.publish_checked_at})].some(view=>view.tone==='neutral');
    return <article className="download-account" key={item.id}>
    <header><span className="download-platform">{platformLabel(item.platform)}</span><h3>{item.nickname||item.name||'未命名账号'}</h3></header>
    <div className="download-scope-row">{item.search_supported&&scopeBadge('素材搜索',item.search_status,item.download_saved,item.search_checked_at)}{scopeBadge('素材下载',downloadStatus,item.download_saved,downloadCheckedAt)}{scopeBadge('视频发布',publishStatus,item.publish_saved,item.publish_checked_at)}</div>
    {item.search_supported===false&&<p className="helper">当前支持分享链接下载，关键词素材搜索尚未接入。</p>}
    {pending&&<p className="helper">待确认不等于已退出登录。检查证据需要更新时，也会回到待确认；请先检查登录，平台要求时再扫码。</p>}
    <p className="helper">状态显示最近8小时内的检查结果；下载、搜索和发布前仍需自动验证登录。</p>
    <dl className="download-account-times"><div><dt>下载凭据保存</dt><dd>{timestamp(item.saved_at)}</dd></div><div><dt>下载登录检查</dt><dd>{timestamp(downloadCheckedAt)}</dd></div>{item.search_supported&&<div><dt>素材搜索检查</dt><dd>{timestamp(item.search_checked_at)}</dd></div>}<div><dt>最近发布登录检查</dt><dd>{timestamp(item.publish_checked_at)}</dd></div></dl>
    {item.message&&<p className="helper">{item.message}</p>}
    <SessionMaintenance item={item}/>
    <footer><Button disabled={busy||loading} onClick={()=>onCheck(item.id)}><RefreshCw size={15}/>检查登录</Button><Button disabled={busy} onClick={()=>onLogin(item.id)}><ExternalLink size={15}/>打开浏览器登录</Button><Button variant="text" disabled={busy||loading||item.download_status!=='available'} onClick={()=>onSelect(item)}>用于素材下载</Button></footer>
  </article>;})}</div>;
}

export function NetworkDownloadJob({job,busy=false,onRead,onAnother}) {
  if(!job)return null;
  const count=registeredMediaCount(job);
  return <section className="network-download-job" aria-label="网络素材下载任务" role="status"><div><strong>{downloadStatusLabel(job.status)}</strong><span className="helper">任务编号：{job.id}</span></div>
    {job.message&&<p>{job.message}</p>}{job.error&&<p className="field-error">{job.error}</p>}
    {job.completed&&<p>{count===null?'下载已完成，素材库登记结果待确认。':count>0?`已将 ${count} 份素材加入素材库。`:'下载任务已完成，暂未登记新素材。'}</p>}
    {!job.terminal&&!job.active&&<p className="helper">已保留原任务编号，请查询原任务；不要重复提交。</p>}
    <div className="network-job-actions"><Button disabled={busy} onClick={onRead}><RefreshCw size={15}/>查询原任务</Button>{job.terminal&&<Button disabled={busy} onClick={onAnother}>下载另一条</Button>}</div>
  </section>;
}

export function LoginPagePreview({task,onRefreshTask}) {
  const [revision,setRevision]=useState(0),[imageError,setImageError]=useState(false),[loaded,setLoaded]=useState(false);
  const [failures,setFailures]=useState(0),[waitingForImage,setWaitingForImage]=useState(true);
  const preview=useRef(null);
  const pending=['opening','waiting','verification'].includes(task?.status),source=loginPreviewImage(task,revision);
  const retryDelay=loginPreviewRetryDelay(task,{failures,waitingForImage});
  useEffect(()=>{setImageError(false);setLoaded(false);setFailures(0);setWaitingForImage(true);setRevision(0);preview.current?.scrollIntoView({block:'nearest'});},[task?.task_id,task?.preview_url]);
  useEffect(()=>{if(retryDelay===null)return;const timer=setTimeout(()=>{setImageError(false);setWaitingForImage(true);setRevision(current=>current+1);},retryDelay);return()=>clearTimeout(timer);},[source,retryDelay]);
  if(!pending)return null;
  const retry=()=>{setImageError(false);setLoaded(false);setFailures(0);setWaitingForImage(true);setRevision(current=>current+1);onRefreshTask?.();};
  return <section ref={preview} className="network-login-preview" aria-label="平台登录页预览"><header><div><h4>{task?.status==='verification'?'完成平台验证':'扫码登录'}</h4><p className="helper">这是当前登录任务的实际页面，预览会定时更新。</p></div><Button onClick={retry}><RefreshCw size={15}/>重试预览</Button></header>
    {(!source||imageError)&&<p className="network-preview-unavailable" role={failures>=LOGIN_PREVIEW_RETRY_LIMIT?'alert':'status'}>{imageError&&failures<LOGIN_PREVIEW_RETRY_LIMIT?`登录页仍在准备，3秒后自动重试（${failures}/${LOGIN_PREVIEW_RETRY_LIMIT}）。`:failures>=LOGIN_PREVIEW_RETRY_LIMIT?'登录页预览暂时无法读取，已暂停自动重试，请点击“重试预览”。':'登录页预览尚未就绪，请稍后重试。'}也可以在已打开的项目浏览器中扫码。</p>}
    {source&&!imageError&&<div className="network-login-preview-frame">{!loaded&&<p className="helper" role="status">正在读取登录页预览…</p>}<a href={source} target="_blank" rel="noopener noreferrer" aria-label="查看登录页原图"><img src={source} alt={task?.status==='verification'?'当前平台验证页面':'当前平台登录页面，请使用对应平台手机扫码'} onLoad={()=>{setLoaded(true);setImageError(false);setFailures(0);setWaitingForImage(false);}} onError={()=>{setImageError(true);setLoaded(false);setFailures(current=>current+1);setWaitingForImage(false);}} referrerPolicy="no-referrer"/></a></div>}
    {source&&!imageError&&<p className="helper">预览最大宽度为500像素；点击图片可查看原图。扫码成功后会自动收起。</p>}
  </section>;
}

export function NetworkMaterials({onImported,initialPanel='',initialPlatform='douyin',hideActions=false,onClose}) {
  const initialId=typeof window==='undefined'?'':savedNetworkJob(window.location.search);
  const [panel,setPanel]=useState(initialPanel||(initialId?'download':'')),[accounts,setAccounts]=useState([]),[loading,setLoading]=useState(false),[loadError,setLoadError]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[url,setUrl]=useState(''),[accountId,setAccountId]=useState(''),[quality,setQuality]=useState('highest'),[rights,setRights]=useState(false);
  const [platform,setPlatform]=useState(initialPlatform),[login,setLogin]=useState(null),[job,setJob]=useState(initialId?downloadJob({id:initialId,status:'unconfirmed'}):null);
  const live=useRef(true),accountSequence=useRef(0),actionLock=useRef(false),jobReading=useRef(false),reportedJob=useRef('');
  useEffect(()=>{live.current=true;return()=>{live.current=false;accountSequence.current++;};},[]);
  async function loadAccounts() {
    const sequence=++accountSequence.current;setLoading(true);setLoadError(false);setError('');
    try{const value=normalizeDownloadSessions(await api(DOWNLOAD_SESSIONS_API));if(live.current&&sequence===accountSequence.current){setAccounts(value);window.dispatchEvent(new Event('haike:sessions-changed'));}}
    catch(e){if(live.current&&sequence===accountSequence.current){setLoadError(true);setError(e.message);}}
    finally{if(live.current&&sequence===accountSequence.current)setLoading(false);}
  }
  useEffect(()=>{if(panel)loadAccounts();},[panel]);
  const rememberJob=id=>window.history.replaceState(window.history.state,'',networkJobUrl(window.location,id));
  function acceptJob(value) {
    const next=downloadJob(value);setJob(next);rememberJob(next.id);
    if(next.completed&&reportedJob.current!==next.id){reportedJob.current=next.id;onImported?.(next);}
    return next;
  }
  async function readJob(id=job?.id) {
    if(!id||jobReading.current)return;jobReading.current=true;
    try{const value=await api(`${NETWORK_DOWNLOAD_API}/${encodeURIComponent(id)}`);if(live.current){acceptJob(value);setError('');}}
    catch(e){if(live.current){setJob(current=>current?.id===id?{...current,status:'submission_unknown',active:false,terminal:false,completed:false}:current);setError(`${e.message} 已保留原任务，请稍后查询。`);}}
    finally{jobReading.current=false;}
  }
  useEffect(()=>{if(panel==='download'&&job?.id&&!actionLock.current)readJob(job.id);},[panel,job?.id]);
  useEffect(()=>{if(!job?.active)return;const timer=setTimeout(()=>readJob(job.id),2500);return()=>clearTimeout(timer);},[job]);
  useEffect(()=>{
    if(!login?.task_id||login.poll_error||loginFinished(login.status)||loginFailed(login.status))return;
    let cancelled=false;const timer=setTimeout(async()=>{try{const value=await api(`${DOWNLOAD_SESSIONS_API}/login/${encodeURIComponent(login.task_id)}`);if(cancelled||!live.current)return;setLogin({...value,task_id:login.task_id});if(loginFinished(value.status)){setNotice('登录流程已完成，请检查下载与发布两项状态。');loadAccounts();}else if(loginFailed(value.status))setError(value.message||value.hint||'登录未完成，请重新打开登录。');}catch(e){if(!cancelled&&live.current){setLogin(current=>({...current,poll_error:true}));setError(`${e.message} 登录窗口可继续使用，请手动查询登录结果。`);}}},2500);
    return()=>{cancelled=true;clearTimeout(timer);};
  },[login]);
  async function task(action) {if(actionLock.current)return;actionLock.current=true;setBusy(true);setError('');setNotice('');try{await action();}catch(e){if(live.current)setError(e.message);}finally{actionLock.current=false;if(live.current)setBusy(false);}}
  function open(next) {setError('');setNotice('');setPanel(next);}
  function close(){setPanel('');onClose?.();}
  async function checkAccount(id) {await task(async()=>{await api(`${DOWNLOAD_SESSIONS_API}/${encodeURIComponent(id)}/check`,{});await loadAccounts();setNotice('已检查登录，请查看下载与发布各自的状态。');});}
  async function openLogin(id) {await task(async()=>{const value=await api(`${DOWNLOAD_SESSIONS_API}/${encodeURIComponent(id)}/open-login`,{});if(value.task_id)setLogin(value);setNotice('已请求打开账号浏览器，请完成扫码或验证，然后检查登录。');});}
  async function selectAccount(item) {await task(async()=>{await api(`${DOWNLOAD_SESSIONS_API}/${encodeURIComponent(item.id)}/select`,{});setAccountId(String(item.id));await loadAccounts();setNotice(`已将“${item.nickname}”用于素材下载。`);});}
  async function startLogin() {await task(async()=>{const value=await api(`${DOWNLOAD_SESSIONS_API}/login`,{platform});if(!value.task_id)throw new Error('登录请求缺少任务编号，请检查是否已打开登录窗口。');setLogin(value);setNotice('登录请求已创建，请在项目浏览器中扫码。');});}
  async function submit(event) {event.preventDefault();await task(async()=>{
    if(job&&!canRetryJob)throw new Error('请先查询原任务；已完成的任务可选择“下载另一条”。');
    const id=canRetryJob?job.id:window.crypto.randomUUID();
    const body=networkDownloadPayload({url,accountId,quality,rightsConfirmed:rights,clientRequestId:id},accounts);
    acceptJob({id,status:'submitting'});
    try{const value=await api(NETWORK_DOWNLOAD_API,body);acceptJob(value);}catch(e){acceptJob({id,status:'submission_unknown'});throw new Error(`${e.message} 已保留原任务编号，请先查询；需要恢复提交时继续使用此编号。`);}
  });}
  function another() {setJob(null);rememberJob('');setRights(false);setError('');setNotice('');}
  const linkedPlatform=sourcePlatform(url),choices=accounts.filter(item=>!linkedPlatform||item.platform===linkedPlatform),selected=accounts.find(item=>String(item.id)===accountId);
  const loginPending=login&&!loginFinished(login.status)&&!loginFailed(login.status),canRetryJob=!!job&&!job.active&&!job.terminal&&['submission_unknown','unconfirmed'].includes(job.status),downloadBlocked=!!job&&!canRetryJob;
  return <>{!hideActions&&<div className="network-material-actions"><Button onClick={()=>open('accounts')}><UserRound size={17}/>账号与下载登录</Button><Button onClick={()=>open('download')}><Download size={17}/>网络素材</Button></div>}
    {panel==='download'&&<Dialog title="网络素材" description="粘贴视频分享链接，使用本机平台登录下载并加入素材库。" busy={busy} onClose={close} footer={<><Button disabled={busy} onClick={close}>关闭</Button><Button form="network-material-download" type="submit" variant="primary" loading={busy} disabled={loading||loadError||downloadBlocked||!url.trim()||!rights||selected?.download_status!=='available'}><Download size={16}/>{canRetryJob?'用原任务编号重试提交':'下载并加入素材库'}</Button></>}>
      <Notice message={error} error/><Notice message={notice}/><form id="network-material-download" className="studio-form network-material-form" onSubmit={submit}><Field label="视频分享链接" hint="可以粘贴分享文案中的完整链接。"><textarea autoFocus rows={3} value={url} maxLength={4000} disabled={busy||downloadBlocked} placeholder="粘贴抖音、快手等平台的视频分享链接" onChange={event=>setUrl(event.target.value)}/></Field>
      <Field label="下载账号" hint={loadError?'账号状态读取失败，请重新读取后选择。':linkedPlatform?`已识别为${platformLabel(linkedPlatform)}链接，只显示同平台账号。`:'选择已确认下载登录可用的平台账号。'}><select value={accountId} disabled={busy||loading||downloadBlocked||loadError} onChange={event=>setAccountId(event.target.value)}><option value="">{loading?'正在读取账号…':'请选择下载账号'}</option>{choices.map(item=><option key={item.id} value={item.id}>{platformLabel(item.platform)} · {item.nickname} · {scopeLabel(item.download_status)}</option>)}</select></Field>
      <div className="network-account-options"><Button disabled={busy} onClick={()=>open('accounts')}><LogIn size={16}/>管理登录</Button><Button disabled={busy||loading} onClick={loadAccounts}><RefreshCw size={15}/>刷新账号</Button>{selected&&selected.download_status!=='available'&&<Button disabled={busy||downloadBlocked} onClick={()=>checkAccount(selected.id)}>检查所选账号</Button>}</div>
      {!loading&&!loadError&&!choices.length&&<p className="helper">{linkedPlatform?`还没有${platformLabel(linkedPlatform)}账号。`:'还没有平台账号。'}点击“管理登录”添加账号并扫码。</p>}
      <Field label="下载清晰度"><select value={quality} disabled={busy||downloadBlocked} onChange={event=>setQuality(event.target.value)}><option value="highest">优先最高画质</option><option value="1080p">最高 1080p</option><option value="720p">最高 720p</option></select></Field><label className="checkbox-row"><input type="checkbox" checked={rights} disabled={busy||downloadBlocked} onChange={event=>setRights(event.target.checked)}/>我有权下载并使用这份素材</label></form>
      {canRetryJob&&<p className="helper">先查询原任务。若需要恢复提交，请填写原链接、原账号和原清晰度，将继续使用同一任务编号。</p>}<NetworkDownloadJob job={job} busy={busy} onRead={()=>readJob()} onAnother={another}/>
    </Dialog>}
    {panel==='accounts'&&<Dialog title="账号与下载登录" description="在项目浏览器中扫码登录；素材搜索、下载和视频发布分别检查。" wide busy={busy} onClose={close} footer={<>{!hideActions&&<Button disabled={busy} onClick={()=>open('download')}><ArrowLeft size={16}/>返回网络素材</Button>}<Button disabled={busy} onClick={close}>完成</Button></>}>
      <div className="download-session-heading"><p className="helper">登录记录保存在这台电脑，重启后复用。需要验证时，请在对应浏览器窗口完成。</p><Button loading={loading} disabled={busy} onClick={loadAccounts}><RefreshCw size={16}/>刷新状态</Button></div><Notice message={error} error/><Notice message={notice}/>
      <DownloadSessionsList items={accounts} loading={loading} loadError={loadError} busy={busy} onRetry={loadAccounts} onCheck={checkAccount} onLogin={openLogin} onSelect={selectAccount}/>
      <section className="download-add-account"><div><h3>添加平台登录</h3><p className="helper">打开项目内置浏览器，扫码后回到这里查看结果。</p></div><Field label="登录平台"><select value={platform} disabled={busy||loginPending} onChange={event=>setPlatform(event.target.value)}>{DOWNLOAD_PLATFORMS.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Button variant="primary" loading={busy} disabled={loginPending} onClick={startLogin}><LogIn size={17}/>打开浏览器扫码</Button></section>
      {login&&<section className="network-login-task"><div role="status"><strong>{loginLabel(login.status)}</strong>{(login.hint||login.message)&&<p className="helper">{login.hint||login.message}</p>}{loginPending&&<p className="helper">请保持登录窗口打开，可以扫描下方登录页中的二维码。</p>}{login.poll_error&&<Button disabled={busy} onClick={()=>setLogin(current=>({...current,poll_error:false}))}><RefreshCw size={15}/>查询登录结果</Button>}</div><LoginPagePreview task={login} onRefreshTask={()=>setLogin(current=>({...current,poll_error:false}))}/></section>}
    </Dialog>}
  </>;
}
