import {N1_TEMPLATE_ID, n1ForSave, validateN1} from './n1-model.js';
import {INVESTMENT_TEMPLATE_ID, investmentForSave, validateInvestment} from './investment-model.js';
export const EXAMPLE_TEXT = "海客科技，让创作更简单。一个接口，连接配音、数字人和创作工作流。";
export const TEMPLATES = [
  { id: "avatar-safe-circle-v1", name: "模板1 · 圆框口播", ratio: "9:16", description: "素材卡片", poster: "template1-layout.png", kind: "布局示意" },
  { id: "avatar-full-width-v2", name: "模板2 · 全宽讲解", ratio: "9:16", description: "全宽素材带", poster: "template2-layout.png", kind: "布局示意" },
  { id: "avatar-template3-card-3x4-v001", name: "模板3 · 卡片讲解", ratio: "3:4", description: "白卡与章节", poster: "template3-layout.svg", kind: "版式示意", previewNote: "白卡与章节版式示意；上传你的人物和声音后生成。" },
  { id: INVESTMENT_TEMPLATE_ID, name: "模板6 · 招商A", ratio: "9:16", description: "紫蓝霓虹 · 全景口播 · 语义重点卡", poster: "investment-a-v6-layout.svg", kind: "版式示意", previewNote: "紫蓝招商封面、玻璃项目牌、红金贴纸和紫边白字幕。此图是版式示意；生成后使用本期人物、声音与文案。" },
  { id: N1_TEMPLATE_ID, name: "深蓝视窗 N1", ratio: "9:16", description: "深蓝主窗 · 四种画面模式", poster: "n1-public-presenter.png", featured: true, kind: "实际渲染样片 · 无声演示", sample: "n1-public-sample-v1.mp4", sampleNote: "15秒无声开发样片，使用通用几何人物与合成内容，由实际N1组件渲染；不代表口型或有声同步验收。", sampleDownload: "海客科技-深蓝视窗N1-通用无声演示.mp4", previewNote: "四张预览均取自同一实际渲染样片；生成后使用你的人物、声音与内容。", previews: [
    {id: 'presenter', name: '主持人', image: 'n1-public-presenter.png', description: '实际样片帧：通用几何人物在主窗内，下方圆框隐藏。'},
    {id: 'material', name: '素材', image: 'n1-public-material.png', description: '实际样片帧：主窗展示素材，下方圆框保留人物。'},
    {id: 'screenshot', name: '来源截图', image: 'n1-public-screenshot.png', description: '实际样片帧：合成说明截图与重点标注，下方圆框保留人物。'},
    {id: 'data', name: '数据板', image: 'n1-public-data.png', description: '实际样片帧：数据逐行出现，下方圆框保留人物。'},
  ] },
];
export function avatarInputForSave(input, aiDefaults = {enabled: false}) {
  const isN1 = input.templateId === N1_TEMPLATE_ID;
  const investment = input.templateId === INVESTMENT_TEMPLATE_ID;
  return {soundMode: input.soundMode, modelId: input.modelId, voiceId: input.voiceId, rate: input.rate,
    subtitles: input.subtitles, ...(typeof input.network_materials_enabled==='boolean'?{network_materials_enabled:input.network_materials_enabled}:{}), ai: isN1 ? {...aiDefaults, ...input.ai, enabled: false} : input.ai || aiDefaults,
    motion: isN1 || investment ? null : input.motion || null, ...(isN1 ? {n1: n1ForSave(input.n1)} : {}),
    ...(investment ? {investment: investmentForSave(input.investment)} : {}),
    ...(input.avatar_defaults_snapshot?{avatar_defaults_snapshot:input.avatar_defaults_snapshot}:{})};
}
export const TTS_MODEL_IDS = ['haike/cosyvoice', 'haike/cosyvoice-public', 'haike/internal-tts'];
export function localAvatarFile(asset) {
  return typeof Blob !== 'undefined' && asset?.file instanceof Blob ? asset.file : null;
}
export function hasAvatarAsset(asset) {
  return !!asset && ((typeof asset.id === 'string' && asset.id.length > 0) || !!localAvatarFile(asset));
}
export function normalizeAvatarMedia(input = {}) {
  return {...input, network_materials_enabled:typeof input.network_materials_enabled==='boolean'?input.network_materials_enabled:undefined, audio: hasAvatarAsset(input.audio) ? input.audio : null,
    portrait: hasAvatarAsset(input.portrait) ? input.portrait : null};
}
export function normalizeVoiceInput(input = {}) {
  const legacyModel = [...TTS_MODEL_IDS,'haike/tencent-tts'].includes(input.voiceId) ? input.voiceId : null;
  return { ...input, modelId: input.modelId || legacyModel || 'haike/cosyvoice',
    voiceId: legacyModel ? '' : String(input.voiceId || ''),
    requiresVoiceSelection: !!legacyModel || !!input.requiresVoiceSelection };
}
export function availableVoicesFromAccount(account, catalog = {}) {
  const enabled = new Set((account?.capabilities?.items || []).filter(v=>!['unconfigured','budget_required','blocked','disabled','unavailable'].includes(v.status)).map(v => v.model || v.id));
  if(catalog.mode==='internal_local')enabled.add('haike/internal-tts');
  return (catalog.items || []).filter(v => TTS_MODEL_IDS.includes(v.model) && enabled.has(v.model) && v.available !== false)
    .map(v => ({ ...v, rate: Number(v.preferences?.speech_rate || 1) }));
}
export function defaultVoiceId(current, voices, preferred = '') {
  // Missing or removed selections remain visible for explicit review.
  if (current) return [...TTS_MODEL_IDS,'haike/tencent-tts'].includes(current) ? '' : current;
  return voices.some(v => v.id === preferred) ? preferred : '';
}
export function validateInputs(input, availableVoices) {
  if (!TEMPLATES.some(t => t.id === input.templateId)) return { field: "template", message: "请选择一个可用模板。" };
  if (!input.text.trim()) return { field: "text", message: "请上传文案，或在文案框中粘贴内容。" };
  if ([...input.text].length > 5000) return { field: "text", message: "口播文案最多5,000字，请精简后再试。" };
  if (input.soundMode === "audio" && !hasAvatarAsset(input.audio)) return { field: "audio", message: "请上传一份口播音频。" };
  const sound = normalizeVoiceInput(input);
  if (input.soundMode === "voice" && sound.modelId === "haike/tencent-tts") return { field: "voice", message: "旧稿配音服务已停用，请重新选择海客音色，或上传已有音频。" };
  if (input.soundMode === "voice" && (!TTS_MODEL_IDS.includes(sound.modelId) || !availableVoices.some(v => v.id === sound.voiceId && v.model === sound.modelId))) return { field: "voice", message: "请在配音中心选择当前账号可用的音色。" };
  if (input.soundMode === 'voice' && (!Number.isFinite(Number(input.rate)) || Number(input.rate) < .5 || Number(input.rate) > 2)) return { field: 'voice', message: '配音倍率需在0.5至2.0之间。' };
  if (!["audio", "voice"].includes(input.soundMode)) return { field: "audio", message: "请选择声音来源。" };
  if (!hasAvatarAsset(input.portrait)) return { field: "portrait", message: "请上传人物正面图片。" };
  if (input.templateId === N1_TEMPLATE_ID) {
    const issue = validateN1(input.n1, input.soundMode === 'audio' ? Number(input.audio?.duration) : undefined);
    if (issue) return {field: 'n1', message: issue};
  }
  if (input.templateId === INVESTMENT_TEMPLATE_ID) {
    const issue = validateInvestment(input.investment);
    if (issue) return {field: 'investment', message: issue};
  }
  return null;
}
