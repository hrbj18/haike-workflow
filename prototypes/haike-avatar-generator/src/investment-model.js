export const INVESTMENT_TEMPLATE_ID = 'avatar-investment-a-v6';
export const INVESTMENT_DEFAULTS = {brand: '海客科技', headline: '', cta: '点击视频下方链接\n加入我们', opening: true, closing: true, emphasis: []};
export function investmentValue(value = {}) {
  return {...INVESTMENT_DEFAULTS, ...value, emphasis: (value.emphasis || []).map(e => typeof e === 'string' ? {match: e, text: e, kind: 'sticker', detail: '', footnote: ''} : {...e})};
}
export function investmentForSave(value = {}) {
  const next = investmentValue(value);
  if (!next.headline.trim()) delete next.headline;
  return next;
}
export function validateInvestment(value) {
  const config = investmentValue(value);
  for (const [key, limit, label] of [['brand', 14, '项目名称'], ['headline', 32, '封面标题'], ['cta', 32, '结尾引导']]) {
    if ([...String(config[key])].length > limit || key !== 'headline' && !String(config[key]).trim()) return `${label}需要1至${limit}字。`;
  }
  if (config.brand.includes('\n')) return '项目名称请使用一行。';
  for (const key of ['headline', 'cta']) {
    if (config[key] && (config[key].split('\n').length > 2 || config[key].split('\n').some(line => !line.trim()))) return '封面标题和结尾引导最多两行，不能包含空白行。';
  }
  if (config.emphasis.length > 32) return '最多设置32条重点内容。';
  const seen = new Set();
  for (const e of config.emphasis) {
    const match = String(e.match || '').replace(/[^\p{L}\p{N}_]/gu, '').toLowerCase();
    if (!match || seen.has(match)) return '请填写不重复的触发原文。';
    seen.add(match);
    if (!['sticker', 'card'].includes(e.kind)) return '重点形式请选择贴纸或信息卡。';
    for (const [key, limit, label] of [['match', 48, '触发原文'], ['text', 18, '重点标题'], ['detail', 48, '说明'], ['footnote', 64, '注释']]) {
      if ([...String(e[key] || '')].length > limit || ['match', 'text'].includes(key) && !String(e[key] || '').trim()) return `${label}最多${limit}字，触发原文和重点标题不能为空。`;
    }
  }
  return null;
}
