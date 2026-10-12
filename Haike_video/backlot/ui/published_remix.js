const $ = id => document.getElementById(id);
const state = { draft: null, dirty: false, busy: false, versions: [] };
const statusNames = { queued: "排队中", running: "渲染中", completed: "待人工观看", failed: "失败，可重试", cancelled: "已取消", paused: "已暂停", ambiguous: "待核对" };
function element(tag, text, className) {
  const node = document.createElement(tag); if (text != null) node.textContent = text; if (className) node.className = className; return node;
}
async function api(path = "", options = {}) {
  const response = await fetch("/api/published-remixes" + path, options);
  const data = await response.json(); if (!response.ok) throw new Error(data.detail || "二剪请求失败"); return data;
}
const body = data => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
const message = text => { $("remix-message").textContent = text; };
function changed() { state.dirty = true; summary(); }
function summary() {
  const segments = state.draft?.payload.segments || [];
  const duration = segments.reduce((n, s) => n + Math.max(0, Number(s.end_seconds) - Number(s.start_seconds)), 0);
  $("remix-summary").textContent = state.draft ? `${segments.length} 段 · 约 ${duration.toFixed(2)} 秒 · 草稿版本 ${state.draft.revision}${state.dirty ? " · 有未保存修改" : " · 已保存"}` : "选择或新建一个二剪草稿";
}
async function refreshList(selected = state.draft?.id) {
  const drafts = await api();
  $("remix-project").replaceChildren(new Option("选择二剪草稿", ""));
  for (const draft of drafts) $("remix-project").append(new Option(draft.title, draft.id));
  $("remix-project").value = selected || "";
  return drafts;
}
async function openDraft(id, discard = false) {
  if ((!discard && state.dirty) || state.busy) { $("remix-project").value = state.draft?.id || ""; message("请先保存当前草稿，再切换项目。"); return; }
  if (!id) return;
  state.busy = true; $("remix-editor").disabled = true;
  try {
    state.draft = await api("/" + id); state.dirty = false; state.versions = state.draft.versions || [];
    $("remix-title").value = state.draft.title;
    $("remix-preview").hidden = true; $("remix-preview").removeAttribute("src");
    $("remix-preview-label").textContent = "";
    renderSegments(); renderVersions(); summary(); message("");
    localStorage.setItem("published-remix-last", id);
  } finally { state.busy = false; $("remix-editor").disabled = false; }
}
async function createDraft() {
  if (state.dirty || state.busy) throw new Error("请先保存当前草稿，再新建项目。");
  state.busy = true;
  try {
    const title = $("remix-new-title").value.trim() || "互动混剪草稿";
    state.draft = await api("", { method: "POST", ...body({ title }) });
    state.versions = []; $("remix-title").value = state.draft.title;
    $("remix-preview").hidden = true; $("remix-preview").removeAttribute("src");
    $("remix-preview-label").textContent = "";
    localStorage.setItem("published-remix-last", state.draft.id);
    await refreshList(); renderSegments(); renderVersions(); summary(); message("草稿已创建，可以加入片段。");
  } finally { state.busy = false; }
}

export async function addToRemix(selection) {
  try {
    if (state.busy) throw new Error("正在保存或提交，请稍后加入片段。");
    if (!state.draft) await createDraft();
    if (state.draft.payload.segments.length >= 30) throw new Error("选材篮最多三十段。");
    state.draft.payload.segments.push({ ...selection, id: crypto.randomUUID(), audio_mode: "original", role: "body", note: "" });
    $("remix-workbench").open = true;
    changed(); renderSegments(); message("已加入选材篮；可继续选材或保存草稿。");
  } catch (error) { message(error.message); }
}

function button(text, fn) {
  const b = element("button", text, "secondary"); b.type = "button";
  b.addEventListener("click", () => { if (!state.busy) fn(); }); return b;
}
function renderSegments() {
  const host = $("remix-segments"); host.replaceChildren();
  for (const [n, segment] of (state.draft?.payload.segments || []).entries()) {
    const card = element("div", null, "remix-segment");
    card.append(element("strong", `${n + 1}. ${segment.source_name || "已选片段"}`));
    card.append(element("p", segment.source_review_status === "confirmed" ? "来源事件已确认；二剪切口仍需观看" : "来源内容待核对，导出结果保留待审状态", "muted"));
    const fields = element("div", null, "remix-fields");
    for (const [key, label] of [["start_seconds", "片段入点"], ["end_seconds", "片段出点"]]) {
      const wrap = element("label", label), input = element("input");
      input.type = "number"; input.min = "0"; input.step = "0.001"; input.value = segment[key];
      input.addEventListener("input", () => { segment[key] = input.value === "" ? null : Number(input.value); changed(); }); wrap.append(input); fields.append(wrap);
    }
    for (const [key, label, options] of [["audio_mode", "原声", { original: "保留原声", lowered: "原声压低 12dB", mute: "静音" }],
      ["role", "用途", { opening: "开场引子", body: "主体互动", ending: "结尾" }]]) {
      const wrap = element("label", label), select = element("select");
      for (const [value, text] of Object.entries(options)) select.append(new Option(text, value));
      select.value = segment[key]; select.addEventListener("change", () => { segment[key] = select.value; changed(); });
      wrap.append(select); fields.append(wrap);
    }
    const noteWrap = element("label", "剪辑备注"), note = element("input"); note.value = segment.note; note.maxLength = 500;
    note.placeholder = "例如：避开原片片尾、保留这句回答";
    note.addEventListener("input", () => { segment.note = note.value; changed(); }); noteWrap.append(note);
    const actions = element("div", null, "actions");
    actions.append(button("看原片区间", () => window.dispatchEvent(new CustomEvent("remix-source-preview", { detail: segment }))));
    for (const [label, shift] of [["上移", -1], ["下移", 1]]) {
      const control = button(label, () => {
        const rows = state.draft.payload.segments;
        [rows[n], rows[n + shift]] = [rows[n + shift], rows[n]];
        changed(); renderSegments();
      });
      control.disabled = n + shift < 0 || n + shift >= state.draft.payload.segments.length;
      actions.append(control);
    }
    actions.append(button("移除片段", () => { state.draft.payload.segments.splice(n, 1); changed(); renderSegments(); }));
    card.append(fields, noteWrap, actions); host.append(card);
  }
}

