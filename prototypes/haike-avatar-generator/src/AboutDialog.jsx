import {useEffect, useRef, useState} from 'react';
import {CheckCircle2, Download, Info, RefreshCw, ShieldCheck} from 'lucide-react';
import {Button, Dialog} from './ui.jsx';
import {api} from './studio-api.js';
import {MAX_RECONNECT_ATTEMPTS, canCancelUpdate, canInstallUpdate, formatUpdateSize, readCurrentVersion, updateActive, updateCompleted, updateProgress, updateStatus, versionReadFailure} from './about-update-model.js';
import './about-update.css';

const endpoint = '/api/studio/app-update';
const noop = () => {};
const checkFailure = '请检查网络连接后重试；本次尚未确认是否为最新版本。';

function releaseDate(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleDateString('zh-CN', {timeZone: 'Asia/Shanghai'}) : '';
}

export function AboutUpdateContent({snapshot, checking = false, checkError = '', versionError = '', disconnected = false, reconnectStopped = false}) {
  const current = snapshot?.current || {}, update = snapshot?.update || {}, operation = snapshot?.operation || {};
  const status = updateStatus(snapshot, {checking, checkError, versionError, disconnected, reconnectStopped});
  const active = updateActive(snapshot), progress = updateProgress(operation.progress);
  const template = typeof current.template_update === 'string' ? current.template_update : current.template_update?.id;
  const date = releaseDate(update.published_at);
  const notes = Array.isArray(update.notes) ? update.notes.join('\n') : typeof update.notes === 'string' ? update.notes : '';
  return <div className="about-update-content">
    <div className="about-product"><div className="about-product-icon"><Info size={26} aria-hidden="true"/></div><div><strong>海客视频</strong><p>选模板、做视频、按计划发布</p></div></div>
    <div className="about-version"><span>当前版本</span><strong>{current.version ? `v${current.version}` : checking ? '正在读取版本' : versionError || checkError ? '版本读取失败' : '版本信息未记录'}</strong>{current.version && <small>{current.development || current.package_type === 'source' ? '开发版' : current.channel === 'stable' ? '稳定版' : '预览版'}</small>}</div>
    <section className={`about-update-status ${status.kind}`} aria-live="polite" role={status.kind === 'error' ? 'alert' : 'status'}>
      <div className="about-status-heading">{status.kind === 'success' ? <CheckCircle2 size={19} aria-hidden="true"/> : <RefreshCw size={18} className={status.kind === 'working' ? 'spinner' : ''} aria-hidden="true"/>}<strong>{status.title}{update.status === 'available' && !active && !checking && !checkError && !updateCompleted(snapshot) ? ` v${update.version}` : ''}</strong></div>
      {status.message && <p>{status.message}</p>}
      {active && operation.status === 'downloading' && <div className="about-download-progress"><progress aria-label="更新包下载进度" max={100} value={progress}/>{progress !== undefined && <span>{progress}%</span>}</div>}
    </section>
    {update.version && update.status !== 'current' && <section className="about-release-notes" aria-label="版本更新说明"><h3>版本更新说明 <span>v{update.version}</span></h3>{(date || update.size > 0) && <p className="helper">{date ? `发布时间：${date}` : ''}{date && update.size > 0 ? ' · ' : ''}{update.size > 0 ? `更新包：${formatUpdateSize(update.size)}` : ''}</p>}<p>{notes || '本次更新暂未提供详细说明。'}</p></section>}
    <p className="about-preservation"><ShieldCheck size={18} aria-hidden="true"/>更新保留配置、平台账号、素材和作品；安装失败时自动恢复旧版本。</p>
    {snapshot?.capability?.reason && !snapshot.capability.can_install && <p className="about-update-hint">{snapshot.capability.reason}</p>}
    {current.version && <details className="about-build-details"><summary>版本详情</summary><dl><div><dt>安装类型</dt><dd>{current.package_type === 'portable' ? '便携安装' : '源码开发副本'}</dd></div>{current.source_commit && <div><dt>构建编号</dt><dd>{String(current.source_commit).slice(0, 12)}</dd></div>}{(current.dirty || current.local_changes) && <div><dt>本地状态</dt><dd>有本地修改</dd></div>}{template && <div><dt>模板补丁</dt><dd>{template}</dd></div>}</dl></details>}
  </div>;
}

