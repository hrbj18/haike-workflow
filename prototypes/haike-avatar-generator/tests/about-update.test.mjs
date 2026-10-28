import test from 'node:test';
import assert from 'node:assert/strict';
import {aboutHref, aboutRoute, canCancelUpdate, canInstallUpdate, formatUpdateSize, readCurrentVersion, updateActive, updateCompleted, updateProgress, updateStatus} from '../src/about-update-model.js';

const available = {current: {version: '1.0.0', package_type: 'portable'}, update: {status: 'available', version: '1.0.1', can_install: true}, capability: {can_install: true}, operation: {status: 'idle'}};

test('旧后台404归为本机版本读取失败，并保留正确的重启指引', async () => {
  const calls = [];
  await assert.rejects(readCurrentVersion(async path => {
    calls.push(path);
    throw Object.assign(new Error('Not Found'), {status: 404});
  }), error => error.scope === 'local-version' && error.status === 404 && error.message.includes('重启此副本工作台'));
  assert.deepEqual(calls, ['/api/studio/app-update']);
  assert.equal(updateStatus(null, {versionError: '请重启此副本工作台'}).title, '暂时无法读取当前版本');
  assert.equal(await readCurrentVersion(async () => available), available);
  await assert.rejects(readCurrentVersion(async () => ({detail: 'not a version response'})), error => error.scope === 'local-version');
});

test('关于弹窗保留草稿、制作模式、其他参数与hash，关闭不导航离开当前页面', () => {
  const location = {pathname: '/avatar', search: '?draft=studio-123&mode=motion&template=card', hash: '#editor'};
  const opened = aboutHref(location);
  assert.equal(opened, '/avatar?draft=studio-123&mode=motion&template=card&panel=about#editor');
  const url = new URL(opened, 'http://127.0.0.1');
  assert.equal(aboutRoute(url), true);
  assert.equal(aboutHref(url, false), '/avatar?draft=studio-123&mode=motion&template=card#editor');
  assert.equal(aboutHref({pathname: '/settings', search: '?panel=audio&voice=public-a'}, false), '/settings?panel=audio&voice=public-a');
});

test('一键更新同时要求真实可用版本与安装能力，源码、未知状态和进行中任务不允许提交', () => {
  assert.equal(canInstallUpdate(available), true);
  assert.equal(canInstallUpdate({...available, capability: {can_install: false}}), false);
  for (const status of ['unchecked', 'current', 'unavailable', 'incompatible']) {
    assert.equal(canInstallUpdate({...available, update: {...available.update, status}}), false, status);
  }
  for (const status of ['downloading', 'waiting', 'installing', 'restarting']) {
    assert.equal(canInstallUpdate({...available, operation: {status}}), false, status);
  }
  assert.equal(canInstallUpdate({...available, update: {status: 'available'}}), false);
  assert.equal(canInstallUpdate({...available, update: {...available.update, can_install: false}}), false);
});

test('只有服务实际运行目标版本才显示更新完成，旧版本complete保持核对而非提前刷新', () => {
  const completed = {...available, operation: {status: 'complete', target_version: '1.0.1'}};
  assert.equal(updateCompleted(completed), false);
  assert.equal(updateActive(completed), true);
  assert.equal(updateStatus(completed).title, '正在确认新版本');
  const verified = {...completed, current: {...completed.current, version: '1.0.1'}};
  assert.equal(updateCompleted(verified), true);
  assert.equal(updateActive(verified), false);
  assert.equal(updateStatus(verified).title, '更新完成');
  assert.equal(canInstallUpdate(verified), false);
  assert.equal(updateCompleted({...verified, operation: {status: 'complete'}}), false);
});

test('检查失败覆盖旧检查成功信息，断线和回退不被误报为最新版本或成功', () => {
  const current = {...available, update: {status: 'current', message: '当前已是最新稳定版'}};
  assert.equal(updateStatus(current, {checkError: '网络不可用'}).title, '暂时无法检查更新');
  assert.equal(updateStatus(current, {checking: true}).title, '正在检查更新');
  const restarting = {...current, operation: {status: 'restarting'}};
  assert.equal(updateStatus(restarting, {disconnected: true}).title, '正在等待工作台重新连接');
  assert.equal(updateStatus(restarting, {reconnectStopped: true}).title, '暂时无法连接工作台');
  assert.match(updateStatus({...current, operation: {status: 'rolled_back'}}).title, /已恢复旧版本/);
  assert.equal(updateStatus({...current, operation: {status: 'failed'}}).title, '更新未完成');
});

test('下载大小和进度只显示有效证据，不把缺失数据写成零或虚构百分比', () => {
  assert.equal(formatUpdateSize(28 * 1024 ** 2), '28.0 MB');
  assert.equal(formatUpdateSize(1.5 * 1024 ** 3), '1.5 GB');
  for (const size of [null, undefined, NaN, -1, 0, '100']) assert.equal(formatUpdateSize(size), '大小待确认');
  assert.equal(updateProgress(35.5), 36);
  for (const value of [undefined, null, -1, 101, NaN, '100']) assert.equal(updateProgress(value), undefined);
});

test('只允许下载和等待阶段暂缓，暂缓成功后可重新检查和发起更新', () => {
  for (const status of ['downloading', 'waiting']) assert.equal(canCancelUpdate({...available, operation: {status}}), true);
  for (const status of ['idle', 'installing', 'restarting', 'complete', 'failed', 'rolled_back', 'cancelled']) assert.equal(canCancelUpdate({...available, operation: {status}}), false);
  const cancelled = {...available, operation: {status: 'cancelled', message: '已暂缓本次更新，原程序与现有任务保持原样。'}};
  assert.equal(updateActive(cancelled), false);
  assert.equal(updateCompleted(cancelled), false);
  assert.equal(canInstallUpdate(cancelled), true);
  assert.equal(updateStatus(cancelled).title, '已暂缓更新');
  assert.equal(updateStatus(cancelled, {checking: true}).title, '正在检查更新');
});
