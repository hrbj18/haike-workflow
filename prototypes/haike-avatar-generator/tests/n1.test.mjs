import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {TEMPLATES, validateInputs, avatarInputForSave} from '../src/generator-model.js';
import {N1_TEMPLATE_ID, n1ForSave, validateN1} from '../src/n1-model.js';

test('N1默认全主持人，自动标题不混入演示文案，持久化保留已上传素材', () => {
  const config=n1ForSave();
  assert.deepEqual(config.scenes,[]);
  assert.equal(config.titleLines,undefined);
  assert.equal(config.sourceLabel,'');
  assert.equal(validateN1(config,5.12),null);
  const draft={templateId:N1_TEMPLATE_ID,text:'我的口播',soundMode:'audio',audio:{id:'owned-audio',duration:5.12},portrait:{id:'owned-portrait',name:'人物.png'},n1:{scenes:[{kind:'material',start:0,end:2,assetId:'asset-a',asset:{id:'asset-a',name:'产品.png',kind:'image',url:'/api/studio/assets/asset-a'}}]}};
  assert.equal(validateInputs(JSON.parse(JSON.stringify(draft)),[]),null);
  assert.equal(n1ForSave(draft.n1).scenes[0].asset.id,'asset-a');
});

test('N1在报价前阻止超音轨、重叠、缺素材与超窗数据，副标题可留空', () => {
  assert.equal(validateN1({titleLines:['主标题','','']},5.12),null);
  assert.match(validateN1({scenes:[{kind:'presenter',start:0,end:6}]},5.12),/超过口播/);
  assert.match(validateN1({scenes:[{kind:'presenter',start:0,end:3},{kind:'presenter',start:2,end:4}]},5.12),/重叠/);
  assert.match(validateN1({scenes:[{kind:'screenshot',start:0,end:2}]},5.12),/上传截图/);
  assert.match(validateN1({scenes:[{kind:'data',start:0,end:2,rows:['字'.repeat(18)]}]},5.12),/每行最多17字/);
});

test('切回模板1/2/3只保存它们允许的输入，N1配置留在编辑器切回时恢复', () => {
  const n1={titleLines:['我的标题','',''],scenes:[{kind:'data',start:0,end:2,rows:['保留我的数据']}]};
  const current={templateId:N1_TEMPLATE_ID,soundMode:'audio',modelId:'haike/cosyvoice',voiceId:'private-a',rate:1.1,subtitles:false,
    n1,ai:{enabled:true,materials:[{id:'retained-material'}]},motion:{style:'quick',layout:'portrait'}};
  const n1Payload=avatarInputForSave(current);
  assert.equal(n1Payload.ai.enabled,false);assert.equal(n1Payload.motion,null);
  assert.deepEqual(n1Payload.n1.scenes,n1.scenes);
  for(const template of TEMPLATES.filter(template=>template.id!==N1_TEMPLATE_ID&&template.id!=='avatar-investment-a-v6')){
    const switched={...current,templateId:template.id,motion:null};
    const payload=JSON.parse(JSON.stringify(avatarInputForSave(switched)));
    assert.ok(!Object.hasOwn(payload,'n1'),template.id);
    assert.deepEqual(Object.keys(payload).sort(),['soundMode','modelId','voiceId','rate','subtitles','ai','motion'].sort());
    assert.deepEqual(payload.ai,current.ai);assert.equal(payload.voiceId,'private-a');
    assert.equal(switched.n1,n1);
    const restored=avatarInputForSave({...switched,templateId:N1_TEMPLATE_ID});
    assert.deepEqual(restored.n1.scenes,n1.scenes);assert.deepEqual(restored.n1.titleLines,n1.titleLines);
  }
  assert.equal(current.ai.enabled,true);assert.equal(current.n1,n1);
});

