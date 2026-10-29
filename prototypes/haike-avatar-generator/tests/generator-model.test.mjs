import { test } from "node:test";
import assert from "node:assert/strict";
import { TEMPLATES, validateInputs, availableVoicesFromAccount, defaultVoiceId, normalizeVoiceInput, normalizeAvatarMedia } from "../src/generator-model.js";
const ready = () => ({ templateId: TEMPLATES[2].id, text: "海客科技", soundMode: "audio", audio: { id: "owned-audio", name: "我的口播.wav", duration: 12 }, portrait: { id: "owned-portrait", name: "人物.png" }, voiceId: "voice-a", rate: 1.2, title: "", subtitles: true });
test("已有音频无需配置配音模型", () => { assert.equal(validateInputs(ready(), []), null); });
test("未配置的音色不能通过校验", () => { assert.equal(validateInputs({ ...ready(), soundMode: "voice" }, []).field, "voice"); });
test("公共和私人音色按开通模型分别选择，旧稿必须明确重选音色", () => {
  const account={capabilities:{items:[
    {capability:"tts",model:"haike/tencent-tts",name:"腾讯精品配音"},
    {capability:"tts",model:"haike/cosyvoice",name:"CosyVoice"},
    {capability:"tts",model:"haike/cosyvoice-public",name:"海客公共音色"},
    {capability:"asr",model:"haike/tencent-asr",name:"识别"},
  ]}};
  const catalog={items:[{id:'public-a',model:'haike/cosyvoice-public',name:'海客清朗',available:true},{id:'private-b',model:'haike/cosyvoice',name:'我的声音',available:true},{id:'unready',model:'haike/cosyvoice',available:false},{id:'old',model:'haike/tencent-tts'}]};
  const voices=availableVoicesFromAccount(account,catalog);
  assert.deepEqual(voices.map(v=>v.id),['public-a','private-b']);
  assert.equal(defaultVoiceId('',voices,'public-a'),'public-a');
  assert.equal(defaultVoiceId('',voices,'not-owned'),'');
  assert.equal(defaultVoiceId('deleted',voices,'public-a'),'deleted');
  assert.equal(defaultVoiceId('haike/tencent-tts',voices),'');
  const old={...ready(),soundMode:"voice",voiceId:"haike/tencent-tts"};
  assert.match(validateInputs(old,[{id:"haike/tencent-tts"}]).message,/已停用/);
  assert.equal(validateInputs({...old,modelId:'haike/cosyvoice-public',voiceId:'public-a'},voices),null);
  assert.equal(validateInputs({...old,modelId:'haike/cosyvoice',voiceId:'public-a'},voices).field,'voice');
  assert.equal(validateInputs({...old,soundMode:"audio"},[]),null);
});
test('旧稿迁移保留文案资产，新稿保留真实voice ID与模型绑定',()=>{
  const old={...ready(),voiceId:'haike/cosyvoice',text:'保留原文'};
  const migrated=normalizeVoiceInput(old);
  assert.equal(migrated.modelId,'haike/cosyvoice');assert.equal(migrated.voiceId,'');assert.equal(migrated.requiresVoiceSelection,true);
  assert.equal(migrated.text,old.text);assert.equal(migrated.audio,old.audio);
  for(const [modelId,voiceId] of [['haike/cosyvoice-public','public-a'],['haike/cosyvoice','private-b'],['haike/cosyvoice','haike/voices/custom']]){
    const next=normalizeVoiceInput(JSON.parse(JSON.stringify({...ready(),modelId,voiceId})));
    assert.equal(next.modelId,modelId);assert.equal(next.voiceId,voiceId);
  }
  assert.deepEqual(availableVoicesFromAccount({capabilities:{items:[]}}, {items:[{id:'v',model:'haike/cosyvoice'}]}),[]);
  assert.deepEqual(availableVoicesFromAccount({capabilities:{items:[{model:'haike/cosyvoice'}]}}),[]);
});
test("缺文案、图片与音频分别定位必填项", () => {
  assert.equal(validateInputs({ ...ready(), text: "  " }, []).field, "text");
  assert.equal(validateInputs({ ...ready(), portrait: null }, []).field, "portrait");
  assert.equal(validateInputs({ ...ready(), audio: null }, []).field, "audio");
});
test('旧版无文件的示例占位不会冒充真实输入，已上传资产和本地文件保持不变', () => {
  const placeholder = {audio:{name:'海客介绍口播.wav',duration:6.56},portrait:{name:'人物示例.png'},text:'保留正文'};
  const restored = normalizeAvatarMedia(placeholder);
  assert.equal(restored.audio,null);assert.equal(restored.portrait,null);assert.equal(restored.text,placeholder.text);
  assert.equal(validateInputs({...ready(),audio:placeholder.audio},[]).field,'audio');
  assert.equal(validateInputs({...ready(),portrait:placeholder.portrait},[]).field,'portrait');
  const owned=ready(), local={file:new Blob(['local file'])};
  assert.equal(normalizeAvatarMedia(owned).audio,owned.audio);
  assert.equal(normalizeAvatarMedia({...owned,portrait:local}).portrait,local);
  const serialized={file:{name:'已序列化文件.wav',type:'audio/wav'}};
  assert.equal(normalizeAvatarMedia({...owned,audio:serialized}).audio,null);
  assert.equal(validateInputs({...owned,audio:serialized},[]).field,'audio');
  const server={id:'owned-audio',url:'/api/studio/assets/owned-audio',file:{}};
  assert.equal(normalizeAvatarMedia({...owned,audio:server}).audio,server);
});
test("未知模板和超长文案不默默替换或截断", () => {
  assert.equal(validateInputs({ ...ready(), templateId: "unknown" }, []).field, "template");
  assert.equal(validateInputs({ ...ready(), text: "字".repeat(5001) }, []).field, "text");
  assert.equal(validateInputs({ ...ready(), text: "字".repeat(5000) }, []), null);
});
