import test from 'node:test';
import assert from 'node:assert/strict';
import * as taskModel from '../src/task-center-model.js';
import {applyTaskSummary,commandLabel,dailyPlanDraft,dailyPlanPayload,formatTaskMoney,microsInput,
  nextReportClientId,parseBudget,productionJobs,productionKindLabel,publicationRows,reportWaiting,
  safeTaskHref,taskCenterHref,taskCenterRequest,taskGroups} from '../src/task-center-model.js';

const task=(id,revision=1,patch={})=>({id,revision,created_at:'2026-10-16T02:00:00Z',...patch});

test('真实提交待核验不再计入执行中，缺失或失败目标不冒充全平台成功',()=>{
  const attempts=['douyin','kuaishou','shipinhao'].map((platform,index)=>({platform,account_id:index+1,status:'done',acceptance_status:index===2?'pending':'verified',identity_verified:true}));
  const value=task('TC-1',1,{status:'running',sources:{queue:{status:'completed'},work:{attempts}}});
  assert.equal(taskModel.taskPresentation(value).status,'awaiting_verification');
  assert.deepEqual(taskModel.taskCounts([value]),{all:1,active:0,waiting:1,completed:0});
  assert.equal(value.status,'running');
  const complete=structuredClone(value);complete.sources.work.attempts[2].acceptance_status='verified';
  assert.equal(taskModel.taskPresentation(complete).status,'fully_verified');
  const failed=structuredClone(value);failed.sources.work.attempts[2].status='failed';
  assert.equal(taskModel.taskPresentation(failed).status,'needs_attention');
  const missing=structuredClone(value);missing.sources.work.attempts.pop();
  assert.notEqual(taskModel.taskPresentation(missing).status,'fully_verified');
  const unreadable=structuredClone(complete);unreadable.sources.work.availability='unavailable';
  assert.equal(taskModel.taskPresentation(unreadable).status,'source_unknown');
});
test('目标按账号逐项核对；发布间隔是等待，心跳过期不暗示执行者在线',()=>{
  const value={expected_targets:[{platform:'douyin',account_id:1},{platform:'douyin',account_id:2}],sources:{work:{attempts:[{platform:'douyin',account_id:1,status:'done',acceptance_status:'verified',identity_verified:true},{platform:'douyin',account_id:2,status:'pending',next_allowed_at:'2026-10-17T02:00:00Z'}]}}};
  assert.equal(publicationRows(value).length,2);assert.equal(publicationRows(value)[1].account_id,2);
  assert.match(publicationRows(value)[1].label,/发布间隔/);assert.equal(taskModel.taskPresentation(value).status,'waiting_publish');
  const now=Date.parse('2026-10-17T02:00:00Z');
  assert.match(taskModel.executorPresence({},now),/未确认/);
  assert.match(taskModel.executorPresence({heartbeat_at:'2026-10-16T02:00:00Z'},now),/未确认/);
  assert.match(taskModel.executorPresence({heartbeat_at:'2026-10-17T01:59:00Z'},now),/收到/);
});

test('历史事件按持久编号最新优先合并，重复页只保留一份且不改原数组',()=>{
  const old=Object.freeze({id:1,kind:'stage',stage:'字幕受阻',message:'18:24旧字幕阻碍'});
  const latest=Object.freeze({id:3,kind:'stage',stage:'制作完成',message:'成片已生成'});
  const beat=Object.freeze({id:2,kind:'heartbeat',message:'仍在响应'});
  const before=Object.freeze([old,beat]),after=Object.freeze([latest,old]);
  assert.deepEqual(taskModel.mergeTaskEvents(before,after),[latest,beat,old]);
  assert.deepEqual(before,[old,beat]);assert.deepEqual(after,[latest,old]);
  assert.deepEqual(taskModel.mergeTaskEvents([],[]),[]);
});

