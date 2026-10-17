import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {avatarDefaultsDraft} from '../src/avatar-defaults-model.js';

const require=createRequire(import.meta.url),root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const result=await build({entryPoints:[resolve(root,'src/AvatarDefaults.jsx')],bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
const compiled={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,compiled,compiled.exports);
const {AvatarDefaultsFields,AvatarDefaultsSettings,AvatarDefaultsSummary}=compiled.exports;
const data={revision:0,scope_id:'a'.repeat(64),scope_type:'haike_account',values:{},templates:[{id:'avatar-deepblue-n1-v1',name:'深蓝视窗 N1'}],
  voices:[{id:'voice-one',name:'雅雅',available:true,image_file_id:'image-one',supplier_key:'MUST-NOT-APPEAR'}]};

test('口播页直接展示完整默认摘要，恢复旧稿时明确另建任务，不自动保存收费',()=>{
  const value={...data,ready:true,values:{voice_id:'voice-one',speech_rate:1.15,template_id:'avatar-deepblue-n1-v1',target_duration_seconds:25,max_charge_micros:5000000,allow_graphic_fallback:true}};
  const html=renderToStaticMarkup(React.createElement(AvatarDefaultsSummary,{data:value,hasDraft:true,onEdit:()=>{},onApply:()=>{}}));
  for(const text of ['雅雅','1.15倍速','深蓝视窗 N1','目标25秒','每条上限5元','允许图文备用','编辑默认设置','新建并采用预设','已有草稿和任务保持原参数'])assert.ok(html.includes(text),text);
  assert.ok(!html.includes('MUST-NOT-APPEAR'));
});

test('默认设置可编辑全部基础参数；未配置预算明确留空',()=>{
  const markup=renderToStaticMarkup(React.createElement(AvatarDefaultsFields,{data,draft:avatarDefaultsDraft(data),setDraft:()=>{},onUpload:()=>{}}));
  for(const label of ['默认音色','默认形象','配音倍速','默认模板','目标时长','每条预算上限','允许图文配音降级','默认联网搜索画面素材','找不到合适素材时明确暂停','未设置'])assert.ok(markup.includes(label),label);
  assert.ok(!markup.includes('MUST-NOT-APPEAR'));assert.ok(!markup.includes('value="5"'));assert.ok(!markup.includes('value="10"'));
  assert.match(markup,/最多六位小数/);assert.match(markup,/先保存不完整设置/);
});
test('保存或上传中锁定编辑，形象只显示当前账号媒体入口',()=>{
  const draft={...avatarDefaultsDraft(data),portrait_file_id:'image-one'};
  const markup=renderToStaticMarkup(React.createElement(AvatarDefaultsFields,{data,draft,setDraft:()=>{},onUpload:()=>{},busy:true}));
  assert.match(markup,/fieldset[^>]*disabled/);assert.match(markup,/\/api\/studio\/audio-center\/media\/image-one/);
  assert.ok(!markup.includes('supplier_key'));
});
test('设置入口说明只影响后续采用预设的新任务，不承诺自动开工',()=>{
  const markup=renderToStaticMarkup(React.createElement(AvatarDefaultsSettings));
  assert.match(markup,/数字人口播默认设置/);assert.match(markup,/编辑默认设置/);
  assert.match(markup,/明确指令优先/);assert.match(markup,/保存不会开始制作或发布/);
});