export function AboutUpdateActions({snapshot, checking = false, submitting = false, canceling = false, cancelPending = false, checkError = '', confirmation = false, savedConfirmed = false, reconnectStopped = false, onClose = noop, onCheck = noop, onRequestInstall = noop, onConfirmInstall = noop, onCancelInstall = noop, onCancelUpdate = noop, onReconnect = noop, onReload = noop}) {
  const active = updateActive(snapshot);
  const installLabel = snapshot?.update?.source === 'local' ? '安装更新包' : '下载并更新';
  if (confirmation) return <><Button onClick={onCancelInstall} disabled={submitting}>暂不更新</Button><Button variant="primary" onClick={onConfirmInstall} loading={submitting} disabled={!savedConfirmed}>确认更新并重启</Button></>;
  return <><Button onClick={onClose} disabled={submitting}>关闭</Button>{updateCompleted(snapshot) ? <Button variant="primary" onClick={onReload}>刷新页面使用新版</Button> : active ? <>{canCancelUpdate(snapshot) && <Button onClick={onCancelUpdate} loading={canceling || cancelPending} disabled={submitting}>{cancelPending ? '正在核对暂缓请求' : '暂缓更新'}</Button>}{reconnectStopped ? <Button variant="primary" onClick={onReconnect}>重新连接</Button> : <span className="helper about-background-note">更新在后台继续</span>}</> : <><Button onClick={onCheck} loading={checking} disabled={submitting}><RefreshCw size={16}/>检查更新</Button>{canInstallUpdate(snapshot) && <Button variant="primary" onClick={onRequestInstall} disabled={checking || submitting || Boolean(checkError)}><Download size={16}/>{installLabel}</Button>}</>}</>;
}

