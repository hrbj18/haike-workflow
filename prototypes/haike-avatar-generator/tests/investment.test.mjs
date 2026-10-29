import test from 'node:test';
import assert from 'node:assert/strict';
import {TEMPLATES, avatarInputForSave} from '../src/generator-model.js';
import {INVESTMENT_TEMPLATE_ID, investmentForSave, validateInvestment} from '../src/investment-model.js';

test('招商A保存本期配置、切换模板保留编辑状态但不污染其他模板', () => {
  const config = {brand:'本期项目',headline:'本期招商\n合作机会',cta:'加入本期项目',opening:false,closing:true,
    emphasis:[{match:'今天收现金',text:'现金生意',kind:'card',detail:'本期脚本内容',footnote:''}]};
  const input = {templateId:INVESTMENT_TEMPLATE_ID,investment:config,soundMode:'audio',subtitles:true,motion:{style:'quick'}};
  const saved = avatarInputForSave(input);
  assert.deepEqual(saved.investment,config);
  assert.equal(saved.motion,null);
  assert.equal(validateInvestment(config),null);
  assert.equal(investmentForSave().headline,undefined);
  const switched = avatarInputForSave({...input,templateId:'avatar-safe-circle-v1'});
  assert.ok(!Object.hasOwn(switched,'investment'));
  assert.equal(input.investment,config);
  assert.equal(TEMPLATES.find(t=>t.id===INVESTMENT_TEMPLATE_ID).poster,'investment-a-v6-layout.svg');
});

test('招商A字段上限和重复触发词在报价前可见', () => {
  assert.match(validateInvestment({brand:'字'.repeat(15)}),/项目名称/);
  assert.match(validateInvestment({emphasis:['现金','现 金']}),/重复/);
  assert.match(validateInvestment({emphasis:[{match:'现金',text:'字'.repeat(19),kind:'sticker'}]}),/重点标题/);
});
