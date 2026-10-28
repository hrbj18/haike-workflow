import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const require = createRequire(import.meta.url);
const result = await build({entryPoints: [fileURLToPath(new URL('../src/AboutDialog.jsx', import.meta.url))], bundle: true, write: false, format: 'cjs', platform: 'node', packages: 'external', jsx: 'automatic', loader: {'.css': 'empty'}});
const compiled = {exports: {}};
new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, compiled, compiled.exports);
const {AboutUpdateContent, AboutUpdateActions} = compiled.exports;
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const available = {current: {version: '1.0.0', package_type: 'portable', channel: 'stable', source_commit: 'abcdef1234567890', template_update: {id: 'template-test'}}, update: {status: 'available', version: '1.0.1', published_at: '2026-10-28T02:00:00Z', size: 28 * 1024 ** 2, notes: '新增模板\n修复进度显示'}, capability: {can_install: true}, operation: {status: 'idle'}};

test('本地版本接口失败后停止读取提示，并明确提示重启工作台而非检查外网', () => {
  const html = render(AboutUpdateContent, {snapshot: null, checking: false, versionError: '工作台尚未加载版本信息，请重启此副本工作台后重试。'});
  assert.match(html, /版本读取失败/);
  assert.match(html, /暂时无法读取当前版本/);
  assert.match(html, /重启此副本工作台/);
  assert.ok(!html.includes('正在读取版本'));
  assert.ok(!html.includes('检查网络连接'));
});

test('关于页清晰展示当前版本、更新说明、实际大小、补丁和数据保留说明', () => {
  const html = render(AboutUpdateContent, {snapshot: available});
  for (const phrase of ['海客视频', 'v1.0.0', '稳定版', 'v1.0.1', '新增模板', '28.0 MB', '2026/10/28', '配置、平台账号、素材和作品', 'template-test', 'abcdef123456']) assert.ok(html.includes(phrase), phrase);
  assert.ok(!html.includes('abcdef1234567890'));
  assert.match(render(AboutUpdateActions, {snapshot: available}), /下载并更新/);
});

test('源码开发副本显示本地修改与原因，不提供自动覆盖按钮', () => {
  const snapshot = {...available, current: {...available.current, package_type: 'source', development: true, dirty: true}, capability: {can_install: false, reason: '源码开发副本有本地修改，请通过版本管理升级。'}};
  const html = render(AboutUpdateContent, {snapshot});
  for (const phrase of ['开发版', '源码开发副本', '有本地修改', '通过版本管理升级']) assert.ok(html.includes(phrase), phrase);
  assert.ok(!render(AboutUpdateActions, {snapshot}).includes('下载并更新'));
});

test('检查异常不会留下已是最新的绿灯文案，发行说明按纯文本显示', () => {
  const html = render(AboutUpdateContent, {snapshot: {...available, update: {status: 'current', notes: '<script>alert(1)</script>'}}, checkError: '检查连接后重试'});
  assert.match(html, /暂时无法检查更新/);
  assert.ok(!html.includes('当前已是最新稳定版'));
  const notes = render(AboutUpdateContent, {snapshot: {...available, update: {...available.update, notes: '<script>alert(1)</script>'}}});
  assert.ok(!notes.includes('<script>')); assert.match(notes, /&lt;script&gt;/);
  assert.match(render(AboutUpdateActions, {snapshot: available, checkError: '连接不可用'}), /disabled=""[^>]*>[\s\S]*?下载并更新/);
});

test('安装确认需要手工保存确认，不在渲染中发起操作', () => {
  let installs = 0;
  const pending = render(AboutUpdateActions, {snapshot: available, confirmation: true, onConfirmInstall: () => installs++});
  assert.match(pending, /disabled=""[^>]*>确认更新并重启/);
  assert.match(pending, /暂不更新/);
  const confirmed = render(AboutUpdateActions, {snapshot: available, confirmation: true, savedConfirmed: true});
  assert.ok(!confirmed.includes('disabled=""'));
  assert.equal(installs, 0);
});

test('重启时仅允许等待和重新连接，只有新版本确认完成才提供刷新按钮', () => {
  const restarting = {...available, operation: {status: 'restarting', target_version: '1.0.1'}};
  const waiting = render(AboutUpdateActions, {snapshot: restarting});
  assert.match(waiting, /更新在后台继续/); assert.ok(!waiting.includes('下载并更新')); assert.ok(!waiting.includes('刷新页面'));
  assert.match(render(AboutUpdateActions, {snapshot: restarting, reconnectStopped: true}), /重新连接/);
  const complete = {...restarting, operation: {status: 'complete', target_version: '1.0.1'}};
  assert.ok(!render(AboutUpdateActions, {snapshot: complete}).includes('刷新页面'));
  assert.match(render(AboutUpdateActions, {snapshot: {...complete, current: {...complete.current, version: '1.0.1'}}}), /刷新页面使用新版/);
});

test('回退结果与不确定进度分别呈现，不编造成功或百分比', () => {
  const rolledBack = render(AboutUpdateContent, {snapshot: {...available, operation: {status: 'rolled_back'}}});
  assert.match(rolledBack, /更新失败，已恢复旧版本/); assert.ok(!rolledBack.includes('新版本已启动'));
  const progress = render(AboutUpdateContent, {snapshot: {...available, operation: {status: 'downloading'}}});
  assert.match(progress, /<progress/); assert.ok(!progress.includes('%')); assert.ok(!progress.includes('value="0"'));
});

test('暂缓按钮仅在下载和等待出现，结果未知时禁用并查询，暂缓后恢复检查与安装', () => {
  let cancellations = 0;
  for (const status of ['downloading', 'waiting']) {
    const snapshot = {...available, operation: {status}};
    assert.match(render(AboutUpdateActions, {snapshot, onCancelUpdate: () => cancellations++}), /暂缓更新/);
    assert.match(render(AboutUpdateActions, {snapshot, cancelPending: true}), /disabled=""[^>]*>[\s\S]*?正在核对暂缓请求/);
  }
  for (const status of ['installing', 'restarting']) assert.ok(!render(AboutUpdateActions, {snapshot: {...available, operation: {status}}}).includes('暂缓更新'));
  const cancelled = {...available, operation: {status: 'cancelled', message: '已暂缓本次更新，原程序与现有任务保持原样。'}};
  const content = render(AboutUpdateContent, {snapshot: cancelled});
  assert.match(content, /已暂缓更新/); assert.match(content, /原程序与现有任务保持原样/); assert.ok(!content.includes('更新完成'));
  const actions = render(AboutUpdateActions, {snapshot: cancelled});
  assert.match(actions, /检查更新/); assert.match(actions, /下载并更新/); assert.ok(!actions.includes('暂缓更新'));
  assert.equal(cancellations, 0);
});
