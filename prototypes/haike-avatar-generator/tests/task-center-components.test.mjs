import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {dailyPlanDraft} from '../src/task-center-model.js';

const require=createRequire(import.meta.url);
const result=await build({entryPoints:[fileURLToPath(new URL('../src/TaskCenter.jsx',import.meta.url))],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
const compiled={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {DailyPlanFields,PlatformResults,QueueState,TaskBudget,TaskCard,TaskCenter,TaskDetailContent,TaskArtifacts,TaskMaterialResult}=compiled.exports;
const noop=()=>{};
const base={id:'TC-test',title:'机器人科技新闻',status:'running',stage:'配音',summary:'声音已生成，等待合成。',
  last_progress_at:'2026-10-16T02:00:00Z',heartbeat_at:'2026-10-16T02:05:00Z',
  budget:{currency:'CNY',actual_micros:2000,reserved_micros:null,estimated_micros:500000,limit_micros:5000000},
  sources:{queue:{id:'PQ-1',availability:'available',status:'running',stage:'正在合成第1段',updated_at:'2026-10-16T02:04:00Z',project_id:'p1'}},links:{},evidence:[],commands:[],events:[]};
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));

test('结果集中展示原成片封面和发布文案，拒绝私密路径和脚本链接',()=>{
  const html=render(TaskArtifacts,{task:{title:'科技新闻',sources:{work:{result:{video_url:'/api/works/work-1/media?version=v1',cover_url:'/api/works/work-1/cover',title:'发布标题',desc:'第一行\n第二行',topics:'科技'}}}}});
  for(const text of ['本条最终成片','/api/works/work-1/media?version=v1','/api/works/work-1/cover','发布标题','第一行','第二行','科技'])assert.ok(html.includes(text),text);
  assert.ok(!html.includes('autoplay'));
  assert.equal(render(TaskArtifacts,{task:{sources:{work:{result:{video_url:'file:///C:/private/video.mp4'}}}}}), '');
});

test('任务素材按实际采用数量与来源展示，默认折叠，阻塞不会显示已采用',()=>{
  const html=render(TaskMaterialResult,{task:{sources:{material_result:{enabled:true,status:'completed',used_count:1,items:[{asset_id:'a',name:'机器人演示',kind:'image',source:'抖音',source_url:'https://example.com/original',preview_url:'/api/studio/assets/owned-a'}]}}}});
  for(const text of ['已采用联网画面','已采用 1 段画面素材','机器人演示','抖音','查看来源','/api/studio/assets/owned-a'])assert.ok(html.includes(text),text);
  assert.match(html,/<details class="task-material-items">/);assert.ok(!html.includes('<details open'));
  const blocked=render(TaskMaterialResult,{task:{sources:{material_result:{enabled:true,status:'blocked',used_count:0,message:'未找到合适画面，请补充素材。',items:[{name:'待查引用',source_url:'javascript:alert(1)',preview_url:'file:///C:/private.png'}]}}}});
  assert.match(blocked,/等待补充素材/);assert.match(blocked,/未找到合适画面/);assert.ok(!blocked.includes('已采用联网画面'));assert.ok(!blocked.includes('javascript:'));assert.ok(!blocked.includes('private.png'));
  assert.equal(render(TaskMaterialResult,{task:base}),'');
});

test('历史任务未知联网策略不冒充关闭，只有实际采用与待合成阶段展示相应数量',()=>{
  const history=render(TaskMaterialResult,{task:{sources:{material_result:{enabled:null,status:'unknown',used_count:null,message:'历史任务沿用原素材策略，未记录独立联网素材结果'}}}});
  assert.match(history,/素材结果待确认/);assert.match(history,/历史任务沿用原素材策略/);assert.ok(!history.includes('未开启联网素材'));assert.ok(!history.includes('已采用'));
  for(const status of ['disabled','blocked','searching','unknown']) {
    const html=render(TaskMaterialResult,{task:{sources:{material_result:{enabled:status==='disabled'?false:true,status,used_count:0}}}});
    assert.ok(!html.includes('已采用 0 段'));assert.ok(!html.includes('已选 0 段'));
  }
  const ready=render(TaskMaterialResult,{task:{sources:{material_result:{enabled:true,status:'ready',used_count:0,selected_count:2,items:[{name:'已选片段',source:'用户素材'}]}}}});
  assert.match(ready,/已选 2 段待合成/);assert.match(ready,/查看已选画面与来源/);assert.ok(!ready.includes('已采用'));
});
test('任务卡区分最后进展、运行心跳、制作记录更新，费用精确且没有虚构百分比',()=>{
  let actions=0;const html=render(TaskCard,{task:base,onOpen:()=>actions++});
  for(const phrase of ['机器人科技新闻','总控阶段：','实际制作队列','正在合成第1段','最后进展','运行心跳','制作记录更新','10:00:00','10:05:00','10:04:00','¥0.002','尚未确认'])assert.ok(html.includes(phrase),phrase);
  assert.ok(!html.includes('%'));assert.equal(actions,0);
  const missing=render(TaskCard,{task:{...base,heartbeat_at:null},onOpen:noop});
  assert.match(missing,/尚未收到心跳/);
});
test('底层失败与来源不可读明确可见，总控完成记录不会掩盖真实队列错误',()=>{
  const html=render(TaskCard,{task:{...base,status:'completed',sources:{queue:{availability:'available',status:'failed',stage:'合成失败',error:{message:'本地渲染器退出'}}}},onOpen:noop});
  assert.match(html,/需要处理/);assert.match(html,/实际制作队列/);assert.match(html,/执行失败/);assert.match(html,/本地渲染器退出/);assert.ok(!html.includes('总控：制作完成'));
  assert.match(render(QueueState,{task:{sources:{queue:{availability:'unavailable'}}}}),/暂时不可读取/);
  assert.match(render(QueueState,{task:{sources:{queue:{availability:'missing'}}}}),/记录未找到/);
});
test('详情时间线来自真实事件，心跳不冒充阶段；作品、项目和安全来源均可打开',()=>{
  const html=render(TaskDetailContent,{task:{...base,sources:{...base.sources,work:{id:'work-7'}},evidence:[{label:'新闻原始来源',ref:'https://example.com/news'},{label:'本地校验证据',ref:'C:\\private\\proof.json'}]},
    events:[{id:1,kind:'stage',stage:'文案',message:'已核对3条来源。',created_at:'2026-10-16T01:00:00Z'},
      {id:2,kind:'heartbeat',stage:'虚构心跳阶段',message:'HEARTBEAT_ONLY',created_at:'2026-10-16T02:05:00Z'}],onReport:noop});
  for(const phrase of ['已核对3条来源。','阶段时间线','href="/projects?work=work-7"','href="/p/p1"','新闻原始来源','href="https://example.com/news"','当前没有可打开的链接'])assert.ok(html.includes(phrase),phrase);
  for(const text of ['HEARTBEAT_ONLY','虚构心跳阶段','C:\\private','暂停任务','已人工观看'])assert.ok(!html.includes(text),text);
});
test('当前完成摘要与旧字幕阻碍分区，历史最新在前且未知费用不变成结算',()=>{
  const html=render(TaskDetailContent,{task:{...base,status:'completed',stage:'当前成片已生成',
    summary:'当前三平台结果分别核验',budget:{...base.budget,actual_micros:null}},events:[
      {id:1,kind:'stage',stage:'字幕受阻',message:'18:24旧字幕阻碍',created_at:'2026-10-16T10:24:00Z'},
      {id:3,kind:'stage',stage:'制作完成',message:'最新进展：成片已生成',created_at:'2026-10-16T12:35:00Z',facts:{status:'completed'}},
      {id:2,kind:'heartbeat',stage:'HEARTBEAT_ONLY',message:'HEARTBEAT_ONLY'}],onReport:noop});
  assert.match(html,/当前阶段与摘要/);
  assert.match(html,/历史记录（最新在前）/);
  assert.match(html,/历史记录不代表当前仍有阻碍/);
  const history=html.slice(html.indexOf('历史记录（最新在前）'));
  assert.ok(history.indexOf('最新进展：成片已生成')<history.indexOf('18:24旧字幕阻碍'));
  assert.match(history,/当时状态：制作完成/);
  assert.ok(html.indexOf('当前三平台结果分别核验')<html.indexOf('历史记录（最新在前）'));
  assert.ok(!html.includes('HEARTBEAT_ONLY'));assert.match(html,/尚未确认/);assert.ok(!html.includes('¥0.00'));
});

test('汇报接收与真实响应分别显示；acknowledged回执允许下一次汇报',()=>{
  const command={id:'cmd1',kind:'report_now',status:'requested',created_at:'2026-10-16T02:00:00Z'};
  const waiting=render(TaskDetailContent,{task:{...base,commands:[command]},onReport:noop});
  assert.match(waiting,/请求已接收，等待响应/);assert.match(waiting,/disabled=""[^>]*>[\s\S]*?等待汇报响应/);
  const responded=render(TaskDetailContent,{task:{...base,commands:[{...command,status:'acknowledged',result:'已检查原任务，当前渲染仍在运行。'}]},onReport:noop});
  assert.match(responded,/汇报已响应/);assert.match(responded,/当前渲染仍在运行/);
  assert.ok(!responded.includes('等待汇报响应'));assert.ok(!responded.includes('disabled=""'));
  const unknown=render(TaskDetailContent,{task:base,onReport:noop,reportUnknown:true});
  assert.match(unknown,/用原编号重试请求/);assert.match(unknown,/不会暂停或重启制作/);
});
test('三平台单独展示失败和未知，不因平台受理通过就宣称公开发布成功',()=>{
  const html=render(PlatformResults,{task:{sources:{work:{attempts:[{platform:'douyin',status:'done',acceptance_status:'verified',result_url:'https://example.com/result'}]},calendar:{attempts:[{platform:'kuaishou',status:'failed',error:'请重新登录快手'},{platform:'shipinhao',status:'uncertain',error:'结果待人工核对'}]}}}});
  for(const phrase of ['抖音','快手','视频号','已提交，公开状态待核验','请重新登录快手','结果待人工核对','平台受理已核验'])assert.ok(html.includes(phrase),phrase);
  assert.ok(!html.includes('已核验公开可见'));
  const unavailable=render(PlatformResults,{task:{sources:{calendar:{availability:'unavailable'}}}});
  assert.match(unavailable,/发布数据暂时无法更新/);assert.ok(!unavailable.includes('尚无发布记录'));
});
test('每日方案提供3个槽位和账号选择，保留不可读取的绑定，不预填真实账号或预算',()=>{
  const draft=dailyPlanDraft({slots:[]});
  draft.slots[0].accounts=[{platform:'douyin',account_id:27}];
  const html=render(DailyPlanFields,{draft,setDraft:noop,accounts:[{id:4,name:'本地测试账号',platform:'kuaishou'}]});
  for(const phrase of ['02:00','第 1 条视频','第 2 条视频','第 3 条视频','深蓝视窗 N1','北京时间','已保存账号 #27（待核对）','本地测试账号','暂不绑定','填写本条预算'])assert.ok(html.includes(phrase),phrase);
  assert.equal((html.match(/placeholder="填写本条预算"/g)||[]).length,3);
  assert.ok(!html.includes('api_key'));assert.ok(!html.includes('API Key'));assert.ok(!html.includes('启用自动发布'));
});
test('未读取的总览使用未知计数；未返回的金额不显示为零',()=>{
  const html=render(TaskCenter,{});
  assert.match(html,/任务总览/);assert.match(html,/正在读取任务/);assert.match(html,/等待读取任务记录/);
  assert.match(html,/>—<\/strong>/);assert.ok(!html.includes('同步成功'));
  const unknown=render(TaskBudget,{budget:{}});assert.equal((unknown.match(/尚未确认/g)||[]).length,4);assert.ok(!unknown.includes('¥0'));
});
