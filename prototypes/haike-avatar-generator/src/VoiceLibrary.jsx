import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, AudioLines, Check, CheckCircle2, Clock3, Headphones, Mic2, Pause, Pencil, Play, Plus, RefreshCw, Search, Upload } from 'lucide-react';
import { api } from './studio-api.js';
import { Button, Dialog, EmptyState, Field, Heading, Notice } from './ui.jsx';
import { filterVoices, operationState, voiceLabel } from './voice-model.js';
import './voices.css';

const money = value => `¥${(Number(value || 0) / 1000000).toFixed(6).replace(/0+$/, '').replace(/\.$/, '.00')}`;
const activeStates = new Set(['queued', 'running', 'submitting', 'polling']);
let activePlayer = null;

export function useVoiceLibrary(enabled = true) {
  const [data, setData] = useState(null), [operations, setOperations] = useState([]);
  const [error, setError] = useState(''), [loading, setLoading] = useState(true);
  const ticket = useRef(0);
  const reload = useCallback(async () => {
    const current = ++ticket.current;
    try {
      const jobs = await api('/api/studio/voice-operations');
      const library = await api('/api/studio/voices');
      if (current !== ticket.current) return;
      setData(library); setOperations(jobs.items); setError('');
    } catch (e) {
      if (current === ticket.current) setError(e.message);
    } finally {
      if (current === ticket.current) setLoading(false);
    }
  }, []);
  useEffect(() => { if (enabled) reload(); return () => { ticket.current++; }; }, [reload, enabled]);
  useEffect(() => {
    if (!enabled || !operations.some(item => activeStates.has(item.job?.status))) return;
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [operations, reload, enabled]);
  return { data, operations, loading, error, reload };
}

function CloneForm({ ready, busy, onNext, onCancel, error, initialData }) {
  const [name, setName] = useState(initialData?.name || ''), [language, setLanguage] = useState(initialData?.language || 'zh'), [tag, setTag] = useState(initialData?.tag || '');
  const [file, setFile] = useState(initialData?.file || null), [url, setUrl] = useState(''), [consent, setConsent] = useState(initialData?.consent || false);
  const [sample, setSample] = useState(initialData?.sample || null), [uploading, setUploading] = useState(false), [localError, setLocalError] = useState('');
  const input = useRef(null), fileTicket = useRef(0);
  useEffect(() => {
    if (!file) { setUrl(''); return; }
    const value = URL.createObjectURL(file); setUrl(value);
    return () => URL.revokeObjectURL(value);
  }, [file]);
  async function choose(event) {
    const selected = event.target.files?.[0]; event.target.value = '';
    if (!selected) return;
    const current = ++fileTicket.current;
    setLocalError(''); setSample(null); setFile(null);
    if (!/\.(wav|mp3|m4a)$/i.test(selected.name) || selected.size > 10 * 1024 * 1024) {
      setLocalError('请选择10MB以内的WAV、MP3或M4A录音。'); return;
    }
    setFile(selected); setUploading(true);
    try {
      const response = await fetch(`/api/studio/voices/samples?filename=${encodeURIComponent(selected.name)}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: selected });
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || '录音上传失败，请重试。');
      if (current === fileTicket.current) setSample(value);
    } catch (e) { if (current === fileTicket.current) setLocalError(e.message); }
    finally { if (current === fileTicket.current) setUploading(false); }
  }
  return <form className="voice-clone-form" onSubmit={e => { e.preventDefault(); onNext({ name: name.trim(), sample_id: sample.id, language, tags: tag.trim() ? [tag.trim()] : [], consent }, { name, language, tag, file, sample, consent }); }}>
    <div className="voice-clone-intro"><span className="voice-mark"><Mic2 size={25}/></span><div><h3>把你的声音，变成可反复使用的音色</h3><p>阿里百炼 CosyVoice 克隆 · 完成后仅保存在你的个人库</p></div></div>
    <div className="voice-record-guide"><strong>准备一段10–20秒的清晰朗读</strong><p>单人、自然语速，避免背景音乐、噪音和长停顿。支持5–60秒的WAV、MP3、M4A，最大10MB。</p><blockquote>你好，欢迎来到我的频道。今天想和你分享一个新的想法，希望我的声音能让每一次表达，都更加自然、清晰、有温度。</blockquote></div>
    <Field label="音色名称"><input autoFocus required maxLength={48} value={name} onChange={e => setName(e.target.value)} placeholder="例如：我的日常口播" disabled={busy}/></Field>
    <div className="voice-form-row"><Field label="录音语言"><select value={language} onChange={e => setLanguage(e.target.value)} disabled={busy}><option value="zh">普通话</option><option value="yue">粤语</option><option value="en">英语</option></select></Field><Field label="用途标签（可选）"><input maxLength={12} value={tag} onChange={e => setTag(e.target.value)} placeholder="例如：品牌解说" disabled={busy}/></Field></div>
    <div className={`voice-upload ${sample ? 'ready' : ''}`}><Upload size={23}/><div><strong>{file?.name || '上传参考录音'}</strong><small>{uploading ? '正在检查时长并上传…' : sample ? `${sample.duration.toFixed(1)}秒 · 录音格式检查通过` : '录音会提交阿里百炼，用于创建这一个音色'}</small></div><Button type="button" disabled={busy || uploading} loading={uploading} onClick={() => input.current.click()}>{file ? '更换录音' : '选择文件'}</Button></div>
    <input hidden ref={input} type="file" accept=".wav,.mp3,.m4a" onChange={choose} aria-label="克隆参考录音"/>
    {url && <div className="voice-reference"><span>参考录音试听</span><audio controls src={url}/></div>}
    <label className="checkbox-row voice-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} disabled={busy}/>我拥有此声音素材的使用授权，同意将录音提交阿里百炼用于音色克隆。</label>
    <Notice message={localError || error} error/>
    <div className="voice-form-actions"><Button type="button" onClick={onCancel} disabled={busy}>返回音色库</Button><Button type="submit" variant="primary" loading={busy} disabled={!ready || !name.trim() || !sample || !consent || uploading || busy}>下一步：确认克隆<ArrowRight size={16}/></Button></div>
  </form>;
}

function VoiceGrid({ items, selectedId, playingId, onPlay, onChoose, onRename, busy }) {
  return <div className="voice-grid">{items.map(voice => <article className={`voice-card ${selectedId === voice.id ? 'selected' : ''}`} key={voice.id}>
    <header><span className="voice-mark"><Mic2 size={23}/></span><div><h3>{voice.name}</h3><p>{voiceLabel(voice)} · {voice.scope === 'personal' ? '仅你可见' : '系统音色'}</p></div>{selectedId === voice.id && <span className="voice-selected"><Check size={15}/>已选择</span>}{voice.scope === 'personal' && <button className="voice-edit" title="重命名音色" aria-label={`重命名${voice.name}`} disabled={busy} onClick={() => onRename(voice)}><Pencil size={15}/></button>}</header>
    <div className="voice-tags">{(voice.tags.length ? voice.tags : ['日常口播']).map(tag => <span key={tag}>{tag}</span>)}<span>CosyVoice</span></div>
    <div className="voice-card-status">{voice.status !== 'ready' ? '当前配音配置不可用' : voice.sample_status === 'succeeded' ? <><Headphones size={14}/>已保存试听 · 重复播放无调用费用</> : activeStates.has(voice.sample_status) ? <><Clock3 size={14}/>试听正在生成</> : '首次试听先核对配音费用'}</div>
    <footer><Button disabled={busy || activeStates.has(voice.sample_status) || (voice.status !== 'ready' && voice.sample_status !== 'succeeded')} onClick={() => onPlay(voice)} aria-label={`${playingId === voice.id ? '暂停' : '试听'}${voice.name}`}>{playingId === voice.id ? <Pause size={16}/> : <Play size={16}/>} {playingId === voice.id ? '暂停' : '试听'}</Button><Button variant={selectedId === voice.id ? 'primary' : undefined} disabled={busy || voice.status !== 'ready'} onClick={() => onChoose(voice)}>{selectedId === voice.id ? '选用此音色' : '选择音色'}<ArrowRight size={15}/></Button></footer>
  </article>)}</div>;
}

export function VoiceLibrary({ picker = false, library, selectedId, onChoose, onClose, initialAudition }) {
  const ownLibrary = useVoiceLibrary(!library);
  const current = library || ownLibrary;
  const [scope, setScope] = useState('system'), [search, setSearch] = useState(''), [language, setLanguage] = useState('all');
  const [view, setView] = useState('browse'), [operation, setOperation] = useState(null), [editing, setEditing] = useState(null), [newName, setNewName] = useState('');
  const [cloneDraft, setCloneDraft] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [playingId, setPlayingId] = useState(''), [playerVoice, setPlayerVoice] = useState(null), [pendingPlay, setPendingPlay] = useState('');
  const player = useRef(null), firstPlay = useRef(false);
  const voices = current.data?.items || [], filtered = filterVoices(voices, { scope, search, language });
  const systemCount = voices.filter(v => v.scope === 'system').length, personalCount = voices.filter(v => v.scope === 'personal').length;
  const select = voice => onChoose ? onChoose(voice) : location.assign(`/avatar?tone=${encodeURIComponent(voice.id)}`);
  const closeView = () => { setView('browse'); setError(''); };
  useEffect(() => () => { if (activePlayer === player.current) activePlayer = null; player.current?.pause(); }, []);
  async function play(voice) {
    setError('');
    if (playingId === voice.id && player.current && !player.current.paused) { player.current.pause(); setPlayingId(''); return; }
    if (voice.sample_status === 'succeeded') {
      if (activePlayer && activePlayer !== player.current) activePlayer.pause();
      setPlayerVoice({ ...voice }); setPlayingId(voice.id);
      return;
    }
    setBusy(true);
    try {
      const result = await api('/api/studio/voices/preview-quotes', { voice_id: voice.id });
      if (result.cached) { await current.reload(); setPendingPlay(voice.id); }
      else if (!result.operation) { setMessage('试听正在生成，完成后即可播放。'); }
      else { setOperation(result.operation); setView('preview-confirm'); }
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!playerVoice || !player.current) return;
    const audio = player.current;
    if (activePlayer && activePlayer !== audio) activePlayer.pause();
    activePlayer = audio;
    audio.play().catch(() => { setPlayingId(''); setMessage('试听已准备好，请点击播放器播放。'); });
    return () => { audio.pause(); if (activePlayer === audio) activePlayer = null; };
  }, [playerVoice]);
  useEffect(() => {
    if (!pendingPlay) return;
    const ready = voices.find(v => v.id === pendingPlay && v.sample_status === 'succeeded');
    if (ready) { setPendingPlay(''); setPlayerVoice(ready); setPlayingId(ready.id); }
  }, [voices, pendingPlay]);
  useEffect(() => {
    if (!initialAudition || firstPlay.current || !current.data) return;
    const voice = voices.find(v => v.id === initialAudition);
    if (voice) { firstPlay.current = true; setScope(voice.scope); play(voice); }
  }, [current.data, initialAudition]);
  async function clone(data, remembered) {
    setCloneDraft(remembered);
    setBusy(true); setError('');
    try { setOperation(await api('/api/studio/voices/clone-quotes', data)); setView('clone-confirm'); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function confirm() {
    setBusy(true); setError('');
    try {
      await api(`/api/studio/voice-operations/${operation.id}/confirm`, { confirmed: true });
      if (operation.kind === 'sample') { setPendingPlay(operation.voice_id); setMessage('试听任务已提交，完成后即可播放。'); }
      else { setScope('personal'); setCloneDraft(null); setMessage('克隆任务已提交，完成后会进入你的个人音色库。'); }
      setView('browse'); await current.reload();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function query(item) {
    setBusy(true); setError('');
    try { await api(`/api/studio/voice-operations/${item.id}/query`, {}); await current.reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function rename(e) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api(`/api/studio/voices/${editing.id}/rename`, { name: newName.trim() }); closeView(); await current.reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  const browse = <>
    <div className="voice-toolbar"><div className="voice-tabs" role="group" aria-label="音色来源">{[['system', '系统音色', systemCount], ['personal', '个人音色库', personalCount]].map(([id, name, count]) => <button key={id} aria-pressed={scope === id} className={scope === id ? 'active' : ''} onClick={() => { setScope(id); setSearch(''); }}>{name}<small>{count}</small></button>)}</div><Button variant="primary" disabled={!current.data?.clone_ready || busy} onClick={() => { setView('clone'); setError(''); }}><Plus size={17}/>克隆音色</Button></div>
    <div className="voice-filter"><label className="voice-search"><Search size={18}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索音色名称或标签" aria-label="搜索音色"/></label><select value={language} onChange={e => setLanguage(e.target.value)} aria-label="音色语言"><option value="all">全部语言</option><option value="zh">普通话</option><option value="yue">粤语</option><option value="en">英语</option></select><Button variant="text" disabled={busy} onClick={current.reload} aria-label="刷新音色库"><RefreshCw size={16}/></Button></div>
    <Notice message={current.error || error} error/><Notice message={message}/>
    {current.data?.clone_hint && <Notice message={current.data.clone_hint}/>}
    {!current.loading && !current.data && <EmptyState icon={AudioLines} title="音色库暂时无法连接" action={<Button href="/settings">检查 API 设置<ArrowRight size={16}/></Button>}>连接海客Key后，系统音色和你的个人音色会自动同步。</EmptyState>}
    {current.loading ? <div className="voice-loading" role="status"><AudioLines size={25}/><p>正在读取你的音色库…</p></div> : current.data && (filtered.length ? <VoiceGrid busy={busy} items={filtered} selectedId={selectedId} playingId={playingId} onPlay={play} onChoose={select} onRename={voice => { setEditing(voice); setNewName(voice.name); setView('rename'); setError(''); }}/> : <EmptyState icon={Mic2} title={search || language !== 'all' ? '没有找到匹配的音色' : scope === 'personal' ? '让视频拥有你自己的声音' : '还没有可用的系统音色'} action={scope === 'personal' && !search && <Button disabled={!current.data.clone_ready} onClick={() => setView('clone')}><Plus size={16}/>克隆第一个音色</Button>}>{search || language !== 'all' ? '换一个关键词，或清除语言筛选后再试。' : scope === 'personal' ? '上传一段清晰录音，克隆后的音色只属于你的账户，可反复试听和用于口播。' : '管理员发布可用音色后，会显示在这里。'}</EmptyState>)}
    {current.operations.filter(item => item.job?.status !== 'succeeded').length > 0 && <section className="voice-jobs"><h3>音色任务</h3>{current.operations.filter(item => item.job?.status !== 'succeeded').map(item => <article key={item.id}><Clock3 size={18}/><div><strong>{item.name} · {item.kind === 'clone' ? '音色克隆' : '生成试听'}</strong><p>{operationState(item.job?.status)}</p></div><Button disabled={busy} onClick={() => query(item)}>查询原任务</Button></article>)}</section>}
    {playerVoice && <div className="voice-player"><span className="voice-mark"><Headphones size={20}/></span><div><strong>{playerVoice.name}</strong><small>已保存的合成试听 · 重复播放无调用费用</small></div><audio key={playerVoice.id} ref={player} controls src={playerVoice.sample_url} onPlay={() => { if (activePlayer && activePlayer !== player.current) activePlayer.pause(); activePlayer = player.current; setPlayingId(playerVoice.id); }} onPause={() => setPlayingId('')} onEnded={() => setPlayingId('')} onError={() => { setPlayingId(''); setError('原试听暂时无法播放，请刷新后重试读取原音频。'); }}/></div>}
  </>;
  const confirmation = <div className="voice-confirm"><span className="voice-mark"><CheckCircle2 size={27}/></span><h3>{operation?.kind === 'clone' ? '创建你的专属音色' : '生成一段合成试听'}</h3><dl className="summary-list"><div><dt>音色</dt><dd>{operation?.name}</dd></div><div><dt>本次费用上限</dt><dd className="voice-price">{money(operation?.quote?.max_charge_micros)}</dd></div><div><dt>存放位置</dt><dd>{operation?.kind === 'clone' ? '个人音色库 · 仅你可见' : '音色试听缓存'}</dd></div></dl>{operation?.kind === 'sample' ? <><p className="helper">{current.data?.sample_text}</p><Notice message="本次将调用配音生成试听，按已确认报价结算。生成成功后重复播放不再调用接口。"/></> : <Notice message="CosyVoice 创建音色免费。合成试听和视频配音分别核对费用，克隆完成不会自动发起收费试听。"/>}<Notice message={error} error/><div className="voice-form-actions"><Button disabled={busy} onClick={() => setView(operation?.kind === 'clone' ? 'clone' : 'browse')}>返回修改</Button><Button variant="primary" loading={busy} onClick={confirm}>确认并{operation?.kind === 'clone' ? '克隆' : '生成试听'}<ArrowRight size={16}/></Button></div></div>;
  const renameForm = <form className="voice-clone-form" onSubmit={rename}><Field label="音色名称"><input autoFocus required maxLength={48} value={newName} onChange={e => setNewName(e.target.value)}/></Field><p className="helper">修改名称不会重新克隆，也不会改变已经提交的视频。</p><Notice message={error} error/><div className="voice-form-actions"><Button type="button" onClick={closeView}>取消</Button><Button type="submit" variant="primary" loading={busy} disabled={!newName.trim()}>保存名称</Button></div></form>;
  const form = view === 'clone' ? <CloneForm ready={current.data?.clone_ready} busy={busy} onNext={clone} onCancel={closeView} error={error} initialData={cloneDraft}/> : view === 'rename' ? renameForm : confirmation;
  const title = view === 'browse' ? '选择音色' : view === 'clone' ? '克隆音色' : view === 'rename' ? '重命名音色' : '确认音色操作';
  if (picker) return <Dialog title={title} description={view === 'browse' ? '试听系统音色和你的个人音色，选中后用于当前口播。' : undefined} wide={view === 'browse'} busy={busy} onClose={onClose}><div className="voice-library voice-picker">{view === 'browse' ? browse : form}</div></Dialog>;
  return <><main className="workspace voice-workspace"><Heading title="资源库" helper="管理熟悉的声音，让每一次创作都更自然。"/><section className="surface voice-library"><div className="voice-library-heading"><span className="voice-mark"><AudioLines size={24}/></span><div><h2>音色库</h2><p>系统音色随时选用，专属音色跟随你的海客账户。</p></div><span className="voice-library-tip"><Headphones size={15}/>所有音色均支持试听</span></div>{browse}</section></main>{view !== 'browse' && <Dialog title={title} busy={busy} onClose={closeView}><div className="voice-library">{form}</div></Dialog>}</>;
}

export function Resources() { return <VoiceLibrary/>; }
