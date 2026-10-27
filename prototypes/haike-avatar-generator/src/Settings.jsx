import {useEffect, useState} from 'react';
import {ArrowUpRight, KeyRound, CheckCircle2, CircleHelp, Eye, EyeOff, Mic, ArrowRight, Sparkles} from 'lucide-react';
import {api} from './studio-api.js';
import {Button, CAPABILITIES, Field, Heading, Notice, availableModels, hasCapability} from './ui.jsx';
import {DEFAULT_GATEWAY_URL,accountCenterUrl} from './gateway-config.js';
import { LEGACY_TOOLS, openAudioCenter } from './studio-routes.js';
import {asrPolicy,isAsrCapability} from './asr-policy.js';
import {AvatarDefaultsSettings} from './AvatarDefaults.jsx';
import {PlatformAccountsSettings} from './PlatformAccounts.jsx';
const money = v => `¥${(Number(v || 0)/1000000).toFixed(2)}`;
const ratePrice = v => `¥${(Number(v || 0)/1000000).toLocaleString('zh-CN',{maximumFractionDigits:6})}`;
export function Settings() {
  const [config,setConfig]=useState({base_url:DEFAULT_GATEWAY_URL}), [key,setKey]=useState(''), [result,setResult]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false), [visible,setVisible]=useState(false);
  useEffect(() => {let live=true;api('/api/studio/settings').then(async c=>{if(!live)return;setConfig(c);if(c.configured||c.mode==='internal_local'||c.service_mode==='internal'){const r=await api('/api/studio/account');if(live)setResult(r);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
  async function connect(e) {e.preventDefault();setBusy(true);setError('');try{const r=await api('/api/studio/settings',{base_url:config.base_url,api_key:key});setConfig(r.settings);setKey('');setVisible(false);setResult(r);window.dispatchEvent(new CustomEvent('haike:gateway-changed',{detail:{base_url:r.settings.base_url}}));}catch(e){setError(e.message);}finally{setBusy(false);}}
  const internal=config.mode==='internal_local'||config.service_mode==='internal'||result?.mode==='internal_local', models=availableModels(result), summary=result?.summary, verified=!!result && (internal||!!summary) && !error;
  const asr=asrPolicy(result);
  const optionalAssets=internal&&(result?.analysis_mode||config.analysis_mode||'agent')==='agent';
  const requiredCapabilities=CAPABILITIES.filter(c=>!optionalAssets||c.model!=='haike/assets');
  const enabled=requiredCapabilities.filter(c=>isAsrCapability(c)?asr.ready:hasCapability(models,c.model));
  return <main className="workspace"><Heading title="API 设置" helper="Agent负责分析，配置制作所需服务。"/>
    <div className="settings-grid"><form className="surface studio-form connection-form" onSubmit={connect}>
      <header className="section-title"><KeyRound size={22}/><div><h2>统一 API 接入{internal?'（可选）':''}</h2><p className="helper">{internal?'当前制作使用已配置的服务；需要统一网关时再填写海客 Key。':'使用账户中心申请的海客 Key。'}</p></div></header>
      <Field label="网关地址" hint="以 /v2 结尾；公网地址使用 HTTPS。"><input type="url" required value={config.base_url} disabled={busy} onChange={e=>setConfig({...config,base_url:e.target.value})} placeholder="https://你的海客网关/v2"/></Field>
      <Field label="API Key" hint={config.configured ? `已保存 ${config.key_hint}，留空保留原 Key。` : internal?'未使用统一网关时可留空。':'请使用海客账户中心申请的 Key。'}><div className="secret-input"><input type={visible?'text':'password'} autoComplete="off" spellCheck="false" value={key} disabled={busy} onChange={e=>setKey(e.target.value)} placeholder={config.configured?'输入新的 Key 可替换':'粘贴海客 API Key'} required={!config.configured}/><button type="button" className="icon-button" aria-label={visible?'隐藏Key':'显示Key'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></Field>
      <p className="helper">Key 仅保存在本机后台，保存后不会回显，也不会写入浏览器草稿。</p>
      <Notice message={error} error/><Notice message={internal?'海客制作服务，按每次报价确认':verified?'连接已验证，查询没有产生费用。':''}/>
      <div className="form-actions"><Button type="submit" variant="primary" loading={busy}>保存并测试连接</Button></div>
    </form><section className="surface studio-form account-summary"><header className="section-title"><h2>{internal?'当前服务':'连接与额度'}</h2><span className={`status-pill ${verified?'ready':''}`}>{internal?'本机制作服务':verified?'连接正常':config.configured?'已保存 · 待验证':'尚未连接'}</span></header>
      {internal?<><div className="balance-display"><span>服务模式</span><strong style={{fontSize:23}}>海客制作服务</strong></div><p className="helper">海客服务费用按每次报价确认，预估费用与实际结算可能不同，以调用结果及账单为准。</p></>:<>
      <div className="balance-display"><span>可用额度</span><strong>{summary?money(summary.commercial_available_micros??summary.available_micros):'—'}</strong></div>
      <div className="balance-details"><div><span>冻结额度</span><strong>{summary?money(summary.commercial_reserved_micros??summary.reserved_micros):'—'}</strong></div><div><span>本月消费</span><strong>{summary?money(summary.commercial_month_spent_micros??summary.month_spent_micros):'—'}</strong></div></div>
      {config.checked_at && <p className="helper">最近连接验证：{new Date(config.checked_at).toLocaleString('zh-CN')}</p>}
      <Button href={accountCenterUrl(config.base_url)} target="_blank" rel="noopener">账户、充值与调用明细<ArrowUpRight size={16}/></Button></>}
    </section></div>
    <section className="surface audio-settings-entry"><div><h2><Mic size={20}/> 海客配音中心</h2><p className="helper">上传录音克隆声音、选择音色；更多设置在音色详情中展开。</p></div><Button variant="primary" onClick={()=>openAudioCenter()}>管理我的音色<ArrowRight size={17}/></Button></section>
    <AvatarDefaultsSettings/>
    <PlatformAccountsSettings/>
    <section className="surface capabilities-panel"><header className="section-title"><div><h2>模型能力</h2><p className="helper">{internal?'海客制作服务，按每次报价确认':'同一个 Key 使用所有已开通能力，共享账户额度。'}</p></div>{verified&&<span className="status-pill">{enabled.length} / {requiredCapabilities.length} 项可用</span>}</header>
      <div className="capability-list"><article aria-label="Agent分析工作方式">
        <div className="capability-icon"><Sparkles size={20}/></div>
        <div><strong>Agent分析</strong><p>文案、图片与视频理解</p></div>
        <div className="capability-status"><span className="status-pill">由当前Agent完成</span><small>工作方式</small></div>
      </article>{CAPABILITIES.map(c=>{
        const isAsr=isAsrCapability(c),optional=optionalAssets&&c.model==='haike/assets',ready=verified&&(isAsr?asr.ready:hasCapability(models,c.model));
        const data=isAsr?asr.capability:result?.capabilities?.items?.find(x=>x.model===c.model||(c.model==='haike/cosyvoice'&&x.model==='haike/cosyvoice-public'));
        return <article key={c.model}>
          <div className={`capability-icon ${ready?'ready':''}`}>{ready?<CheckCircle2 size={20}/>:<CircleHelp size={20}/>}</div>
          <div><strong>{isAsr?asr.name:c.name}</strong><p>{optional?'按需配置Pexels，供当前Agent备用取材':isAsr?asr.detail:c.detail}</p></div>
          <div className="capability-status">
            <span className={`status-pill ${ready?'ready':!optional&&verified?'pending':''}`}>{optional?(ready?'备用已配置':'可选备用'):ready?(isAsr?asr.readyLabel:'已开通'):verified?(isAsr?asr.unreadyLabel:'未开通'):'待连接验证'}</span>
            {ready&&(isAsr&&asr.provider!=='gateway'?<small>{asr.billing}</small>:data?.billing_mode==='wallet_receipt'?<small>按实际用量结算</small>:data?.rates?.[0]?<small>{ratePrice(data.rates[0].price_micros)} / {data.rates[0].included_units} {data.rates[0].unit}</small>:isAsr&&<small>{asr.billing}</small>)}
          </div>
        </article>;
      })}</div>
      {verified&&enabled.length<requiredCapabilities.length&&<Notice error message={`${requiredCapabilities.filter(c=>!enabled.includes(c)).map(c=>c.name).join('、')}尚未开通，请联系管理员。`}/>}
      {result&&asr.notice&&<Notice message={asr.notice}/>}
      <p className="helper">{internal?'海客服务按当前配置执行；开始前请确认费用预估与预算。':'海客连接检查仅验证 Key、可用额度和已开通功能，不产生费用。实际制作费用以报价、调用结果和账单为准；本地图文合成免费。'}</p>
    </section>
    <section className="surface capabilities-panel"><h2>更多制作工具</h2><p className="helper">继续使用已有的素材、项目和完整制作流程。</p><div className="more-tools-grid">{LEGACY_TOOLS.map(tool=><a href={tool.path} key={tool.path}><strong>{tool.label}</strong><small>{tool.description}</small></a>)}</div></section>
  </main>;
}
