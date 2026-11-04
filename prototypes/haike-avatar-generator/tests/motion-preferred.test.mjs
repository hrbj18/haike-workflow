import test from 'node:test';
import assert from 'node:assert/strict';
import {motionSelection,productionInstruction} from '../src/motion-preferred-model.js';
import {avatarInputForSave} from '../src/generator-model.js';
const card={id:'canonical',name:'测试动效',preferred_production:{template_id:'test-motion',version:'exact.2',production_contract:'fixed-contract',prepare_endpoint:'/fixed-prepare',required_inputs:[{path:'input.asr',label:'真实时钟'}]}};
test('selection persists only exact identities and keeps existing sound and draft parameters',()=>{
 const old={templateId:'avatar-template3-card-3x4-v001',text:'原文',soundMode:'audio',audio:{id:'existing'},portrait:{id:'portrait'},rate:1.1,ai:{materials:[{id:'material'}]}};
 const next={...old,motion_production:motionSelection(card)};
 assert.equal(next.audio,old.audio);assert.equal(next.portrait,old.portrait);assert.equal(next.ai,old.ai);
 const stored=avatarInputForSave(next);assert.deepEqual(stored.motion_production,{gallery_id:'canonical',template_id:'test-motion',version:'exact.2',production_contract:'fixed-contract'});assert.equal(stored.rate,1.1);assert.equal(stored.soundMode,'audio');assert.deepEqual(stored.ai.materials,old.ai.materials);
});
test('handoff fixes production identity and refers to the saved original draft',()=>{
 const value=productionInstruction(card,'studio-owned');assert.match(value,/test-motion@exact.2/);assert.match(value,/studio-owned/);assert.match(value,/fixed-contract/);assert.match(value,/真实时钟/);assert.match(value,/不重复购买/);
});