export function AboutDialog({onClose}) {
  const [snapshot, setSnapshot] = useState(null), [checking, setChecking] = useState(true), [checkError, setCheckError] = useState('');
  const [versionError, setVersionError] = useState('');
  const [confirmation, setConfirmation] = useState(false), [savedConfirmed, setSavedConfirmed] = useState(false), [submitting, setSubmitting] = useState(false);
  const [canceling, setCanceling] = useState(false), [cancelPending, setCancelPending] = useState(false);
  const [disconnected, setDisconnected] = useState(false), [reconnectStopped, setReconnectStopped] = useState(false), [pollEpoch, setPollEpoch] = useState(0);
  const alive = useRef(true), requestId = useRef(0);
  const active = updateActive(snapshot);

  async function check(force = true) {
    const id = ++requestId.current;
    setChecking(true); setCheckError(''); setVersionError(''); setConfirmation(false); setSavedConfirmed(false);
    try {
      const existing = await readCurrentVersion(api);
      if (!alive.current || id !== requestId.current) return;
      setSnapshot(existing);
      if (updateActive(existing)) return;
      if (!force && existing.update?.source === 'local' && existing.update.status === 'available') return;
      const result = await api(`${endpoint}/check`, {});
      if (alive.current && id === requestId.current) setSnapshot(result);
    } catch (error) {
      if (alive.current && id === requestId.current) {
        if (error.scope === 'local-version' || error.status === 404) setVersionError(error.scope === 'local-version' ? error.message : versionReadFailure(error));
        else setCheckError(checkFailure);
      }
    } finally {
      if (alive.current && id === requestId.current) setChecking(false);
    }
  }

  useEffect(() => {
    alive.current = true; void check(false);
    return () => {alive.current = false; ++requestId.current;};
  }, []);

  async function importPackage(event) {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    if (file.size > 300000000) {setCheckError('更新包不能超过300 MB。'); return;}
    const id = ++requestId.current;
    setChecking(true); setCheckError(''); setConfirmation(false); setSavedConfirmed(false);
    try {
      const response = await fetch(`${endpoint}/import`, {method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || '更新包检查未通过');
      if (alive.current && id === requestId.current) setSnapshot(value);
    } catch (error) {
      if (alive.current && id === requestId.current) setCheckError(error.message || '更新包导入失败，请重试。');
    } finally {
      if (alive.current && id === requestId.current) setChecking(false);
    }
  }

  useEffect(() => {
    if (!active || reconnectStopped) return;
    let disposed = false, timer, failures = 0;
    const poll = async () => {
      try {
        const result = await api(endpoint);
        if (disposed) return;
        failures = 0; setDisconnected(false); setCancelPending(false); setSnapshot(result);
        if (!updateActive(result)) return;
      } catch {
        if (disposed) return;
        setDisconnected(true);
        if (++failures >= MAX_RECONNECT_ATTEMPTS) {setReconnectStopped(true); return;}
      }
      timer = setTimeout(poll, 2000);
    };
    timer = setTimeout(poll, 1000);
    return () => {disposed = true; clearTimeout(timer);};
  }, [active, reconnectStopped, pollEpoch]);

  async function install() {
    if (!savedConfirmed || submitting || !canInstallUpdate(snapshot)) return;
    const previous = snapshot;
    setSubmitting(true); setConfirmation(false); setCheckError(''); setDisconnected(false); setReconnectStopped(false);
    // A lost submission response is uncertain. Poll the durable operation;
    // never repeat the POST automatically after the service disconnects.
    setSnapshot({...snapshot, operation: {status: 'restarting', target_version: snapshot.update.version, message: '正在提交并核对更新请求。'}});
    try {
      const result = await api(`${endpoint}/install`, {version: previous.update.version, confirmed: true});
      if (alive.current) setSnapshot(result);
    } catch (error) {
      if (!alive.current) return;
      if (error.status >= 400 && error.status < 500) {
        setSnapshot(previous); setCheckError('当前任务、版本或安装条件已变化，请重新检查更新后再试。');
      } else setDisconnected(true);
    } finally {
      if (alive.current) setSubmitting(false);
    }
  }

  async function cancelUpdate() {
    if (!canCancelUpdate(snapshot) || canceling || cancelPending) return;
    setCanceling(true);
    try {
      const result = await api(`${endpoint}/cancel`, {});
      if (alive.current) {setSnapshot(result); setCancelPending(false);}
    } catch {
      if (!alive.current) return;
      // Installation may have started while the cancellation was in flight.
      // Only GET the durable state; do not repeat an uncertain cancel POST.
      setCancelPending(true); setDisconnected(true); setReconnectStopped(false); setPollEpoch(value => value + 1);
    } finally {
      if (alive.current) setCanceling(false);
    }
  }

  return <Dialog title="关于海客视频" description="版本信息与程序更新" onClose={onClose} busy={submitting} footer={<AboutUpdateActions snapshot={snapshot} checking={checking} submitting={submitting} canceling={canceling} cancelPending={cancelPending} checkError={checkError || versionError} confirmation={confirmation} savedConfirmed={savedConfirmed} reconnectStopped={reconnectStopped} onClose={onClose} onCheck={check} onRequestInstall={() => {setSavedConfirmed(false); setConfirmation(true);}} onConfirmInstall={install} onCancelInstall={() => setConfirmation(false)} onCancelUpdate={cancelUpdate} onReconnect={() => {setReconnectStopped(false); setPollEpoch(value => value + 1);}} onReload={() => window.location.reload()}/> }>
    <AboutUpdateContent snapshot={snapshot} checking={checking} checkError={checkError} versionError={versionError} disconnected={disconnected} reconnectStopped={reconnectStopped}/>
    {snapshot?.capability?.can_install && !active && !confirmation && <label className="about-local-import">导入已下载的更新包（ZIP，300 MB以内）<input aria-label="选择本地程序更新包" type="file" accept=".zip,application/zip" disabled={checking || submitting} onChange={importPackage}/><span className="helper">检查通过后再确认安装，无需重新下载运行依赖。</span></label>}
    {confirmation && <section className="about-install-confirmation" aria-label="确认程序更新"><h3>准备更新到 v{snapshot.update.version}</h3><p>请先保存当前正在编辑的草稿。更新会等待制作、下载和发布任务结束，再备份程序、安装并重启工作台。</p><p>配置、账号和作品会保留；安装或启动检查失败时恢复旧版本。</p><label className="checkbox-row"><input type="checkbox" checked={savedConfirmed} onChange={event => setSavedConfirmed(event.target.checked)}/>我已保存当前工作，可以更新并重启</label></section>}
  </Dialog>;
}
