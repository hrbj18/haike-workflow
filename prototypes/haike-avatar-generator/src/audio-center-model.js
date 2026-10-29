export const AUDIO_CENTER_API = '/api/studio/audio-center';
export const TTS_MODELS = ['haike/cosyvoice', 'haike/cosyvoice-public', 'haike/internal-tts'];
const READY = new Set(['ready', 'available', 'active', 'ok', 'completed']);

export function voiceAvailable(voice) {
  return voice?.available !== false && (!voice?.status || READY.has(String(voice.status).toLowerCase()));
}

export function normalizeCatalog(value = {}) {
  const preferences = value.preferences || {};
  return {
    mode: value.mode || 'gateway',
    billing_mode: value.billing_mode,
    preferences,
    items: (value.items || []).map(v => ({
      ...v, id: String(v.id || ''), name: v.name || '未命名音色',
      model: v.model || 'haike/cosyvoice', kind: v.kind === 'public' ? 'public' : 'cloned',
      available: voiceAvailable(v), preferences: v.preferences || {},
    })).filter(v => v.id),
  };
}

export function voiceImageUrl(voice) {
  const file = voice?.preferences?.image_file_id;
  return file ? `${AUDIO_CENTER_API}/media/${encodeURIComponent(file)}` : '';
}

export function quotedMicros(quote) {
  const value = Number(quote?.max_charge_micros);
  if (!Number.isSafeInteger(value) || value < 0) throw new Error('报价缺少有效费用上限，请重新获取报价。');
  return value;
}

export function budgetMicros(value, minimum = 0) {
  const text = String(value).trim();
  if (!/^\d+(?:\.\d{1,6})?$/.test(text)) throw new Error('请输入有效费用上限，最多保留六位小数。');
  const [whole, fraction = ''] = text.split('.');
  const micros = Number(whole) * 1000000 + Number(fraction.padEnd(6, '0'));
  if (!Number.isSafeInteger(micros) || micros < minimum || micros > 1000000000) throw new Error('费用上限不能低于报价，最高为1,000元。');
  return micros;
}

export function makeVoiceQuote(operation, input) {
  if (operation === 'clone') {
    if (!input.name?.trim() || !input.audio_file || input.consent !== true) throw new Error('请填写名称、上传录音并确认使用权。');
    return { model: 'haike/voice-clone', input: { name: input.name.trim(), audio_file: input.audio_file, consent: true } };
  }
  if (operation !== 'preview' || !input.voice?.id || !voiceAvailable(input.voice)) throw new Error('请选择当前可用的音色。');
  if (!TTS_MODELS.includes(input.voice.model)) throw new Error('当前音色暂不支持试听。');
  const text = String(input.text || '').trim();
  if (!text || text.length > 180) throw new Error('试听文案需为1至180字。');
  const rate = Number(input.speech_rate);
  if (!Number.isFinite(rate) || rate < .5 || rate > 2) throw new Error('配音倍率需在0.5至2.0之间。');
  return { model: input.voice.model, input: { text, voice_id: input.voice.id, speech_rate: rate } };
}

export function paidJobBody(quote, budget, confirmed) {
  if (confirmed !== true) throw new Error('请先确认本次报价和费用上限。');
  const operationId = quote?.operation_id;
  if (!operationId || !/^call_[a-f0-9]{32}$/.test(operationId)) throw new Error('报价缺少可恢复的调用编号，请更新中转站后重试。');
  if (!quote.id) throw new Error('报价编号缺失。');
  if (quote.expires_at && new Date(quote.expires_at).getTime() <= Date.now()) throw new Error('报价已过期，请返回重新获取报价。');
  return { quote_id: quote.id, max_charge_micros: budgetMicros(budget, quotedMicros(quote)), confirmed: true, operation_id: operationId };
}

export function jobState(value = {}) {
  const status = value.status || 'pending';
  return { ...value, status, unresolved: ['pending', 'queued', 'running', 'processing', 'submitted', 'submitting', 'submission_unknown', 'uncertain', 'unknown'].includes(status) };
}
