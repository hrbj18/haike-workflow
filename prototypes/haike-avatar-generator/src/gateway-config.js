export const DEFAULT_GATEWAY_URL = 'https://8.138.207.71:17894/v2';
export function accountCenterUrl(base = DEFAULT_GATEWAY_URL) {
  try {
    const url = new URL(base);
    const local = ['127.0.0.1','localhost','[::1]'].includes(url.hostname);
    if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) || url.username || url.password) throw new Error('Invalid gateway');
    url.pathname = url.pathname.replace(/\/v2\/?$/, '/');
    url.search = ''; url.hash = '';
    return url.href;
  } catch { return 'https://8.138.207.71:17894/'; }
}
