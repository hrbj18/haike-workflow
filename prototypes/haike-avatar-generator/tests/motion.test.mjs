import test from 'node:test';
import assert from 'node:assert/strict';
import {parseSrt,validateMotion,issueLabel,motionRenderRevision} from '../src/motion-model.js';

test('exact SRT timestamps, multiline and literal markup survive without interpolation',()=>{
  const result=parseSrt('1\r\n00:00:00,020 --> 00:00:02,380\r\n<本期原文>\r\n第二行\r\n\r\n2\r\n00:00:02,500 --> 00:00:06,500\r\n完整观点');
  assert.deepEqual(result[0],{start:.02,end:2.38,text:'<本期原文>\n第二行',en:''});
  assert.equal(result[1].start,2.5);
  assert.throws(()=>parseSrt('1\n00:99:00,000 --> 00:00:02,000\n字'));
  assert.throws(()=>parseSrt('1\n00:00:03,000 --> 00:00:02,000\n字'));
  assert.throws(()=>parseSrt('没有时码的原文'));
});
test('a narration, complete ordered transcript and explicit music choice are necessary',()=>{
  const input={source:{id:'owned'},segments:[{text:'完整'},{text:'原文'}],music:{mode:'none'}};
  assert.equal(validateMotion(input,'完整原文'),'');
  assert.match(validateMotion({...input,segments:[{text:'遗漏'}]},'完整原文'),/完整覆盖/);
  assert.match(validateMotion({...input,music:{mode:''}},'完整原文'),/请选择/);
  assert.match(validateMotion({...input,music:{mode:'track'}},'完整原文'),/上传/);
});
test('native missing bindings receive actionable labels',()=>{
  assert.match(issueLabel('anchor entry (entry)'),/开场.*动作落点/);
  assert.match(issueLabel('slot heading'),/标题/);
  assert.match(issueLabel('slot body-0'),/第1项文字/);
});
test('engineering download is bound to the completed render after a newer draft is saved',()=>{
  assert.equal(motionRenderRevision({parent_job_id:'studio-4',frozen_request:{draft:{revision:4}}}),4);
  assert.equal(motionRenderRevision({parent_job_id:'studio-4'}),4);
  assert.equal(motionRenderRevision({parent_job_id:'other',frozen_request:{draft:{revision:2}}}),2);
  assert.equal(motionRenderRevision({parent_job_id:'../private'}),undefined);
});
