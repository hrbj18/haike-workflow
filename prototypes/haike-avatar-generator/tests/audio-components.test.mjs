import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { build } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require=createRequire(import.meta.url),root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const result=await build({entryPoints:[resolve(root,'src/AudioCenter.jsx')],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
const compiled={exports:{}};
new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {VoiceCatalog,VoiceDetails}=compiled.exports;
const voice={id:'public-a',name:'海客清朗',gender:'male',kind:'public',model:'haike/cosyvoice-public',available:true,preferences:{},provider_key:'must-not-appear',supplier_model:'private-provider-name'};

test('公共/私人音色分组呈现；首层只提供选择，不泄漏供应商字段',()=>{
  let actions=0;const markup=renderToStaticMarkup(React.createElement(VoiceCatalog,{items:[voice],defaultVoiceId:voice.id,onOpen:()=>actions++}));
  assert.match(markup,/公共音色/);assert.match(markup,/我的音色/);assert.match(markup,/选择音色：海客清朗/);assert.match(markup,/默认音色/);
  for(const text of ['must-not-appear','private-provider-name','CosyVoice','生成试听','倍率'])assert.ok(!markup.includes(text));
  assert.equal(actions,0);
});
test('详情有默认、倍率、配图与报价试听；未知任务禁用新的试听',()=>{
  const noop=()=>{};const markup=renderToStaticMarkup(React.createElement(VoiceDetails,{voice,isDefault:false,rate:'1.1',setRate:noop,text:'测试',setText:noop,busy:false,unresolved:true,onDefault:noop,onSaveRate:noop,onPreview:noop,onImage:noop,onBack:noop}));
  for(const text of ['设为默认音色','配音倍率','关联人物图','查看试听报价','先查看报价'])assert.ok(markup.includes(text),text);
  assert.match(markup,/disabled=""[^>]*>.*?查看试听报价/s);
  assert.ok(!markup.includes('must-not-appear'));assert.ok(!markup.includes('private-provider-name'));
});
test('读取失败显示未知状态，不把连接故障当成零音色或服务未开放',()=>{
  const markup=renderToStaticMarkup(React.createElement(VoiceCatalog,{loadError:true,onRetry:()=>{}}));
  assert.match(markup,/暂时无法读取音色/);assert.match(markup,/请检查连接后刷新/);
  assert.ok(!markup.includes('0 个'));assert.ok(!markup.includes('暂未开放'));assert.ok(!markup.includes('没有这款音色'));
});
test('候选公共音色明确标注待试听验证，模型阻断时保持不可用',()=>{
  const markup=renderToStaticMarkup(React.createElement(VoiceCatalog,{items:[{...voice,verification:'candidate_unverified'}],onOpen:()=>{}}));
  assert.match(markup,/待试听验证/);
  const blocked=renderToStaticMarkup(React.createElement(VoiceCatalog,{items:[{...voice,available:false,verification:'candidate_unverified'}],onOpen:()=>{}}));
  assert.match(blocked,/暂不可用/);assert.ok(!blocked.includes('待试听验证'));
});
