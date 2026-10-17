import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {LOGIN_PREVIEW_RETRY_LIMIT,downloadJob,downloadStatusLabel,loginPreviewImage,loginPreviewRetryDelay,networkDownloadPayload,networkJobUrl,normalizeDownloadSessions,registeredMediaCount,savedNetworkJob,scopeLabel,sessionObservability,sourceLink,sourcePlatform} from '../src/network-materials-model.js';

const uuid='0e81dd21-2431-4cce-9c6d-d729435ac4e1';
const accounts=normalizeDownloadSessions({available:true,items:[{id:12,platform:'douyin',name:'测试抖音号',download_status:'available',publish_status:'login_required',publish_checked_at:new Date().toISOString(),cookie:'DO_NOT_EXPOSE_COOKIE',storage_state:'DO_NOT_EXPOSE_STATE',profile_dir:'PRIVATE_PROFILE'}]});

test('下载和发布分别归一，未知证据不会成为可用，凭据不进入前端账号模型',()=>{
  assert.equal(accounts[0].download_status,'available');assert.equal(accounts[0].publish_status,'login_required');
  for(const secret of ['cookie','storage_state','profile_dir'])assert.equal(secret in accounts[0],false);
  assert.equal(scopeLabel('active'),'待确认');
  assert.equal(normalizeDownloadSessions({items:[{id:2,name:'未知'}]})[0].download_status,'unconfirmed');
  assert.throws(()=>normalizeDownloadSessions({available:false,items:[]}),/暂时不可用/);
  assert.throws(()=>normalizeDownloadSessions({error:'offline'}),/返回不完整/);
});

test('分享文案提取链接并按真实域名识别平台',()=>{
  assert.equal(sourceLink('复制此链接 https://v.douyin.com/AbC/ 查看视频。'),'https://v.douyin.com/AbC/');
  assert.equal(sourcePlatform('https://v.douyin.com/AbC/'),'douyin');
  assert.equal(sourcePlatform('https://www.kuaishou.com/short-video/123'),'kuaishou');
  assert.equal(sourcePlatform('https://xhslink.com/a/123'),'xhs');
  assert.equal(sourcePlatform('https://channels.weixin.qq.com/platform/post/list'),'shipinhao');
  assert.equal(sourcePlatform('https://douyin.com.example.org/path'),'');
  assert.throws(()=>sourceLink('file:///C:/Cookies'),/完整/);
  assert.throws(()=>sourceLink('https://user:password@v.douyin.com/a'),/不含账号密码/);
});

test('下载请求要求同平台真实可用会话、使用权和固定任务编号',()=>{
  const input={url:' https://v.douyin.com/AbC/ ',accountId:'12',rightsConfirmed:true,clientRequestId:uuid};
  assert.deepEqual(networkDownloadPayload(input,accounts),{url:'https://v.douyin.com/AbC/',account_id:12,quality:'highest',rights_confirmed:true,client_request_id:uuid});
  assert.deepEqual(networkDownloadPayload(input,accounts),networkDownloadPayload(input,accounts),'恢复提交继续使用原UUID');
  assert.throws(()=>networkDownloadPayload({...input,rightsConfirmed:false},accounts),/有权/);
  assert.throws(()=>networkDownloadPayload({...input,url:'https://v.kuaishou.com/abc'},accounts),/平台不一致/);
  assert.throws(()=>networkDownloadPayload(input,[{...accounts[0],download_status:'unconfirmed'}]),/尚未确认/);
  assert.throws(()=>networkDownloadPayload({...input,quality:'4k'},accounts),/清晰度/);
  assert.throws(()=>networkDownloadPayload({...input,clientRequestId:''},accounts),/任务编号/);
});

test('下载完成只按真实登记结果计数，未知/失败不会伪装完成',()=>{
  const job=downloadJob({id:uuid,status:'completed',result:{media_count:2,items:[{id:'a'},{id:'b'}]}});
  assert.equal(job.completed,true);assert.equal(registeredMediaCount(job),2);
  assert.equal(registeredMediaCount(downloadJob({id:uuid,status:'completed'})),null);
  const unknown=downloadJob({id:uuid,status:'submission_unknown'});
  assert.equal(unknown.active,false);assert.equal(unknown.terminal,false);assert.equal(unknown.completed,false);
  assert.equal(downloadStatusLabel(unknown.status),'结果待核对');
  assert.equal(downloadJob({id:uuid,status:'login_required'}).terminal,true);
  assert.throws(()=>downloadJob({status:'completed'}),/任务编号/);
});

