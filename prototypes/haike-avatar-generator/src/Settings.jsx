import {useEffect, useState} from 'react';
import {ArrowUpRight, KeyRound, CheckCircle2, CircleHelp, Eye, EyeOff} from 'lucide-react';
import {api} from './studio-api.js';
import {Button, CAPABILITIES, Field, Heading, Notice, availableModels} from './ui.jsx';
import {DEFAULT_GATEWAY_URL,accountCenterUrl} from './gateway-config.js';
const money = v => `¥${(Number(v || 0)/1000000).toFixed(2)}`;
const ratePrice = v => `¥${(Number(v || 0)/1000000).toLocaleString('zh-CN',{maximumFractionDigits:6})}`;
export function Settings() {
  const [config,setConfig]=useState({base_url:DEFAULT_GATEWAY_URL}), [key,setKey]=useState(''), [result,setResult]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false), [visible,setVisible]=useState(false);
  useEffect(() => {let live=true;api('/api/studio/settings').then(async c=>{if(!live)return;setConfig(c);if(c.configured){const r=await api('/api/studio/account');if(live)setResult(r);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
  async function connect(e) {e.preventDefault();setBusy(true);setError('');try{const r=await api('/api/studio/settings',{base_url:config.base_url,api_key:key});setConfig(r.settings);setKey('');setVisible(false);setResult(r);window.dispatchEvent(new CustomEvent('haike:gateway-changed',{detail:{base_url:r.settings.base_url}}));}catch(e){setError(e.message);}finally{setBusy(false);}}
  const models=availableModels(result), summary=result?.summary, verified=!!summary && !error;
  return <main className="workspace"><Heading title="API 设置" helper="一个海客 Key，连接制作所需能力。"/>
    <div className="settings-grid"><form className="surface studio-form connection-form" onSubmit={connect}>
      <header className="section-title"><KeyRound size={22}/><div><h2>统一 API 接入</h2><p className="helper">使用账户中心申请的海客 Key。</p></div></header>
      <Field label="网关地址" hint="以 /v2 结尾；公网地址使用 HTTPS。"><input type="url" required value={config.base_url} disabled={busy} onChange={e=>setConfig({...config,base_url:e.target.value})} placeholder="https://你的海客网关/v2"/></Field>
      <Field label="API Key" hint={config.configured ? `已保存 ${config.key_hint}，留空保留原 Key。` : '第三方平台密钥由管理员统一管理。'}><div className="secret-input"><input type={visible?'text':'password'} autoComplete="off" spellCheck="false" value={key} disabled={busy} onChange={e=>setKey(e.target.value)} placeholder={config.configured?'输入新的 Key 可替换':'粘贴海客 API Key'} required={!config.configured}/><button type="button" className="icon-button" aria-label={visible?'隐藏Key':'显示Key'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></Field>
      <p className="helper">Key 仅保存在本机后台，保存后不会回显，也不会写入浏览器草稿。</p>
      <Notice message={error} error/><Notice message={verified?'连接已验证，查询没有产生费用。':''}/>
      <div className="form-actions"><Button type="submit" variant="primary" loading={busy}>保存并测试连接</Button></div>
    </form><section className="surface studio-form account-summary"><header className="section-title"><h2>连接与额度</h2><span className={`status-pill ${verified?'ready':''}`}>{verified?'连接正常':config.configured?'已保存 · 待验证':'尚未连接'}</span></header>
      <div className="balance-display"><span>可用额度</span><strong>{summary?money(summary.commercial_available_micros??summary.available_micros):'—'}</strong></div>
      <div className="balance-details"><div><span>冻结额度</span><strong>{summary?money(summary.commercial_reserved_micros??summary.reserved_micros):'—'}</strong></div><div><span>本月消费</span><strong>{summary?money(summary.commercial_month_spent_micros??summary.month_spent_micros):'—'}</strong></div></div>
      {config.checked_at && <p className="helper">最近连接验证：{new Date(config.checked_at).toLocaleString('zh-CN')}</p>}
      <Button href={accountCenterUrl(config.base_url)} target="_blank" rel="noopener">账户、充值与调用明细<ArrowUpRight size={16}/></Button>
    </section></div>
    <section className="surface capabilities-panel"><header className="section-title"><div><h2>模型能力</h2><p className="helper">同一个 Key 使用所有已开通能力，共享账户额度。</p></div>{verified&&<span className="status-pill">{models.size} / {CAPABILITIES.length} 项已开通</span>}</header>
      <div className="capability-list">{CAPABILITIES.map(c=>{const local=c.model==='haike/tencent-asr'&&result?.local_asr?.ready, ready=verified&&(local||models.has(c.model)), data=result?.capabilities?.items?.find(x=>x.model===c.model);return <article key={c.model}><div className={`capability-icon ${ready?'ready':''}`}>{ready?<CheckCircle2 size={20}/>:<CircleHelp size={20}/>}</div><div><strong>{c.name}</strong><p>{local?'本地 Whisper · 词级时间轴':c.detail}</p></div><div className="capability-status"><span className={`status-pill ${ready?'ready':verified?'pending':''}`}>{ready?'已开通':verified?'未开通':'待连接验证'}</span>{ready&&(local?<small>本地识别 · 无 API 费用</small>:data?.billing_mode==='wallet_receipt'?<small>供应商实扣 × 1.5</small>:data?.rates?.[0]&&<small>{ratePrice(data.rates[0].price_micros)} / {data.rates[0].included_units} {data.rates[0].unit}</small>)}</div></article>;})}</div>
      {verified&&models.size<CAPABILITIES.length&&<Notice error message={`${CAPABILITIES.filter(c=>!models.has(c.model)).map(c=>c.name).join('、')}尚未开通。请联系管理员确认对应采购价与模型配置，开通后才能使用这些功能。`}/>}
      {result?.local_asr?.ready&&<Notice message="字幕和分镜时间轴使用已验收的本地 Whisper，按音频取得词级时间戳，无识别 API 费用。新任务使用此引擎，旧任务保留原模型。"/>}
      <p className="helper">连接验证仅核对 Key、额度和开通状态；真实生成与扣费以调用结果及账单为准。本地图文合成不收费。</p>
    </section>
  </main>;
}
