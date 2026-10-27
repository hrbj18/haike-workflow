import test from 'node:test';
import assert from 'node:assert/strict';
import { budgetMicros, jobState, makeVoiceQuote, normalizeCatalog, paidJobBody, voiceImageUrl } from '../src/audio-center-model.js';
import { pendingAudioOperation,rememberAudioOperation,forgetAudioOperation } from '../src/audio-operation-store.js';
const voice={id:'public-a',model:'haike/cosyvoice-public',status:'ready'};
const quote={id:'q_1',operation_id:'call_'+'a'.repeat(32),max_charge_micros:1200,expires_at:'2099-01-01T00:00:00Z'};

test('试听必须按选中音色绑定的公共或私人模型报价',()=>{
  assert.deepEqual(makeVoiceQuote('preview',{voice,text:' 测试文案 ',speech_rate:1.1}),{model:'haike/cosyvoice-public',input:{text:'测试文案',voice_id:'public-a',speech_rate:1.1}});
  assert.equal(makeVoiceQuote('preview',{voice:{...voice,id:'private-b',model:'haike/cosyvoice'},text:'私有试听',speech_rate:1}).model,'haike/cosyvoice');
  assert.throws(()=>makeVoiceQuote('preview',{voice:{...voice,status:'processing'},text:'不能使用',speech_rate:1}),/可用/);
});
test('克隆报价必须具备样音、名称、明确授权；不接受静默默认授权',()=>{
  assert.throws(()=>makeVoiceQuote('clone',{name:'我的声音',audio_file:'f_1'}),/使用权/);
  assert.deepEqual(makeVoiceQuote('clone',{name:' 我的声音 ',audio_file:'f_1',consent:true}),{model:'haike/voice-clone',input:{name:'我的声音',audio_file:'f_1',consent:true}});
});
test('付费提交要求明确确认、有效费用上限与原报价的稳定操作编号',()=>{
  assert.throws(()=>paidJobBody(quote,'.0012',false),/确认/);
  assert.throws(()=>paidJobBody(quote,'0.0011',true),/不能低于/);
  assert.throws(()=>paidJobBody({...quote,operation_id:''},'1',true),/调用编号/);
  assert.throws(()=>paidJobBody({...quote,expires_at:'2000-01-01T00:00:00Z'},'1',true),/过期/);
  const first=paidJobBody(quote,'0.001200',true),retry=paidJobBody(JSON.parse(JSON.stringify(quote)),'0.001200',true);
  assert.deepEqual(first,retry);assert.equal(first.operation_id,quote.operation_id);assert.equal(first.max_charge_micros,1200);
  assert.equal(budgetMicros('0',0),0);assert.throws(()=>budgetMicros('1e3'),/有效/);assert.throws(()=>budgetMicros('-1'),/有效/);
});
test('未知提交保持阻塞，只有已知终态允许新报价；账号列表不会补造公共音色',()=>{
  for(const status of ['submission_unknown','running','queued','uncertain'])assert.equal(jobState({status}).unresolved,true);
  for(const status of ['completed','failed'])assert.equal(jobState({status}).unresolved,false);
  assert.deepEqual(normalizeCatalog({}).items,[]);
  const result=normalizeCatalog({items:[{...voice,name:'公开',kind:'public',preferences:{image_file_id:'file/one'}}],preferences:{voice_id:'public-a'}});
  assert.equal(result.items[0].available,true);assert.equal(result.preferences.voice_id,'public-a');
  assert.equal(voiceImageUrl(result.items[0]),'/api/studio/audio-center/media/file%2Fone');
});
test('关闭弹窗后同一标签页仍可恢复原调用，只存操作编号；账号切换可清除',()=>{
  const stored=new Map(),previous=globalThis.sessionStorage;
  globalThis.sessionStorage={getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)};
  try{
    rememberAudioOperation(quote.operation_id);assert.equal(pendingAudioOperation(),quote.operation_id);
    assert.deepEqual([...stored.values()],[quote.operation_id]);
    assert.throws(()=>rememberAudioOperation('sk-key'),/编号/);
    forgetAudioOperation();assert.equal(pendingAudioOperation(),'');
  }finally{if(previous===undefined)delete globalThis.sessionStorage;else globalThis.sessionStorage=previous;}
});
