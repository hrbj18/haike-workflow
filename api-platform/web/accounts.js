"use strict";
const fundingChannels = {wechat: "微信私域", alipay: "支付宝", bank: "银行转账", private: "其他私域渠道"};
function channelOptions() {
  return Object.entries(fundingChannels).map(([k, v]) => '<option value="' + k + '">' + v + '</option>').join("");
}
function fundingFields() {
  return '<label>收款渠道<select name="channel">' + channelOptions() + '</select></label>' +
    field("收款凭证 / 交易单号（不可重复）", "payment_ref", "", 'required maxlength="100"') +
    field("入账备注", "note", "", 'required maxlength="200"') +
    '<label class="connection-switch"><input type="checkbox" name="received" required>已核实线下收款，金额与本次充值一致</label>';
}
function accountPage() {
  return heading("账户与安全", "管理登录密码。忘记密码时，通过私域渠道联系管理员核实身份。") +
    '<section class="card"><h2>' + esc(state.user.name) + '</h2><p>' + esc(state.user.email) + '</p><p class="tiny mono">账户编号：' + esc(state.user.id) + '</p>' +
    (state.user.must_change_password ? '<div class="notice">请先修改管理员提供的初始密码，完成后即可充值和申请 API Key。</div>' : '') +
    '<form id="account-password" method="post">' + field("当前密码", "current", "", 'type="password" maxlength="128" required autocomplete="current-password"') +
    field("新密码", "password", "", 'type="password" maxlength="128" required autocomplete="new-password"') +
    field("确认新密码", "confirm", "", 'type="password" maxlength="128" required autocomplete="new-password"') +
    '<button type="submit" class="primary">保存新密码</button></form><p class="tiny muted">修改后其他浏览器需重新登录；平台 API Key 保留。</p></section>';
}
function actualFundingTable(items, admin = false) {
  return table(admin ? ["到账时间 / 凭证", "用户", "方式", "到账金额", "操作人"] : ["到账时间 / 凭证", "方式", "到账金额", "操作人"], items.map(r =>
    '<tr><td>' + date(r.created_at) + '<small class="mono">' + esc(r.id) + '</small></td>' +
    (admin ? '<td>' + esc(r.name) + '<small>' + esc(r.email) + '</small></td>' : '') +
    '<td>' + esc(creditKinds(r.kind)) + '</td><td>' + money(r.amount_micros, true) + '</td><td>' + esc(r.operator) + '</td></tr>'), "暂无充值到账记录");
}
async function usersAdminPage() {
  const [users, info] = await Promise.all([api("/admin/v1/users?search=" + encodeURIComponent(commerceState.userSearch || "")), api("/portal/v1/funding-info")]);
  commerceState.users = users.items;
  const customers = users.items.filter(u => u.role === "customer" && u.status === "active");
  return heading("用户与充值", "先核实私域收款，再手动入账或发放兑换码。充值按 1:1 到账，调用按采购成本 × 1.5 计费。") +
    '<div class="grid-two"><section class="card"><h3>管理员开户</h3><form id="commerce-user" method="post">' +
    field("用户名", "username", "", 'required maxlength="120" autocomplete="username"') +
    field("初始密码", "password", "", 'type="password" maxlength="128" required autocomplete="new-password"') +
    '<button type="submit" class="primary">创建用户</button></form><p class="tiny muted">用户首次登录必须修改初始密码。</p></section>' +
    '<section class="card"><h3>手动充值</h3><form id="commerce-credit" method="post"><label>用户<select name="user_id" required><option value="">请选择收款对应用户</option>' +
    customers.map(u => '<option value="' + esc(u.id) + '">' + esc(u.name + " · " + u.email) + '</option>').join("") + '</select></label>' +
    field("充值金额（元，1:1 到账）", "amount", "100", 'required inputmode="decimal"') +
    '<button class="primary" type="submit"' + (!customers.length ? ' disabled' : '') + '>核对充值信息</button></form><p class="tiny muted">系统自动记录充值用户、金额、时间与操作人。</p></section></div>' +
    '<section class="card admin-section"><div class="card-head"><h2>用户列表</h2><button data-page="funding">查看充值记录 →</button></div>' +
    '<form id="account-user-search" class="filter-row" method="post">' + field("搜索名称、用户名或账户编号", "search", commerceState.userSearch || "", 'maxlength="120"') + '<button type="submit">搜索</button><button type="button" data-action="account-clear-search">显示全部</button></form>' +
    table(["用户 / 账户编号", "用户名", "状态", "商业余额 / 冻结", "注册时间", "操作"], users.items.map(u =>
      '<tr><td>' + esc(u.name) + '<small class="mono">' + esc(u.id) + '</small></td><td>' + esc(u.email) + '</td><td><span class="pill ' + (u.status === "active" ? "good" : "warn") + '">' + (u.status === "active" ? "正常" : "已停用") + '</span>' + (u.must_change_password ? '<small>待修改初始密码</small>' : '') + '</td><td>' + money(u.commercial_available_micros, true) + '<small>冻结 ' + money(u.reserved_micros, true) + '</small></td><td>' + date(u.created_at) + '</td><td>' +
      (u.role === "customer" ? '<div class="row"><button data-action="account-select-credit" data-id="' + esc(u.id) + '"' + (u.status !== "active" ? ' disabled' : '') + '>充值</button><button data-action="account-reset" data-id="' + esc(u.id) + '">重置密码</button><button data-action="account-status" data-id="' + esc(u.id) + '">' + (u.status === "active" ? "停用" : "启用") + '</button></div>' : '管理员') + '</td></tr>')) + '<p class="tiny muted">最多展示 500 个匹配用户。停用将退出会话并暂停 Key 新调用，已接受任务继续按原账单结算，余额保留。</p></section>' +
    '<section class="card admin-section"><details><summary>私域充值联系方式与说明</summary><form id="account-funding-info" method="post">' + field("联系管理员（微信 / 电话 / 私域账号）", "contact", info.contact, 'required maxlength="200"') + '<label>充值说明<textarea name="instructions" maxlength="1000" required>' + esc(info.instructions) + '</textarea></label><button type="submit" class="primary">保存用户端指引</button></form></details></section>';
}
async function fundingAdminPage() {
  const r = await api("/admin/v1/funding-history");
  return heading("充值记录", "收款登记与余额到账分别记录。发码尚未兑换时，用户余额不会增加。", '<a href="/admin/v1/funding-history/export">↓ 导出收款登记 CSV</a>') +
    '<section class="card"><h2>私域收款登记</h2>' + table(["时间 / 记录", "充值方式", "用户", "确认收款金额", "渠道 / 凭证", "备注", "操作人 / 兑换进度"], r.receipts.map(x =>
      '<tr><td>' + date(x.created_at) + '<small class="mono">' + esc(x.id) + '</small></td><td>' + (x.kind === "manual" ? "手动入账" : "兑换码充值") + '</td><td>' + esc(x.email || "未绑定用户") + '</td><td>' + money(x.amount_micros, true) + '</td><td>' + esc(fundingChannels[x.channel]) + '<small>' + esc(x.payment_ref || "系统记录：" + x.id) + '</small></td><td>' + esc(x.note) + '</td><td>' + esc(x.operator) + (x.kind === "codes" ? '<small>已兑换 ' + x.redeemed_count + ' / ' + x.code_count + '</small>' : '<small>已到账</small>') + '</td></tr>')) + '</section><section class="card admin-section"><h2>实际余额到账记录</h2>' + actualFundingTable(r.items, true) + '<p class="tiny muted">每个列表最多 500 条；记录不可删除或修改，充值不是模型调用收入。</p></section>';
}
function fundingBody(f) {
  return {channel: f.channel.value, payment_ref: f.payment_ref.value.trim(), note: f.note.value.trim(), received_confirmed: f.received.checked};
}
function prepareCredit(form) {
  const f = form.elements, user = commerceState.users.find(u => u.id === f.user_id.value);
  if (!user) throw Error("请选择充值用户");
  const body = {amount_micros: micros(f.amount.value)};
  if (body.amount_micros === "0") throw Error("充值金额必须大于 0");
  const serialized = JSON.stringify({user: user.id, body});
  if (commerceState.creditRequest?.serialized !== serialized) commerceState.creditRequest = {serialized, user_id: user.id, body, idem: crypto.randomUUID()};
  modal('<h2>核对手动充值</h2><p>用户：<strong>' + esc(user.name) + '</strong><br>' + esc(user.email) + '</p><div class="notice">本次增加余额 ' + money(body.amount_micros, true) + '，充值按 1:1 到账。</div><button class="primary" data-action="account-confirm-credit">确认充值</button>');
}
function prepareCodes(form) {
  const f = form.elements, body = {amount_micros: micros(f.amount.value), count: Number(f.count.value), expires_days: Number(f.days.value), batch: f.batch.value, bound_user_id: f.bound.value || null, ...fundingBody(f)};
  if (body.amount_micros === "0") throw Error("兑换码额度必须大于 0");
  const serialized = JSON.stringify(body);
  if (commerceState.codeRequest?.serialized !== serialized) commerceState.codeRequest = {serialized, body, idem: crypto.randomUUID()};
  modal('<h2>核对兑换码充值</h2><p>绑定用户：' + esc(f.bound.selectedOptions[0].textContent) + '</p><div class="notice">' + body.count + ' 个码 × ' + money(body.amount_micros, true) + '，对应已收款合计 ' + money((BigInt(body.amount_micros) * BigInt(body.count)).toString(), true) + '</div><p>收款凭证：' + esc(body.payment_ref) + '</p><p>用户确认兑换后余额才到账。兑换码仅在生成后展示一次，请立即复制保存并通过私域交付用户。</p><button class="primary" data-action="account-confirm-codes">确认已收款并生成</button>');
}
function showIssuedCodes(result) {
  commerceState.issued = result.items;
  $("modal-content").innerHTML = '<h2>' + (result.replayed ? '本次兑换码已签发' : '兑换码已生成') + '</h2><p>' + (result.replayed ? '未重复发码。此前响应中的明文仅展示一次，如未保存，可对未使用码重新签发，沿用原收款记录。' : '明文仅展示本次，请复制保存并通过私域交付绑定用户。') + '</p><pre class="code-block" id="issued-codes">' + esc(result.items.map(c => (c.code || c.prefix + "…") + "  " + money(c.amount, true)).join("\n")) + '</pre>' + (!result.replayed ? '<button data-action="account-copy-codes">复制兑换码</button>' : '');
}
async function accountAction(button) {
  const action = button.dataset.action, id = button.dataset.id;
  if (action === "account-toggle-password") {
    const input = $("auth-form").elements.password;
    input.type = input.type === "password" ? "text" : "password";
    const label = input.type === "password" ? "显示密码" : "隐藏密码";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.setAttribute("aria-pressed", String(input.type === "text"));
  }
  if (action === "account-forgot") {
    const info = await api("/portal/v1/funding-info");
    modal('<h2>联系管理员重置密码</h2><p class="contact-text">' + esc(info.contact) + '</p><p>请提供用户名，通过原私域渠道核实身份。管理员重置后使用临时密码登录，并立即设置自己的新密码。</p>');
  }
  if (action === "account-clear-search") { commerceState.userSearch = ""; await loadPage("users"); }
  if (action === "account-select-credit") {
    const form = $("commerce-credit"); form.elements.user_id.value = id; form.scrollIntoView({behavior: "smooth", block: "center"}); form.elements.amount.focus();
  }
  if (action === "account-reset") {
    const user = commerceState.users.find(u => u.id === id);
    modal('<h2>重置用户登录密码</h2><p>' + esc(user.name + " · " + user.email) + '</p><form id="account-reset-password" method="post" data-id="' + esc(id) + '">' + field("新的临时密码", "password", "", 'type="password" maxlength="128" required autocomplete="new-password"') + '<label class="connection-switch"><input type="checkbox" required>已通过私域核实用户身份</label><button type="submit" class="primary">确认重置密码</button></form><p class="tiny muted">旧会话立即失效，用户再次登录必须修改临时密码。</p>');
  }
  if (action === "account-status") {
    const user = commerceState.users.find(u => u.id === id), next = user.status === "active" ? "disabled" : "active";
    modal('<h2>' + (next === "disabled" ? "停用用户" : "启用用户") + '</h2><p>' + esc(user.name + " · " + user.email) + '</p><p>余额与历史账单保留。停用后不能登录或发起新的 API 调用，已接受任务继续结算。</p><button class="primary" data-action="account-confirm-status" data-id="' + esc(id) + '" data-status="' + next + '">确认' + (next === "disabled" ? "停用" : "启用") + '</button>');
  }
  if (action === "account-confirm-status") {
    await api("/admin/v1/users/" + id + "/status", {method: "POST", body: {status: button.dataset.status}}); $("modal").close(); toast("账户状态已更新"); await loadPage("users");
  }
  if (action === "account-confirm-credit") {
    const r = commerceState.creditRequest;
    if (!r) throw Error("请重新核对充值信息");
    await api("/admin/v1/users/" + r.user_id + "/credits", {method: "POST", headers: {"Idempotency-Key": r.idem}, body: r.body});
    commerceState.creditRequest = null; $("modal").close(); toast("充值已到账，凭证已记录"); await loadPage("users");
  }
  if (action === "account-reissue-code") {
    modal('<h2>重新签发未使用兑换码</h2><p>旧码立即失效，新码保留原金额、绑定用户及有效期，沿用原收款记录。不会重复登记收款或增加余额。</p><button class="primary" data-action="account-confirm-reissue" data-id="' + esc(id) + '">确认替换旧码</button>');
  }
  if (action === "account-confirm-reissue") {
    showIssuedCodes(await api("/admin/v1/redeem-codes/" + id + "/reissue", {method: "POST"}));
    await loadPage("codes");
  }
  if (action === "account-confirm-codes") {
    const r = commerceState.codeRequest;
    if (!r) throw Error("请重新核对兑换码信息");
    const result = await api("/admin/v1/redeem-codes", {method: "POST", headers: {"Idempotency-Key": r.idem}, body: r.body});
    commerceState.codeRequest = null;
    showIssuedCodes(result);
    await loadPage("codes");
  }
  if (action === "account-copy-codes") { await navigator.clipboard.writeText(commerceState.issued.map(c => c.code).join("\n")); toast("兑换码已复制"); }
}
document.addEventListener("submit", async event => {
  const form = event.target, formId = form.getAttribute("id") || "";
  if (!formId.startsWith("account-")) return;
  event.preventDefault();
  const f = form.elements, button = form.querySelector('[type="submit"]'); button.disabled = true;
  try {
    if (formId === "account-password") {
      if (f.password.value !== f.confirm.value) throw Error("两次输入的新密码不一致");
      const result = await api("/portal/v1/password", {method: "POST", body: {current_password: f.current.value, new_password: f.password.value}});
      await enter(result); toast("密码已修改，其他登录会话已失效");
    }
    if (formId === "account-user-search") { commerceState.userSearch = f.search.value.trim(); await loadPage("users"); }
    if (formId === "account-reset-password") {
      await api("/admin/v1/users/" + form.dataset.id + "/password", {method: "POST", body: {password: f.password.value}});
      form.reset(); $("modal").close(); toast("临时密码已设置，请通过原私域渠道交付用户"); await loadPage("users");
    }
    if (formId === "account-funding-info") {
      await api("/admin/v1/funding-info", {method: "POST", body: {contact: f.contact.value, instructions: f.instructions.value}}); toast("用户端充值指引已保存");
    }
  } catch (e) { toast(e.message); }
  finally { button.disabled = false; }
});
document.addEventListener("input", event => {
  if (event.target.closest("#commerce-redeem")) {
    commerceState.redeem = null;
    $("redeem-preview").replaceChildren();
  }
});
