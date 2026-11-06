import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, ChevronRight, ImagePlus, Mic, Play, RefreshCw, Upload } from 'lucide-react';
import { api } from './studio-api.js';
import { Button, Dialog, EmptyState, Field, Notice } from './ui.jsx';
import { AUDIO_CENTER_API, budgetMicros, jobState, makeVoiceQuote, normalizeCatalog, paidJobBody, quotedMicros, voiceImageUrl } from './audio-center-model.js';
import { changeAudioRoute, closeAudioCenter } from './studio-routes.js';
import {forgetAudioOperation,pendingAudioOperation,rememberAudioOperation} from './audio-operation-store.js';
import './audio-center.css';
import {QuoteBilling} from './QuoteBilling.jsx';

const money = micros => `¥${(Number(micros || 0) / 1000000).toLocaleString('zh-CN', { maximumFractionDigits: 6 })}`;
const errorText = error => typeof error === 'string' ? error : error?.message || '操作未完成，请稍后重试。';
const jobLabel = status => ({ pending: '等待处理', uploading: '正在上传文件', queued: '排队中', running: '正在处理', processing: '正在处理', completed: '已完成', succeeded: '已完成', partial: '音色已保留，部分步骤待完成', paused: '原任务待继续', failed: '处理失败', submission_unknown: '结果待核对', uncertain: '结果待核对' })[status] || '处理中';
const enrollmentStage = { clone: '正在克隆声音', image: '正在关联人物图', preview: '正在生成试听', done: '音色与试听已就绪' };

