/** Backend-only client for the Python queue HTTP contract. Node.js >=18.
 * Browser code uses its host's authenticated routes instead of this token.
 * No automatic request retries. Store returned job.id in your business DB.
 */
export class RefinementClient {
  constructor({baseUrl, token, fetchImpl = globalThis.fetch}) {
    if (!token || !baseUrl || !fetchImpl) throw new Error('需要精修服务地址、内部token和fetch');
    const url = new URL(baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('精修服务地址无效');
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.token = token;
    this.fetch = fetchImpl;
  }
  async request(path, namespace, {method='GET', bytes, json, binary=false, confirmed=false}={}) {
    const query = new URLSearchParams({namespace, confirmed:String(confirmed === true)});
    let response;
    try {
      response = await this.fetch(`${this.baseUrl}${path}?${query}`, {
        method, redirect:'error', signal:AbortSignal.timeout(30000),
        headers:{Authorization:`Bearer ${this.token}`, 'Content-Type':json ? 'application/json' : 'application/octet-stream'},
        body:json ? JSON.stringify(json) : bytes,
      });
    } catch {
      throw new Error('精修服务连接中断；原请求结果未知，请查询原任务，勿自动重发');
    }
    if (!response.ok) {
      const error = new Error(`精修服务返回HTTP ${response.status}，请检查权限或原任务状态`);
      error.status = response.status;
      throw error;
    }
    return binary ? new Uint8Array(await response.arrayBuffer()) : response.json();
  }
  submit(bytes, namespace, {confirmed=false}={}) {
    return this.request('/v1/jobs', namespace, {method:'POST', bytes, confirmed});
  }
  get(id, namespace) { return this.request(`/v1/jobs/${encodeURIComponent(id)}`, namespace); }
  file(id, namespace, kind='result') {
    return this.request(`/v1/jobs/${encodeURIComponent(id)}/files/${encodeURIComponent(kind)}`, namespace, {binary:true});
  }
  retry(id, namespace, {confirmed=false, acknowledgeUncertain=false}={}) {
    return this.request(`/v1/jobs/${encodeURIComponent(id)}/retry`, namespace, {
      method:'POST', json:{confirmed, acknowledge_uncertain:acknowledgeUncertain},
    });
  }
}
