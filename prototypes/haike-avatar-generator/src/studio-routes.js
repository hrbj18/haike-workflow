export const LEGACY_TOOLS = [
  { path: '/legacy/projects', label: '项目工作台', description: '查看项目、编排片段与审核成片' },
  { path: '/material-library', label: '素材库', description: '检索、查看与管理已有素材' },
];
export const MANAGEMENT_ROUTES = [
  ['/projects','我的作品'],
  ['/task-center','任务总览'],
  ['/calendar','发布日历'],
];

export function audioRoute(locationLike) {
  const query = new URLSearchParams(locationLike.search || '');
  return { open: query.get('panel') === 'audio', voiceId: query.get('voice') || '', operationId: query.get('audio_job') || '' };
}

export function audioHref(locationLike, { open = true, voiceId = '', operationId } = {}) {
  const query = new URLSearchParams(locationLike.search || '');
  if (open) query.set('panel', 'audio'); else query.delete('panel');
  if (open && voiceId) query.set('voice', voiceId); else query.delete('voice');
  if (operationId !== undefined) {
    if (operationId) query.set('audio_job', operationId); else query.delete('audio_job');
  }
  if (!open) query.delete('audio_job');
  return `${locationLike.pathname || '/settings'}${query.size ? '?' + query.toString() : ''}`;
}

export function openAudioCenter(voiceId = '') {
  const previous = `${location.pathname}${location.search}`;
  const href = audioHref(location, { voiceId });
  if (href !== previous) history.pushState({ ...history.state, haikeAudioFrom: history.state?.haikeAudioFrom || previous }, '', href);
  window.dispatchEvent(new Event('haike:navigate'));
}

export function changeAudioRoute(patch, { replace = false } = {}) {
  const current = audioRoute(location);
  const href = audioHref(location, { ...current, ...patch });
  history[replace ? 'replaceState' : 'pushState'](history.state, '', href);
  window.dispatchEvent(new Event('haike:navigate'));
}

export function closeAudioCenter() {
  // A direct URL has no in-app predecessor; close locally without navigating away.
  const href = audioHref(location, { open: false });
  history.replaceState({ ...history.state, haikeAudioFrom: undefined }, '', href);
  window.dispatchEvent(new Event('haike:navigate'));
}

export function accountsRoute(locationLike) {
  const query=new URLSearchParams(locationLike.search||'');
  return {open:query.get('panel')==='accounts',platform:['douyin','kuaishou','shipinhao','xhs'].includes(query.get('platform'))?query.get('platform'):'douyin'};
}
export function accountsHref(locationLike,{open=true,platform='douyin'}={}) {
  const query=new URLSearchParams(locationLike.search||'');
  if(open){query.set('panel','accounts');query.set('platform',platform);}else{query.delete('panel');query.delete('platform');}
  return `${locationLike.pathname||'/settings'}${query.size?'?'+query:''}`;
}
export function openPlatformAccounts(platform='douyin') {
  history.pushState(history.state,'',accountsHref(location,{platform}));window.dispatchEvent(new Event('haike:navigate'));
}
export function closePlatformAccounts() {
  history.replaceState(history.state,'',accountsHref(location,{open:false}));window.dispatchEvent(new Event('haike:navigate'));
  window.dispatchEvent(new Event('haike:sessions-changed'));
}