export function CloneVoiceForm({ busy, unresolved, internal, onCreate }) {
  const [name,setName]=useState(''),[sample,setSample]=useState(null),[portrait,setPortrait]=useState(null);
  const [text,setText]=useState('你好，这是我的专属音色试听。用自然清晰的声音，分享每一个值得记录的故事。'),[budget,setBudget]=useState('1.00'),[error,setError]=useState(''),[portraitUrl,setPortraitUrl]=useState('');
  const audioInput=useRef(null),imageInput=useRef(null);
  useEffect(()=>{if(!portrait){setPortraitUrl('');return;}const url=URL.createObjectURL(portrait);setPortraitUrl(url);return()=>URL.revokeObjectURL(url);},[portrait]);
  const disabled=busy||unresolved;
  function choose(file,kind) {
    if(!file)return;
    const valid=kind==='audio'?/\.(wav|mp3|m4a|ogg)$/i:/\.(png|jpe?g)$/i;
    if(!valid.test(file.name)||file.size>10*1024*1024){setError(kind==='audio'?'请选择10 MB以内的WAV、MP3、M4A或OGG录音。':'请选择10 MB以内的JPG或PNG人物图。');return;}
    setError('');
    if(kind==='audio'){setSample(file);if(!name.trim())setName(file.name.replace(/\.[^.]+$/,'').slice(0,40));}else setPortrait(file);
  }
  async function create(event) {
    event.preventDefault();setError('');
    try {budgetMicros(budget);if(!sample||!name.trim()||!text.trim())throw new Error('请选择录音，并填写音色名称和试听文案。');await onCreate({name:name.trim(),sample,portrait,text:text.trim(),budget});}
    catch(e){setError(errorText(e));}
  }
  return <details className="clone-upload clone-disclosure"><summary className="clone-disclosure-heading"><Mic size={19} aria-hidden="true"/><span>克隆声音</span><small>上传录音，可附人物图</small><ChevronRight size={18} aria-hidden="true"/></summary><div className="clone-disclosure-body"><p className="helper">选择录音和可选人物图，一次确认完成克隆与试听。录音推荐10～20秒（至少5秒），单个文件不超过10 MB。</p>
    <form className="clone-fields" onSubmit={create}>
      <Field label="音色名称"><input value={name} maxLength={40} placeholder="选择录音后自动填写，可修改" onChange={e=>setName(e.target.value)} disabled={disabled}/></Field>
      <Field label="本次总预算（元）" hint="克隆和一次试听共用此预算。"><input type="text" inputMode="decimal" value={budget} onChange={e=>setBudget(e.target.value)} disabled={disabled}/></Field>
      <div className="clone-file-inputs"><Button disabled={disabled} onClick={()=>audioInput.current.click()}><Upload size={17}/>{sample?sample.name:'选择参考录音'}</Button><input ref={audioInput} hidden type="file" accept=".wav,.mp3,.m4a,.ogg" aria-label="克隆参考录音" onChange={e=>{choose(e.target.files?.[0],'audio');e.target.value='';}}/>
        <Button disabled={disabled} onClick={()=>imageInput.current.click()}><ImagePlus size={17}/>{portrait?'更换人物图':'附上人物图（可选）'}</Button><input ref={imageInput} hidden type="file" accept=".png,.jpg,.jpeg" aria-label="克隆关联人物图" onChange={e=>{choose(e.target.files?.[0],'image');e.target.value='';}}/></div>
      {portrait&&<div className="clone-portrait">{portraitUrl&&<img src={portraitUrl} alt="待关联人物图预览"/>}<span>{portrait.name}</span><Button variant="text" disabled={disabled} onClick={()=>setPortrait(null)}>移除图片</Button></div>}
      <details className="clone-audition-text"><summary>试听文案</summary><Field label="试听内容"><textarea rows={3} maxLength={180} value={text} onChange={e=>setText(e.target.value)} disabled={disabled}/></Field></details>
      <details className="clone-audition-text"><summary>费用说明</summary><p className="helper">包含声音克隆和一次试听；超出预算时停止后续调用，已创建的音色继续保留。{internal?'海客制作服务默认使用百炼 Qwen 3.1 TTS Plus；创建音色免费，试听费用按字符估算，与供应商账单可能有差异，上游不执行本机预算硬封顶。':'实际费用按当前海客账号的服务报价计算。'}</p></details>
      <p className="helper clone-consent">点击确认即表示你有权使用所选声音与图片，并授权在本次总预算内完成克隆和试听{internal?'（费用为采购估算）':''}。</p>
      <Notice message={error} error/><Button type="submit" variant="primary" disabled={disabled||!sample||!name.trim()||!text.trim()} loading={busy}>确认克隆并试听</Button>
    </form></div></details>;
}

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
  const [rate, setRate] = useState('1'), [text, setText] = useState('海客科技，让创作更简单。用自然清晰的声音，分享每一个值得记录的故事。');
  const [payment, setPayment] = useState(null), [budget, setBudget] = useState('0'), [job, setJob] = useState(()=>{const id=route.operationId||pendingAudioOperation();return id?jobState({id,status:'pending'}):null;});
  const submitting = useRef(false), accountGeneration = useRef(0), taskBusy = useRef(false),quoteTrigger=useRef(null);
  const voice = catalog.items.find(v => v.id === route.voiceId), unresolved = !!job?.unresolved || (!!route.operationId&&!job);

  async function load() {
    const generation = accountGeneration.current;
    setLoading(true); setError('');setCatalogError(false);
    try { const value = await api(AUDIO_CENTER_API); if (generation === accountGeneration.current) setCatalog(normalizeCatalog(value)); }
    catch (e) { if (generation === accountGeneration.current){setCatalogError(true);setError(errorText(e));} }
    finally { if (generation === accountGeneration.current) setLoading(false); }
  }
  useEffect(() => { load(); const changed = () => {
    accountGeneration.current++; setCatalog({ items: [], preferences: {} }); setPayment(null); setJob(null);
    forgetAudioOperation();changeAudioRoute({ operationId: '' }, { replace: true }); load();
  }; window.addEventListener('haike:gateway-changed', changed); return () => { accountGeneration.current++; window.removeEventListener('haike:gateway-changed', changed); }; }, []);
  useEffect(() => { setRate(String(voice?.preferences?.speech_rate || 1)); setPayment(null); }, [voice?.id, voice?.preferences?.speech_rate]);
  async function readJob(id = route.operationId || job?.operation_id || job?.id || pendingAudioOperation(), resume = false) {
    if (!id) return;
    const generation=accountGeneration.current,enrollment=id.startsWith('enroll_'),path=`${AUDIO_CENTER_API}/${enrollment?'enrollments':'jobs'}/${encodeURIComponent(id)}`;
    try { if(resume&&enrollment)await api(`${path}/resume`,{});const value = jobState(await api(path)); if(generation!==accountGeneration.current)return; setJob(value); setError(''); if(!value.unresolved)forgetAudioOperation();if (!value.unresolved && (['completed', 'succeeded'].includes(value.status)||value.result?.voice)) { await load(); window.dispatchEvent(new Event('haike:voices-changed')); } }
    catch (e) { if(generation!==accountGeneration.current)return;if(enrollment&&e.status===404){setJob(jobState({id,kind:'enrollment',status:'paused',error:'当前账号未找到原任务，请确认使用创建时的账号和服务配置；原任务编号已保留。'}));return;}setJob(jobState({ id, kind:enrollment?'enrollment':undefined,status: 'submission_unknown', error: '暂时无法核对原任务，请恢复连接后继续原任务。' })); setError(errorText(e)); }
  }
  useEffect(() => { const id=route.operationId||pendingAudioOperation();if(!id||submitting.current)return;if(!route.operationId){changeAudioRoute({operationId:id},{replace:true});return;}readJob(id,true); }, [route.operationId]);
  useEffect(() => {
    if (!job?.unresolved || job.status==='paused' || (!route.operationId?.startsWith('enroll_')&&['submission_unknown', 'uncertain', 'unknown'].includes(job.status)) || !route.operationId) return;
    const timer = setInterval(() => readJob(route.operationId), 3000); return () => clearInterval(timer);
  }, [job?.status, route.operationId]);

  async function task(action) { if(taskBusy.current)return;taskBusy.current=true;setBusy(true); setError(''); setNotice(''); try { await action(); } catch (e) { setError(errorText(e)); } finally { taskBusy.current=false;setBusy(false); } }
  async function uploadFile(file, kind) {
    const response = await fetch(`${AUDIO_CENTER_API}/upload?${new URLSearchParams({ kind, filename: file.name })}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
    const value = await response.json(); if (!response.ok) throw new Error(value.detail || '文件上传未完成，请重试。');
    const id = value.id || value.file_id; if (!id) throw new Error('上传结果缺少文件编号。'); return id;
  }
  async function createVoice({name,sample,portrait,text,budget}) {await task(async()=>{
    const generation=accountGeneration.current;
    if(unresolved)throw new Error('已有任务尚未结束，请先继续原任务。');
    const maximum=budgetMicros(budget);
    setJob(jobState({status:'uploading',kind:'enrollment'}));
    let id;
    try {
      const audio=await uploadFile(sample,'audio');
      if(generation!==accountGeneration.current)return;
      const image=portrait?await uploadFile(portrait,'image'):null;
      if(generation!==accountGeneration.current)return;
      id='enroll_'+crypto.randomUUID().replaceAll('-','');
      submitting.current=true;rememberAudioOperation(id);changeAudioRoute({operationId:id},{replace:true});
      setJob(jobState({id,kind:'enrollment',status:'queued'}));
      const value=jobState(await api(`${AUDIO_CENTER_API}/enrollments`,{operation_id:id,name,audio_file:audio,image_file:image,text,max_charge_micros:maximum,confirmed:true,consent:true}));
      if(generation!==accountGeneration.current)return;setJob(value);
      if(!value.unresolved)forgetAudioOperation();
    }catch(e){if(generation!==accountGeneration.current)return;const rejected=id&&[400,401,403,404,415,422].includes(e.status);if(rejected){forgetAudioOperation();changeAudioRoute({operationId:''},{replace:true});}setJob(jobState({id:rejected?undefined:id,kind:'enrollment',status:id&&!rejected?'submission_unknown':'failed',error:id&&!rejected?'原任务编号已保留，请继续原任务核对结果。':rejected?'任务尚未受理，请检查提示后重新确认。':'文件上传未完成，尚未提交克隆或试听。'}));setError(errorText(e));}
    finally{submitting.current=false;}
  });}
  async function quote(operation,trigger) {quoteTrigger.current=trigger||document.activeElement;await task(async () => {
    const generation=accountGeneration.current;
    if (unresolved) throw new Error('已有任务结果待核对，请先查询原任务。');
    const request = makeVoiceQuote('preview', { voice, text, speech_rate: rate });
    if(generation!==accountGeneration.current)throw new Error('账号已切换，请重新选择当前账号的音色。');
    const value = await api(`${AUDIO_CENTER_API}/quotes`, request); if(generation!==accountGeneration.current)return;const maximum = quotedMicros(value);
    if (!value.operation_id) throw new Error('中转站尚未提供可恢复的调用编号，请更新音色服务后重试。');
    setBudget((maximum / 1000000).toFixed(6)); setPayment({ operation, quote: value, label: voice.name });
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
  const operationPanel=job&&<section className="audio-operation" role="status"><strong>{job.kind==='enrollment'&&job.status==='processing'?enrollmentStage[job.stage]||jobLabel(job.status):jobLabel(job.status)}</strong>{job.error&&<p className="helper">{errorText(job.error)}</p>}{job.warning&&<p className="helper">{job.warning}</p>}{job.unresolved&&job.id&&<p className="helper">{job.status==='paused'?'原任务已保存，继续时会复用已完成的音色和试听。':'原任务已保存，关闭弹窗后也会继续；刷新可恢复进度。'}</p>}{job.result?.audio_url&&<audio controls preload="metadata" src={job.result.audio_url} aria-label="音色试听结果"/>}{job.result?.voice&&<p>音色已创建：{job.result.voice.name||'我的音色'}{job.result.image_linked?' · 人物图已关联':''}</p>}<div className="voice-detail-actions">{job.id&&<Button disabled={busy} onClick={()=>readJob(undefined,true)}><RefreshCw size={15}/>{job.kind==='enrollment'&&(job.unresolved||job.warning)?'继续原任务':'查询原任务'}</Button>}{job.result?.voice?.id&&<Button onClick={()=>changeAudioRoute({voiceId:job.result.voice.id})}>查看音色</Button>}</div></section>;
  return <Dialog title="海客配音中心" description="上传声音与可选人物图，一次确认完成克隆和试听。" wide onClose={closeAudioCenter} footer={<><span className="helper">{internal?'设置仅用于本机内部服务。':'设置按当前海客账号保存。'}</span><Button onClick={closeAudioCenter}>完成</Button></>}>
    <div className="audio-center"><Notice message={error} error /><Notice message={notice} />{operationPanel}
      {catalogError ? <VoiceCatalog loadError onRetry={load}/> : loading && !catalog.items.length ? <p role="status" className="helper">正在读取音色…</p> : route.voiceId && voice ? <VoiceDetails voice={voice} isDefault={catalog.preferences.voice_id === voice.id} rate={rate} setRate={setRate} text={text} setText={setText} busy={busy} unresolved={unresolved} onDefault={() => preferences({ voice_id: voice.id })} onSaveRate={() => { const value = Number(rate); if (!Number.isFinite(value) || value < .5 || value > 2) { setError('配音倍率需在0.5至2.0之间。'); return; } preferences({ speech_rate: value }, voice.id); }} onPreview={trigger => quote('preview',trigger)} onImage={image} onUse={useInAvatar} onBack={() => changeAudioRoute({ voiceId: '' })} /> : route.voiceId ? <EmptyState title="当前账号没有这款音色" action={<Button onClick={() => changeAudioRoute({ voiceId: '' })}>返回音色列表</Button>}>音色可能已删除或属于另一个账号。</EmptyState> : <>
        <CloneVoiceForm key={accountGeneration.current} busy={busy} unresolved={unresolved} internal={internal} onCreate={createVoice}/>
        <div className="audio-section-heading"><h3>选择音色</h3><Button variant="text" disabled={busy || loading} onClick={load}><RefreshCw size={15} />刷新</Button></div><VoiceCatalog items={catalog.items} defaultVoiceId={catalog.preferences.voice_id} onOpen={id => changeAudioRoute({ voiceId: id })} />
      </>}
    </div>
    {payment && <Dialog title="确认生成试听" description="确认后才提交本次调用。" busy={busy} returnFocus={quoteTrigger.current} onClose={() => setPayment(null)} footer={<><Button disabled={busy} onClick={() => setPayment(null)}>返回</Button><Button variant="primary" loading={busy} onClick={submit}>确认费用并提交</Button></>}><dl className="summary-list"><div><dt>音色</dt><dd>{payment.label}</dd></div><div><dt>{payment.quote.estimate_only?'采购估算':'报价上限'}</dt><dd>{money(payment.quote.max_charge_micros)}</dd></div></dl><QuoteBilling quote={payment.quote} internal={internal}/><Field label={payment.quote.estimate_only?'本次批准预算（元）':'本次最高费用（元）'} hint={payment.quote.estimate_only?'此预算用于确认采购估算，不代表供应商账单硬封顶。':'达到费用上限将停止，已完成的调用继续保留。'}><input type="text" inputMode="decimal" value={budget} onChange={e => setBudget(e.target.value)} disabled={busy} /></Field><Notice message={error} error /></Dialog>}
  </Dialog>;
}
