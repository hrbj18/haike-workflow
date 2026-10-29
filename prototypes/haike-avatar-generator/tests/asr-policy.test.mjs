import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {asrPolicy,isAsrCapability} from '../src/asr-policy.js';

const require=createRequire(import.meta.url);
const compiled=await build({
  entryPoints:[fileURLToPath(new URL('../src/Settings.jsx',import.meta.url))],
  bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'},
});

function settingsMarkup(localAsr,{internal=true,items=[],configured=true}={}) {
  const account={mode:internal?'internal_local':'gateway',summary:{},local_asr:localAsr,
    capabilities:{items}};
  const states=[{mode:account.mode,configured,base_url:'https://example.invalid/v2'},'',account,'',false,false];
  const hooks={...React,useEffect(){},useState(initial){
    return [states.length?states.shift():typeof initial==='function'?initial():initial,()=>{}];
  }};
  const module={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(
    name=>name==='react'?hooks:require(name),module,module.exports);
  return renderToStaticMarkup(React.createElement(module.exports.Settings));
}

const bailian={provider:'bailian',model:'haike/bailian-asr',backend:'internal_asr',ready:true,
  name:'百炼 ASR · 词级时间轴',fallback:'local-whisper',fallback_ready:true,
  fallback_on:['invalid_key','insufficient_balance']};

test('海客默认识别显示费用预估与受限备用，不冒充本机免费或网关开通',()=>{
  const html=settingsMarkup(bailian);
  assert.match(html,/海客ASR/);assert.match(html,/音频识别与字幕提取/);
  assert.match(html,/费用预估 · 按报价确认/);
  assert.match(html,/服务授权无效/);
  assert.match(html,/识别额度不足/);
  assert.ok(!html.includes('本地识别 · 无识别调用费用'));
  assert.doesNotMatch(html,/百炼|Whisper|供应商|采购|直连/);
  assert.match(html,/开始前请确认费用预估与预算/);
});

test('海客本机识别仍如实显示无识别调用费用',()=>{
  const html=settingsMarkup({provider:'local-whisper',ready:true});
  assert.match(html,/海客ASR/);
  assert.match(html,/本地识别 · 无识别调用费用/);
  assert.doesNotMatch(html,/百炼|Whisper|供应商|采购|直连/);
});

test('默认识别未就绪不能因为备用已就绪而声明字幕能力已就绪',()=>{
  const html=settingsMarkup({...bailian,ready:false});
  assert.match(html,/海客ASR/);
  assert.match(html,/未就绪|待验收/);
  assert.doesNotMatch(html,/百炼|Whisper|供应商|采购|直连/);
});

test('字幕准入信任所选primary，不由Whisper备用或旧腾讯能力越权放行',()=>{
  const account={local_asr:{...bailian,ready:false},capabilities:{items:[
    {model:'haike/tencent-asr',status:'available'},
  ]}};
  assert.equal(asrPolicy(account).ready,false);
  assert.equal(asrPolicy({...account,local_asr:bailian}).ready,true);
  assert.equal(asrPolicy({local_asr:{...bailian,ready:'true'}}).ready,false);
  assert.equal(asrPolicy(null).ready,false);
});

test('海客备用只呈现后台明确允许的授权或额度原因，不扩大到网络及未知提交',()=>{
  const policy=asrPolicy({local_asr:{...bailian,fallback_on:[
    'invalid_key','network_error','submission_unknown','invalid_key',
  ]}});
  assert.deepEqual(policy.fallbackOn,['invalid_key']);
  assert.equal(policy.fallbackReady,true);
  assert.match(policy.notice,/仅在服务授权无效时/);
  assert.ok(!policy.notice.includes('识别额度不足'));
  assert.ok(!policy.notice.includes('network_error'));
  const noRule=asrPolicy({local_asr:{...bailian,fallback_on:[]}});
  assert.match(noRule.notice,/未配置自动备用条件/);
});

test('备用未就绪不影响已就绪默认识别，但不可声称备用会自动生效',()=>{
  const html=settingsMarkup({...bailian,fallback_ready:false});
  assert.match(html,/备用.*尚未就绪/);
  assert.ok(!html.includes('时尝试海客备用'));
  assert.equal(asrPolicy({local_asr:{...bailian,fallback_ready:false}}).ready,true);
  assert.equal(asrPolicy({local_asr:{...bailian,fallback:'other',fallback_ready:true}}).fallbackReady,false);
});

test('旧网关ASR及新的能力名均可兼容，未开通或待预算的能力不放行',()=>{
  for(const model of ['haike/tencent-asr','haike/bailian-asr']) {
    const account={local_asr:{provider:'gateway',ready:false},capabilities:{items:[{model,status:'available'}]}};
    assert.equal(asrPolicy(account).ready,true);
    assert.equal(asrPolicy(account).provider,'gateway');
    account.capabilities.items[0].status='budget_required';
    assert.equal(asrPolicy(account).ready,false);
  }
  assert.equal(isAsrCapability({capability:'asr',model:'haike/future-asr'}),true);
  assert.equal(isAsrCapability({model:'haike/avatar'}),false);
});

test('网关字幕费用保留实际结算提示，不声称本机识别免费',()=>{
  const html=settingsMarkup({provider:'gateway',ready:false},{internal:false,items:[
    {model:'haike/tencent-asr',status:'available',billing_mode:'wallet_receipt'},
  ]});
  assert.match(html,/按实际用量结算/);
  assert.match(html,/海客连接检查仅验证 Key、可用额度和已开通功能，不产生费用/);
  assert.match(html,/实际制作费用以报价、调用结果和账单为准/);
  assert.doesNotMatch(html,/百炼|Whisper|供应商|采购|直连/);
  assert.ok(!html.includes('无识别调用费用'));
});

test('Agent分析是独立工作方式，中转文本未开通不影响四项制作服务',()=>{
  const html=settingsMarkup({provider:'gateway',ready:false},{internal:false,items:[
    ...['haike/cosyvoice','haike/tencent-asr','haike/avatar','haike/assets'].map(model=>({model,status:'available'})),
    {model:'haike/text',status:'unavailable',rates:[{price_micros:999999,included_units:1,unit:'次'}]},
  ]});
  assert.match(html,/Agent分析工作方式/);
  assert.match(html,/由当前Agent完成/);
  assert.match(html,/4 \/ 4 项可用/);
  assert.doesNotMatch(html,/文本与视觉|尚未开通|未开通|0\.999999/);
});

test('Agent分析不掩盖真正缺少的制作服务',()=>{
  const html=settingsMarkup(bailian,{items:[
    {model:'haike/cosyvoice',status:'available'},
    {model:'haike/assets',status:'available'},
  ]});
  assert.match(html,/2 \/ 3 项可用/);
  assert.match(html,/数字人口播尚未开通，请联系管理员/);
  assert.match(html,/由当前Agent完成/);
  assert.doesNotMatch(html,/Agent分析尚未开通|文本与视觉/);
});

test('首次海客ASR可进入报价，未记录成功结果不冒充已实测',()=>{
  const primary={...bailian,ready:true,configured:true,enabled:true,budget_ready:true,verified:false};
  assert.equal(asrPolicy({local_asr:primary}).ready,true);
  const html=settingsMarkup(primary);
  assert.match(html,/可开始识别/);
  assert.match(html,/尚未记录首次成功结果/);
  assert.doesNotMatch(html,/已实测|已验收|百炼|Whisper|供应商|采购|直连/);
});

test('默认制作服务不要求海客网关Key，网关模式仍保留原接入说明',()=>{
  const html=settingsMarkup(bailian,{configured:false});
  assert.match(html,/Agent负责分析，配置制作所需服务/);
  assert.match(html,/统一 API 接入（可选）/);
  assert.match(html,/未使用统一网关时可留空/);
  assert.match(html,/海客制作服务/);
  assert.doesNotMatch(html,/一个海客 Key|海客备用服务|本机内部服务/);
  const gateway=settingsMarkup({provider:'gateway',ready:false},{internal:false,configured:false});
  assert.match(gateway,/使用账户中心申请的海客 Key/);
  assert.doesNotMatch(gateway,/统一 API 接入（可选）/);
});

test('百炼与数字人已配置但无Pexels时核心三项就绪，网关仍保留原素材准入',()=>{
  const items=[
    {model:'haike/cosyvoice',status:'available'},
    {model:'haike/avatar',status:'available'},
    {model:'haike/assets',status:'unconfigured'},
  ];
  const html=settingsMarkup(bailian,{configured:false,items});
  assert.match(html,/3 \/ 3 项可用/);
  assert.match(html,/按需配置Pexels，供当前Agent备用取材/);
  assert.match(html,/status-pill ">可选备用/);
  assert.doesNotMatch(html,/素材检索尚未开通|尚未开通，请联系管理员/);
  const gateway=settingsMarkup({provider:'gateway',ready:false},{internal:false,items:[
    ...items,{model:'haike/tencent-asr',status:'available'},
  ]});
  assert.match(gateway,/3 \/ 4 项可用/);
  assert.match(gateway,/素材检索尚未开通，请联系管理员/);
  assert.doesNotMatch(gateway,/可选备用|备用取材/);
});
