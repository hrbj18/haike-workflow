"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {items: [], total: 0, page: 1, pageSize: 20, selected: new Map(), searchSequence: 0, detailSequence: 0, detail: null, detailConflict: false, busy: false, loading: false, batchItems: []};
  const healthNames = {valid: "存在有效副本", missing: "文件缺失", changed: "内容已变化", error: "检测失败", unchecked: "尚未检测"};
  const reviewNames = {candidate: "候选", confirmed: "已确认", unreviewed: "无审核记录"};
  const make = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; };
  const seconds = value => Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} 秒` : "未记录";
  const interval = (start, end) => `${Number(start).toFixed(2)}–${Number(end).toFixed(2)} 秒`;
  const timestamp = value => { if (!value) return "尚未检测"; const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString("zh-CN", {hour12: false}); };
  const labels = value => [...new Set(value.split(/[,，\n]/).map(s => s.trim()).filter(Boolean))];
  const list = value => Array.isArray(value) ? value : [];
  const pill = (text, kind = "") => make("span", text, `pill ${kind}`);
  const healthKind = status => status === "valid" ? "good" : ["missing", "changed", "error"].includes(status) ? "bad" : "";
  function notice(id, text, kind = "") { $(id).textContent = text; $(id).className = `notice ${kind}`; }
  async function api(path, body) {
    let response;
    try { response = await fetch(`/api/material-library/${path}`, body === undefined ? {cache: "no-store"} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}); }
    catch (_) { throw new Error("无法连接素材库服务，请检查服务是否启动后重试。"); }
    let value;
    try { value = await response.json(); } catch (_) { throw new Error("素材库服务返回了无法读取的结果，请刷新后重试。"); }
    if (!response.ok) {
      let message = "操作未完成，请检查输入后重试。";
      if (typeof value.detail === "string") message = value.detail;
      else if (value.detail && typeof value.detail.message === "string") message = value.detail.message;
      else if (response.status === 422) message = "输入格式或数值不正确，请检查必填项与时间范围。";
      if (response.status === 409) message = `记录已变化或存在冲突，请重新读取后再操作。${typeof value.detail === "string" ? `\n${value.detail}` : ""}`;
      const error = new Error(message); error.status = response.status; throw error;
    }
    return value;
  }
  function controls() {
    const count = state.selected.size;
    $("selection-count").textContent = count ? `已选 ${count} 条 · 切换检索或页码将清空选择` : "选择仅限当前页";
    document.querySelectorAll("[data-selection]").forEach(el => { el.disabled = !count || state.busy || state.loading; });
    document.querySelectorAll("[data-mutation]").forEach(el => { el.disabled = state.busy; });
    $("save-metadata").disabled = state.busy || state.detailConflict || !state.detail;
    $("select-page").disabled = state.busy || state.loading || !state.items.length;
    $("select-page").checked = count > 0 && count === state.items.length;
    $("select-page").indeterminate = count > 0 && count < state.items.length;
    document.querySelectorAll(".row-select").forEach(el => { el.disabled = state.busy || state.loading; });
    $("previous").disabled = state.loading || state.page <= 1;
    $("next").disabled = state.loading || state.page * state.pageSize >= state.total;
    $("batch-cancel").disabled = state.busy;
    $("batch-save").disabled = state.busy || !state.batchItems.length || (!$("batch-use-tags").checked && !$("batch-use-collections").checked);
    $("metadata-form").querySelectorAll("input,textarea").forEach(el => { el.disabled = state.busy || state.detailConflict; });
  }
  function queryParameters() {
    const params = new URLSearchParams({query: $("query").value.trim(), tag: $("filter-tag").value.trim(), collection: $("filter-collection").value.trim(), platform: $("filter-platform").value.trim(), aspect: $("filter-aspect").value, review_status: $("filter-review").value, health: $("filter-health").value, archived: $("filter-archived").value, page: String(state.page), page_size: String(state.pageSize)});
    const min = $("filter-min").value, max = $("filter-max").value;
    if (min !== "") params.set("min_duration", min);
    if (max !== "") params.set("max_duration", max);
    if (min !== "" && max !== "" && Number(min) > Number(max)) throw new Error("最短时长不能大于最长时长。");
    return params;
  }
  function renderSummary(summary) {
    $("stat-media").textContent = summary.media ?? "—";
    $("stat-intervals").textContent = summary.intervals ?? "—";
    $("stat-reviews").textContent = summary.review_versions ?? "—";
    $("stat-observations").textContent = summary.confirmed_versions ?? "—";
  }
  function renderRows() {
    const fragment = document.createDocumentFragment();
    for (const item of state.items) {
      const metadata = item.metadata || {}, counts = item.counts || {}, health = item.health || {};
      const row = make("tr"), selection = make("td"), checkbox = make("input");
      checkbox.type = "checkbox"; checkbox.className = "row-select"; checkbox.checked = state.selected.has(item.id); checkbox.setAttribute("aria-label", `选择素材：${item.title || item.id}`);
      checkbox.addEventListener("change", () => { if (checkbox.checked) state.selected.set(item.id, {media_id: item.id, expected_revision: metadata.revision ?? 0}); else state.selected.delete(item.id); controls(); });
      selection.append(checkbox);
      const title = make("td"), button = make("button", item.title || "未命名素材", "title-button"); button.addEventListener("click", () => openDetail(item.id)); title.append(button);
      if (metadata.archived) title.append(pill("已归档", "warn"));
      title.append(make("span", list(item.platforms).filter(Boolean).join(" · ") || "本地素材", "subline"));
      const dimensions = make("td", seconds(item.duration), "nowrap"); dimensions.append(make("span", `${item.width || "—"} × ${item.height || "—"}`, "subline"));
      const tags = make("td", undefined, "pills");
      for (const tag of list(metadata.tags).slice(0, 4)) tags.append(pill(tag));
      if (list(metadata.tags).length > 4) tags.append(pill(`+${metadata.tags.length - 4}`));
      if (list(metadata.collections).length) tags.append(make("span", `集合：${metadata.collections.join("、")}`, "subline"));
      if (!list(metadata.tags).length && !list(metadata.collections).length) tags.append(make("span", "尚未整理", "muted"));
      const reviews = make("td"); reviews.append(make("span", `${counts.intervals || 0} 个区间`), make("span", `${counts.review_versions || 0} 个版本 · ${counts.confirmed_versions || 0} 个确认`, "subline"));
      const healthCell = make("td"); healthCell.append(pill(healthNames[health.status] || healthNames.unchecked, healthKind(health.status)));
      if (health.checked_at) healthCell.append(make("span", timestamp(health.checked_at), "subline"));
      row.append(selection, title, dimensions, tags, reviews, healthCell); fragment.append(row);
    }
    $("results").replaceChildren(fragment); $("empty").hidden = state.items.length !== 0;
    $("result-count").textContent = `共 ${state.total} 条符合条件的素材`;
    $("page-label").textContent = `第 ${state.page} / ${Math.max(1, Math.ceil(state.total / state.pageSize))} 页`;
    controls();
  }
  async function search({clearMessage = true} = {}) {
    let params;
    try { params = queryParameters(); } catch (error) { notice("message", error.message, "error"); return; }
    const sequence = ++state.searchSequence; state.loading = true; state.selected.clear(); controls();
    if (clearMessage) notice("message", "正在检索素材…");
    try {
      const result = await api(`manage/search?${params}`);
      if (sequence !== state.searchSequence) return;
      state.items = list(result.items); state.total = result.total || 0; state.page = result.page || state.page;
      if (!state.items.length && state.page > 1) { state.page = Math.max(1, Math.ceil(state.total / state.pageSize)); await search({clearMessage}); return; }
      renderSummary(result.summary || {}); renderRows();
      if (clearMessage) notice("message", "");
    } catch (error) {
      if (sequence !== state.searchSequence) return;
      state.items = []; state.total = 0; renderRows(); $("empty").hidden = true;
      $("result-count").textContent = "素材读取失败"; notice("message", error.message, "error");
    } finally { if (sequence === state.searchSequence) { state.loading = false; controls(); } }
  }
  function fact(container, label, value) { container.append(make("dt", label), make("dd", value === undefined || value === null || value === "" ? "未记录" : String(value))); }
  function recordHeader(title, status) { const header = make("div", undefined, "record-header"); header.append(make("strong", title)); if (status) header.append(status); return header; }
  function noRecords(target, text) { $(target).replaceChildren(make("p", text, "muted")); }
  function renderOrigins(media) {
    const container = $("detail-origins"); container.replaceChildren();
    container.append(make("p", `素材 ID：${media.id}`, "mono"), make("p", `内容 SHA256：${media.sha256}`, "mono"));
    for (const origin of list(media.origins)) { const box = make("div", undefined, "record"); box.append(make("strong", origin.title || origin.platform || "来源记录")); const facts = make("dl", undefined, "kv"); fact(facts, "平台", origin.platform); fact(facts, "来源 ID", origin.video_id); fact(facts, "来源地址", origin.source_url); fact(facts, "权利状态", origin.rights_status); box.append(facts); container.append(box); }
  }
  function renderHealth(media) {
    const health = media.health || {}, container = $("detail-locations");
    $("health-summary").textContent = `${healthNames[health.status] || healthNames.unchecked} · ${health.checked_at ? `检测于 ${timestamp(health.checked_at)}` : "尚未进行完整文件检测"}`;
    const results = new Map(list(health.locations).map(location => [location.path, location]));
    const locations = new Map(list(media.locations).map(location => [location.path, {...location, ...(results.get(location.path) || {})}]));
    for (const location of list(health.locations)) if (!locations.has(location.path)) locations.set(location.path, location);
    container.replaceChildren();
    for (const location of locations.values()) { const box = make("div", undefined, "record"); box.append(recordHeader(location.path, pill(healthNames[location.status] || healthNames.unchecked, healthKind(location.status)))); if (location.reason) box.append(make("p", location.reason, "muted")); if (location.checked_at) box.append(make("small", `检测于 ${timestamp(location.checked_at)}`)); container.append(box); }
    if (!locations.size) noRecords("detail-locations", "尚未记录文件位置。");
  }
  function factText(value) { if (typeof value === "boolean") return value ? "有" : "无"; if (Array.isArray(value)) return value.join("、"); if (typeof value === "string" || typeof value === "number") return String(value); return "未记录"; }
  function scopeText(scope) { return scope === "source-content" ? "原片内容事实" : scope === "template-band-v1" ? "旧模板中央带" : scope || "未记录范围"; }
  function renderObservations(media) {
    const container = $("detail-observations"), observations = list(media.observations); container.replaceChildren();
    for (const observation of observations) {
      const box = make("div", undefined, "record"); box.append(recordHeader(interval(observation.source_in, observation.source_out), pill(reviewNames[observation.review_status] || "未审核", observation.review_status === "confirmed" ? "good" : "warn")), make("p", observation.observation || "未填写观察"));
      const facts = make("dl", undefined, "kv"); fact(facts, "审核范围", scopeText(observation.scope)); fact(facts, "文字事实", factText(observation.facts?.text)); fact(facts, "原声", factText(observation.facts?.source_audio)); fact(facts, "字幕", factText(observation.facts?.subtitles)); fact(facts, "审核者", observation.reviewer); fact(facts, "记录时间", timestamp(observation.created_at)); box.append(facts);
      if (list(observation.evidence).length) { const details = make("details"), evidence = make("div"); details.append(make("summary", `查看 ${observation.evidence.length} 项证据来源`)); for (const entry of observation.evidence) evidence.append(make("p", entry.path || "未记录路径", "mono"), make("p", `SHA256：${entry.sha256 || "未记录"}`, "mono")); details.append(evidence); box.append(details); }
      box.append(make("p", `观察版本：${observation.id}`, "mono")); container.append(box);
    }
    if (!observations.length) noRecords("detail-observations", "暂无通用观察。管理标签不会自动生成或确认观察。");
  }
  function renderClips(media) {
    const container = $("detail-clips"), clips = list(media.clips); container.replaceChildren();
    for (const clip of clips) {
      const box = make("div", undefined, "record"), fromIndex = clip.task_id === "published-index";
      const status = fromIndex ? "旧索引候选，未作画幅审核" : clip.review_status === "confirmed" ? (clip.metadata?.usable ? "已确认：适用旧模板" : "已确认：不适用旧模板") : "待确认";
      const scope = fromIndex ? "来源：旧成片索引，未作画幅审核" : "原有审核范围：旧模板中央带";
      box.append(recordHeader(interval(clip.start, clip.end), pill(status, !fromIndex && clip.review_status === "confirmed" && clip.metadata?.usable ? "good" : "warn")), make("p", clip.observation || "未填写观察"), make("p", `${scope} · 版本：${clip.id}`, "mono")); container.append(box);
    }
    if (!clips.length) noRecords("detail-clips", "暂无旧模板区间审核记录。");
  }
  function renderUsage(media) {
    const container = $("detail-usage"), usage = list(media.usage); container.replaceChildren();
    for (const entry of usage) {
      const ref = entry.reference || {}, box = make("div", undefined, "record"); box.append(recordHeader(entry.project_id || "未记录项目", pill(`版本 ${entry.project_version || "未记录"}`)));
      const facts = make("dl", undefined, "kv"); fact(facts, "项目素材", entry.asset_id); if (entry.source_asset_id) fact(facts, "原片素材", entry.source_asset_id); if (entry.project_asset_media_id) fact(facts, "项目文件身份", entry.project_asset_media_id); fact(facts, "原片身份", ref.media_id || entry.media_id); fact(facts, "场景 / 槽位", [entry.scene_id, entry.slot_id].filter(Boolean).join(" / ")); fact(facts, "原片区间", Number.isFinite(Number(ref.source_in)) && Number.isFinite(Number(ref.source_out)) ? interval(ref.source_in, ref.source_out) : "未记录"); fact(facts, "使用目的", ref.usage_intent); fact(facts, "证据范围", scopeText(ref.scope)); fact(facts, "观察版本", ref.observation_id || ref.legacy_clip_id || "未引用审核记录"); box.append(facts, make("p", `冻结引用：${entry.ref_id || "未记录"}`, "mono")); container.append(box);
    }
    if (!usage.length) noRecords("detail-usage", "暂无已登记的项目使用关系。");
  }
  function renderDetail(media) {
    const metadata = media.metadata || {}; state.detail = media; state.detailConflict = false;
    $("detail-title").textContent = media.title || "未命名素材"; $("detail-subtitle").textContent = `${seconds(media.duration)} · ${media.width || "—"} × ${media.height || "—"}${metadata.archived ? " · 已归档" : ""}`;
    $("edit-tags").value = list(metadata.tags).join("，"); $("edit-collections").value = list(metadata.collections).join("，"); $("edit-notes").value = metadata.notes || ""; $("edit-archived").checked = Boolean(metadata.archived); $("detail-revision").textContent = `管理版本 ${metadata.revision ?? 0}`;
    const facts = $("detail-facts"); facts.replaceChildren(); fact(facts, "文件大小", `${(Number(media.bytes || 0) / 1024 / 1024).toFixed(1)} MB`); fact(facts, "不同区间", media.counts?.intervals ?? 0); fact(facts, "审核版本", media.counts?.review_versions ?? 0);
    renderOrigins(media); renderHealth(media); renderObservations(media); renderClips(media); renderUsage(media);
    $("detail-loading").hidden = true; $("detail-content").hidden = false; controls();
  }
  async function openDetail(id, {retainMessage = false, retainVideo = false} = {}) {
    const sequence = ++state.detailSequence;
    state.detail = null; state.detailConflict = false; controls();
    if (!$("detail-dialog").open) $("detail-dialog").showModal();
    if (!retainMessage) notice("detail-message", "");
    $("detail-title").textContent = "素材详情"; $("detail-subtitle").textContent = ""; $("detail-content").hidden = true; $("detail-loading").hidden = false;
    if (!retainVideo) { $("video").pause(); $("video").removeAttribute("src"); $("video").load(); }
    try {
      const media = await api(`manage/media/${encodeURIComponent(id)}`);
      if (sequence !== state.detailSequence || !$("detail-dialog").open) return;
      renderDetail(media);
      if (!retainVideo) $("video").src = `/api/material-library/media/${encodeURIComponent(id)}/video`;
    } catch (error) { if (sequence === state.detailSequence) { $("detail-loading").hidden = true; notice("detail-message", error.message, "error"); } }
  }
  async function mutation(messageId, action) {
    if (state.busy) return;
    const detailSequence = messageId === "detail-message" ? state.detailSequence : null;
    state.busy = true; controls(); notice(messageId, "正在处理，请稍候…");
    try { await action(); } catch (error) {
      const sameDetail = detailSequence === null || (detailSequence === state.detailSequence && $("detail-dialog").open);
      notice(sameDetail ? messageId : "message", error.message, "error");
      if (error.status === 409) {
        if (messageId === "detail-message" && sameDetail) state.detailConflict = true;
        if (messageId !== "detail-message") { state.batchItems = []; state.selected.clear(); renderRows(); if (messageId === "batch-message") notice("batch-message", `${error.message}\n请关闭此对话框，刷新素材后重新选择。`, "error"); }
      }
    }
    finally { state.busy = false; controls(); }
  }
  async function updateBatch(patch, items, messageId) {
    await mutation(messageId, async () => {
      const result = await api("manage/metadata", {items, patch});
      $("batch-dialog").close(); await search({clearMessage: false});
      notice("message", `已更新 ${result.updated ?? items.length} 条素材。`, "success");
    });
  }
  $("search-form").addEventListener("submit", event => { event.preventDefault(); state.page = 1; search(); });
  $("reset-filters").addEventListener("click", () => { $("search-form").reset(); state.page = 1; search(); });
  $("refresh").addEventListener("click", () => search());
  $("previous").addEventListener("click", () => { state.page = Math.max(1, state.page - 1); search(); });
  $("next").addEventListener("click", () => { state.page += 1; search(); });
  $("page-size").addEventListener("change", () => { state.pageSize = Number($("page-size").value); state.page = 1; search(); });
  $("select-page").addEventListener("change", () => { state.selected.clear(); if ($("select-page").checked) for (const item of state.items) state.selected.set(item.id, {media_id: item.id, expected_revision: item.metadata?.revision ?? 0}); renderRows(); });
  $("batch-edit").addEventListener("click", () => { state.batchItems = [...state.selected.values()].map(item => ({...item})); $("batch-form").reset(); $("batch-tags").disabled = true; $("batch-collections").disabled = true; $("batch-count").textContent = `将修改当前选择的 ${state.batchItems.length} 条素材。`; notice("batch-message", ""); $("batch-dialog").showModal(); controls(); });
  for (const field of ["tags", "collections"]) $("batch-use-" + field).addEventListener("change", () => { $("batch-" + field).disabled = !$("batch-use-" + field).checked; controls(); });
  $("batch-cancel").addEventListener("click", () => $("batch-dialog").close());
  $("batch-dialog").addEventListener("cancel", event => { if (state.busy) event.preventDefault(); });
  $("batch-form").addEventListener("submit", event => { event.preventDefault(); const patch = {}; if ($("batch-use-tags").checked) patch.tags = labels($("batch-tags").value); if ($("batch-use-collections").checked) patch.collections = labels($("batch-collections").value); if (!Object.keys(patch).length) return; updateBatch(patch, state.batchItems, "batch-message"); });
  $("batch-archive").addEventListener("click", () => updateBatch({archived: true}, [...state.selected.values()], "message"));
  $("batch-restore").addEventListener("click", () => updateBatch({archived: false}, [...state.selected.values()], "message"));
  $("close-detail").addEventListener("click", () => $("detail-dialog").close());
  $("detail-dialog").addEventListener("close", () => { state.detailSequence += 1; state.detail = null; $("video").pause(); $("video").removeAttribute("src"); $("video").load(); });
  $("reload-detail").addEventListener("click", () => { if (state.detail) openDetail(state.detail.id, {retainVideo: true}); });
  $("metadata-form").addEventListener("submit", event => {
    event.preventDefault(); if (!state.detail || state.detailConflict) return;
    const media = state.detail, sequence = state.detailSequence;
    const patch = {tags: labels($("edit-tags").value), collections: labels($("edit-collections").value), notes: $("edit-notes").value, archived: $("edit-archived").checked};
    mutation("detail-message", async () => { await api("manage/metadata", {items: [{media_id: media.id, expected_revision: media.metadata?.revision ?? 0}], patch}); if (sequence === state.detailSequence && $("detail-dialog").open) { await openDetail(media.id, {retainMessage: true, retainVideo: true}); notice("detail-message", "管理信息已保存。", "success"); } await search({clearMessage: false}); notice("message", "管理信息已保存，素材列表已刷新。", "success"); });
  });
  $("check-health").addEventListener("click", () => {
    if (!state.detail) return;
    const media = state.detail, sequence = state.detailSequence;
    mutation("detail-message", async () => { await api(`manage/media/${encodeURIComponent(media.id)}/health`, {}); if (sequence === state.detailSequence && $("detail-dialog").open) { await openDetail(media.id, {retainMessage: true, retainVideo: true}); notice("detail-message", "完整文件检测已完成，请查看各位置的检测结果。", "success"); } await search({clearMessage: false}); });
  });
  $("relink-form").addEventListener("submit", event => {
    event.preventDefault(); if (!state.detail) return;
    const media = state.detail, sequence = state.detailSequence, path = $("relink-path").value.trim(); if (!path) return;
    mutation("detail-message", async () => { await api(`manage/media/${encodeURIComponent(media.id)}/relink`, {path}); if (sequence === state.detailSequence && $("detail-dialog").open) { $("relink-path").value = ""; await openDetail(media.id, {retainMessage: true}); notice("detail-message", "已验证内容一致，并登记新位置。", "success"); } await search({clearMessage: false}); });
  });
  $("import-form").addEventListener("submit", event => {
    event.preventDefault(); const path = $("import-path").value.trim(), kind = $("import-kind").value; if (!path) return;
    mutation("message", async () => { const result = await api("import", {path, kind}); state.page = 1; await search({clearMessage: false}); const failures = list(result.failures); notice("message", failures.length ? `登记已完成，其中 ${failures.length} 个文件未成功，请检查路径和视频格式。` : "素材登记已完成，可通过搜索查看。", failures.length ? "error" : "success"); });
  });
  $("video").addEventListener("error", () => { if ($("video").getAttribute("src") && $("detail-dialog").open) notice("detail-message", "素材暂时无法播放。可检查文件健康、修复位置；如文件有效，请确认浏览器支持该视频编码。", "error"); });
  search();
})();