test('URL保留下载编号及原页面参数，刷新恢复同任务',()=>{
  const route=networkJobUrl({href:'http://127.0.0.1:14756/material-library?query=test#details'},uuid);
  assert.equal(savedNetworkJob(route.split('?')[1].split('#')[0]),uuid);
  assert.match(route,/query=test/);assert.match(route,/#details$/);
  assert.equal(networkJobUrl({href:`http://localhost/material-library?query=test&network_job=${uuid}`},''),'/material-library?query=test');
});

const require=createRequire(import.meta.url),root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const result=await build({entryPoints:[resolve(root,'src/NetworkMaterials.jsx')],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
const compiled={exports:{}};
new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {DownloadSessionsList,NetworkDownloadJob,NetworkMaterials,LoginPagePreview,SessionMaintenance}=compiled.exports;

test('账号界面只显示分scope状态和扫码入口，不展示或要求粘贴Cookie',()=>{
  let actions=0;const noop=()=>actions++;
  const markup=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items:[{...accounts[0],cookie:'DO_NOT_EXPOSE_COOKIE',storage_state:'DO_NOT_EXPOSE_STATE',profile_dir:'PRIVATE_PROFILE'}],onCheck:noop,onLogin:noop,onSelect:noop}));
  for(const label of ['素材下载','视频发布','需要登录','检查登录','打开浏览器登录','用于素材下载','下载凭据保存','下载登录检查','最近发布登录检查','会话检查点','最近后台检查','最早检查窗口'])assert.ok(markup.includes(label),label);
  for(const privateValue of ['DO_NOT_EXPOSE_COOKIE','DO_NOT_EXPOSE_STATE','PRIVATE_PROFILE','<textarea','type="password"'])assert.ok(!markup.includes(privateValue),privateValue);
  assert.equal(actions,0);
});

test('账号读取失败保持未知，不冒充零账号或可用状态',()=>{
  const markup=renderToStaticMarkup(React.createElement(DownloadSessionsList,{loadError:true,onRetry:()=>{}}));
  assert.match(markup,/暂时无法读取账号状态/);assert.ok(!markup.includes('还没有平台账号'));
  const unknown=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items:[{id:7,platform:'kuaishou',name:'待查账号'}]}));
  assert.match(unknown,/待检查/);assert.match(unknown,/disabled=""[^>]*>用于素材下载/);
});
test('已保存未验证和检查证据更新显示待确认，不被解释为登录已失效',()=>{
  const items=normalizeDownloadSessions({available:true,items:[{id:7,platform:'shipinhao',name:'测试视频号',download_status:'stored_unverified',publish_status:'unconfirmed'}]});
  assert.equal(items[0].download_status,'unconfirmed');assert.equal(items[0].publish_status,'unconfirmed');
  const markup=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items,onCheck:()=>{},onLogin:()=>{},onSelect:()=>{}}));
  for(const phrase of ['待确认不等于已退出登录','检查证据需要更新','请先检查登录，平台要求时再扫码'])assert.ok(markup.includes(phrase),phrase);
  assert.ok(!markup.includes('已失效'));assert.ok(!markup.includes('需要登录'));assert.ok(!markup.includes('可用</strong>'));
  const ready=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items:[{...items[0],download_status:'available',publish_status:'available',download_check_status:'available',publish_check_status:'available',download_checked_at:new Date().toISOString(),publish_checked_at:new Date().toISOString()}]}));
  assert.ok(!ready.includes('待确认不等于已退出登录'));
});

