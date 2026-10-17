import test from 'node:test';
import assert from 'node:assert/strict';
import { accountsHref,accountsRoute,audioHref, audioRoute, LEGACY_TOOLS, MANAGEMENT_ROUTES } from '../src/studio-routes.js';

test('设置入口和音色详情能够从直接URL恢复，任务编号保留',()=>{
  const location={pathname:'/settings',search:'?panel=audio&voice=private-a&audio_job=call_123'};
  assert.deepEqual(audioRoute(location),{open:true,voiceId:'private-a',operationId:'call_123'});
  assert.equal(audioHref(location,{open:false}),'/settings');
});
test('从口播打开或关闭弹窗保留原有草稿、动效和其他查询参数',()=>{
  const location={pathname:'/avatar',search:'?draft=studio-123&template=card'};
  const opened=audioHref(location,{voiceId:'voice a'});
  assert.equal(opened,'/avatar?draft=studio-123&template=card&panel=audio&voice=voice+a');
  assert.equal(audioHref({pathname:'/avatar',search:opened.slice(opened.indexOf('?'))},{open:false}),'/avatar?draft=studio-123&template=card');
});
test('更多工具按最新范围仅保留项目工作台与素材库',()=>{
  const paths=LEGACY_TOOLS.map(t=>t.path);
  assert.deepEqual(paths,['/legacy/projects','/material-library']);
  assert.equal(new Set(paths).size,paths.length);assert.ok(!paths.includes('/audio'));assert.ok(!paths.includes('/calendar'));
});

test('平台登录弹窗从URL恢复并保留原草稿，关闭清除自身参数',()=>{
  const href=accountsHref({pathname:'/avatar',search:'?draft=studio-123'},{platform:'kuaishou'});
  assert.equal(href,'/avatar?draft=studio-123&panel=accounts&platform=kuaishou');
  const current={pathname:'/avatar',search:href.slice(href.indexOf('?'))};
  assert.deepEqual(accountsRoute(current),{open:true,platform:'kuaishou'});
  assert.equal(accountsHref(current,{open:false}),'/avatar?draft=studio-123');
  assert.equal(accountsRoute({search:'?panel=accounts&platform=unknown'}).platform,'douyin');
});
test('管理区任务总览与作品、发布日历各有单独且唯一的入口',()=>{
  assert.deepEqual(MANAGEMENT_ROUTES,[['/projects','我的作品'],['/task-center','任务总览'],['/calendar','发布日历']]);
  assert.equal(new Set(MANAGEMENT_ROUTES.map(([path])=>path)).size,MANAGEMENT_ROUTES.length);
});
