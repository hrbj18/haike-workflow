import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filterVoices, operationState } from '../src/voice-model.js';
import { validateInputs } from '../src/generator-model.js';

const voices = [
  { id: 'voice_system', name: '海客口播', scope: 'system', language: 'zh', tags: ['清晰'], status: 'ready' },
  { id: 'voice_personal', name: '我的英语', scope: 'personal', language: 'en', tags: [], status: 'ready' },
];
test('系统与个人音色分别筛选，搜索名称、语言和标签', () => {
  assert.deepEqual(filterVoices(voices, { scope: 'system', search: '清晰' }).map(v => v.id), ['voice_system']);
  assert.deepEqual(filterVoices(voices, { scope: 'personal', language: 'en' }).map(v => v.id), ['voice_personal']);
  assert.equal(filterVoices(voices, { scope: 'personal', language: 'zh' }).length, 0);
});
test('切换账号后不把失效的个人音色替换成系统默认音色', () => {
  const input = { templateId: 'avatar-safe-circle-v1', text: '你好', soundMode: 'voice', voiceId: 'haike/cosyvoice', toneId: 'voice_old_account', portrait: {} };
  const models = [{ id: 'haike/cosyvoice' }];
  assert.equal(validateInputs(input, models, voices).field, 'voice');
  assert.equal(validateInputs({ ...input, toneId: 'voice_personal' }, models, voices), null);
  assert.equal(validateInputs({ ...input, toneId: 'voice_personal' }, models, voices.map(v => ({ ...v, status: 'unavailable' }))).field, 'voice');
});
test('已有音频保持免配音，音色库或模型不可用不阻断已有音频', () => {
  const input = { templateId: 'avatar-safe-circle-v1', text: '你好', soundMode: 'audio', voiceId: '', audio: {}, portrait: {} };
  assert.equal(validateInputs(input, [], []), null);
});
test('结果未知明确引导查询原任务，不提示重新克隆', () => {
  assert.match(operationState('submission_unknown'), /查询原任务/);
  assert.doesNotMatch(operationState('submission_unknown'), /重新创建|重新克隆/);
});
