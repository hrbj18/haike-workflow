export const N1_TEMPLATE_ID = 'avatar-deepblue-n1-v1';
export const N1_DEFAULTS = {sourceLabel: '', brand: '海客科技', englishLabel: 'HAIKE TECHNOLOGY', scenes: []};
export const N1_SCENE_KINDS = [
  {id: 'presenter', name: '主持人'}, {id: 'material', name: '图片 / 视频素材'},
  {id: 'screenshot', name: '来源截图'}, {id: 'data', name: '数据板'},
];

export function n1Value(value = {}) {
  return {...N1_DEFAULTS, ...value, titleLines: Array.from({length: 3}, (_, i) => value.titleLines?.[i] || ''), scenes: value.scenes || []};
}
export function n1ForSave(value = {}) {
  const next = n1Value(value);
  if (!next.titleLines.some(line => line.trim())) delete next.titleLines;
  return next;
}
export function newN1Scene(scenes = []) {
  const start = Number(scenes.at(-1)?.end) || 0;
  return {kind: 'presenter', start, end: Math.min(120, start + 3)};
}
export function validateN1(value, audioDuration) {
  const config = n1Value(value);
  if (config.titleLines.some(line => line.trim())) {
    if (!config.titleLines[0].trim()) return '请填写主标题，也可以清空三行使用自动标题。';
    if (config.titleLines.some((line, i) => [...line.trim()].length > (i === 0 ? 16 : 20))) return '主标题最多16字，两行副标题分别最多20字。';
  }
  for (const [field, limit, label] of [['sourceLabel', 40, '来源声明'], ['brand', 8, '品牌名称'], ['englishLabel', 40, '背景英文']]) {
    if ([...String(config[field] || '')].length > limit) return `${label}最多${limit}字。`;
  }
  if (!String(config.brand).trim()) return '请填写品牌名称，最多8字。';
  let previousEnd = 0;
  for (const [index, scene] of config.scenes.entries()) {
    const prefix = `第${index + 1}个画面`, start = Number(scene.start), end = Number(scene.end);
    if (!N1_SCENE_KINDS.some(kind => kind.id === scene.kind)) return `${prefix}请选择画面类型。`;
    if (scene.start === '' || scene.end === '' || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > 120) return `${prefix}的开始、结束时间需在0至120秒内，结束晚于开始。`;
    if (start < previousEnd) return `${prefix}与前一个画面重叠，请按时间先后排列。`;
    if (Number.isFinite(audioDuration) && end > audioDuration + 0.001) return `${prefix}超过口播音频的${audioDuration.toFixed(2)}秒，请调整结束时间。`;
    if (['material', 'screenshot'].includes(scene.kind) && !scene.assetId) return `${prefix}需要上传${scene.kind === 'screenshot' ? '截图' : '图片或视频'}。`;
    if (scene.kind === 'screenshot' && scene.asset?.kind === 'video') return `${prefix}的来源截图需要图片。`;
    if (scene.kind === 'data' && (!scene.rows?.length || scene.rows.length > 4 || scene.rows.some(row => !String(row).trim()))) return `${prefix}的数据板需要1至4行内容。`;
    if (scene.kind === 'data' && (scene.rows.some(row => [...row].length > 17) || [...(scene.dataTitle || '')].length > 16 || [...(scene.dataLabel || '')].length > 12)) return `${prefix}的数据标题最多16字，说明最多12字，每行最多17字。`;
    previousEnd = end;
  }
  return null;
}
