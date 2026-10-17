import {budgetMicros} from './audio-center-model.js';

export const AVATAR_DEFAULTS_API='/api/studio/audio-center/avatar-defaults';
const display=value=>value==null?'':String(value);
const ID=/^[A-Za-z0-9_.:-]{1,160}$/;

export function avatarDefaultsDraft(value) {
  if(!Number.isInteger(value?.revision)||value.revision<0||!/^[a-f0-9]{64}$/.test(value?.scope_id||'')||!value.values||typeof value.values!=='object')throw new Error('默认设置返回不完整，请重新读取。');
  const v=value.values,amount=v.max_charge_micros;
  if(amount!=null&&(!Number.isSafeInteger(amount)||amount<=0))throw new Error('已保存预算无法读取，请核对原记录。');
  return {revision:value.revision,scope_id:value.scope_id,voice_id:display(v.voice_id),portrait_file_id:display(v.portrait_file_id),
    speech_rate:display(v.speech_rate),template_id:display(v.template_id),target_duration_seconds:display(v.target_duration_seconds),
    budget:amount==null?'':String(amount/1000000),network_materials_enabled:v.network_materials_enabled===true,allow_graphic_fallback:v.allow_graphic_fallback===true?'allow':v.allow_graphic_fallback===false?'deny':''};
}

export function avatarDefaultsPayload(draft) {
  if(!Number.isInteger(draft.revision)||draft.revision<0||!/^[a-f0-9]{64}$/.test(draft.scope_id||''))throw new Error('请先重新读取当前账号的默认设置。');
  function identity(value) {if(!value)return null;if(!ID.test(value))throw new Error('音色或形象编号无效，请重新选择。');return value;}
  function number(value,min,max,label) {if(String(value).trim()==='')return null;const result=Number(value);if(!Number.isFinite(result)||result<min||result>max)throw new Error(`${label}需要在${min}至${max}之间。`);return result;}
  if(!['','allow','deny'].includes(draft.allow_graphic_fallback))throw new Error('请明确选择是否允许图文配音降级。');
  return {expected_revision:draft.revision,expected_scope_id:draft.scope_id,values:{
    voice_id:identity(draft.voice_id),portrait_file_id:identity(draft.portrait_file_id),template_id:identity(draft.template_id),
    speech_rate:number(draft.speech_rate,.5,2,'倍速'),target_duration_seconds:number(draft.target_duration_seconds,1,120,'目标时长'),
    max_charge_micros:String(draft.budget).trim()===''?null:budgetMicros(draft.budget,1),
    network_materials_enabled:draft.network_materials_enabled===true,
    allow_graphic_fallback:draft.allow_graphic_fallback===''?null:draft.allow_graphic_fallback==='allow'}};
}

export async function requestAvatarDefaults({body,signal,fetchImpl=fetch}={}) {
  const response=await fetchImpl(AVATAR_DEFAULTS_API,{signal,...(body===undefined?{}:{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  let value;try {value=await response.json();if(!value||typeof value!=='object')throw new Error();}catch{throw new Error('默认设置服务没有返回有效记录，请重新读取。');}
  if(!response.ok)throw Object.assign(new Error(typeof value.detail==='string'?value.detail:'默认设置未保存，请重新读取后核对。'),{status:response.status});
  return value;
}

export function avatarPresetInput(input,data) {
  if(!data?.ready||!data.snapshot)throw new Error('请先补全当前账号的默认设置。');
  const v=data.values;
  return {...input,soundMode:'voice',voiceId:v.voice_id,modelId:data.voice_model,rate:v.speech_rate,
    templateId:v.template_id,motion:null,requiresVoiceSelection:false,network_materials_enabled:v.network_materials_enabled===true,avatar_defaults_snapshot:data.snapshot};
}

export function presetBudget(input) {
  const amount=input?.avatar_defaults_snapshot?.values?.max_charge_micros;
  return Number.isSafeInteger(amount)&&amount>0?String(amount/1000000):'';
}

export function shouldApplyAvatarPreset({restored=false,edited=false,explicit=false,handled=false,ready=false}={}) {
  return ready&&!restored&&!edited&&!explicit&&!handled;
}