async function saveDraft() {
  if (!state.draft) throw new Error("请先新建或选择草稿。");
  const saved = await api("/" + state.draft.id, { method: "PUT", ...body({ revision: state.draft.revision,
    title: $("remix-title").value.trim(), segments: state.draft.payload.segments }) });
  state.draft = saved; state.dirty = false; renderSegments(); summary(); await refreshList();
  message("草稿已保存。"); return saved;
}

function renderVersions() {
  const host = $("remix-versions"); host.replaceChildren();
  for (const version of state.versions) {
    const row = element("div", null, "remix-version");
    row.append(element("strong", `版本 ${version.revision} · ${statusNames[version.status] || version.status}${version.revision !== state.draft.revision ? " · 历史版本" : ""}`));
    if (version.status === "completed") {
      const url = `/api/published-remixes/${state.draft.id}/versions/${version.signature}/media`;
      row.append(button("播放此版本", () => {
        $("remix-preview").hidden = false; $("remix-preview").src = url;
        $("remix-preview-label").textContent = `正在预览版本 ${version.revision} · ${version.duration_seconds?.toFixed(2)} 秒 · 待人工观看`;
        $("remix-preview").play().catch(() => {});
      }));
      const download = element("a", "下载待审 MP4"); download.href = url + "?download=true"; download.setAttribute("download", ""); row.append(download);
      row.append(element("span", " 画面720×1280 · 技术检查通过", "muted"));
    } else {
      row.append(element("span", " " + (version.error || version.stage || "等待统一调度"), "muted"));
      if (version.status === "failed" && version.queue_job) row.append(button("重试此版本", async () => {
        try {
          await fetch(`/api/production-queue/jobs/${version.queue_job.job_id}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(async response => {
            if (!response.ok) throw new Error((await response.json()).detail || "重试失败");
          });
          await refreshVersions();
        } catch (error) { message(error.message); }
      }));
    }
    host.append(row);
  }
}
async function refreshVersions() {
  const id = state.draft?.id; if (!id) return;
  const data = await api("/" + id); if (state.draft?.id !== id) return;
  state.versions = data.versions || []; renderVersions();
}
async function busyAction(fn) {
  if (state.busy) return;
  state.busy = true; $("remix-editor").disabled = true;
  try { await fn(); } catch (error) { message(error.message); }
  finally { state.busy = false; $("remix-editor").disabled = false; }
}
$("remix-create").addEventListener("click", () => createDraft().catch(e => message(e.message)));
$("remix-project").addEventListener("change", () => openDraft($("remix-project").value).catch(e => message(e.message)));
$("remix-title").addEventListener("input", changed);
$("remix-save").addEventListener("click", () => busyAction(saveDraft));
$("remix-reload").addEventListener("click", () => {
  if (state.draft && !state.busy && (!state.dirty || confirm("放弃本页未保存修改，并读取服务器最新草稿？"))) {
    openDraft(state.draft.id, true).catch(e => message(e.message));
  }
});
$("remix-render").addEventListener("click", () => busyAction(async () => {
  const saved = await saveDraft();
  await api(`/${saved.id}/render`, { method: "POST", ...body({ revision: saved.revision }) });
  message("已进入统一生产队列；可继续编辑，已提交版本不会被改变。");
  await refreshVersions();
}));
$("remix-refresh").addEventListener("click", () => refreshVersions().catch(e => message(e.message)));
window.addEventListener("beforeunload", event => { if (state.dirty) { event.preventDefault(); event.returnValue = ""; } });
setInterval(() => { if (!state.busy && state.versions.some(v => ["queued", "running"].includes(v.status))) refreshVersions().catch(e => message(e.message)); }, 5000);
refreshList().then(drafts => {
  const requested = new URLSearchParams(location.search).get("remix");
  const previous = requested || localStorage.getItem("published-remix-last");
  if (drafts.some(d => d.id === previous)) {
    $("remix-project").value = previous;
    if (requested) $("remix-workbench").open = true;
    return openDraft(previous);
  }
}).catch(e => message(e.message));
