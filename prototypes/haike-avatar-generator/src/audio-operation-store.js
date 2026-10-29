// Only a recovery reference is kept in this tab. Account data stays on the server.
const KEY = 'haike.audio.pending-operation';
export function pendingAudioOperation() {
  try { const value=sessionStorage.getItem(KEY);return /^call_[a-f0-9]{32}$/.test(value||'')?value:''; } catch { return ''; }
}
export function rememberAudioOperation(id) {
  if(!/^call_[a-f0-9]{32}$/.test(id||''))throw new Error('调用编号无效。');
  try { sessionStorage.setItem(KEY,id); } catch { /* The URL remains a recovery reference. */ }
}
export function forgetAudioOperation() { try { sessionStorage.removeItem(KEY); } catch { /* No tab storage is available. */ } }
