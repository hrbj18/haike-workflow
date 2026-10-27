import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, ChevronRight, ImagePlus, Mic, Play, RefreshCw, Upload } from 'lucide-react';
import { api } from './studio-api.js';
import { Button, Dialog, EmptyState, Field, Notice } from './ui.jsx';
import { AUDIO_CENTER_API, jobState, makeVoiceQuote, normalizeCatalog, paidJobBody, quotedMicros, voiceImageUrl } from './audio-center-model.js';
import { changeAudioRoute, closeAudioCenter } from './studio-routes.js';
import {forgetAudioOperation,pendingAudioOperation,rememberAudioOperation} from './audio-operation-store.js';
import './audio-center.css';
import {QuoteBilling} from './QuoteBilling.jsx';

const money = micros => `¥${(Number(micros || 0) / 1000000).toLocaleString('zh-CN', { maximumFractionDigits: 6 })}`;
const errorText = error => typeof error === 'string' ? error : error?.message || '操作未完成，请稍后重试。';
const jobLabel = status => ({ pending: '等待处理', queued: '排队中', running: '正在处理', processing: '正在处理', completed: '已完成', succeeded: '已完成', failed: '处理失败', submission_unknown: '结果待核对', uncertain: '结果待核对' })[status] || '处理中';

export function VoiceCatalog({ items, defaultVoiceId, onOpen, loadError, onRetry }) {
  if(loadError)return <EmptyState title="暂时无法读取音色" action={<Button onClick={onRetry}><RefreshCw size={15}/>刷新音色</Button>}>请检查连接后刷新，当前无法确认可用音色。</EmptyState>;
  return <div className="voice-catalog">{['public', 'cloned'].map(kind => {
    const voices = items.filter(v => v.kind === kind);
    return <section key={kind}><header className="audio-section-heading"><h3>{kind === 'public' ? '公共音色' : '我的音色'}</h3><span>{voices.length} 个</span></header>
      {voices.length ? <div className="voice-grid">{voices.map(voice => <button className={`voice-tile ${defaultVoiceId === voice.id ? 'is-default' : ''}`} key={voice.id} onClick={() => onOpen(voice.id)} aria-label={`选择音色：${voice.name}`}>
        <span className="voice-avatar">{voiceImageUrl(voice) ? <img src={voiceImageUrl(voice)} alt="关联人物图" /> : <Mic size={22} />}</span>
        <span className="voice-tile-copy"><strong>{voice.name}</strong><small>{voice.gender === 'male' || voice.gender === '男' ? '男声' : voice.gender === 'female' || voice.gender === '女' ? '女声' : '音色'} · {voice.available ? voice.verification==='candidate_unverified'?'待试听验证':'可用' : '暂不可用'}</small>{defaultVoiceId === voice.id && <span className="voice-default"><Check size={12} />默认音色</span>}</span><ChevronRight size={17} />
      </button>)}</div> : <p className="helper audio-empty">{kind === 'public' ? '公共音色暂未开放，请稍后刷新。' : '上传已获授权的录音，创建你的第一款音色。'}</p>}
    </section>;
  })}</div>;
}

export function VoiceDetails({ voice, isDefault, rate, setRate, text, setText, busy, unresolved, onDefault, onSaveRate, onPreview, onImage, onUse, onBack }) {
  const file = useRef(null), section=useRef(null);
  useEffect(()=>section.current?.focus(),[voice.id]);
  return <section ref={section} tabIndex={-1} aria-label={`${voice.name}音色详情`} className="voice-details"><Button variant="text" onClick={onBack}><ArrowLeft size={16} />返回全部音色</Button>
    <div className="voice-detail-title"><div className="voice-detail-image">{voiceImageUrl(voice) ? <img src={voiceImageUrl(voice)} alt={`${voice.name}关联人物图`} /> : <Mic size={32} />}</div><div><span className="eyebrow">{voice.kind === 'public' ? '公共音色' : '我的克隆音色'}</span><h3>{voice.name}</h3><p className="helper">{voice.description || '选择适合这期内容的声音，再设置倍率与人物图。'}</p></div></div>
    {!voice.available && <Notice error message="此音色当前不可用；已有项目与音频继续保留。" />}
    {voice.available&&voice.verification==='candidate_unverified'&&<p className="helper">此音色尚待实际试听验证，请先核对试听效果。</p>}
    <div className="voice-detail-actions"><Button loading={busy} disabled={!voice.available || isDefault} onClick={onDefault}>{isDefault ? <><Check size={16} />当前默认音色</> : '设为默认音色'}</Button>{onUse && <Button variant="primary" disabled={busy || !voice.available} onClick={onUse}>用于当前口播</Button>}</div>
    <div className="voice-settings-grid"><section className="voice-option"><h4>配音倍率</h4><p className="helper">仅保存当前账号对此音色的设置。</p><Field label="语速倍率"><input type="number" min="0.5" max="2" step="0.05" value={rate} onChange={e => setRate(e.target.value)} disabled={busy} /></Field><Button onClick={onSaveRate} disabled={busy}>保存倍率</Button></section>
      <section className="voice-option"><h4>关联人物图</h4><p className="helper">用于口播时，可明确选择采用此图。</p><Button onClick={() => file.current.click()} disabled={busy}><ImagePlus size={17} />{voiceImageUrl(voice) ? '更换人物图' : '上传人物图'}</Button>{voiceImageUrl(voice) && <Button variant="text" onClick={() => onImage(null)} disabled={busy}>移除关联图</Button>}<input ref={file} hidden type="file" accept="image/png,image/jpeg" aria-label="关联人物图片" onChange={e => { const selected = e.target.files?.[0]; e.target.value = ''; if (selected) onImage(selected); }} /></section></div>
    <section className="voice-option voice-audition"><h4>试听</h4><Field label="试听文案" hint="最多180字；先查看报价，确认费用上限后才生成声音。"><textarea rows={3} maxLength={180} value={text} onChange={e => setText(e.target.value)} disabled={busy} /></Field><Button onClick={event=>onPreview(event.currentTarget)} disabled={busy || unresolved || !voice.available || !text.trim()}><Play size={16} />查看试听报价</Button></section>
  </section>;
}

