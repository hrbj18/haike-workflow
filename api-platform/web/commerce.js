"use strict";
Object.assign(pageNames, {users: "用户与充值", codes: "兑换码管理", providers: "供应商与售价", operations: "运营账单"});
const commerceState = {redeem: null, issued: [], users: [], providers: [], models: [], pendingRequest: null};
const serviceStatus = {available: "已开通", price_pending: "成本待确认", disabled: "尚未开通"};
const submitButton = '<button class="primary" type="submit">保存</button>';
const usageLabels = {characters: "字符", input_tokens: "输入 Token", output_tokens: "输出 Token", seconds: "秒", tasks: "工作流任务", requests: "次请求"};
function commercialUsage(usage) {
  return Object.keys(usage).length ? Object.entries(usage).map(([k, v]) => esc(v) + ' ' + esc(usageLabels[k] || k)).join("<br>") : "尚未取得回执";
}
function rateMoney(value) {
  const [whole, fraction = ""] = String(value ?? "0").split(".");
  return money(whole, true) + fraction.replace(/0+$/, "");
}
function billingTable(j) {
  const b = j.billing;
  if (!b) return "";
  return '<section class="admin-section bill-lines"><h3>费用明细 · 采购成本 × ' + esc(b.multiplier) + '</h3>' +
    table(["计费项", "实际用量", "固定售价 / 每份", "金额"], b.lines.map(r =>
      '<tr><td>' + esc(r.unit) + '</td><td>' + (r.quantity === null ? "—" : esc(r.quantity)) + '</td><td>' + rateMoney(r.unit_price_micros) + ' / ' + esc(r.included_units) + ' ' + esc(r.unit) + '</td><td>' + (r.amount_micros === null ? "待结算 / 未收费" : money(r.amount_micros, true)) + '</td></tr>')) +
    '<p class="tiny muted">' + esc(b.rounding) + '</p><div class="details-grid"><div><small>合计舍入调整</small>' + money(b.rounding_adjustment_micros, true) +
    '</div><div><small>附加服务费</small>' + money(b.fee_micros, true) + '</div><div><small>超出确认上限减免</small>' + money(b.ceiling_discount_micros, true) +
    '</div><div><small>释放回可用余额</small>' + money(b.released_micros, true) + '</div></div>' +
    (b.usage_status === "pending" ? '<div class="notice">用量尚待确认，当前只冻结额度，没有实际扣费。</div>' : '') + '</section>' +
    '<section class="admin-section"><h3>本次调用资金流水</h3>' + table(["时间 / 凭证", "事件", "可用变动", "冻结变动", "可用余额"], (j.ledger || []).map(r =>
      '<tr><td>' + date(r.created_at) + '<small class="mono">' + esc(r.id) + '</small></td><td>' + esc(creditKinds(r.kind)) + '</td><td>' + money(r.postings.available || "0", true) + '</td><td>' + money(r.postings.reserved || "0", true) + '</td><td>' + money(r.available_after_micros, true) + '</td></tr>')) + '</section>';
}
function commercialBill(j) {
  modal('<h2>调用账单详情</h2><p class="mono tiny">' + esc(j.id) + '</p><div class="row">' + badge(j.status) + badge(j.funds_status) +
    '<span class="pill">真实服务</span></div><div class="details-grid"><div><small>模型</small>' + esc(j.model_name) +
    '</div><div><small>项目 / Key</small>' + esc(j.project_ref) + ' / ' + esc(j.key_name) +
    '</div><div><small>实际用量</small>' + commercialUsage(j.usage) +
    '</div><div><small>固定价格 v' + j.price.version + '</small>' + j.price.rates.map(r => rateMoney(r.price_micros) + ' / ' + r.included_units + ' ' + esc(r.unit)).join("<br>") +
    '</div><div><small>确认费用上限</small>' + money(j.max_charge_micros, true) + '</div><div><small>当前冻结</small>' + money(j.reserved_micros, true) +
    '</div><div><small>实际扣费</small>' + money(j.charged_micros, true) + '</div><div><small>创建时间</small>' + date(j.created_at) +
    '</div><div><small>调用回执编号</small>' + esc(j.upstream_id || "待取得") + '</div></div>' +
    (j.estimated_cost_micros !== undefined ? '<div class="details-grid"><div><small>估算采购成本</small>' + (j.estimated_cost_micros === null ? '待核对' : money(j.estimated_cost_micros, true)) + '</div><div><small>估算毛利</small>' + (j.estimated_profit_micros === null ? '待核对' : money(j.estimated_profit_micros, true)) + '</div></div><p class="tiny muted">成本依据：' + esc(j.cost_basis) + '</p>' : '') + billingTable(j) + (j.error ? '<div class="notice">' + esc(j.error) + '</div>' : "") + '<pre class="code-block">' + esc(JSON.stringify(j.result || {message: "结果尚未返回"}, null, 2)) + '</pre>' +
    (j.status === "queued" ? '<button data-action="cancel-job" data-id="' + esc(j.id) + '">取消排队任务</button>' : ""));
}
function field(label, name, value = "", extra = "") {
  return '<label>' + esc(label) + '<input name="' + name + '" value="' + esc(value) + '" ' + extra + '></label>';
}
function creditKinds(kind) {
  return ({admin_credit: "管理员充值", redeem_credit: "兑换码到账", recharge: "模拟充值", reserve: "调用冻结", settle: "调用结算", release: "失败 / 取消释放"})[kind] || kind;
}
async function commercialWalletPage() {
  const [w, ledger, info, history] = await Promise.all([api("/portal/v1/wallet"), api("/portal/v1/ledger"), api("/portal/v1/funding-info"), api("/portal/v1/funding-history")]);
  return heading("余额与充值", "申请一个 API Key，充值后即可统一调用全部已开通模型。") +
    '<div class="stats"><div class="stat accent"><div class="stat-label">可用商业额度</div><div class="stat-value">' + money(w.commercial_available_micros) + '</div><div class="stat-note">所有已开通模型共享此余额</div></div>' +
    '<div class="stat"><div class="stat-label">冻结额度</div><div class="stat-value">' + money(w.commercial_reserved_micros) + '</div><div class="stat-note">已确认调用，等待结算</div></div>' +
    '<div class="stat"><div class="stat-label">本月已结算</div><div class="stat-value">' + money(w.commercial_month_spent_micros) + '</div><div class="stat-note">充值与冻结不计入消费</div></div></div>' +
    '<div class="grid-two"><section class="card"><h2>兑换服务额度</h2><p class="muted">先核对额度，再确认领取。每个兑换码仅可领取一次。</p><form id="commerce-redeem" method="post">' +
    field("兑换码", "code", "", 'required maxlength="80" autocomplete="off"') +
    '<button type="submit" class="primary">查看对应额度</button></form><div id="redeem-preview"></div></section>' +
    '<section class="card"><h2>私域充值</h2><p class="contact-text">' + esc(info.contact) + '</p><p class="contact-text">' + esc(info.instructions) + '</p><p>充值时提供用户名：<strong>' + esc(state.user.email) + '</strong></p><div class="notice">线下付款 → 管理员核实收款 → 手动到账，或领取兑换码后确认兑换。充值 ¥100 到账 ¥100；模型调用按采购成本 × 1.5 实扣。</div>' +
    '<button data-page="keys">管理 API Key →</button><p class="tiny muted">当前充值方式为管理员入账与兑换码；在线支付尚未接入。</p>' +
    (state.user.role === "admin" ? '<p class="tiny muted">保留的模拟额度：' + money(w.simulation_available_micros) + '，不能支付真实调用。</p>' : '') + '</section></div>' +
    '<section class="card admin-section"><h2>充值到账明细</h2>' + actualFundingTable(history.items) + '</section>' +
    '<section class="card admin-section"><div class="card-head"><h2>额度流水</h2><a href="/portal/v1/ledger/export">↓ 导出资金流水 CSV</a></div><p class="tiny muted">充值、冻结、实扣、释放分别记录；每笔调用按采购成本 × 1.5 计费，附加服务费为零。</p>' + table(["时间", "事件", "记录", "可用变动", "冻结变动", "余额"], ledger.items.map(r =>
      '<tr><td>' + date(r.created_at) + '</td><td>' + esc(creditKinds(r.kind)) + '</td><td class="mono">' + esc(r.reference.slice(-12)) + '</td><td>' + money(r.postings.available || "0", true) + '</td><td>' + money(r.postings.reserved || "0", true) + '</td><td>' + money(r.available_after_micros, true) + '</td></tr>')) + '</section>';
}
async function commercialModelsPage() {
  state.models = (await api("/portal/v1/catalogue")).items;
  const models = state.models.filter(m => !m.simulation);
  return heading("模型与价格", "一个平台 Key，共享余额与调用明细。仅已开通模型可以调用。") +
    '<div class="card-list">' + models.map(m => '<article class="card"><div class="model-top"><span class="model-symbol">◈</span><span class="pill ' + (m.status === "available" ? "good" : "warn") + '">' + esc(serviceStatus[m.status]) + '</span></div><h2>' + esc(m.name) + '</h2><p class="tiny mono">' + esc(m.model) + '</p>' +
      (m.version ? m.rates.map(r => '<div class="model-price">' + rateMoney(r.price_micros) + '<small> / ' + r.included_units.toLocaleString() + ' ' + esc(r.unit) + '</small></div>').join("") : '<p class="muted">价格待确认</p>') +
      '<p class="tiny muted">服务费 ' + money(m.fee_micros, true) + ' / 次 · 价格 v' + m.version + '</p><button data-action="commerce-connect-model" data-id="' + esc(m.model) + '">前往接入 →</button></article>').join("") +
    '</div><div class="notice">点击对应模型填写上游平台的 API 地址和密钥。平台接入由管理员维护；用户用一个海客 Key 调用全部已开通模型，按采购成本 × 1.5 计费。</div>';
}
const providerFieldLabels = {
  api_key: "平台 API 密钥", secret_id: "腾讯云 SecretId", secret_key: "腾讯云 SecretKey",
  region: "地域", voice: "音色 ID", text_model: "上游模型 ID", workflow_id: "工作流 ID",
  workflow_profile: "工作流配置", base_url: "平台 API 地址",
};
function connectionPrices(model) {
  if (!model.rule) return '<div class="notice"><strong>价格待确认</strong><p>这个模型尚未填写采购单价，保存平台密钥后仍需设置价格才能开通。售价按采购成本 × 1.5 计算。</p><button type="button" data-action="commerce-tariff" data-id="' + esc(model.model) + '">设置对应价格</button></div>';
  return '<section class="connection-prices"><h3>对应价格 · v' + model.version + '</h3>' +
    table(["计费项", "采购单价", "调用售价"], model.rates.map(r => '<tr><td>每 ' + r.included_units.toLocaleString() + ' ' + esc(r.unit) + '</td><td>' +
      money(model.rule.costs[r.meter], true) + '</td><td class="money">' + rateMoney(r.price_micros) + '</td></tr>')) +
    '<p class="tiny muted">售价 = 采购成本 × ' + esc(model.rule.multiplier) + '；附加服务费 ' + money(model.fee_micros, true) + ' / 次。调用后按实际用量记录明细账单。</p></section>';
}
async function connectModel(modelId) {
  if (state.user.role !== "admin") throw Error("平台接入需要管理员权限");
  const [configs, models] = await Promise.all([api("/admin/v1/providers"), api("/admin/v1/gateway-models")]);
  commerceState.providers = configs.items; commerceState.models = models.items;
  const model = models.items.find(m => m.model === modelId);
  if (!model) throw Error("模型不存在，请刷新后重试");
  const provider = configs.items.find(p => p.id === model.provider);
  if (!provider) throw Error("请先添加对应平台");
  commerceState.connectionPage = state.page;
  const advanced = Object.keys(provider.config).filter(k => !["base_url", "enabled"].includes(k));
  if (provider.id === "bailian" && !advanced.includes("voice")) advanced.push("voice");
  if (model.model === "haike/text" && !advanced.includes("text_model")) advanced.push("text_model");
  modal('<h2>接入 ' + esc(model.name) + '</h2><p class="muted">' + esc(provider.name) + ' · ' + esc(model.model) + '</p>' +
    connectionPrices(model) + '<form id="commerce-connect" method="post" data-id="' + esc(provider.id) + '" data-model="' + esc(model.model) + '">' +
    (provider.config.base_url ? field("平台 API 地址", "base_url", provider.config.base_url, 'type="url" required maxlength="300"') : '<p class="tiny muted">腾讯云使用官方 SDK 地址，通过 SecretId 和 SecretKey 接入。</p>') +
    provider.secret_fields.map(k => field(providerFieldLabels[k] || k, k, "", 'type="password" autocomplete="off" maxlength="500"' + (provider.configured ? ' placeholder="已保存，留空保留原密钥"' : ' required placeholder="输入对应平台的密钥"'))).join("") +
    (advanced.length ? '<details class="connection-advanced"><summary>高级设置（按需调整）</summary>' + advanced.map(k => field(providerFieldLabels[k] || k, k, provider.config[k] || (k === "text_model" ? model.target_model : ""), 'maxlength="300"')).join("") + '</details>' : '') +
    '<label class="connection-switch"><input type="checkbox" name="enabled"' + (provider.config.enabled || !provider.configured ? ' checked' : '') + '>启用此平台接入</label><button type="submit" class="primary full">保存平台接入</button></form>' +
    '<p class="tiny muted">密钥加密保存，不回显。' + (provider.id === "tencent" ? '腾讯配音与识别共用这组平台配置。' : '同一平台下的模型共用这组接入配置。') + '</p>');
}
function exampleInput(model) {
  return (model === "haike/text" || state.models.find(m => m.model === model)?.capability === "chat") ? {messages: [{role: "user", content: "请为海客科技写一段品牌介绍。"}], max_output_tokens: 512} :
    model.includes("tts") || model.includes("cosyvoice") ? {text: "欢迎使用海客科技创作服务。"} :
    model === "haike/assets" ? {query: "technology", media: "videos", per_page: 5} :
    model === "haike/avatar" ? {audio_file: "上传后填入音频编号", image_file: "上传后填入图片编号"} : {audio_file: "上传后填入音频编号"};
}
function commercialPlaygroundPage() {
  const models = state.models.filter(m => !m.simulation);
  if (!models.length) return heading("接入试用", "请先在后台添加渠道、接入模型并发布采购价格。 ");
  const selected = models.find(m => m.status === "available") || models[0];
  return heading("统一 API 接入", "真实调用前先报价，确认上限后执行。服务端保存供应商密钥。") +
    '<div class="grid-two"><section class="card"><form id="commerce-call" method="post">' +
    field("平台 API Key", "key", state.key, 'type="password" required autocomplete="off"') +
    '<label>模型<select name="model" id="commerce-model">' + models.map(m => '<option value="' + esc(m.model) + '"' + (m === selected ? " selected" : "") + '>' + esc(m.name) + ' · ' + esc(serviceStatus[m.status]) + '</option>').join("") + '</select></label>' +
    '<label>调用参数 JSON<textarea id="commerce-input" name="input" rows="9">' + esc(JSON.stringify(exampleInput(selected?.model || "haike/text"), null, 2)) + '</textarea></label>' +
    field("项目标记", "project", "海客工作流", 'maxlength="100"') +
    '<button type="submit" class="primary">获取费用报价</button></form><div id="commerce-quote"></div></section>' +
    '<section class="card"><h3>上传音频 / 形象</h3><p class="tiny muted">用于录音识别与数字人。音频：单声道 16 位 PCM WAV；图片：PNG/JPEG；每个文件最多 5MB。</p>' +
    '<form id="commerce-upload"><label>类型<select name="kind"><option value="audio">WAV 音频</option><option value="image">形象图片</option></select></label><label>文件<input name="file" type="file" required accept=".wav,.png,.jpg,.jpeg"></label><button type="submit">上传并获取文件编号</button></form><pre id="commerce-file" class="code-block">文件仅属于当前账户</pre>' +
    '<h3>接入配置</h3><pre class="code-block">HAIKE_API_BASE_URL=' + esc(location.origin) + '/v2\nHAIKE_API_KEY=&lt;你的平台 Key&gt;\n\nPOST /quotes → POST /jobs → GET /jobs/{id}\nGET /account/summary → GET /account/usage</pre><a href="/docs">查看接入文档与 Python 客户端 →</a></section></div>' +
    '<section class="card admin-section"><h3>调用结果</h3><pre id="commerce-response" class="code-block">确认提交后在这里查询状态、用量和实扣。</pre><button data-action="commerce-refresh">刷新调用结果</button></section>';
}
async function commercePage(page) {
  if (state.user.role !== "admin") throw Error("需要管理员权限");
  if (page === "users") return usersAdminPage();
  if (page === "codes") {
    const [codes, users] = await Promise.all([api("/admin/v1/redeem-codes"), api("/admin/v1/users")]);
    return heading("兑换码管理", "设置额度、数量、有效期，可绑定指定用户。明文仅在生成后展示一次。") +
      '<section class="card"><form id="commerce-codes" method="post"><div class="form-grid">' + field("每个兑换码额度（元）", "amount", "100", 'required inputmode="decimal"') +
      field("生成数量", "count", "1", 'type="number" min="1" max="100" required') + field("有效期（天）", "days", "30", 'type="number" min="1" max="365" required') +
      field("批次名称", "batch", "海客客户额度", 'required maxlength="80"') + '<label>绑定用户<select name="bound" required><option value="" disabled selected>请选择收款对应用户</option>' +
      users.items.filter(u => u.role === "customer" && u.status === "active").map(u => '<option value="' + esc(u.id) + '">' + esc(u.name + " · " + u.email) + '</option>').join("") + '</select></label></div>' + fundingFields() + '<button type="submit" class="primary">核对并生成兑换码</button></form><p class="tiny muted">按每码金额 × 数量登记已收款总额。签发时不增加用户余额，兑换成功才到账。</p></section>' +
      '<section class="card admin-section"><h2>已签发兑换码</h2>' + table(["批次 / 前缀", "额度", "有效期", "绑定用户", "状态", "操作"], codes.items.map(c =>
        '<tr><td>' + esc(c.batch) + '<small class="mono">' + esc(c.prefix) + '…</small></td><td>' + money(c.amount, true) + '</td><td>' + date(c.expires_at) + '</td><td>' +
        esc(users.items.find(u => u.id === c.bound_user_id)?.email || "不限") + '</td><td>' + (c.replacement_id ? "已重新签发" : c.redeemed_at ? "已领取 · " + esc(users.items.find(u => u.id === c.redeemed_by)?.email || "") : c.revoked_at ? "已作废" : c.expires_at < new Date().toISOString() ? "已过期" : "待领取") +
        '</td><td>' + (!c.redeemed_at && !c.revoked_at && c.expires_at > new Date().toISOString() ? '<button data-action="account-reissue-code" data-id="' + esc(c.id) + '">重新签发</button><button class="danger" data-action="commerce-revoke-code" data-id="' + esc(c.id) + '">作废</button>' : "—") + '</td></tr>')) + '</section>';
  }
  if (page === "providers") {
    const [configs, models] = await Promise.all([api("/admin/v1/providers"), api("/admin/v1/gateway-models")]);
    commerceState.providers = configs.items; commerceState.models = models.items;
    return heading("供应商与售价", "默认售价＝成本 × 1.5；版本化发布，已接受任务沿用原价。") +
      '<div class="stats"><div class="stat accent"><div class="stat-label">默认成本加价系数</div><div class="stat-value">1.5 ×</div><div class="stat-note">基础毛利率约 33.33%</div></div><div class="stat"><div class="stat-label">已配置供应商</div><div class="stat-value">' +
      configs.items.filter(p => p.configured).length + ' / ' + configs.items.length + '</div><div class="stat-note">密钥加密存储，页面无法读取明文</div></div><div class="stat"><div class="stat-label">已开通模型档位</div><div class="stat-value">' +
      models.items.filter(m => m.status === "available").length + ' / ' + models.items.length + '</div><div class="stat-note">有配置、有价格且供应商开关开启</div></div></div>' +
      '<section class="card"><div class="card-head"><h2>供应商连接</h2><button data-action="commerce-new-provider">＋ 添加平台</button></div>' + table(["供应商", "密钥", "地址 / 地域", "调用开关", "验证", "操作"], configs.items.map(p =>
        '<tr><td>' + esc(p.name) + '</td><td>' + (p.configured ? "已保存" : "待填写") + '</td><td class="mono">' + esc(p.config.base_url || p.config.region) + '</td><td>' +
        (p.config.enabled ? "开启" : "关闭") + '</td><td>' + esc(p.verification) + '</td><td><button data-action="commerce-provider" data-id="' + esc(p.id) + '">配置</button></td></tr>')) + '</section>' +
      '<section class="card admin-section"><div class="card-head"><h2>模型成本与售价</h2><button data-action="commerce-new-model">＋ 接入模型</button></div>' + table(["模型", "采购成本 / 每份", "用户售价 / 每份", "系数 / 版本", "状态", "操作"], models.items.map(m =>
        '<tr><td>' + esc(m.name) + '<small class="mono">' + esc(m.model) + '</small><small>上游：' + esc(m.provider) + ' / ' + esc(m.target_model) + '</small></td><td>' +
        (m.rule ? Object.keys(m.meters).map(k => money(m.rule.costs[k], true) + ' / ' + m.meters[k] + ' ' + esc(m.rates.find(r => r.meter === k).unit)).join("<br>") : "待提供采购价") +
        '</td><td>' + (m.version ? m.rates.map(r => rateMoney(r.price_micros) + ' / ' + r.included_units + ' ' + esc(r.unit)).join("<br>") : "未发布") +
        '</td><td>' + esc(m.rule?.multiplier || "1.5") + ' × · v' + m.version + '</td><td>' + esc(serviceStatus[m.status]) + '</td><td><button data-action="commerce-tariff" data-id="' + esc(m.model) + '">设置成本 / 售价</button>' + (!['haike/text','haike/cosyvoice','haike/tencent-tts','haike/tencent-asr','haike/avatar','haike/assets'].includes(m.model) ? '<button data-action="commerce-model-route" data-id="' + esc(m.model) + '">路由 / 开关</button>' : '') + '</td></tr>')) +
      '</section><div class="notice">公开标价作为估算成本；实际采购成本需要与供应商账单核对。中转站与 RunningHub 价格必须按你的采购渠道填写。Pexels 素材检索免费，保留来源信息。</div>';
  }
  const jobs = (await api("/admin/v1/gateway-jobs")).items;
  const revenue = jobs.reduce((a, j) => a + BigInt(j.charged_micros), 0n);
  const cost = jobs.reduce((a, j) => a + BigInt(j.estimated_cost_micros || "0"), 0n);
  return heading("运营账单", "查看用户调用、收入、估算采购成本及待核对任务。", '<a href="/admin/v1/gateway-jobs/export"><button>↓ 导出运营明细 CSV</button></a>') +
    '<div class="stats"><div class="stat accent"><div class="stat-label">已结算收入 · 最近500条</div><div class="stat-value">' + money(revenue) + '</div></div><div class="stat"><div class="stat-label">成功任务估算成本</div><div class="stat-value">' + money(cost) +
    '</div><div class="stat-note">失败 / 未知任务供应商成本尚待核对</div></div><div class="stat"><div class="stat-label">成功任务估算毛利</div><div class="stat-value">' + money(revenue - cost) +
    '</div><div class="stat-note">未扣税费、运营费，非最终净利润</div></div></div><section class="card">' +
    table(["时间 / 任务", "客户", "模型 / 项目", "状态", "客户实扣", "估算成本", "估算毛利", "核对"], jobs.map(j =>
      '<tr><td>' + date(j.created_at) + '<small class="mono">' + esc(j.id.slice(-12)) + '</small></td><td>' + esc(j.account_name) + '<small>' + esc(j.account_email) + '</small></td><td>' + esc(j.model_name) + '<small>' + esc(j.project_ref) + '</small></td><td>' + badge(j.status) +
      '</td><td>' + money(j.charged_micros, true) + '</td><td>' + (j.estimated_cost_micros === null ? "待核对" : money(j.estimated_cost_micros, true)) + '</td><td>' +
      (j.estimated_profit_micros === null ? "待核对" : money(j.estimated_profit_micros, true)) + '</td><td>' +
      (j.status === "submission_unknown" ? '<button data-action="commerce-reconcile" data-id="' + esc(j.id) + '" data-model="' + esc(j.model) + '">提交回执</button>' : esc(j.upstream_id || "—")) + '<button data-action="commerce-bill" data-id="' + esc(j.id) + '">查看明细</button></td></tr>')) + '</section>';
}

