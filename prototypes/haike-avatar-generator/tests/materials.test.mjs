import test from 'node:test';
import assert from 'node:assert/strict';
import {materialImport,materialQuery,metadataUpdate} from '../src/materials-model.js';
import {normalizeCatalog,makeVoiceQuote} from '../src/audio-center-model.js';
import {availableVoicesFromAccount,validateInputs,TEMPLATES} from '../src/generator-model.js';

test('素材检索保留用户条件并正确编码，导入只接受真实路径与已有方式',()=>{
  const query=new URLSearchParams(materialQuery({query:' 产品 & 标签 ',archived:'archived',aspect:'portrait',page:2}));
  assert.equal(query.get('query'),'产品 & 标签');assert.equal(query.get('archived'),'archived');assert.equal(query.get('page'),'2');
  assert.deepEqual(materialImport({kind:'folder',path:' D:\\我的素材 '}),{kind:'folder',path:'D:\\我的素材'});
  assert.throws(()=>materialImport({kind:'upload',path:'file.mp4'}),/导入方式/);assert.throws(()=>materialImport({kind:'file',path:'  '}),/完整路径/);
});
test('整理保存使用原元数据版本，不覆盖文件或伪造审核状态',()=>{
  const item={id:'MAT-a',metadata:{revision:7}};
  const payload=metadataUpdate(item,{tags:'产品，产品, 知识\n口播',collections:'素材A',notes:'保留来源',archived:true});
  assert.deepEqual(payload,{items:[{media_id:'MAT-a',expected_revision:7}],patch:{tags:['产品','知识','口播'],collections:['素材A'],notes:'保留来源',archived:true}});
  assert.throws(()=>metadataUpdate({id:'MAT-a',metadata:{}},{}),/重新读取/);assert.throws(()=>metadataUpdate(item,{notes:'字'.repeat(4001)}),/4,000/);
});
test('内部备用音色从账号能力参与选择、表单校验与报价；元数据不丢失',()=>{
  const catalog=normalizeCatalog({mode:'internal_local',billing_mode:'provider_direct_estimate',items:[{id:'internal-a',name:'内部音色',model:'haike/internal-tts',kind:'public',status:'ready'}]});
  assert.equal(catalog.mode,'internal_local');assert.equal(catalog.billing_mode,'provider_direct_estimate');
  const voices=availableVoicesFromAccount({capabilities:{items:[{model:'haike/internal-tts',status:'available'}]}},catalog);
  assert.equal(voices.length,1);
  assert.equal(availableVoicesFromAccount({mode:'gateway',capabilities:{items:[]}},catalog).length,1);
  assert.equal(makeVoiceQuote('preview',{voice:voices[0],text:'试听',speech_rate:1}).model,'haike/internal-tts');
  assert.equal(validateInputs({templateId:TEMPLATES[0].id,text:'正文',soundMode:'voice',modelId:'haike/internal-tts',voiceId:'internal-a',rate:1,portrait:{id:'local'}},voices),null);
});