export function AudioCenterDialog({ route }) {
  const [catalog, setCatalog] = useState({ items: [], preferences: {} });
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''),[catalogError,setCatalogError]=useState(false);
  const [name, setName] = useState(''), [sample, setSample] = useState(null), [consent, setConsent] = useState(false);
  const [rate, setRate] = useState('1'), [text, setText] = useState('海客科技，让创作更简单。用自然清晰的声音，分享每一个值得记录的故事。');
  const [payment, setPayment] = useState(null), [budget, setBudget] = useState('0'), [job, setJob] = useState(()=>{const id=route.operationId||pendingAudioOperation();return id?jobState({id,status:'pending'}):null;});
  const audioUpload = useRef(null), submitting = useRef(false), uploadCache = useRef(null), accountGeneration = useRef(0), taskBusy = useRef(false),quoteTrigger=useRef(null);
  const voice = catalog.items.find(v => v.id === route.voiceId), unresolved = !!job?.unresolved || (!!route.operationId&&!job);

  async function load() {
    const generation = accountGeneration.current;
    setLoading(true); setError('');setCatalogError(false);
    try { const value = await api(AUDIO_CENTER_API); if (generation === accountGeneration.current) setCatalog(normalizeCatalog(value)); }
    catch (e) { if (generation === accountGeneration.current){setCatalogError(true);setError(errorText(e));} }
    finally { if (generation === accountGeneration.current) setLoading(false); }
  }
  useEffect(() => { load(); const changed = () => {
    accountGeneration.current++; setCatalog({ items: [], preferences: {} }); setPayment(null); setJob(null); setSample(null); setConsent(false); uploadCache.current = null;
    forgetAudioOperation();changeAudioRoute({ operationId: '' }, { replace: true }); load();
  }; window.addEventListener('haike:gateway-changed', changed); return () => { accountGeneration.current++; window.removeEventListener('haike:gateway-changed', changed); }; }, []);
  useEffect(() => { setRate(String(voice?.preferences?.speech_rate || 1)); setPayment(null); }, [voice?.id, voice?.preferences?.speech_rate]);
  async function readJob(id = route.operationId || job?.operation_id || job?.id || pendingAudioOperation()) {
    if (!id) return;
    const generation=accountGeneration.current;
    try { const value = jobState(await api(`${AUDIO_CENTER_API}/jobs/${encodeURIComponent(id)}`)); if(generation!==accountGeneration.current)return; setJob(value); setError(''); if(!value.unresolved)forgetAudioOperation();if (!value.unresolved && ['completed', 'succeeded'].includes(value.status)) { await load(); window.dispatchEvent(new Event('haike:voices-changed')); } }
    catch (e) { if(generation!==accountGeneration.current)return; setJob(jobState({ id, status: 'submission_unknown', error: '暂时无法核对原任务，请恢复连接后查询原任务。' })); setError(errorText(e)); }
  }
  useEffect(() => { const id=route.operationId||pendingAudioOperation();if(id&&!submitting.current)readJob(id); }, [route.operationId]);
  useEffect(() => {
    if (!job?.unresolved || ['submission_unknown', 'uncertain', 'unknown'].includes(job.status) || !route.operationId) return;
    const timer = setInterval(() => readJob(route.operationId), 3000); return () => clearInterval(timer);
  }, [job?.status, route.operationId]);

  async function task(action) { if(taskBusy.current)return;taskBusy.current=true;setBusy(true); setError(''); setNotice(''); try { await action(); } catch (e) { setError(errorText(e)); } finally { taskBusy.current=false;setBusy(false); } }
  async function uploadFile(file, kind) {
    const response = await fetch(`${AUDIO_CENTER_API}/upload?${new URLSearchParams({ kind, filename: file.name })}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
    const value = await response.json(); if (!response.ok) throw new Error(value.detail || '文件上传未完成，请重试。');
    const id = value.id || value.file_id; if (!id) throw new Error('上传结果缺少文件编号。'); return id;
  }
  async function quote(operation,trigger) {quoteTrigger.current=trigger||audioUpload.current?.parentElement?.querySelector('button.primary')||document.activeElement;await task(async () => {
    const generation=accountGeneration.current;
    if (unresolved) throw new Error('已有任务结果待核对，请先查询原任务。');
    let request;
    if (operation === 'clone') {
      if (!sample || !name.trim() || !consent) throw new Error('请填写名称、选择录音并确认使用权。');
      let fileId = uploadCache.current?.file === sample ? uploadCache.current.id : null;
      if (!fileId) { fileId = await uploadFile(sample, 'audio'); uploadCache.current = { file: sample, id: fileId }; }
      request = makeVoiceQuote('clone', { name, audio_file: fileId, consent });
    } else request = makeVoiceQuote('preview', { voice, text, speech_rate: rate });
    if(generation!==accountGeneration.current)throw new Error('账号已切换，请重新选择当前账号的音色。');
    const value = await api(`${AUDIO_CENTER_API}/quotes`, request); if(generation!==accountGeneration.current)return;const maximum = quotedMicros(value);
    if (!value.operation_id) throw new Error('中转站尚未提供可恢复的调用编号，请更新音色服务后重试。');
    setBudget((maximum / 1000000).toFixed(6)); setPayment({ operation, quote: value, label: operation === 'clone' ? name.trim() : voice.name });
  }); }
  async function submit() { await task(async () => {
    const generation=accountGeneration.current,body = paidJobBody(payment?.quote, budget, true), id = body.operation_id;
    submitting.current = true;rememberAudioOperation(id); changeAudioRoute({ operationId: id }, { replace: true }); setJob(jobState({ id, status: 'submitting' })); setPayment(null);
    try { const value = jobState(await api(`${AUDIO_CENTER_API}/jobs`, body));if(generation!==accountGeneration.current)return; setJob(value);if(!value.unresolved)forgetAudioOperation(); if (!value.unresolved && ['completed', 'succeeded'].includes(value.status)) { await load(); window.dispatchEvent(new Event('haike:voices-changed')); } }
    catch (e) { if(generation!==accountGeneration.current)return;setJob(jobState({ id, status: 'submission_unknown', error: '提交结果暂不确定，请查询原任务，避免重复扣费。' })); setError(errorText(e)); }
    finally { submitting.current = false; }
  }); }
  async function preferences(body, id) { await task(async () => {
    const path = id ? `/voices/${encodeURIComponent(id)}/preferences` : '/preferences';
    await api(AUDIO_CENTER_API + path, body, 'PUT'); await load(); window.dispatchEvent(new Event('haike:voices-changed')); setNotice('设置已保存。');
  }); }
  async function image(file) { await task(async () => {
    if (file && (!/\.(jpe?g|png)$/i.test(file.name) || file.size > 10 * 1024 * 1024)) throw new Error('请选择10 MB以内的JPG或PNG人物图片。');
    const id = file ? await uploadFile(file, 'image') : null;
    await api(`${AUDIO_CENTER_API}/voices/${encodeURIComponent(voice.id)}/preferences`, { image_file_id: id }, 'PUT'); await load(); window.dispatchEvent(new Event('haike:voices-changed')); setNotice(file ? '人物图已关联；制作时可明确选择使用。' : '已移除关联人物图。');
  }); }
  const useInAvatar = location.pathname === '/avatar' ? () => {
    window.dispatchEvent(new CustomEvent('haike:voice-selected', { detail: { voiceId: voice.id, modelId: voice.model, rate: Number(voice.preferences?.speech_rate || 1) } })); closeAudioCenter();
  } : undefined;

  const internal=catalog.mode==='internal_local';
  return <Dialog title="海客配音中心" description="上传录音克隆声音，或选择适合你的音色。" wide onClose={closeAudioCenter} footer={<><span className="helper">{internal?'设置仅用于本机内部服务。':'设置按当前海客账号保存。'}</span><Button onClick={closeAudioCenter}>完成</Button></>}>
    <div className="audio-center"><Notice message={error} error /><Notice message={notice} /><Notice message={internal?'内部备用服务，按每次报价确认':''}/>
      {catalogError ? <VoiceCatalog loadError onRetry={load}/> : loading && !catalog.items.length ? <p role="status" className="helper">正在读取音色…</p> : route.voiceId && voice ? <VoiceDetails voice={voice} isDefault={catalog.preferences.voice_id === voice.id} rate={rate} setRate={setRate} text={text} setText={setText} busy={busy} unresolved={unresolved} onDefault={() => preferences({ voice_id: voice.id })} onSaveRate={() => { const value = Number(rate); if (!Number.isFinite(value) || value < .5 || value > 2) { setError('配音倍率需在0.5至2.0之间。'); return; } preferences({ speech_rate: value }, voice.id); }} onPreview={trigger => quote('preview',trigger)} onImage={image} onUse={useInAvatar} onBack={() => changeAudioRoute({ voiceId: '' })} /> : route.voiceId ? <EmptyState title="当前账号没有这款音色" action={<Button onClick={() => changeAudioRoute({ voiceId: '' })}>返回音色列表</Button>}>音色可能已删除或属于另一个账号。</EmptyState> : <>
        <section className="clone-upload"><div><span className="eyebrow">我的声音</span><h3>上传录音，克隆专属音色</h3><p className="helper">使用清晰的本人或已获授权录音，先查看报价再确认创建。</p></div><div className="clone-fields"><Field label="音色名称"><input value={name} maxLength={40} placeholder="例如：我的知识口播" onChange={e => setName(e.target.value)} disabled={busy} /></Field><Button disabled={busy} onClick={() => audioUpload.current.click()}><Upload size={17} />{sample ? sample.name : '选择参考录音'}</Button><input ref={audioUpload} hidden type="file" accept=".wav,.mp3,.m4a,.ogg" aria-label="克隆参考录音" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return; if (!/\.(wav|mp3|m4a|ogg)$/i.test(file.name) || file.size > 10 * 1024 * 1024) { setError('请选择10 MB以内的WAV、MP3、M4A或OGG录音。'); return; } setSample(file); uploadCache.current = null; }} /><label className="checkbox-row"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy} />我有权上传并克隆这段声音</label><Button variant="primary" disabled={busy || unresolved || !sample || !name.trim() || !consent} loading={busy} onClick={() => quote('clone')}>查看克隆报价</Button></div></section>
        <div className="audio-section-heading"><h3>选择音色</h3><Button variant="text" disabled={busy || loading} onClick={load}><RefreshCw size={15} />刷新</Button></div><VoiceCatalog items={catalog.items} defaultVoiceId={catalog.preferences.voice_id} onOpen={id => changeAudioRoute({ voiceId: id })} />
      </>}
      {job && <section className="audio-operation" role="status"><strong>{jobLabel(job.status)}</strong>{job.error && <p className="helper">{errorText(job.error)}</p>}{job.unresolved && <p className="helper">已有调用编号已保留；刷新页面后仍查询同一任务。</p>}{job.result?.audio_url && <audio controls preload="none" src={job.result.audio_url} aria-label="音色试听结果" />}{job.result?.voice && <p>音色已创建：{job.result.voice.name || '我的音色'}</p>}<Button disabled={busy} onClick={() => readJob()}><RefreshCw size={15} />查询原任务</Button></section>}
    </div>
    {payment && <Dialog title={payment.operation === 'clone' ? '确认克隆音色' : '确认生成试听'} description="确认后才提交本次调用。" busy={busy} returnFocus={quoteTrigger.current} onClose={() => setPayment(null)} footer={<><Button disabled={busy} onClick={() => setPayment(null)}>返回</Button><Button variant="primary" loading={busy} onClick={submit}>确认费用并提交</Button></>}><dl className="summary-list"><div><dt>音色</dt><dd>{payment.label}</dd></div><div><dt>{payment.quote.estimate_only?'采购估算':'报价上限'}</dt><dd>{money(payment.quote.max_charge_micros)}</dd></div></dl><QuoteBilling quote={payment.quote} internal={internal}/><Field label={payment.quote.estimate_only?'本次批准预算（元）':'本次最高费用（元）'} hint={payment.quote.estimate_only?'此预算用于确认采购估算，不代表供应商账单硬封顶。':'达到费用上限将停止，已完成的调用继续保留。'}><input type="text" inputMode="decimal" value={budget} onChange={e => setBudget(e.target.value)} disabled={busy} /></Field><Notice message={error} error /></Dialog>}
  </Dialog>;
}