test('增量空页保留已有视频，低版本不覆盖；同版真实来源刷新仍生效',()=>{
  const initial=[task('TC-1',2,{stage:'配音',sources:{queue:{status:'running'}}})];
  const empty=applyTaskSummary(initial,{changes:[],next_cursor:4,has_more:false},{cursor:4});
  assert.deepEqual(empty.tasks,initial);
  const stale=applyTaskSummary(empty.tasks,{changes:[task('TC-1',1,{stage:'选题'})],next_cursor:5,has_more:false},{cursor:4});
  assert.equal(stale.tasks[0].stage,'配音');
  const refreshed=applyTaskSummary(stale.tasks,{changes:[task('TC-1',2,{sources:{queue:{status:'failed'}}})],next_cursor:6,has_more:false},{cursor:5});
  assert.equal(refreshed.tasks[0].sources.queue.status,'failed');
  assert.equal(initial[0].sources.queue.status,'running');
});
test('首次快照与后续分页逐页合并；只有显式刷新替换旧快照',()=>{
  const first=applyTaskSummary([task('old')],{changes:[task('TC-1')],next_cursor:1,has_more:true},{reset:true});
  assert.deepEqual(first.tasks.map(t=>t.id),['TC-1']);
  const next=applyTaskSummary(first.tasks,{changes:[task('TC-2')],next_cursor:2,has_more:false},{cursor:first.cursor});
  assert.deepEqual(next.tasks.map(t=>t.id),['TC-1','TC-2']);
  for(const value of [{changes:[],next_cursor:1,has_more:false},{changes:[],next_cursor:2,has_more:true},
    {changes:null,next_cursor:3,has_more:false},{changes:[],next_cursor:3},
    {changes:[{id:'TC-broken'}],next_cursor:3,has_more:false}]) {
    assert.throws(()=>applyTaskSummary(next.tasks,value,{cursor:2}));
    assert.equal(next.tasks.length,2);
  }
});
test('分组依据持久批次编号；独立任务也有入口',()=>{
  const groups=taskGroups([task('a',1,{batch_id:'2026-10-16'}),task('b'),task('c',1,{batch_id:'2026-10-16'})]);
  assert.deepEqual(groups.map(g=>g.tasks.map(t=>t.id)),[['a','c'],['b']]);
});
test('金额保留真实微元费用，未知不显示为0；输入六位小数精确往返',()=>{
  assert.equal(formatTaskMoney(null),'尚未确认');assert.equal(formatTaskMoney(undefined),'尚未确认');
  assert.equal(formatTaskMoney(0),'¥0.00');assert.equal(formatTaskMoney(2000),'¥0.002');
  assert.equal(formatTaskMoney(1),'¥0.000001');assert.equal(formatTaskMoney(-1),'尚未确认');
  for(const amount of [0,1,2000,1000000,5123456,25000000])assert.equal(parseBudget(microsInput(amount)),amount);
  assert.equal(parseBudget('0.002'),2000);
  for(const value of ['', '-1','0.0000001','1e3','1,000','Infinity','9007199255'])assert.throws(()=>parseBudget(value));
});
test('每日方案默认3个模板槽位，无账号和预算假设；始终保存为未启用且包含CAS版本',()=>{
  const draft=dailyPlanDraft({revision:7,slots:[]});
  assert.equal(draft.start_time,'02:00');assert.equal(draft.slots.length,3);
  assert.equal(new Set(draft.slots.map(s=>s.template_id)).size,3);
  assert.ok(draft.slots.every(s=>s.accounts.length===0&&s.budget===''));
  assert.throws(()=>dailyPlanPayload(draft),/预算/);
  draft.slots.forEach((slot,index)=>slot.budget=['0.002','5','0'][index]);
  const payload=dailyPlanPayload({...draft,enabled:true});
  assert.equal(payload.enabled,false);assert.equal(payload.expected_revision,7);
  assert.equal(payload.timezone,'Asia/Shanghai');
  assert.deepEqual(payload.slots.map(s=>s.budget_limit_micros),[2000,5000000,0]);
  assert.ok(payload.slots.every(s=>s.accounts.length===0));
});
test('已保存账号与微元预算完整保留，非法时间/重复平台/无效账号/模板不会发请求',()=>{
  const draft=dailyPlanDraft({revision:3,start_time:'03:20',slots:Array.from({length:3},(_,i)=>({template_id:['avatar-safe-circle-v1','avatar-full-width-v2','avatar-deepblue-n1-v1'][i],topic:'科技新闻🤖',budget_limit_micros:2000,accounts:[{platform:'douyin',account_id:27}]}))});
  const payload=dailyPlanPayload(draft);
  assert.equal(payload.slots[0].accounts[0].account_id,27);assert.equal(payload.slots[2].budget_limit_micros,2000);
  assert.equal(payload.slots[2].topic,'科技新闻🤖');
  assert.throws(()=>dailyPlanPayload({...draft,start_time:'25:00'}),/时间/);
  assert.throws(()=>dailyPlanPayload({...draft,slots:[]}),/三个/);
  for(const accounts of [[{platform:'douyin',account_id:0}],[{platform:'x',account_id:1}],
    [{platform:'douyin',account_id:1},{platform:'douyin',account_id:2}]]) {
    assert.throws(()=>dailyPlanPayload({...draft,slots:draft.slots.map((s,i)=>i===0?{...s,accounts}:s)}),/账号/);
  }
  assert.throws(()=>dailyPlanPayload({...draft,slots:draft.slots.map((s,i)=>i===0?{...s,template_id:'unknown'}:s)}),/模板/);
});
test('汇报未知提交沿用原编号，待响应禁用重复操作，真实应答后允许新一轮汇报',()=>{
  let ids=0;const create=()=>`request-${++ids}`;
  const first=nextReportClientId(null,[],create);
  assert.equal(nextReportClientId(first,[],create),first);
  const requested={client_id:first,kind:'report_now',status:'requested'};
  assert.equal(reportWaiting(requested),true);
  assert.equal(nextReportClientId(first,[requested],create),first);
  const acknowledged={...requested,status:'acknowledged',result:'配音已生成，等待本地渲染。'};
  assert.equal(reportWaiting(acknowledged),false);assert.equal(commandLabel(acknowledged),'汇报已响应');
  assert.equal(nextReportClientId(first,[acknowledged],create),'request-2');
  assert.equal(commandLabel(requested),'请求已接收，等待响应');assert.equal(ids,2);
});
test('三平台各自保留错误与不确定结果；提交和受理核验不会冒充公开可见',()=>{
  const rows=publicationRows({sources:{work:{attempts:[{platform:'douyin',status:'done',acceptance_status:'verified',account_id:3,result_url:'https://www.douyin.com/video/123'}]},
    calendar:{attempts:[{platform:'kuaishou',status:'failed',error:'登录态失效'},{platform:'shipinhao',status:'uncertain',error:'平台回执待确认'}]}}});
  assert.deepEqual(rows.map(r=>r.name),['抖音','快手','视频号']);
  assert.equal(rows[0].label,'已提交，公开状态待核验');assert.equal(rows[1].error,'登录态失效');
  assert.equal(rows[2].label,'结果待核对');
  assert.equal(publicationRows({sources:{work:{attempts:[{platform:'douyin',status:'done',public_visible:true}]}}})[0].label,'已核验公开可见');
});
test('来源读取失败不冒充零发布记录；较晚真实回执优先于另一个来源的旧快照',()=>{
  assert.ok(publicationRows({sources:{calendar:{availability:'unavailable'}}}).every(row=>row.label==='发布状态暂不可读'));
  assert.ok(publicationRows({sources:{}}).every(row=>row.label==='尚无发布记录'));
  const rows=publicationRows({sources:{work:{attempts:[{platform:'kuaishou',status:'done',synced_at:'2026-10-16T03:00:00Z'}]},
    calendar:{attempts:[{platform:'kuaishou',status:'failed',synced_at:'2026-10-16T02:00:00Z'}]}}});
  assert.equal(rows[1].status,'done');
});
test('证据只打开允许的页面或HTTP链接，不把本机私密路径/脚本做成链接',()=>{
  for(const ref of ['javascript:alert(1)','data:text/html,x','file:///C:/private','C:\\private\\report.json','//example.com','https://a:b@example.com','/api/settings','https://example.com/ x'])assert.equal(safeTaskHref(ref),null);
  assert.equal(safeTaskHref('/api/works/w1/media'),'/api/works/w1/media');
  assert.equal(safeTaskHref('https://example.com/news/1'),'https://example.com/news/1');
});
test('制作队列保留旧任务与未知来源，跳转仅关联原编号而不重建任务',()=>{
  const jobs=[{job_id:'PQ-1',kind:'studio_avatar'},{job_id:'PQ-2',kind:'material_commentary'},{job_id:'PQ-3',kind:'future_flow'}];
  assert.deepEqual(productionJobs({tasks:jobs}),jobs);assert.throws(()=>productionJobs({}),/队列/);
  assert.equal(productionKindLabel(jobs[1].kind),'素材解说');assert.equal(productionKindLabel(jobs[2].kind),'制作任务');
  const href=taskCenterHref({queueJob:'PQ old',projectId:'project-7'}),query=new URLSearchParams(href.split('?')[1]);
  assert.equal(query.get('queue_job'),'PQ old');assert.equal(query.get('project'),'project-7');
  assert.equal(taskCenterHref({id:'TC-7'}),'/task-center?task=TC-7');
});
test('接口读取与保存使用约定URL/方法，错误和并发冲突原样返回而不显示成功',async()=>{
  const calls=[];const fetchImpl=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({revision:8})};};
  await taskCenterRequest('/summary?cursor=4&limit=100',{fetchImpl});
  assert.equal(calls[0].url,'/api/task-center/summary?cursor=4&limit=100');assert.equal(calls[0].options.method,undefined);
  await taskCenterRequest('/plan',{body:{expected_revision:7,enabled:false},method:'PUT',fetchImpl});
  assert.equal(calls[1].options.method,'PUT');assert.equal(JSON.parse(calls[1].options.body).enabled,false);
  await assert.rejects(()=>taskCenterRequest('/plan',{fetchImpl:async()=>({ok:false,status:409,json:async()=>({detail:'版本已变化'})})}),e=>e.status===409&&e.message==='版本已变化');
  await assert.rejects(()=>taskCenterRequest('/summary',{fetchImpl:async()=>({ok:true,json:async()=>{throw Error('html');}})}),/有效状态/);
});
