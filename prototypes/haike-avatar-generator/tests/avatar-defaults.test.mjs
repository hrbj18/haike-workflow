import test from 'node:test';
import assert from 'node:assert/strict';
import {avatarDefaultsDraft,avatarDefaultsPayload,requestAvatarDefaults,avatarPresetInput,presetBudget,shouldApplyAvatarPreset} from '../src/avatar-defaults-model.js';

const response={revision:0,scope_id:'a'.repeat(64),values:{voice_id:'voice-one',speech_rate:1.15,
  portrait_file_id:'image-one',template_id:null,target_duration_seconds:null,max_charge_micros:null,allow_graphic_fallback:null}};

test('新任务自动采用完整预设；恢复草稿、已有修改、明确专业模式都保留原参数',()=>{
  assert.equal(shouldApplyAvatarPreset({ready:true}),true);
  for(const field of ['restored','edited','explicit','handled'])assert.equal(shouldApplyAvatarPreset({ready:true,[field]:true}),false);
  assert.equal(shouldApplyAvatarPreset({ready:false}),false);
  const data={ready:true,values:{...response.values,template_id:'avatar-deepblue-n1-v1',max_charge_micros:2531064},voice_model:'haike/internal-tts',snapshot:{values:{max_charge_micros:2531064}}};
  const old={text:'用户自己的文案',audio:{id:'old-audio'},rate:1};
  const next=avatarPresetInput(old,data);
  assert.equal(next.text,old.text);assert.equal(next.rate,1.15);assert.equal(next.soundMode,'voice');assert.equal(next.voiceId,'voice-one');
  assert.equal(old.rate,1);assert.equal(presetBudget(next),'2.531064');assert.equal(presetBudget(old),'');
  assert.throws(()=>avatarPresetInput(old,{...data,ready:false}),/补全/);
});

test('首次读取保留未设置预算和模板，继承既有音色倍率',()=>{
  const draft=avatarDefaultsDraft(response);
  assert.equal(draft.budget,'');assert.equal(draft.template_id,'');assert.equal(draft.speech_rate,'1.15');
  const body=avatarDefaultsPayload(draft);
  assert.equal(body.expected_scope_id,response.scope_id);assert.equal(body.values.max_charge_micros,null);
  assert.equal(body.values.allow_graphic_fallback,null);
  assert.equal(draft.network_materials_enabled,false);assert.equal(body.values.network_materials_enabled,false);
});

test('联网素材独立于AI辅助与图文降级，预设采用后冻结到新输入',()=>{
  const data={ready:true,values:{...response.values,network_materials_enabled:true,allow_graphic_fallback:true},snapshot:{values:{network_materials_enabled:true}},voice_model:'haike/internal-tts'};
  const input={text:'已有文案',network_materials_enabled:false,ai:{enabled:false}},next=avatarPresetInput(input,data);
  assert.equal(next.network_materials_enabled,true);assert.equal(next.ai.enabled,false);assert.equal(input.network_materials_enabled,false);
  const payload=avatarDefaultsPayload({...avatarDefaultsDraft(response),network_materials_enabled:true,allow_graphic_fallback:'deny'});
  assert.equal(payload.values.network_materials_enabled,true);assert.equal(payload.values.allow_graphic_fallback,false);
});
test('按六位精度保存用户预算，false降级选择不会丢失',()=>{
  const draft={...avatarDefaultsDraft(response),budget:'2.531064',allow_graphic_fallback:'deny',target_duration_seconds:'30',template_id:'avatar-deepblue-n1-v1'};
  const body=avatarDefaultsPayload(draft);
  assert.equal(body.values.max_charge_micros,2531064);assert.equal(body.values.allow_graphic_fallback,false);
  assert.equal(body.values.target_duration_seconds,30);
});
test('预算零、超精度和无效倍率在保存前拒绝',()=>{
  for(const budget of ['0','-1','2.1234567','1001'])assert.throws(()=>avatarDefaultsPayload({...avatarDefaultsDraft(response),budget}));
  assert.throws(()=>avatarDefaultsPayload({...avatarDefaultsDraft(response),speech_rate:'NaN'}));
  assert.throws(()=>avatarDefaultsPayload({...avatarDefaultsDraft(response),target_duration_seconds:'121'}));
  assert.throws(()=>avatarDefaultsDraft({values:{}}));
});
test('保存用PUT携带账号与版本；失败保留未知而非宣称保存成功',async()=>{
  const body=avatarDefaultsPayload(avatarDefaultsDraft(response));
  const fetchImpl=async(url,options)=>{assert.equal(url,'/api/studio/audio-center/avatar-defaults');
    assert.equal(options.method,'PUT');assert.deepEqual(JSON.parse(options.body),body);
    return {ok:false,status:409,json:async()=>({detail:'账号已变化'})};};
  await assert.rejects(()=>requestAvatarDefaults({body,fetchImpl}),error=>error.status===409&&error.message==='账号已变化');
  await assert.rejects(()=>requestAvatarDefaults({fetchImpl:async()=>({ok:true,json:async()=>{throw new Error('bad json');}})}),/没有返回/);
});
