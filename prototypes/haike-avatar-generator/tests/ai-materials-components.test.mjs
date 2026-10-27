import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const require=createRequire(import.meta.url);
const compiled=await build({
  entryPoints:[fileURLToPath(new URL('../src/AiMaterials.jsx',import.meta.url))],
  bundle:true,write:false,format:'cjs',platform:'node',packages:'external',jsx:'automatic',loader:{'.css':'empty'},
});

function materialMarkup(state,{value={},networkPolicyExplicit=true,networkRequired=false}={}) {
  const states=[state,''];
  const hooks={...React,useEffect(){},useState(initial){
    return [states.length?states.shift():typeof initial==='function'?initial():initial,()=>{}];
  }};
  const module={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(
    name=>name==='react'?hooks:require(name),module,module.exports);
  return renderToStaticMarkup(React.createElement(module.exports.AiMaterials,{
    value:{enabled:true,...value},networkPolicyExplicit,networkRequired,onChange(){},onPlan(){},
  }));
}

function planButton(html,label) {
  return [...html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].find(([, , content])=>content.includes(label));
}

test('当前Agent分析不要求开通中转服务，也不显示中转模型或免费承诺',()=>{
  const html=materialMarkup({analysis_mode:'agent',configured:false,chat_model:'relay-model-must-not-appear',image_model:'optional-image-model'});
  assert.match(html,/分析 · 当前Agent/);
  assert.match(html,/当前Agent读取素材并提交分析与分镜结果/);
  assert.doesNotMatch(html,/AI服务尚未配置|relay-model-must-not-appear|optional-image-model|免费试用/);
  const button=planButton(html,'准备素材，交给Agent分析');
  assert.ok(button);
  assert.doesNotMatch(button[1],/disabled/);
});

test('明确选择的兼容中转路线仍保留配置错误和按钮限制',()=>{
  const html=materialMarkup({analysis_mode:'relay',configured:false,chat_model:'legacy-model',image_model:'gpt-image-2',image_verified:false},{networkPolicyExplicit:false,value:{allow_images:true}});
  assert.match(html,/理解 · legacy-model/);
  assert.match(html,/兼容AI服务尚未配置/);
  assert.match(html,/gpt-image-2/);
  assert.match(html,/允许补齐 AI 示意插画/);
  assert.match(html,/插画数量上限/);
  assert.match(planButton(html,'AI 理解素材并建议分镜')[1],/disabled/);
});

test('Agent模式隐藏旧稿插画服务与降级控件，网络素材仍按本次选择',()=>{
  const html=materialMarkup({analysis_mode:'agent',configured:false,image_model:'gpt-image-2',image_verified:false},
    {networkRequired:true,value:{allow_images:true,max_images:2}});
  assert.match(html,/当前Agent先选已有素材，再搜索网络，Pexels作为备用/);
  assert.match(html,/当前Agent获得授权后生成并上传/);
  assert.doesNotMatch(html,/gpt-image|插画 ·|插画数量上限|允许补齐 AI 示意插画|管理员完成单张验收/);
  const offline=materialMarkup({analysis_mode:'agent',configured:false});
  assert.match(offline,/本次联网素材已关闭/);
});

test('状态读取失败仍明确提示，不把失败当成已准备好分析',()=>{
  const html=materialMarkup({status_error:true});
  assert.match(html,/素材分析状态暂时无法读取/);
  assert.match(planButton(html,'准备素材，交给Agent分析')[1],/disabled/);
});