const require=createRequire(import.meta.url),root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const result=await build({entryPoints:[resolve(root,'src/TemplatePreview.jsx'),resolve(root,'src/N1Settings.jsx'),resolve(root,'src/App.jsx')],bundle:true,write:false,outdir:'unused',format:'cjs',platform:'node',packages:'external',jsx:'automatic',define:{'import.meta.env.BASE_URL':'"/"'},loader:{'.css':'empty'}});
function exported(file){const compiled={exports:{}};new Function('require','module','exports',result.outputFiles.find(output=>output.path.endsWith(file)).text)(require,compiled,compiled.exports);return compiled.exports;}
const {TemplatePreview,TemplateSampleDialog}=exported('TemplatePreview.js'),{N1Settings}=exported('N1Settings.js'),{App}=exported('App.js');
test('新电脑口播页面要求真实音频与人物输入，不请求不存在的示例声音', () => {
  const previous=globalThis.location;
  globalThis.location={search:''};
  try{
    const markup=renderToStaticMarkup(React.createElement(App));
    assert.match(markup,/尚未选择音频/);assert.match(markup,/尚未上传图片/);
    assert.match(markup,/portrait-placeholder\.svg/);
    assert.ok(!markup.includes('narration.wav'));assert.ok(!markup.includes('海客介绍口播.wav'));
    assert.ok(!markup.includes('presenter.png'));assert.ok(!markup.includes('播放样片'));
  }finally{
    if(previous===undefined)delete globalThis.location;else globalThis.location=previous;
  }
});
test('模板预览列出四模式，N1编辑沿用带标签控件且默认折叠画面安排', () => {
  const template=TEMPLATES.find(item=>item.id===N1_TEMPLATE_ID),noop=()=>{};
  const preview=renderToStaticMarkup(React.createElement(TemplatePreview,{template,onPlay:noop}));
  for(const label of ['主持人','来源截图','数据板','实际样片帧','播放样片','无声'])assert.ok(preview.includes(label),label);
  assert.equal((preview.match(/aria-pressed=/g)||[]).length,4);
  assert.equal(template.sample,'n1-public-sample-v1.mp4');assert.match(template.sampleNote,/15秒.*通用几何人物/);
  const sample=renderToStaticMarkup(React.createElement(TemplateSampleDialog,{template,onClose:noop}));
  assert.match(sample,/n1-public-sample-v1\.mp4/);assert.match(sample,/下载样片/);
  const missingSample=renderToStaticMarkup(React.createElement(TemplateSampleDialog,{template:TEMPLATES[2],onClose:noop}));
  assert.ok(!missingSample.includes('<video'));assert.ok(!missingSample.includes('下载样片'));assert.match(missingSample,/版式示意/);
  const fields=renderToStaticMarkup(React.createElement(N1Settings,{onChange:noop,onTitle:noop,onFile:noop}));
  for(const label of ['主标题','副标题','来源声明','品牌名称','背景淡英文','画面安排'])assert.ok(fields.includes(label),label);
  assert.match(fields,/aria-expanded="false"/);assert.ok(!fields.includes('AI辅助制作'));
});
test('模板3保留明确的源码版式示意，不引用缺失或未授权的旧样片', async () => {
  for(const template of TEMPLATES.filter(item=>item.id==='avatar-template3-card-3x4-v001')){
    assert.equal(template.kind,'版式示意');assert.equal(template.sample,undefined);
    for(const name of [template.poster,...(template.previews||[]).map(preview=>preview.image)]){
      assert.ok(name.endsWith('.svg'),name);
      const svg=await readFile(resolve(root,'public/assets',name),'utf8');
      assert.match(svg,/<svg/);assert.match(svg,/Original vector layout reference/);
      assert.ok(!/<image\b|data:image|https?:\/\/(?!www\.w3\.org)/.test(svg),name);
    }
  }
});
test('N1可分发样片和四帧来自公开源码输入，与来源清单的实际哈希一致', async () => {
  const template=TEMPLATES.find(item=>item.id===N1_TEMPLATE_ID);
  const manifest=JSON.parse(await readFile(resolve(root,'public/assets/n1-public-provenance.json'),'utf8'));
  assert.equal(manifest.private_media_used,false);assert.equal(manifest.cloud_calls,0);assert.equal(manifest.queue_used,false);
  assert.equal(manifest.render_kind,'offline_development_showcase');assert.equal(manifest.video.file,template.sample);
  assert.equal(manifest.verification.frames,450);assert.equal(manifest.verification.audio_streams,0);assert.equal(manifest.verification.full_decode,'pass');
  assert.deepEqual(template.previews.map(item=>item.image),manifest.frames.map(item=>item.file));
  for(const item of [manifest.video,...manifest.frames]){
    const bytes=await readFile(resolve(root,'public/assets',item.file));
    assert.equal(bytes.length,item.bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),item.sha256);
  }
  for(const item of manifest.inputs){
    assert.match(item.path,/^Haike_video\/templates\/avatar-deepblue-n1\/showcase\//);
    const bytes=await readFile(resolve(root,'../..',item.path));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),item.sha256);
  }
});
