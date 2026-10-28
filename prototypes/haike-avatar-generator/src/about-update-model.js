const RUNNING = new Set(['downloading', 'waiting', 'installing', 'restarting']);
export const MAX_RECONNECT_ATTEMPTS = 60;

export function versionReadFailure(error) {
  return error?.status === 404
    ? '工作台尚未加载版本信息，请重启此副本工作台后重试。'
    : '暂时无法读取本机版本，请确认工作台服务正常后重试。';
}

export async function readCurrentVersion(request) {
  try {
    const snapshot = await request('/api/studio/app-update');
    if (!snapshot?.current || typeof snapshot.current !== 'object') throw new Error('invalid version response');
    return snapshot;
  } catch (error) {
    throw Object.assign(new Error(versionReadFailure(error)), {scope: 'local-version', status: error?.status});
  }
}

export function aboutRoute(locationLike = {}) {
  return new URLSearchParams(locationLike.search || '').get('panel') === 'about';
}

export function aboutHref(locationLike = {}, open = true) {
  const query = new URLSearchParams(locationLike.search || '');
  if (open) query.set('panel', 'about');
  else if (query.get('panel') === 'about') query.delete('panel');
  return `${locationLike.pathname || '/avatar'}${query.size ? `?${query}` : ''}${locationLike.hash || ''}`;
}

export function updateCompleted(snapshot) {
  const operation = snapshot?.operation;
  return operation?.status === 'complete' && Boolean(operation.target_version) &&
    snapshot?.current?.version === operation.target_version;
}

export function updateActive(snapshot) {
  const status = snapshot?.operation?.status;
  return RUNNING.has(status) || (status === 'complete' && !updateCompleted(snapshot));
}

export function canInstallUpdate(snapshot) {
  return snapshot?.update?.status === 'available' && Boolean(snapshot.update.version) &&
    snapshot.capability?.can_install === true && snapshot.update.can_install !== false &&
    !updateActive(snapshot) && !updateCompleted(snapshot);
}

export function canCancelUpdate(snapshot) {
  return ['downloading', 'waiting'].includes(snapshot?.operation?.status);
}

export function updateStatus(snapshot, {checking = false, disconnected = false, reconnectStopped = false, checkError = '', versionError = ''} = {}) {
  const operation = snapshot?.operation || {};
  const update = snapshot?.update || {};
  if (updateCompleted(snapshot)) return {kind: 'success', title: '更新完成', message: '新版本已启动并通过检查，刷新页面即可使用。'};
  if (updateActive(snapshot)) {
    if (reconnectStopped) return {kind: 'warning', title: '暂时无法连接工作台', message: '尚未确认更新结果。请重新连接查看原更新记录，不要重复安装。'};
    if (disconnected) return {kind: 'working', title: '正在等待工作台重新连接', message: '正在连接工作台并核对原更新记录，请勿重复提交。'};
    const title = {downloading: '正在下载更新', waiting: '等待任务结束', installing: '正在安装更新', restarting: '正在重启并检查工作台', complete: '正在确认新版本'}[operation.status];
    return {kind: 'working', title, message: operation.message || '更新会在后台继续，可以稍后重新打开此窗口查看。'};
  }
  if (operation.status === 'rolled_back') return {kind: 'warning', title: '更新失败，已恢复旧版本', message: operation.message || '旧版本已经恢复，配置、账号和作品保留。请检查更新说明后重试。'};
  if (operation.status === 'failed') return {kind: 'error', title: '更新未完成', message: operation.message || '请重新检查更新，查看当前版本后再试。'};
  if (checking) return {kind: 'working', title: '正在检查更新', message: '正在获取最新稳定版本。'};
  if (versionError) return {kind: 'error', title: '暂时无法读取当前版本', message: versionError};
  if (checkError) return {kind: 'error', title: '暂时无法检查更新', message: checkError};
  if (['cancelled', 'canceled'].includes(operation.status)) return {kind: 'warning', title: '已暂缓更新', message: operation.message || '已暂缓本次更新，原程序与现有任务保持原样。'};
  const title = {available: '发现新版本', current: snapshot?.current?.development ? '未发现更新的稳定版本' : '当前已是最新稳定版', unavailable: '暂时无法检查更新', incompatible: '需要完整升级', unchecked: '尚未检查更新'}[update.status] || '尚未检查更新';
  return {kind: update.status === 'current' ? 'success' : update.status === 'available' ? 'available' : 'warning', title, message: update.message || ''};
}

export function formatUpdateSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '大小待确认';
  const unit = bytes >= 1024 ** 3 ? 'GB' : bytes >= 1024 ** 2 ? 'MB' : 'KB';
  const divisor = unit === 'GB' ? 1024 ** 3 : unit === 'MB' ? 1024 ** 2 : 1024;
  return `${Math.max(0.1, bytes / divisor).toFixed(1)} ${unit}`;
}

export function updateProgress(value) {
  return Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value) : undefined;
}