test('持久检查记录与即时操作状态分别保留，旧API无新增字段时兼容原记录',()=>{
  const checked=new Date(Date.now()-60*60*1000).toISOString();
  const item=normalizeDownloadSessions({items:[{id:12,platform:'douyin',download_status:'unconfirmed',publish_status:'unconfirmed',
    download_check_status:'available',download_checked_at:checked,publish_check_status:'available',publish_checked_at:checked,last_checked_at:null}]})[0];
  assert.equal(item.download_check_status,'available');assert.equal(item.download_checked_at,checked);assert.equal(item.publish_check_status,'available');assert.equal(item.publish_checked_at,checked);
  assert.equal(item.download_status,'unconfirmed');assert.equal(item.publish_status,'unconfirmed');
  const html=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items:[item]}));
  assert.equal((html.match(/最近检查正常/g)||[]).length,2);assert.match(html,/disabled=""[^>]*>用于素材下载/);
  assert.throws(()=>networkDownloadPayload({url:'https://v.douyin.com/AbC/',accountId:'12',rightsConfirmed:true,clientRequestId:uuid},[item]),/尚未确认/);
  const legacy=normalizeDownloadSessions({items:[{id:12,download_status:'available',last_checked_at:checked,publish_status:'login_required',publish_checked_at:checked}]})[0];
  assert.equal(legacy.download_check_status,'available');assert.equal(legacy.download_checked_at,checked);assert.equal(legacy.publish_check_status,'login_required');
  const missing=normalizeDownloadSessions({items:[{id:12,download_status:'available',last_checked_at:checked,download_check_status:null,download_checked_at:null,publish_status:'available',publish_check_status:null}]})[0];
  assert.equal(missing.download_check_status,'unconfirmed');assert.equal(missing.download_checked_at,null);assert.equal(missing.publish_check_status,'unconfirmed');
});
test('会话检查点、后台检查和账号活跃分别显示，下一窗口明确不保证准时执行',()=>{
  const observation={checkpoint_at:'2026-10-16T01:00:00Z',background_health_checked_at:'2026-10-16T02:00:00Z',
    background_health_outcome:'verified',account_last_active_at:'2026-10-16T03:00:00Z',cookie:'SECRET_COOKIE',profile:'SECRET_PROFILE',
    keepalive:{configured:true,engine_running:true,mode:'keepalive',idle_hours:6,check_interval_seconds:1800,jitter_ratio:.15,next_eligible_at:'2026-10-16T09:00:00Z',schedule_status:'waiting',proxy:'SECRET_PROXY'}};
  const normalized=normalizeDownloadSessions({available:true,items:[{id:7,platform:'shipinhao',login_record_saved:true,publish_saved:true,publish_status:'stored_unverified',observability:observation}]})[0];
  assert.ok(!JSON.stringify(normalized).includes('SECRET'));
  const markup=renderToStaticMarkup(React.createElement(DownloadSessionsList,{items:[normalized]}));
  for(const phrase of ['本机登录记录已保存','已保存 · 待检查','会话检查点','最近后台检查','最近账号活跃','最早检查窗口','09:00:00','10:00:00','11:00:00','17:00:00','每30分钟','闲置6小时','15%错峰','可能因任务占用或风控延后','不能延长平台有效期'])assert.ok(markup.includes(phrase),phrase);
  assert.ok(!markup.includes('SECRET'));assert.ok(!markup.includes('自动续期成功'));
});
test('未接收维护数据保留未知；引擎停止和调度关闭不虚构下一次检查',()=>{
  const empty=renderToStaticMarkup(React.createElement(SessionMaintenance,{item:{}}));
  assert.match(empty,/尚无可计算的计划/);assert.ok(!empty.includes('登录已失效'));
  for(const [state,phrase] of [['engine_stopped','后台引擎未运行'],['disabled','后台检查已关闭'],['due','已到检查窗口，等待后台调度']]) {
    const markup=renderToStaticMarkup(React.createElement(SessionMaintenance,{item:{observability:{keepalive:{schedule_status:state}}}}));
    assert.ok(markup.includes(phrase),phrase);
  }
  const clean=sessionObservability({checkpoint_at:'SECRET_INVALID_TIME',background_health_outcome:{token:'SECRET'},keepalive:{idle_hours:true,jitter_ratio:Infinity,proxy:'SECRET'}});
  assert.equal(clean.checkpoint_at,null);assert.equal(clean.keepalive.idle_hours,null);assert.equal(clean.keepalive.jitter_ratio,null);
  assert.ok(!JSON.stringify(clean).includes('SECRET'));
});

