export const voiceLabel = voice => ({ zh: '普通话', en: '英语', yue: '粤语' })[voice.language] || '多语言';
export function filterVoices(voices, { scope = 'system', search = '', language = 'all' } = {}) {
  const term = search.trim().toLocaleLowerCase();
  return voices.filter(voice => voice.scope === scope && (language === 'all' || voice.language === language) && (!term || [voice.name, ...voice.tags, voiceLabel(voice)].join(' ').toLocaleLowerCase().includes(term)));
}
export function operationState(status) {
  return ({ queued: '排队中', submitting: '正在提交阿里百炼', running: '正在处理，完成后自动进入音色库', polling: '正在查询原任务', succeeded: '已完成', failed: '未完成，费用已释放；请检查录音或联系管理员', cancelled: '已取消', submission_unknown: '受理结果待确认，请查询原任务，避免重复创建' })[status] || '进度待查询';
}
