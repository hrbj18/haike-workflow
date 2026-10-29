import {useCallback,useEffect,useRef,useState} from 'react';
import {RefreshCw,UserRound} from 'lucide-react';
import {Button,Notice} from './ui.jsx';
import {DOWNLOAD_SESSIONS_API,accountScopeView,normalizeDownloadSessions} from './network-materials-model.js';
export {accountScopeView} from './network-materials-model.js';
import {openPlatformAccounts} from './studio-routes.js';
import './platform-accounts.css';

const PLATFORMS=[{id:'douyin',name:'抖音'},{id:'kuaishou',name:'快手'},{id:'shipinhao',name:'视频号'}];
const time=value=>{const date=value?new Date(value):null;return date&&Number.isFinite(date.getTime())?date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'尚未检查';};
function StatusDot({tone}) {
  return <span className={`platform-state-dot ${tone==='ready'?'green':tone==='danger'?'red':'yellow'}`} aria-hidden="true"/>;
}
export async function checkPlatformSession(id,{controller=new AbortController(),timeoutMs=70000,fetchImpl=fetch}={}) {
  const timeout=setTimeout(()=>controller.abort(),timeoutMs);
  try {
    const response=await fetchImpl(`${DOWNLOAD_SESSIONS_API}/${encodeURIComponent(id)}/check`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:controller.signal});
    const value=await response.json();
    if(!response.ok||!value||typeof value!=='object')throw new Error('检查未完成，请稍后重试。');
    return value;
  }catch(error){throw new Error(controller.signal.aborted?'检查超时，结果待确认，请稍后重新检查。':'检查未完成，请稍后重试。');}
  finally{clearTimeout(timeout);}
}
export function usePlatformSessions() {
  const [items,setItems]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [checking,setChecking]=useState(false),[checkErrors,setCheckErrors]=useState([]),[checkNotice,setCheckNotice]=useState('');
  const knownItems=useRef([]),checkLock=useRef(false),activeCheck=useRef(null),mounted=useRef(true);
  const load=useCallback(async(signal)=>{
    setLoading(true);
    try{const response=await fetch(DOWNLOAD_SESSIONS_API,{signal}),body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'账号状态暂时无法读取。');const value=normalizeDownloadSessions(body);if(mounted.current&&!signal?.aborted){knownItems.current=value;setItems(value);setError('');}return value;}
    catch(e){if(mounted.current&&!signal?.aborted)setError(e.message||'账号状态暂时无法读取。');}
    finally{if(mounted.current&&!signal?.aborted)setLoading(false);}
  },[]);
  useEffect(()=>{mounted.current=true;const controller=new AbortController(),refresh=()=>{if(!checkLock.current)void load(controller.signal);};refresh();window.addEventListener('haike:sessions-changed',refresh);const timer=setInterval(refresh,60000);return()=>{mounted.current=false;controller.abort();activeCheck.current?.abort();clearInterval(timer);window.removeEventListener('haike:sessions-changed',refresh);};},[load]);
  const check=useCallback(async()=>{
    if(checkLock.current)return;checkLock.current=true;setChecking(true);setCheckErrors([]);setCheckNotice('');
    const failures=[];let checked=0;
    try {
      const current=knownItems.current.length?knownItems.current:await load(),accounts=(current||[]).filter(item=>PLATFORMS.some(platform=>platform.id===item.platform));
      if(!accounts.length){if(mounted.current)setCheckNotice('尚无可检查的平台账号，请先管理登录。');return;}
      for(const account of accounts) {
        if(!mounted.current)break;
        const controller=new AbortController();activeCheck.current=controller;
        try{await checkPlatformSession(account.id,{controller});checked++;}
        catch(e){failures.push(`${PLATFORMS.find(platform=>platform.id===account.platform).name} · ${account.nickname}：${e.message}`);}
        finally{if(activeCheck.current===controller)activeCheck.current=null;}
        if(mounted.current)setCheckErrors([...failures]);
      }
      if(mounted.current){await load();setCheckNotice(`已完成 ${checked} 个账号的登录检查，请查看各项状态${failures.length?`；${failures.length} 个账号检查未完成。`:'。'}`);window.dispatchEvent(new Event('haike:sessions-changed'));}
    }finally{checkLock.current=false;if(mounted.current)setChecking(false);}
  },[load]);
  return {items,loading,error,checking,checkErrors,checkNotice,refresh:()=>load(),check};
}
export function MaterialLoginSummary({items=[],loading=false,error=''}) {
  const candidates=items.filter(item=>PLATFORMS.some(p=>p.id===item.platform)&&item.selected&&item.search_supported);
  const usable=candidates.filter(item=>accountScopeView(item.search_status,{checkedAt:item.search_checked_at}).tone==='ready');
  const tone=error||loading?'neutral':usable.length?'ready':candidates.length&&candidates.every(item=>accountScopeView(item.search_status,{checkedAt:item.search_checked_at}).tone==='danger')?'danger':'neutral';
  const label=error?'状态读取失败':loading?'正在读取状态':tone==='ready'?'素材账号最近检查正常':tone==='danger'?'联网素材需登录':'联网素材待确认';
  return <p className="material-login-summary helper" role="status"><strong className={`platform-session-state ${tone}`}><StatusDot tone={tone}/>{label}</strong>{' '}{error?'素材账号状态暂不可读，请管理登录后重试。':loading?'正在读取上次检查结果…':usable.length?`${usable.map(item=>PLATFORMS.find(p=>p.id===item.platform).name).filter((value,index,list)=>list.indexOf(value)===index).join('、')}素材账号最近检查正常；搜索前会自动验证。`:tone==='danger'?'上次检查需要登录，请登录素材账号后重新检查。':'尚无已确认可用于搜索的登录态，执行前请检查账号。'} <button type="button" className="text-button" onClick={()=>openPlatformAccounts()}>管理登录</button></p>;
}
function ScopeStatus({label,status,checkedAt,supported=true,saved=false,note=''}) {
  const view=accountScopeView(status,{supported,saved,checkedAt});
  return <div className="platform-scope-status"><span>{label}</span><strong className={`platform-session-state ${view.tone}`}><StatusDot tone={view.tone}/>{view.label}</strong><small>{note&&`${note} · `}{supported?`检查：${time(checkedAt)}`:'关键词搜索尚未接入'}</small></div>;
}
export function PlatformAccountRows({items=[],loading=false,error=''}) {
  return <div className="platform-account-rows">{PLATFORMS.map(platform=>{
    const accounts=items.filter(item=>item.platform===platform.id),material=accounts.find(item=>item.selected)||accounts[0],publisher=accounts.find(item=>accountScopeView(item.publish_check_status??item.publish_status,{checkedAt:item.publish_checked_at}).tone==='ready')||material;
    return <article className="platform-account-row" key={platform.id}>
      <div className="platform-account-identity"><strong>{platform.name}</strong><span>{loading&&!items.length?'正在读取…':error&&!items.length?'账号状态未知':material?.nickname||'尚未添加账号'}</span>{material&&!material.selected&&<small>尚未选作素材账号</small>}{accounts.length>1&&<small>{accounts.length} 个账号 · 管理中查看全部</small>}</div>
      <ScopeStatus label={material?.search_supported||platform.id==='douyin'?'素材搜索':'素材下载'} status={error?'unknown':material?.search_supported?material.search_status:material?.download_check_status??material?.download_status??'unconfirmed'} checkedAt={material?.search_supported?material.search_checked_at:material&&Object.hasOwn(material,'download_checked_at')?material.download_checked_at:material?.last_checked_at} note={platform.id!=='douyin'?'仅链接下载':''} saved={material?.download_saved}/>
      <ScopeStatus label="视频发布" status={error?'unknown':publisher?.publish_check_status??publisher?.publish_status??'unconfirmed'} checkedAt={publisher?.publish_checked_at} note={publisher&&publisher.id!==material?.id?publisher.nickname:''} saved={publisher?.publish_saved}/>
      <Button onClick={()=>openPlatformAccounts(platform.id)}>管理登录</Button>
    </article>;
  })}</div>;
}
export function PlatformAccountsSettings() {
  const sessions=usePlatformSessions();
  return <section className="surface platform-accounts-settings" aria-label="平台账号登录状态"><header className="section-title"><div><h2><UserRound size={20}/> 平台账号</h2><p className="helper">素材搜索与视频发布分别检查；登录记录保存在本机。</p></div><Button loading={sessions.checking} disabled={sessions.loading||sessions.checking} onClick={sessions.check}><RefreshCw size={15}/>{sessions.checking?'正在检查登录':'检查登录状态'}</Button></header>
    <Notice message={sessions.error} error/><PlatformAccountRows {...sessions}/>
    {sessions.checkErrors.map(message=><Notice key={message} message={message} error/>)}<Notice message={sessions.checkNotice}/>
    <div className="platform-status-legend helper" aria-label="登录状态颜色说明"><span><StatusDot tone="ready"/>最近检查正常</span><span><StatusDot tone="neutral"/>待确认</span><span><StatusDot tone="danger"/>需登录</span></div>
    <p className="helper platform-accounts-note">绿灯表示最近8小时内检查正常，超过8小时需重新确认。搜索前自动验证登录；发布前逐个自动验证目标账号。</p>
  </section>;
}
export function NetworkMaterialChoice({enabled,onChange,busy=false,sessions}) {
  return <section className="network-material-choice"><div className="network-material-choice-heading"><label className="checkbox-row"><input type="checkbox" checked={enabled===true} disabled={busy} onChange={event=>onChange(event.target.checked)}/><strong>联网搜索画面素材</strong></label><span className="helper">仅本次任务</span></div>
    {typeof enabled!=='boolean'&&<p className="helper">此旧稿沿用原来的 AI 素材策略；切换此开关后使用本次选择。</p>}
    {enabled&&<><p className="helper">搜索并采用相关网络画面；找不到合适素材时会明确暂停，等待补充。</p><MaterialLoginSummary {...sessions}/></>}
  </section>;
}
