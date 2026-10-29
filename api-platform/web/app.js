"use strict";
const state = {
  user: null,
  csrf: "",
  page: "wallet",
  authMode: "login",
  key: "",
  quote: null,
  intent: null,
  idem: null,
  amount: 10000,
  models: [],
  render: 0,
  activeJob: null,
  polling: false,
};
const $ = (id) => document.getElementById(id);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  queued: "排队中",
  submitting: "提交中",
  running: "执行中",
  succeeded: "已完成",
  failed: "已失败",
  submission_unknown: "提交待核对",
  reconciliation_pending: "待核对",
  cancel_pending: "取消待确认",
  cancelled: "已取消",
  reserved: "已冻结",
  settled: "已结算",
  released: "已释放",
  pending: "待付款",
  paid: "已到账",
};
const pageNames = {
  wallet: "余额与充值",
  keys: "API Key",
  bills: "调用账单",
  account: "账户与安全",
  funding: "充值记录",
  catalogue: "模型与价格",
  playground: "接入试用",
  admin: "运营后台",
};
function money(value, precise = false) {
  const n = BigInt(String(value ?? "0").split(".")[0]);
  const sign = n < 0n ? "−" : "";
  const a = n < 0n ? -n : n;
  if (!precise && a > 0n && a < 10000n) return `${sign}<¥0.01`;
  const decimals = (a % 1000000n).toString().padStart(6, "0");
  return `${sign}¥${(a / 1000000n).toLocaleString("zh-CN")}.${precise ? decimals : decimals.slice(0, 2)}`;
}
function micros(value) {
  if (!/^\d{1,6}(\.\d{1,6})?$/.test(String(value)))
    throw Error("金额格式不正确，最多六位小数");
  const [whole, part = ""] = String(value).split(".");
  return (BigInt(whole) * 1000000n + BigInt(part.padEnd(6, "0"))).toString();
}
function date(value) {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
      })
    : "—";
}
function badge(status) {
  const c = ["succeeded", "settled", "paid"].includes(status)
    ? "good"
    : ["failed"].includes(status)
      ? "bad"
      : [
            "submission_unknown",
            "cancel_pending",
            "reconciliation_pending",
            "reserved",
            "pending",
          ].includes(status)
        ? "warn"
        : "neutral";
  return `<span class="pill ${c}">${esc(labels[status] || status)}</span>`;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").style.display = "block";
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(
    () => ($("toast").style.display = "none"),
    4500,
  );
}
async function api(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...options.headers,
  };
  if (
    !["GET", "HEAD"].includes(options.method || "GET") &&
    !path.startsWith("/v2/")
  )
    headers["X-CSRF-Token"] = state.csrf;
  if (path.startsWith("/v2/")) {
    if (!state.key) throw Error("请粘贴你创建的平台 Key");
    headers.Authorization = "Bearer " + state.key;
  }
  const response = await fetch(path, {
    ...options,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const result = await response.json();
  if (!response.ok) {
    if (["login_required", "account_disabled"].includes(result.error?.code) && state.user) {
      endSession();
      showAuth("login");
    }
    throw Error(result.error?.message || "请求失败，请刷新后重试");
  }
  return result;
}
function modal(html) {
  $("modal-content").innerHTML = html;
  $("modal").classList.toggle("bill-dialog", html.includes("调用账单详情"));
  $("modal").showModal();
  $("modal").scrollTop = 0;
}
function heading(title, desc, extra = "") {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${desc}</p></div>${extra}</div>`;
}
function table(headers, rows, empty = "暂无记录") {
  return `<div class="table-scroll"><table><thead><tr>${headers.map((v) => `<th>${v}</th>`).join("")}</tr></thead><tbody>${rows.length ? rows.join("") : `<tr><td colspan="${headers.length}" class="empty">${empty}</td></tr>`}</tbody></table></div>`;
}
function showAuth(mode) {
  state.authMode = mode;
  $("auth").hidden = false;
  $("workspace").hidden = true;
  $("auth-title").textContent = mode === "setup" ? "创建管理员" : mode === "register" ? "创建账户" : "欢迎登录";
  $("auth-submit").textContent = mode === "setup" ? "创建管理员" : mode === "register" ? "注册并登录" : "登录";
  $("auth-modes").hidden = mode === "setup";
  $("auth-login").setAttribute("aria-pressed", String(mode === "login"));
  $("auth-register").setAttribute("aria-pressed", String(mode === "register"));
  $("auth-forgot").hidden = mode !== "login";
  const password = $("auth-form").elements.password;
  password.autocomplete = mode === "login" ? "current-password" : "new-password";
  password.type = "password";
  password.value = "";
  const toggle = document.querySelector('[data-action="account-toggle-password"]');
  toggle.setAttribute("aria-label", "显示密码");
  toggle.title = "显示密码";
  toggle.setAttribute("aria-pressed", "false");
  clearAuthError();
}
function clearAuthError() {
  $("auth-error").hidden = true;
  $("auth-error").textContent = "";
  for (const input of $("auth-form").querySelectorAll("input")) input.removeAttribute("aria-invalid");
}
async function enter(result) {
  state.user = result.user;
  state.csrf = result.csrf;
  $("auth-form").reset();
  $("auth").hidden = true;
  $("workspace").hidden = false;
  $("user-label").innerHTML =
    `${esc(state.user.name)}<small>${state.user.role === "admin" ? "管理员账户" : "创作账户"}</small>`;
  $("avatar").textContent = state.user.name.slice(0, 1);
  $("admin-link").hidden = state.user.role !== "admin";
  document.querySelectorAll("[data-admin]").forEach((node) => { node.hidden = state.user.role !== "admin"; });
  if (!state.user.must_change_password) {
    const catalogue = await api("/portal/v1/catalogue");
    state.models = catalogue.items;
  }
  await loadPage(pageFromAddress(), { historyMode: "replace" });
}
function pageFromAddress() {
  return new URL(location.href).searchParams.get("page") ||
    (location.pathname === "/admin" ? "providers" : "wallet");
}
function recordPage(page, historyMode) {
  const url = new URL(location.href);
  url.searchParams.set("page", page);
  // Reloading data or saving a form on the same page must not add a back step.
  const replace = historyMode === "replace" ||
    history.state?.accountPage === page && url.href === location.href;
  history[replace ? "replaceState" : "pushState"](
    { ...history.state, accountPage: page }, "", url,
  );
}
async function loadPage(page, { historyMode = "push" } = {}) {
  if (!Object.hasOwn(pageNames, page)) page = "wallet";
  if (state.user.role !== "admin" && !["wallet", "keys", "bills", "account"].includes(page)) page = "wallet";
  if (state.user.must_change_password) page = "account";
  recordPage(page, historyMode);
  const seq = ++state.render;
  state.page = page;
  state.quote = null;
  document
    .querySelectorAll("[data-page]")
    .forEach((v) => v.classList.toggle("active", v.dataset.page === page));
  $("breadcrumb").textContent = "账户中心 / " + pageNames[page];
  $("page-content").innerHTML = '<div class="empty">正在加载账户数据…</div>';
  let html;
  if (page === "wallet") html = await commercialWalletPage();
  if (page === "keys") html = await keysPage();
  if (page === "bills") html = await billsPage();
  if (page === "account") html = accountPage();
  if (page === "funding") html = await fundingAdminPage();
  if (page === "catalogue") html = await commercialModelsPage();
  if (page === "playground") {
    state.models = (await api("/portal/v1/catalogue")).items;
    html = commercialPlaygroundPage();
  }
  if (["users", "codes", "providers", "operations"].includes(page)) html = await commercePage(page);
  if (page === "admin") html = await adminPage();
  if (seq === state.render) {
    $("page-content").innerHTML = html;
    if (page === "admin" && state.user.role === "admin") {
      syncPriceForm();
      await action(document.querySelector('[data-action="preview-price"]'));
    }
  }
}
window.addEventListener("popstate", async () => {
  // Browser navigation changes the page, while the authenticated session stays active.
  if (!state.user) return;
  $("modal").close();
  try {
    await loadPage(pageFromAddress(), { historyMode: "replace" });
  } catch (e) {
    toast(e.message);
  }
});
async function walletPage() {
  const [w, l, o] = await Promise.all([
    api("/portal/v1/wallet"),
    api("/portal/v1/ledger"),
    api("/portal/v1/recharges"),
  ]);
  const ledgerKinds = {
    recharge: "模拟充值",
    reserve: "任务冻结",
    settle: "任务结算",
    release: "冻结释放",
  };
  return (
    heading(
      "余额与充值",
      "让每一次创作，都有清晰的预算。",
      '<span class="pill">CNY · 模拟额度</span>',
    ) +
    `<div class="stats"><div class="stat accent"><div class="stat-label">可用余额 <span>◈</span></div><div class="stat-value">${money(w.available_micros)}</div><div class="stat-note">可用于新的模拟任务</div></div>
    <div class="stat"><div class="stat-label">冻结额度 <span>◷</span></div><div class="stat-value">${money(w.reserved_micros)}</div><div class="stat-note">任务完成后结算，确定失败后释放</div></div>
    <div class="stat"><div class="stat-label">本月消费 <span>▤</span></div><div class="stat-value">${money(w.month_spent_micros)}</div><div class="stat-note">只统计已结算调用，充值不算消费</div></div></div>
    <div class="grid-two"><section class="card"><div class="card-head"><h2>充值额度</h2><span class="pill neutral">模拟付款</span></div><p class="tiny muted">选择额度，创建订单后模拟确认到账。</p>
    <div class="amount-options">${[1000, 5000, 10000, 30000, 50000, 100000].map((f) => `<button data-action="amount" data-value="${f}" class="${state.amount === f ? "selected" : ""}">¥${f / 100}<small>模拟额度</small></button>`).join("")}</div>
    <div class="row"><button class="primary" data-action="recharge">创建模拟充值订单 →</button><span class="tiny muted">不产生真实付款</span></div></section>
    <section class="card"><h3>三步开始接入</h3><div class="steps"><div class="step"><span class="step-number">1</span><div><strong>充值你的创作额度</strong><p>按账户统一结算，冻结与消费分别展示。</p></div></div><div class="step"><span class="step-number">2</span><div><strong>创建一个 API Key</strong><p>设置每日预算，明文仅展示一次。</p></div></div><div class="step"><span class="step-number">3</span><div><strong>连接工作流 / Agent</strong><p>统一地址与 Key，按能力报价后提交任务。</p></div></div></div><button class="text-button" data-page="keys">前往 API Key →</button></section></div>
    <section class="card"><div class="card-head"><h2>充值订单</h2><span class="tiny muted">付款状态由后端确认</span></div>${table(
      ["订单", "创建时间", "金额", "状态", "操作"],
      o.items.map(
        (r) =>
          `<tr><td class="mono">${esc(r.id.slice(-12))}</td><td>${date(r.created_at)}</td><td>${money(String(r.amount_fen * 10000))}</td><td>${badge(r.state)}</td><td>${r.state === "pending" ? `<button data-action="pay-order" data-id="${esc(r.id)}">模拟到账</button>` : "—"}</td></tr>`,
      ),
    )}</section>
    <section class="card admin-section"><div class="card-head"><h2>钱包流水</h2><span class="tiny muted">不可变账本 · 最近 500 条</span></div>${table(
      ["时间", "事件", "关联记录", "可用变动", "冻结变动", "可用余额"],
      l.items.map(
        (r) =>
          `<tr><td>${date(r.created_at)}</td><td>${ledgerKinds[r.kind] || esc(r.kind)}</td><td class="mono">${esc(r.reference.slice(-12))}</td><td class="money">${money(r.postings.available || "0", true)}</td><td class="money">${money(r.postings.reserved || "0", true)}</td><td>${money(r.available_after_micros, true)}</td></tr>`,
      ),
    )}</section>`
  );
}
async function keysPage() {
  const { items } = await api("/portal/v1/api-keys");
  return (
    heading(
      "API Key",
      "申请一个 Key、保持账户余额充足，即可调用全部已开通模型。",
      '<button class="primary" data-action="new-key">＋ 申请 API Key</button>',
    ) +
    `<section class="card"><div class="card-head"><h2>我的 Key</h2><span class="tiny muted">明文仅在创建时展示</span></div>${table(
      ["名称", "Key", "每日预算", "到期时间", "状态", "操作"],
      items.map(
        (k) =>
          `<tr><td>${esc(k.name)}<small>最后调用 ${date(k.last_used_at)}</small></td><td class="mono">${esc(k.prefix)}…</td><td>${money(k.daily_limit, true)}</td><td>${date(k.expires_at)}</td><td>${k.revoked_at ? badge("已撤销") : k.expires_at < new Date().toISOString() ? badge("已过期") : '<span class="pill good">有效</span>'}</td><td>${!k.revoked_at ? `<button class="danger" data-action="revoke" data-id="${esc(k.id)}">撤销</button>` : "—"}</td></tr>`,
      ),
      "还没有 Key，创建一个开始接入",
    )}</section>
    <section class="card admin-section"><h3>统一接入配置</h3><p>将下面的地址和平台 Key 填入工作流 / Agent，供应商接入由管理员维护。所有模型共用余额，新模型开通后原 Key 即可使用。</p><pre class="code-block">Base URL: ${esc(location.origin)}/v2
Authorization: Bearer &lt;你的 Key&gt;

GET  /account/summary    读取账户与余额
POST /quotes            获取固定价格报价
POST /jobs              确认上限并提交任务
GET  /jobs/{id}         查询状态与账单</pre><a href="/docs">查看接入文档 →</a><div class="notice">账户余额与 Key 每日预算均需充足。调用时指定模型编号，无需单独申请模型权限；撤销 Key 后新调用停止，已接受任务继续结算。</div></section>`
  );
}
async function billsPage(model = "", status = "") {
  const query = new URLSearchParams();
  if (model) query.set("model", model);
  if (status) query.set("status", status);
  const { items } = await api("/portal/v1/bills?" + query);
  const filterModels = [...new Map([...state.models, ...items.map(j => ({model: j.model, name: j.model_name}))].map(m => [m.model, m])).values()];
  return (
    heading(
      "调用账单",
      "查看每次调用的模型、用量、冻结与实扣。",
      `<a href="/portal/v1/bills/export?${esc(query.toString())}"><button>↓ 导出当前筛选 CSV</button></a>`,
    ) +
    `<section class="card"><div class="filters"><select id="bill-model" aria-label="按模型筛选"><option value="">全部模型</option>${filterModels.map((m) => `<option value="${esc(m.model)}" ${model === m.model ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select><select id="bill-status" aria-label="按状态筛选"><option value="">全部状态</option>${["succeeded", "failed", "queued", "running", "submission_unknown", "cancelled"].map((s) => `<option value="${s}" ${status === s ? "selected" : ""}>${labels[s]}</option>`).join("")}</select><button data-action="filter-bills">筛选 / 刷新</button><span class="tiny muted">最近 500 个任务</span></div>
    ${table(
      [
        "任务 / 时间",
        "模型 / Key",
        "用量",
        "冻结额度",
        "实扣费用",
        "状态",
        "详情",
      ],
      items.map(
        (j) =>
          `<tr><td class="mono">${esc(j.id.slice(-12))}<small>${date(j.created_at)}</small></td><td>${esc(j.model_name)}<small>${esc(j.key_name)} · ${esc(j.project_ref || "未标记项目")}</small></td><td>${j.usage ? commercialUsage(j.usage) : j.quantity + " " + esc(j.price.unit)}<small>价格 v${j.price.version}</small></td><td>${money(j.reserved_micros, true)}</td><td class="money">${money(j.charged_micros, true)}</td><td>${badge(j.status)}<small>${esc(labels[j.funds_status])}</small></td><td><button data-action="bill" data-id="${esc(j.id)}">查看</button></td></tr>`,
      ),
      "还没有调用，前往统一 API 接入获取报价",
    )}</section><div class="notice">冻结额度不等于已扣款；未知提交保留冻结，核对后才结算或释放。详情展示实际用量与固定价格版本。</div>`
  );
}
async function cataloguePage() {
  const { items } = await api("/portal/v1/catalogue");
  state.models = items;
  return (
    heading(
      "模型与价格",
      "统一入口，保留每种能力的计量方式。",
      '<span class="pill neutral">2 个模拟档位</span>',
    ) +
    `<div class="card-list">${items.map((m, i) => `<article class="card"><div class="model-top"><span class="model-symbol">${i ? "◉" : "≋"}</span><span class="pill">模拟服务</span></div><h2>${esc(m.name)}</h2><p class="tiny muted">目标：${esc(m.target_model)}</p><div class="model-price">${money(m.unit_price_micros, true)}<small>/ ${m.included_units.toLocaleString()} ${esc(m.unit)}</small></div><p class="tiny muted">服务费 ${money(m.fee_micros, true)} / 任务 · 价格 v${m.version}</p><p class="tiny muted">${esc(m.description)}</p><button data-page="playground">测试接入 →</button></article>`).join("")}</div><section class="card admin-section"><h3>正式能力接入路线</h3><p class="tiny muted">下一阶段接入百炼配音与声音克隆，再接 RunningHub 数字人。文本、视觉、ASR、生图与生视频逐个验证协议、产物和计量后开放。</p><div class="notice">当前价格为假设示例，不代表供应商实际采购成本，也不能用于真实收费。</div></section>`
  );
}
function playgroundPage() {
  return (
    heading(
      "接入试用",
      "用真实签发的演示 Key，走一遍报价、冻结和结算。",
      '<span class="pill">API v2 · 模拟任务</span>',
    ) +
    `<div class="grid-two"><section class="card"><form id="demo-form"><h3>连接与参数</h3><label>API Key<input name="key" type="password" autocomplete="off" value="${esc(state.key)}" placeholder="粘贴 hk_demo_ 开头的 Key" required></label><div class="row"><button type="button" data-action="connect">读取余额 / 验证连接</button><span id="connect-result" class="tiny muted">Key 只保存在本页内存</span></div><div class="form-grid admin-section"><label>能力<select name="model" id="demo-model">${state.models.map((m) => `<option value="${esc(m.model)}">${esc(m.name)}</option>`).join("")}</select></label><label>模拟结果<select name="outcome"><option value="succeeded">成功并结算</option><option value="failed">确定失败并释放</option><option value="submission_unknown">提交未知，等待核对</option></select></label></div><label id="text-field">配音文本<textarea name="text">欢迎使用海客工作流。一个 Key，连接你的创作服务。</textarea></label><label id="roles-field" hidden>角色数<select name="roles"><option value="1">1 个角色</option><option value="2">2 个角色</option></select></label><label>项目标记<input name="project" maxlength="100" value="本地接入演示"></label><button class="primary" type="submit">获取报价 →</button></form><div id="quote-result"></div></section>
    <section class="card"><h3>费用如何流转</h3><div class="steps"><div class="step"><span class="step-number">1</span><div><strong>免费报价</strong><p>冻结模型、输入、单价版本与费用上限。</p></div></div><div class="step"><span class="step-number">2</span><div><strong>确认后冻结额度</strong><p>同一请求重复提交返回原任务。并发冻结计入预算。</p></div></div><div class="step"><span class="step-number">3</span><div><strong>持久化提交，再执行</strong><p>结果未知时保留额度；服务重启不会盲目重试。</p></div></div><div class="step"><span class="step-number">4</span><div><strong>完成后结算与记录</strong><p>确定失败只释放冻结。完整证据保留在账单详情。</p></div></div></div><div class="notice">这里返回模拟用量回执，不会生成可播放媒体。正式客户端应由本地后端保存 Key，浏览器不长期保存明文。</div><pre id="demo-response" class="code-block">等待任务提交…</pre></section></div>`
  );
}
async function adminPage() {
  if (state.user.role !== "admin")
    return (
      heading("运营后台", "此页面需要管理员账户登录。") +
      '<div class="notice">请退出后使用管理员用户名登录。</div>'
    );
  const [p, r, c] = await Promise.all([
    api("/admin/v1/price-versions"),
    api("/admin/v1/reconciliation"),
    api("/admin/v1/ledger-check"),
  ]);
  state.adminPrices = p.items;
  return (
    heading(
      "运营定价",
      "管理客户售价，核对待确认任务。",
      `<span class="pill ${c.ok ? "good" : "bad"}">账本${c.ok ? "校验通过" : "存在异常"}</span>`,
    ) +
    `<div class="admin-layout"><section class="card"><h3>创建价格草稿</h3><form id="price-form"><label>模型 / 档位<select name="model">${state.models.filter(m => m.simulation).map((m) => `<option value="${esc(m.model)}">${esc(m.name)} · 每 ${m.included_units} ${esc(m.unit)}</option>`).join("")}</select></label><div class="form-grid"><label>定价方式<select name="mode"><option value="markup">成本 × 加价系数</option><option value="margin">目标毛利率</option><option value="fixed">固定售价</option></select></label><label>成本基准（元 / 每份）<input name="cost" inputmode="decimal" value="0.8" required></label><label>加价系数<input name="multiplier" inputmode="decimal" value="1.3" required></label><label>目标毛利率（0–0.95）<input name="margin" inputmode="decimal" value="0.3" required></label><label>固定售价（元 / 每份）<input name="fixed" inputmode="decimal" value="1.04" required></label><label>服务费（元 / 任务）<input name="fee" inputmode="decimal" value="0" required></label><label>预览用量<input name="quantity" type="number" min="1" max="20000" value="1200" required></label></div><div class="row"><button type="button" data-action="preview-price">预览费用</button><button class="primary" type="submit">保存为新草稿</button></div></form></section>
    <section class="card"><h3>费用预览</h3><div id="price-result" class="price-result">示例：0.8 元 / 万字符 × 1.3<br>1,200 字符售价 <strong>¥0.124800</strong>基础毛利率约 23.08%</div><div class="notice">加价 30% 对应毛利率约 23.08%。成本为模拟基准，未核对真实采购费用。<br>充值不是营业收入；收入以已结算服务为准。</div><p class="tiny muted">发布会产生新版本，已接受任务和有效旧报价继续按原版本结算。价格发布由后端管理员权限校验。</p><button data-action="ledger-check">重新校验账本</button></section></div>
    <section class="card admin-section"><div class="card-head"><h2>价格版本</h2><span class="tiny muted">先保存草稿，再发布</span></div>${table(
      ["模型", "版本", "规则", "状态", "发布时间", "操作"],
      p.items.map(
        (v) =>
          `<tr><td>${esc(state.models.find((m) => m.model === v.model)?.name || v.model)}</td><td>v${v.version}</td><td>${esc({ markup: "加价系数", margin: "目标毛利", fixed: "固定售价" }[v.rule.mode])}<small>${v.rule.mode === "markup" ? esc(v.rule.multiplier) : v.rule.mode === "margin" ? esc(v.rule.margin) : money(v.rule.fixed_micros, true)}</small></td><td><span class="pill ${v.state === "published" ? "good" : "neutral"}">${v.state === "published" ? "已发布" : "草稿"}</span></td><td>${date(v.published_at)}</td><td>${v.state === "draft" ? `<button data-action="publish" data-id="${esc(v.id)}">发布此版本</button>` : "不可修改"}</td></tr>`,
      ),
    )}</section>
    <section class="card admin-section"><div class="card-head"><h2>提交待核对</h2><span class="tiny muted">仅模拟适配器支持手动指定结果</span></div>${table(
      ["任务", "模型 / 项目", "冻结", "状态", "模拟核对"],
      r.items.map(
        (j) =>
          `<tr><td class="mono">${esc(j.id.slice(-12))}</td><td>${esc(j.model_name)}<small>${esc(j.project_ref)}</small></td><td>${money(j.reserved_micros, true)}</td><td>${badge(j.status)}</td><td><button data-action="resolve" data-id="${esc(j.id)}" data-outcome="succeeded">确认成功</button> <button data-action="resolve" data-id="${esc(j.id)}" data-outcome="failed">确认失败并释放</button></td></tr>`,
      ),
      "没有待核对任务",
    )}</section>`
  );
}
function priceBody() {
  const f = $("price-form").elements;
  return {
    model: f.model.value,
    rule: {
      mode: f.mode.value,
      cost_micros: micros(f.cost.value),
      multiplier: f.multiplier.value,
      margin: f.margin.value,
      fixed_micros: micros(f.fixed.value),
      fee_micros: micros(f.fee.value),
    },
  };
}
async function showBill(id) {
  const j = await api("/portal/v1/bills/" + encodeURIComponent(id));
  if (!j.simulation) return commercialBill(j);
  modal(
    `<h2>调用详情</h2><p class="tiny muted mono">${esc(j.id)}</p><div class="row">${badge(j.status)} ${badge(j.funds_status)} <span class="pill">${j.simulation ? "模拟调用" : "真实服务"}</span></div><div class="details-grid"><div><small>模型</small>${esc(j.model_name)}</div><div><small>项目 / Key</small>${esc(j.project_ref)} / ${esc(j.key_name)}</div><div><small>用量</small>${j.usage ? esc(JSON.stringify(j.usage)) : j.quantity + " " + esc(j.price.unit)}</div><div><small>冻结单价</small>${money(j.price.unit_price_micros, true)} / ${j.price.included_units} ${esc(j.price.unit)}</div><div><small>价格版本</small>v${j.price.version}</div><div><small>确认费用上限</small>${money(j.max_charge_micros, true)}</div><div><small>当前冻结</small>${money(j.reserved_micros, true)}</div><div><small>实际扣费</small>${money(j.charged_micros, true)}</div><div><small>创建时间</small>${date(j.created_at)}</div><div><small>最后更新</small>${date(j.updated_at)}</div></div>${j.error ? `<div class="notice">${esc(j.error)}</div>` : ""}<pre class="code-block">${esc(JSON.stringify(j.result || { message: "尚无交付回执" }, null, 2))}</pre>${["reserved", "reconciliation_pending"].includes(j.funds_status) ? `<button data-action="cancel-job" data-id="${esc(j.id)}">申请取消</button>` : ""}`,
  );
}
async function action(button) {
  if (button.dataset.action.startsWith("account-")) return accountAction(button);
  if (button.dataset.action.startsWith("commerce-")) return commerceAction(button);
  const a = button.dataset.action,
    id = button.dataset.id;
  if (a === "amount") {
    state.amount = Number(button.dataset.value);
    document
      .querySelectorAll('[data-action="amount"]')
      .forEach((v) => v.classList.toggle("selected", v === button));
    return;
  }
  if (a === "recharge") {
    const order = await api("/portal/v1/recharges", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: { amount_fen: state.amount, currency: "CNY" },
    });
    modal(
      `<span class="pill">模拟付款</span><h2 class="admin-section">订单已创建</h2><p class="muted">金额 ${money(String(order.amount_fen * 10000))}</p><p class="tiny mono">${esc(order.id)}</p><div class="notice">这是本地模拟支付，不提供真实付款二维码。正式版将接入微信 Native 支付。</div><button class="primary full" data-action="pay-order" data-id="${esc(order.id)}">模拟确认到账</button>`,
    );
    await loadPage("wallet");
    return;
  }
  if (a === "pay-order") {
    await api("/portal/v1/recharges/" + id + "/mock-confirm", {
      method: "POST",
    });
    $("modal").close();
    toast("模拟额度已到账，重复确认不会重复入账");
    await loadPage("wallet");
    return;
  }
  if (a === "new-key") {
    modal(
      '<h2>创建 API Key</h2><p class="tiny muted">设置此 Key 的每日预算，冻结额度也计入预算。</p><form id="key-form"><label>Key 名称<input name="name" maxlength="60" value="我的工作流" required></label><label>每日预算（元）<input name="budget" inputmode="decimal" value="100" required></label><label>有效期（天）<input name="days" type="number" min="1" max="365" value="90" required></label><button class="primary full" type="submit">创建并查看 Key</button></form>',
    );
    return;
  }
  if (a === "copy-key") {
    await navigator.clipboard.writeText($("new-secret").textContent);
    toast("已复制 Key，请保存在私有配置中");
    return;
  }
  if (a === "use-key") {
    state.key = $("new-secret").textContent;
    $("modal").close();
    await loadPage("playground");
    return;
  }
  if (a === "revoke") {
    modal(
      `<h2>撤销这个 Key？</h2><p class="muted">新调用将被拒绝，已经接受的任务继续执行。此操作不能恢复原 Key。</p><button class="danger" data-action="confirm-revoke" data-id="${esc(id)}">确认撤销</button>`,
    );
    return;
  }
  if (a === "confirm-revoke") {
    await api("/portal/v1/api-keys/" + id + "/revoke", { method: "POST" });
    state.key = "";
    $("modal").close();
    toast("Key 已撤销");
    await loadPage("keys");
    return;
  }
  if (a === "connect") {
    state.key = $("demo-form").elements.key.value.trim();
    const summary = await api("/v2/account/summary");
    $("connect-result").textContent =
      `已连接 · ${summary.account_name} · 可用 ${money(summary.available_micros)}`;
    return;
  }
  if (a === "submit-job") {
    if (!state.quote) throw Error("请重新获取报价");
    const job = await api("/v2/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": state.idem },
      body: {
        quote_id: state.quote.id,
        max_charge_micros: state.quote.max_charge_micros,
        call_intent_id: state.intent,
        currency: "CNY",
        confirmed: true,
      },
    });
    state.activeJob = job.id;
    $("demo-response").textContent = JSON.stringify(job, null, 2);
    toast("任务已接受，额度已冻结");
    $("quote-result").innerHTML =
      `<div class="quote-card"><span id="job-status">${badge(job.status)}</span><p class="tiny mono">${esc(job.id)}</p><button data-action="bill" data-id="${esc(job.id)}">查看账单详情</button> <button data-action="poll-job" data-id="${esc(job.id)}">刷新任务状态</button></div>`;
    return;
  }
  if (a === "poll-job") {
    const job = await api("/v2/jobs/" + id);
    updateJob(job);
    toast(labels[job.status] || job.status);
    return;
  }
  if (a === "bill") {
    await showBill(id);
    return;
  }
  if (a === "cancel-job") {
    await api("/portal/v1/bills/" + id + "/cancel", { method: "POST" });
    $("modal").close();
    toast("取消状态已更新");
    await loadPage("bills");
    return;
  }
  if (a === "filter-bills") {
    $("page-content").innerHTML = await billsPage(
      $("bill-model").value,
      $("bill-status").value,
    );
    return;
  }
  if (a === "preview-price") {
    const body = priceBody();
    const result = await api("/admin/v1/price-versions/preview", {
      method: "POST",
      body: {
        ...body,
        quantity: Number($("price-form").elements.quantity.value),
      },
    });
    if (!$("price-result")) return;
    $("price-result").innerHTML =
      `${result.quantity.toLocaleString()} ${esc(result.unit)} 的客户费用<strong>${money(result.charge_micros, true)}</strong>估算成本 ${money(result.estimated_cost_micros, true)}<br>基础毛利率约 ${(Number(result.estimated_margin) * 100).toFixed(2)}%`;
    return;
  }
  if (a === "publish") {
    modal(
      `<h2>发布新价格版本？</h2><p class="muted">发布后新报价使用此版本，有效旧报价与已接受任务保留原价格。</p><button class="primary" data-action="confirm-publish" data-id="${esc(id)}">确认发布</button>`,
    );
    return;
  }
  if (a === "confirm-publish") {
    await api("/admin/v1/price-versions/" + id + "/publish", {
      method: "POST",
    });
    $("modal").close();
    toast("新价格版本已发布");
    state.models = (await api("/portal/v1/catalogue")).items;
    await loadPage("admin");
    return;
  }
  if (a === "resolve") {
    await api("/admin/v1/reconciliation/" + id + "/mock-resolve", {
      method: "POST",
      body: { outcome: button.dataset.outcome },
    });
    toast("模拟核对已完成");
    await loadPage("admin");
    return;
  }
  if (a === "ledger-check") {
    const check = await api("/admin/v1/ledger-check");
    toast(check.ok ? "所有凭证平衡，钱包与账本一致" : "账本存在异常");
    return;
  }
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-page],[data-action]");
  if (!button) return;
  if (button.dataset.page) {
    try {
      await loadPage(button.dataset.page);
    } catch (e) {
      toast(e.message);
    }
    return;
  }
  button.disabled = true;
  try {
    await action(button);
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!["auth-form", "key-form", "demo-form", "price-form"].includes(form.id))
    return;
  event.preventDefault();
  const button = form.querySelector('[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  const isAuth = form.id === "auth-form", originalLabel = button.textContent;
  if (isAuth) {
    clearAuthError();
    form.setAttribute("aria-busy", "true");
    button.textContent = state.authMode === "login" ? "登录中…" : "创建中…";
    $("auth-login").disabled = $("auth-register").disabled = true;
  }
  try {
    const f = form.elements;
    if (isAuth) {
      const body = { username: f.username.value.trim(), password: f.password.value };
      if (!body.username) throw Error("请填写用户名");
      await enter(
        await api("/portal/v1/" + state.authMode, { method: "POST", body }),
      );
    }
    if (form.id === "key-form") {
      const created = await api("/portal/v1/api-keys", {
        method: "POST",
        body: {
          name: f.name.value,
          daily_limit_micros: micros(f.budget.value),
          expires_days: Number(f.days.value),
        },
      });
      $("modal-content").innerHTML =
        `<h2>Key 已创建</h2><div class="notice">明文仅展示这一次。关闭后无法再次读取，请现在复制保存。</div><div class="secret mono" id="new-secret">${esc(created.secret)}</div><div class="row admin-section"><button data-action="copy-key">复制 Key</button>${state.user.role === "admin" ? '<button class="primary" data-action="use-key">用于本页接入试用</button>' : ''}</div>`;
      await loadPage("keys");
    }
    if (form.id === "demo-form") {
      state.key = f.key.value.trim();
      state.quote = null;
      const inputs =
        f.model.value === "demo/avatar-role"
          ? { roles: Number(f.roles.value), demo_outcome: f.outcome.value }
          : { text: f.text.value, demo_outcome: f.outcome.value };
      const q = await api("/v2/quotes", {
        method: "POST",
        body: {
          model: f.model.value,
          input: inputs,
          project_ref: f.project.value,
        },
      });
      state.quote = q;
      state.intent = crypto.randomUUID();
      state.idem = crypto.randomUUID();
      $("quote-result").innerHTML =
        `<div class="quote-card"><span class="tiny muted">本次费用上限 · 价格 v${q.price.version}</span><p><strong>${money(q.max_charge_micros, true)}</strong></p><span class="tiny muted">${q.quantity} ${esc(q.price.unit)} · 报价有效至 ${date(q.expires_at)}</span><br><button class="primary" data-action="submit-job">确认费用并提交模拟任务</button></div>`;
    }
    if (form.id === "price-form") {
      const result = await api("/admin/v1/price-versions", {
        method: "POST",
        body: priceBody(),
      });
      toast(`草稿 v${result.version} 已保存，发布后才生效`);
      await loadPage("admin");
    }
  } catch (e) {
    if (isAuth) {
      $("auth-error").textContent = e.message;
      $("auth-error").hidden = false;
      const input = form.elements[e.message.includes("用户名已") || e.message === "请填写用户名" ? "username" : "password"];
      input.setAttribute("aria-invalid", "true");
      input.focus();
    } else toast(e.message);
  } finally {
    button.disabled = false;
    if (isAuth) {
      button.textContent = originalLabel;
      form.removeAttribute("aria-busy");
      $("auth-login").disabled = $("auth-register").disabled = false;
    }
  }
});
document.addEventListener("change", (event) => {
  if (event.target.closest("#price-form")) {
    if (event.target.name === "model") syncPriceForm();
    $("price-result").textContent = "参数已修改，点击预览费用查看最新结果。";
  }
  if (event.target.id === "demo-model") {
    $("roles-field").hidden = event.target.value !== "demo/avatar-role";
    $("text-field").hidden = event.target.value === "demo/avatar-role";
  }
  if (event.target.closest("#demo-form") && state.quote) {
    state.quote = null;
    $("quote-result").innerHTML =
      '<div class="notice">参数已修改，请重新获取报价。</div>';
  }
});
function syncPriceForm() {
  const f = $("price-form").elements;
  const price = state.adminPrices.find(
    (p) => p.model === f.model.value && p.state === "published",
  );
  if (!price) return;
  const rule = price.rule;
  f.mode.value = rule.mode;
  f.multiplier.value = rule.multiplier;
  f.margin.value = rule.margin;
  for (const [field, source] of [
    ["cost", "cost_micros"],
    ["fixed", "fixed_micros"],
    ["fee", "fee_micros"],
  ]) {
    f[field].value = money(rule[source], true)
      .replace("¥", "")
      .replaceAll(",", "");
  }
  const avatar = f.model.value === "demo/avatar-role";
  f.quantity.value = avatar ? "2" : "1200";
  f.quantity.max = avatar ? "2" : "20000";
  $("price-result").textContent = "正在获取费用预览…";
}
$("auth-login").onclick = () => { if (state.authMode !== "login") showAuth("login"); };
$("auth-register").onclick = () => { if (state.authMode !== "register") showAuth("register"); };
$("auth-form").addEventListener("input", clearAuthError);
async function logout() {
  try {
    await api("/portal/v1/logout", { method: "POST" });
    endSession();
    showAuth("login");
  } catch (e) {
    toast(e.message);
  }
}
function endSession() {
  state.key = "";
  state.activeJob = null;
  state.quote = null;
  state.user = null;
  state.csrf = "";
  state.render++;
  Object.assign(commerceState, {pendingRequest: null, redeem: null, issued: [], lastJobId: null, creditRequest: null, codeRequest: null, users: [], models: [], providers: []});
  $("modal").close();
  $("page-content").replaceChildren();
}
$("logout").onclick = logout;
$("logout-mobile").onclick = logout;
function clearModal() {
  $("modal-content").replaceChildren();
  commerceState.issued = [];
}
$("modal-close").onclick = () => {
  $("modal").close();
  clearModal();
};
$("modal").addEventListener("close", clearModal);
function updateJob(job) {
  if ($("commerce-response")) $("commerce-response").textContent = JSON.stringify(job, null, 2);
  if ($("demo-response"))
    $("demo-response").textContent = JSON.stringify(job, null, 2);
  if ($("job-status")) $("job-status").innerHTML = badge(job.status);
  if (
    !["queued", "submitting", "running", "cancel_pending"].includes(job.status)
  )
    state.activeJob = null;
}
setInterval(async () => {
  if (state.polling || !state.user) return;
  state.polling = true;
  try {
    if (state.page === "playground" && state.activeJob && state.key) {
      const id = state.activeJob;
      const job = await api("/v2/jobs/" + id);
      if (state.page === "playground" && state.activeJob === id) updateJob(job);
    }
  } catch {
    state.activeJob = null;
  } finally {
    state.polling = false;
  }
}, 1000);
async function boot() {
  document.querySelector(".sidebar-help code").textContent =
    location.origin + "/v2";
  try {
    const s = await api("/portal/v1/setup-status");
    if (s.setup_required) showAuth("setup");
    else {
      try {
        await enter(await api("/portal/v1/me"));
      } catch {
        showAuth("login");
      }
    }
  } catch (e) {
    showAuth("login");
    toast(e.message);
  }
}
boot();
