import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {normalizeDownloadSessions} from '../src/network-materials-model.js';
import {avatarInputForSave,normalizeAvatarMedia} from '../src/generator-model.js';

const require=createRequire(import.meta.url),result=await build({entryPoints:[fileURLToPath(new URL('../src/PlatformAccounts.jsx',import.meta.url))],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
const compiled={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {accountScopeView,checkPlatformSession,PlatformAccountRows,PlatformAccountsSettings,MaterialLoginSummary,NetworkMaterialChoice}=compiled.exports;
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const accounts=normalizeDownloadSessions({items:[{id:8,platform:'douyin',nickname:'已选素材号',selected:true,search_supported:true,search_status:'unconfirmed',download_status:'available',publish_status:'login_required',publish_checked_at:new Date().toISOString(),search_checked_at:'2026-10-17T01:00:00Z',cookie:'PRIVATE-COOKIE'},
  {id:9,platform:'kuaishou',nickname:'快手号',search_supported:false,search_status:'unsupported',download_status:'available',publish_status:'network_error'}]});

test('三平台卡分别展示素材与发布状态，下载可用不会冒充搜索已登录',()=>{
  const html=render(PlatformAccountRows,{items:accounts});
  for(const label of ['抖音','快手','视频号','已选素材号','素材搜索','素材下载','视频发布','需要登录','检查失败','仅链接下载','09:00:00','管理登录'])assert.ok(html.includes(label),label);
  const douyin=html.slice(0,html.indexOf('快手号'));
  assert.ok(!douyin.includes('最近检查正常'));assert.ok(!html.includes('PRIVATE-COOKIE'));assert.equal((html.match(/>管理登录</g)||[]).length,3);
  assert.equal(accounts[0].selected,true);assert.equal(accounts[0].search_status,'unconfirmed');
});
test('卡片八小时内显示最近检查正常，超过窗口或未来时间均待检查',()=>{
  const now=Date.parse('2026-10-17T09:00:00Z');
  for(const checkedAt of ['2026-10-17T09:00:00Z','2026-10-17T01:00:00Z'])assert.equal(accountScopeView('available',{checkedAt,now}).label,'最近检查正常');
  for(const checkedAt of [undefined,null,'','invalid','2026-10-16T01:00:00Z','2026-10-17T00:59:59Z','2026-10-17T09:00:01Z']) {
    const view=accountScopeView('available',{checkedAt,now,saved:true});
    assert.equal(view.label,'已保存 · 待检查',String(checkedAt));assert.equal(view.tone,'neutral');
    assert.equal(accountScopeView('login_required',{checkedAt,now}).tone,'danger','明确需要登录的状态只能由后续真实检查改变');
  }
  assert.equal(accountScopeView('login_required',{checkedAt:'2026-10-17T01:00:00Z',now}).label,'需要登录');
  const stale={...accounts[1],last_checked_at:'2026-10-16T01:00:00Z',publish_checked_at:'2026-10-16T01:00:00Z',publish_status:'available',download_saved:true,publish_saved:true};
  const html=render(PlatformAccountRows,{items:[stale]});
  assert.ok(!html.includes('最近检查正常'));assert.match(html,/已保存 · 待检查/);assert.match(html,/2026\/10\/16/);
  assert.equal(stale.download_status,'available');assert.equal(stale.publish_status,'available','展示降级不改变操作数据');
});
test('登录摘要仅接受真实搜索证据，错误和空账号保留未知',()=>{
  assert.match(render(MaterialLoginSummary,{items:accounts}),/尚无已确认可用于搜索/);
  assert.match(render(MaterialLoginSummary,{items:[{...accounts[0],search_status:'available',search_checked_at:new Date().toISOString()}]}),/抖音素材账号最近检查正常；搜索前会自动验证/);
  assert.match(render(MaterialLoginSummary,{items:[{...accounts[1],search_status:'available'}]}),/尚无已确认可用于搜索/);
  assert.match(render(MaterialLoginSummary,{items:[{...accounts[0],selected:false,search_status:'available'}]}),/尚无已确认可用于搜索/);
  const error=render(PlatformAccountRows,{items:accounts,error:'offline'});assert.match(error,/状态未知/);assert.ok(!error.includes('最近检查正常'));
});

test('红黄绿灯区分明确失效与尚未确认，搜索摘要排除过期和非搜索账号',()=>{
  const fresh=new Date().toISOString(),stale=new Date(Date.now()-8*60*60*1000-1000).toISOString();
  const summary=overrides=>render(MaterialLoginSummary,{items:[{...accounts[0],search_checked_at:fresh,...overrides}]});
  assert.match(summary({search_status:'available'}),/platform-state-dot green/);
  assert.match(summary({search_status:'login_required'}),/platform-state-dot red/);
  for(const search_status of ['unconfirmed','unknown','network_error'])assert.match(summary({search_status}),/platform-state-dot yellow/);
  for(const overrides of [{search_status:'available',search_checked_at:stale},{search_status:'available',selected:false},{search_status:'available',search_supported:false}]) {
    const html=summary(overrides);assert.match(html,/platform-state-dot yellow/);assert.ok(!html.includes('素材账号最近检查正常'));
  }
  for(const props of [{error:'offline'},{loading:true}])assert.match(render(MaterialLoginSummary,{items:[{...accounts[0],search_status:'available',search_checked_at:fresh}],...props}),/platform-state-dot yellow/);
  const html=render(PlatformAccountRows,{items:[{...accounts[0],search_status:'available',search_checked_at:fresh,publish_status:'login_required'}]});
  assert.match(html,/platform-state-dot green/);assert.match(html,/platform-state-dot red/);assert.match(html,/platform-state-dot yellow/);
  const failed=render(PlatformAccountRows,{items:[{...accounts[0],search_status:'network_error',publish_status:'network_error',publish_check_status:'network_error'}]});
  assert.ok(!failed.includes('platform-state-dot red'));assert.match(failed,/检查失败/);
});
test('单次联网选择明确无素材暂停，关闭时不展开状态细节',()=>{
  assert.match(render(NetworkMaterialChoice,{enabled:true,sessions:{items:accounts},onChange:()=>{}}),/找不到合适素材时会明确暂停/);
  assert.ok(!render(NetworkMaterialChoice,{enabled:false,onChange:()=>{}}).includes('管理登录'));
});
test('旧AI草稿缺省保留原策略，显式开关与AI参数独立持久化',()=>{
  const old=normalizeAvatarMedia({ai:{enabled:true,skip_douyin:true}});
  assert.equal(old.network_materials_enabled,undefined);assert.equal('network_materials_enabled' in avatarInputForSave(old),false);
  assert.deepEqual(avatarInputForSave(old).ai,{enabled:true,skip_douyin:true});
  const saved=avatarInputForSave({network_materials_enabled:true,ai:{enabled:false}});
  assert.equal(saved.network_materials_enabled,true);assert.equal(saved.ai.enabled,false);
  assert.equal(avatarInputForSave({network_materials_enabled:false}).network_materials_enabled,false);
});

test('设置卡明确提供真实检查入口，保留状态灯和上次检查时间说明',()=>{
  const html=render(PlatformAccountsSettings,{});
  assert.match(html,/检查登录状态/);assert.ok(!html.includes('>刷新状态<'));assert.match(html,/最近8小时内检查正常/);assert.match(html,/搜索前自动验证登录；发布前逐个自动验证目标账号/);
});

test('重启后即时状态待验证仍显示持久历史检查，不借历史状态放行动作',()=>{
  const checked=new Date(Date.now()-60*60*1000).toISOString(),items=normalizeDownloadSessions({items:[{id:9,platform:'kuaishou',nickname:'历史账号',selected:true,
    download_status:'unconfirmed',download_check_status:'available',download_checked_at:checked,last_checked_at:null,
    publish_status:'unconfirmed',publish_check_status:'available',publish_checked_at:checked}]});
  const html=render(PlatformAccountRows,{items});
  assert.equal((html.match(/platform-state-dot green/g)||[]).length,2);assert.equal((html.match(/最近检查正常/g)||[]).length,2);
  assert.equal(items[0].download_checked_at,checked);assert.equal(items[0].publish_checked_at,checked);
  assert.equal(items[0].download_status,'unconfirmed');assert.equal(items[0].publish_status,'unconfirmed');
  const missing=render(PlatformAccountRows,{items:normalizeDownloadSessions({items:[{...items[0],download_checked_at:null,last_checked_at:checked,publish_checked_at:null}]})});
  assert.ok(!missing.includes('platform-state-dot green'),'缺少历史检查时间不能回退到其他旧时间放绿灯');
});

function sessionHookHarness(fetchImpl) {
  const slots=[],effects=[],listeners=new Map();let index=0;
  const cell=initial=>{const current=index++;if(!(current in slots))slots[current]=typeof initial==='function'?initial():initial;return current;};
  const hooks={...React,useState(initial){const current=cell(initial);return [slots[current],value=>{slots[current]=typeof value==='function'?value(slots[current]):value;}];},useRef(initial){return slots[cell(()=>({current:initial}))];},useCallback:fn=>fn,useEffect:effect=>effects.push(effect)};
  const module={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(name=>name==='react'?hooks:require(name),module,module.exports);
  const previousFetch=globalThis.fetch,previousWindow=globalThis.window;
  globalThis.fetch=fetchImpl;globalThis.window={addEventListener:(name,callback)=>listeners.set(name,callback),removeEventListener:name=>listeners.delete(name),dispatchEvent:event=>listeners.get(event.type)?.(event)};
  const read=()=>{index=0;return module.exports.usePlatformSessions();};read();const cleanup=effects[0]();
  return {read,notify:()=>globalThis.window.dispatchEvent(new Event('haike:sessions-changed')),close(){cleanup();globalThis.fetch=previousFetch;if(previousWindow===undefined)delete globalThis.window;else globalThis.window=previousWindow;}};
}
const turn=()=>new Promise(resolve=>setImmediate(resolve));

test('真实hook自动与事件读取只GET，用户检查逐账号POST；部分失败继续且不抹掉成功状态',async()=>{
  const requests=[],fresh=new Date().toISOString(),initial=[{id:8,platform:'douyin',nickname:'素材号',selected:true,search_supported:true,search_status:'unconfirmed',publish_status:'unconfirmed'},
    {id:9,platform:'kuaishou',nickname:'快手号',publish_status:'unconfirmed'}, {id:10,platform:'shipinhao',nickname:'视频号',publish_status:'unconfirmed'}];
  let completed=false;
  const harness=sessionHookHarness(async(url,options={})=>{
    requests.push({url,method:options.method||'GET'});
    if(options.method==='POST') {
      if(url.endsWith('/9/check'))return {ok:false,json:async()=>({detail:'fixture unavailable'})};
      if(url.endsWith('/10/check'))completed=true;
      return {ok:true,json:async()=>({account:{id:Number(url.split('/').at(-2))}})};
    }
    return {ok:true,json:async()=>({items:completed?initial.map(item=>item.id===9?{...item,publish_status:'network_error'}:{...item,search_status:'available',search_checked_at:fresh,publish_status:'available',publish_checked_at:fresh}):initial})};
  });
  try {
    await turn();harness.notify();await turn();
    assert.deepEqual(requests.map(item=>item.method),['GET','GET'],'打开页面和事件刷新不会访问平台检查');
    const checking=harness.read().check(),duplicate=harness.read().check();await Promise.all([checking,duplicate]);await turn();
    assert.deepEqual(requests.slice(2),[{url:'/api/studio/download-sessions/8/check',method:'POST'},{url:'/api/studio/download-sessions/9/check',method:'POST'},{url:'/api/studio/download-sessions/10/check',method:'POST'},{url:'/api/studio/download-sessions',method:'GET'}]);
    const state=harness.read();assert.equal(state.error,'');assert.equal(state.checking,false);assert.equal(state.checkErrors.length,1);assert.match(state.checkErrors[0],/快手 · 快手号：检查未完成/);assert.match(state.checkNotice,/已完成 2 个账号/);
    assert.equal(state.items.find(item=>item.id===8).publish_status,'available');assert.equal(state.items.find(item=>item.id===10).publish_status,'available');
    const html=render(PlatformAccountRows,state);assert.match(html,/platform-state-dot green/);assert.match(html,/检查失败/);assert.ok(!html.includes('状态未知'));
  }finally{harness.close();}
});

test('单账号检查有界超时，用中文保留待确认结果',async()=>{
  await assert.rejects(()=>checkPlatformSession(8,{timeoutMs:1,fetchImpl:async(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}))}),/检查超时，结果待确认/);
});