async function commerceAction(button) {
  const action = button.dataset.action, id = button.dataset.id;
  if (action === "commerce-connect-model") { await connectModel(id); }
  if (action === "commerce-bill") { commercialBill(await api("/admin/v1/gateway-jobs/" + id)); }
  if (action === "commerce-new-provider") {
    modal('<h2>添加 OpenAI 兼容平台</h2><p>填写平台地址和上游密钥。新渠道默认关闭，配置模型与采购成本后再开启。</p><form id="commerce-new-provider" method="post">' +
      field("渠道编号", "id", "channel/", 'required maxlength="50"') + field("平台名称", "name", "", 'required maxlength="60"') +
      field("API Base URL（包含 /v1）", "base_url", "https://", 'required maxlength="300"') + field("上游 API Key", "api_key", "", 'type="password" required maxlength="500" autocomplete="off"') + submitButton + '</form>');
  }
  if (action === "commerce-new-model" || action === "commerce-model-route") {
    const m = commerceState.models.find(m => m.model === id);
    const channels = commerceState.providers.filter(p => p.id === "openai" || p.id.startsWith("channel/"));
    modal('<h2>' + (m ? '模型路由与开关' : '接入新模型') + '</h2><p>仅需在后台配置一次，所有用户原有 Key 即可使用。支持文本与视觉的 OpenAI 兼容协议。</p><form id="commerce-model-route">' +
      field("平台模型编号", "model", m?.model || "haike/", 'required maxlength="80"' + (m ? ' readonly' : '')) +
      field("显示名称", "name", m?.name || "", 'required maxlength="60"') + '<label>上游平台<select name="provider">' +
      channels.map(p => '<option value="' + esc(p.id) + '"' + (m?.provider === p.id ? ' selected' : '') + '>' + esc(p.name) + '</option>').join('') + '</select></label>' +
      field("上游模型 ID", "target_model", m?.target_model || "", 'required maxlength="100"') +
      '<label>模型开关<select name="enabled"><option value="false">暂停</option><option value="true"' + (m?.enabled ? ' selected' : '') + '>开启（需同时有价格和渠道）</option></select></label>' + submitButton + '</form>');
  }
  if (action === "commerce-redeem") {
    if (!commerceState.redeem) throw Error("请先查看兑换码额度");
    await api("/portal/v1/redeem-codes/redeem", {method: "POST", body: {code: commerceState.redeem}});
    commerceState.redeem = null; toast("服务额度已到账"); await loadPage("wallet");
  }
  if (action === "commerce-revoke-code") {
    await api("/admin/v1/redeem-codes/" + id + "/revoke", {method: "POST"}); await loadPage("codes");
  }
  if (action === "commerce-provider") {
    const p = commerceState.providers.find(p => p.id === id);
    modal('<h2>' + esc(p.name) + '</h2><form id="commerce-provider" method="post" data-id="' + esc(id) + '">' +
      Object.keys(p.config).filter(k => k !== "enabled" && !(id === "runninghub" && ["billing_mode", "quote_cost_limit_micros", "quote_cost_per_audio_second_micros"].includes(k))).map(k => field(k, k, p.config[k])).join("") +
      p.secret_fields.map(k => field(k + "（留空保留）", k, "", 'type="password" autocomplete="off" maxlength="500"')).join("") +
      (id === "bailian" && !("voice" in p.config) ? field("复刻音色 ID", "voice") : "") +
      (id === "runninghub" ? '<label>数字人计价方式<select name="billing_mode"><option value="task">保留原固定任务档位</option><option value="wallet_receipt"' + (p.config.billing_mode === "wallet_receipt" ? ' selected' : '') + '>实际 API 钱包回执 × 1.5</option></select></label>' + field("任务报价采购上限（整数微元，1元=1000000）", "quote_cost_limit_micros", p.config.quote_cost_limit_micros || "") + field("每秒音频采购预估（整数微元，可留空预留全额）", "quote_cost_per_audio_second_micros", p.config.quote_cost_per_audio_second_micros || "") + '<p class="tiny muted">预估只决定冻结上限，成功按供应商实扣 × 1.5 结算并释放余款。供应商超出报价的成本由平台承担；变更计量方式需发布新费率。</p>' : "") +
      '<label>供应商调用开关<select name="enabled"><option value="false">关闭</option><option value="true"' + (p.config.enabled ? " selected" : "") + '>开启</option></select></label>' + submitButton + '</form><p class="tiny muted">开启后，具备已发布价格的模型会接受真实调用。</p>');
  }
  if (action === "commerce-tariff") {
    commerceState.tariffPage = state.page;
    const m = commerceState.models.find(m => m.model === id);
    modal('<h2>' + esc(m.name) + ' · 新价格</h2><form id="commerce-tariff" data-id="' + esc(id) + '">' +
      Object.keys(m.meters).map(k => field('采购成本（元 / ' + m.meters[k] + ' ' + m.rates.find(r => r.meter === k).unit + '）', k, m.rule ? (Number(m.rule.costs[k]) / 1000000).toString() : "", 'required inputmode="decimal"')).join("") +
      field("成本加价系数（固定）", "multiplier", "1.5", 'readonly') +
      field("附加服务费（固定为零）", "fee", "0", 'readonly') +
      field("成本来源 / 采购凭证", "source", m.rule?.source || "", 'required maxlength="300"') +
      field("成本说明", "basis", m.rule?.cost_basis || "采购单价待核对", 'required maxlength="300"') +
      '<label><input type="checkbox" name="confirmed" required>已核对成本与计量单位</label><div class="row"><button type="button" data-action="commerce-preview-price">预览售价与毛利</button><button type="submit" class="primary">发布新价格</button></div></form><div id="commerce-price-preview"></div>');
  }
  if (action === "commerce-preview-price") {
    const form = $("commerce-tariff"), m = commerceState.models.find(m => m.model === form.dataset.id);
    const usage = Object.fromEntries(Object.entries(m.meters));
    const r = await api("/admin/v1/gateway-prices/preview", {method: "POST", body: {...tariffBody(form), usage}});
    $("commerce-price-preview").textContent = "每个计费项各取一份：成本 " + money(r.cost_micros, true) + " → 售价 " + money(r.sale_micros, true) + "；毛利 " + money(r.profit_micros, true) + "；毛利率 " + (Number(r.gross_margin) * 100).toFixed(2) + "%";
  }
  if (action === "commerce-submit") {
    const request = commerceState.pendingRequest;
    if (!request) throw Error("请先获取报价");
    const job = await api("/v2/jobs", {method: "POST", headers: {"Idempotency-Key": request.idem}, body: request.body});
    state.activeJob = job.id; commerceState.lastJobId = job.id; $("commerce-response").textContent = JSON.stringify(job, null, 2);
    $("commerce-quote").textContent = "已接受任务：" + job.id + "；费用上限 " + money(request.body.max_charge_micros, true);
    toast("已确认费用，任务已入队");
  }
  if (action === "commerce-refresh") {
    const jobId = commerceState.lastJobId || state.activeJob;
    if (!jobId) throw Error("尚未提交任务");
    $("commerce-response").textContent = JSON.stringify(await api("/v2/jobs/" + jobId), null, 2);
  }
  if (action === "commerce-reconcile") {
    modal('<h2>核对未知提交</h2><p class="muted">先向供应商核对请求结果，再填写用量和凭证。不能直接重新发起付费任务。</p><form id="commerce-reconcile" data-id="' + esc(id) + '">' +
      '<label>核对结果<select name="outcome"><option value="succeeded">确认成功</option><option value="failed">确认失败 / 未接受</option></select></label><label>供应商实际用量 JSON<textarea name="usage">{}</textarea></label>' +
      field("核对凭证 / 说明", "evidence", "", 'required minlength="10" maxlength="500"') + submitButton + '</form>');
  }
}
function tariffBody(form) {
  const f = form.elements, m = commerceState.models.find(m => m.model === form.dataset.id);
  return {model: m.model, rule: {costs: Object.fromEntries(Object.keys(m.meters).map(k => [k, micros(f[k].value)])),
    multiplier: f.multiplier.value, fee_micros: micros(f.fee.value), source: f.source.value,
    cost_basis: f.basis.value, confirmed: f.confirmed.checked}};
}
document.addEventListener("change", event => {
  if (event.target.id === "commerce-model") $("commerce-input").value = JSON.stringify(exampleInput(event.target.value), null, 2);
  if (event.target.closest("#commerce-call") && commerceState.pendingRequest) {
    commerceState.pendingRequest = null; $("commerce-quote").textContent = "参数已修改，请重新报价";
  }
  if (event.target.closest("#commerce-redeem")) { commerceState.redeem = null; $("redeem-preview").replaceChildren(); }
});
document.addEventListener("submit", async event => {
  const form = event.target, formId = form.getAttribute("id") || "";
  if (!formId.startsWith("commerce-")) return;
  event.preventDefault();
  const button = form.querySelector('[type="submit"]'), f = form.elements;
  button.disabled = true;
  try {
    if (formId === "commerce-new-provider") {
      await api("/admin/v1/providers", {method: "POST", body: Object.fromEntries(new FormData(form))});
      $("modal").close(); toast("平台已添加，请配置模型和价格后开启"); await loadPage("providers");
    }
    if (formId === "commerce-model-route") {
      const body = Object.fromEntries(new FormData(form)); body.enabled = body.enabled === "true";
      await api("/admin/v1/gateway-models", {method: "POST", body});
      $("modal").close(); toast("模型路由已保存，请确认采购成本"); await loadPage("providers");
    }
    if (formId === "commerce-redeem") {
      const code = f.code.value.trim(), preview = await api("/portal/v1/redeem-codes/preview", {method: "POST", body: {code}});
      commerceState.redeem = code;
      $("redeem-preview").innerHTML = '<div class="quote-card"><h3>可兑换 ' + money(preview.amount_micros, true) + '</h3><p>有效期至 ' + date(preview.expires_at) + '</p><button class="primary" data-action="commerce-redeem">确认兑换到账</button></div>';
    }
    if (formId === "commerce-user") {
      await api("/admin/v1/users", {method: "POST", body: {username: f.username.value, password: f.password.value}});
      form.reset(); toast("用户已创建，首次登录需修改初始密码"); await loadPage("users");
    }
    if (formId === "commerce-credit") prepareCredit(form);
    if (formId === "commerce-codes") prepareCodes(form);
    if (formId === "commerce-provider") {
      const config = Object.fromEntries(new FormData(form)); config.enabled = config.enabled === "true";
      await api("/admin/v1/providers/" + form.dataset.id, {method: "POST", body: {config}});
      $("modal").close(); toast("供应商配置已保存"); await loadPage("providers");
    }
    if (formId === "commerce-connect") {
      const config = Object.fromEntries(new FormData(form)); config.enabled = f.enabled.checked;
      await api("/admin/v1/providers/" + form.dataset.id, {method: "POST", body: {config}});
      const models = (await api("/admin/v1/gateway-models")).items;
      const model = models.find(m => m.model === form.dataset.model);
      $("modal").close();
      toast(model?.status === "available" ? "平台接入已保存，模型已开通" : "平台接入已保存；" + (serviceStatus[model?.status] || "请核对模型开关与高级设置"));
      await loadPage(commerceState.connectionPage || "catalogue");
    }
    if (formId === "commerce-tariff") {
      const r = await api("/admin/v1/gateway-prices", {method: "POST", body: tariffBody(form)});
      $("modal").close(); toast("价格 v" + r.version + " 已发布"); await loadPage(commerceState.tariffPage || "providers");
    }
    if (formId === "commerce-call") {
      state.key = f.key.value.trim(); commerceState.pendingRequest = null;
      const q = await api("/v2/quotes", {method: "POST", body: {model: f.model.value, input: JSON.parse(f.input.value), project_ref: f.project.value}});
      commerceState.pendingRequest = {idem: crypto.randomUUID(), body: {quote_id: q.id, max_charge_micros: q.max_charge_micros, call_intent_id: crypto.randomUUID(), currency: "CNY", confirmed: true}};
      $("commerce-quote").innerHTML = '<div class="quote-card"><h3>本次费用上限 ' + money(q.max_charge_micros, true) + '</h3><p class="tiny">报价用量上限 ' + esc(JSON.stringify(q.quoted_usage)) + ' · 价格 v' + q.price.version + '</p><p>真实调用会消耗服务额度。</p><button class="primary" data-action="commerce-submit">确认费用并提交</button></div>';
    }
    if (formId === "commerce-upload") {
      state.key = $("commerce-call").elements.key.value.trim();
      if (!state.key) throw Error("请先填写平台 Key");
      const file = f.file.files[0];
      if (file.size > 5 * 1024 * 1024) throw Error("文件不能超过 5MB");
      const response = await fetch("/v2/files?kind=" + encodeURIComponent(f.kind.value), {method: "POST", headers: {Authorization: "Bearer " + state.key, "Content-Type": "application/octet-stream"}, body: file});
      const result = await response.json();
      if (!response.ok) throw Error(result.error?.message || "上传失败");
      $("commerce-file").textContent = JSON.stringify(result, null, 2);
      const input = JSON.parse($("commerce-input").value);
      input[f.kind.value + "_file"] = result.id;
      $("commerce-input").value = JSON.stringify(input, null, 2);
      commerceState.pendingRequest = null; $("commerce-quote").replaceChildren();
    }
    if (formId === "commerce-reconcile") {
      await api("/admin/v1/gateway-jobs/" + form.dataset.id + "/reconcile", {method: "POST", body: {outcome: f.outcome.value, usage: JSON.parse(f.usage.value), evidence: f.evidence.value}});
      $("modal").close(); await loadPage("operations");
    }
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
});