test('下载任务显示实际登记数量及恢复入口，服务未知不提供新建替代',()=>{
  const completed=renderToStaticMarkup(React.createElement(NetworkDownloadJob,{job:downloadJob({id:uuid,status:'completed',result:{media_count:1}})}));
  assert.match(completed,/已将 1 份素材加入素材库/);assert.match(completed,/下载另一条/);
  const unknown=renderToStaticMarkup(React.createElement(NetworkDownloadJob,{job:downloadJob({id:uuid,status:'submission_unknown'})}));
  assert.match(unknown,/查询原任务/);assert.match(unknown,/不要重复提交/);assert.ok(!unknown.includes('下载另一条'));
  const actions=renderToStaticMarkup(React.createElement(NetworkMaterials,{}));
  assert.match(actions,/账号与下载登录/);assert.match(actions,/网络素材/);
});

test('登录预览只接受本任务受控路径，终态不展示旧二维码或其他浏览器页面',()=>{
  const taskId='a'.repeat(32),path=`/api/studio/download-sessions/login/${taskId}/preview.png`;
  const task={task_id:taskId,status:'waiting',preview_url:path};
  assert.equal(loginPreviewImage(task,3),`${path}?_preview=3`);
  for(const invalid of ['https://outside.example/secret.png','//outside.example/secret.png','/api/studio/assets/private',path.replace(taskId,'b'.repeat(32))])assert.equal(loginPreviewImage({...task,preview_url:invalid}), '');
  assert.equal(loginPreviewImage({...task,status:'done'}),'');
  assert.equal(loginPreviewImage({...task,status:'error'}),'');
  assert.equal(loginPreviewImage({...task,task_id:'../private'}),'');
  assert.equal(loginPreviewImage({...task,preview_url:undefined}),'');
});

test('等待扫码或验证显示真实登录页图片，未就绪能重试，完成后立即收起',()=>{
  const taskId='b'.repeat(32),preview_url=`/api/studio/download-sessions/login/${taskId}/preview.png`;
  const waiting=renderToStaticMarkup(React.createElement(LoginPagePreview,{task:{task_id:taskId,status:'waiting',preview_url}}));
  assert.match(waiting,/<img/);assert.match(waiting,/当前平台登录页面/);assert.match(waiting,/重试预览/);
  const verification=renderToStaticMarkup(React.createElement(LoginPagePreview,{task:{task_id:taskId,status:'verification',preview_url}}));
  assert.match(verification,/完成平台验证/);assert.match(verification,/当前平台验证页面/);
  const notReady=renderToStaticMarkup(React.createElement(LoginPagePreview,{task:{task_id:taskId,status:'opening'}}));
  assert.match(notReady,/登录页预览尚未就绪/);assert.ok(!notReady.includes('<img'));
  const done=renderToStaticMarkup(React.createElement(LoginPagePreview,{task:{task_id:taskId,status:'done',preview_url}}));
  assert.equal(done,'');
});

test('登录页暂未就绪时3秒后继续尝试，连续20次失败后停止，终态不再轮询',()=>{
  const taskId='c'.repeat(32),task={task_id:taskId,status:'waiting',preview_url:`/api/studio/download-sessions/login/${taskId}/preview.png`};
  assert.equal(LOGIN_PREVIEW_RETRY_LIMIT,20);
  for(let failures=0;failures<20;failures++)assert.equal(loginPreviewRetryDelay(task,{failures}),3000,`第${failures}次失败不会提前停止`);
  assert.equal(loginPreviewRetryDelay(task,{failures:20}),null);
  assert.equal(loginPreviewRetryDelay(task,{failures:21}),null);
  assert.equal(loginPreviewRetryDelay(task,{failures:0,waitingForImage:true}),null,'正在读取截图时不重开请求');
  assert.equal(loginPreviewRetryDelay(task,{failures:0}),3000,'成功或手动重试归零后允许刷新');
  for(const status of ['done','confirmed','expired','error','failed'])assert.equal(loginPreviewRetryDelay({...task,status}),null);
  assert.equal(loginPreviewRetryDelay({...task,preview_url:'https://outside.example/x'}),null);
});
