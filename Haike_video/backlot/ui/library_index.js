import { el, getJSON } from "/ui/lib.js";

const zone = "Asia/Shanghai";
const dateFormat = new Intl.DateTimeFormat("sv-SE", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" });
const clockFormat = new Intl.DateTimeFormat("zh-CN", { timeZone: zone, hour: "2-digit", minute: "2-digit", hour12: false });
const filters = { search: "", date: "all", production: "all", publication: "all", sort: "created" };
let rerender = () => {};
let reload = () => {};
let activeProject = null;
let detail = null;
let saving = false;
const modal = el("dialog", { class: "project-dialog library-index-dialog", "aria-labelledby": "libraryIndexTitle" });
document.body.append(modal);

function day(value) {
  const date = new Date(value || "");
  return Number.isFinite(date.getTime()) ? dateFormat.format(date) : "";
}
function relativeDay(value) {
  const key = day(value);
  if (!key) return "日期待确认";
  if (key === day(Date.now())) return "今天";
  if (key === day(Date.now() - 86400000)) return "昨天";
  return key;
}
export function dateLabel(value) {
  if (!day(value)) return "日期待确认";
  const relative = relativeDay(value);
  return `${relative === day(value) ? relative : `${relative}（${day(value)}）`} ${clockFormat.format(new Date(value))}`;
}
export function projectDateLine(project) {
  const index = project.library || {};
  return `创建：${dateLabel(index.created_at)}${index.created_source === "manual" ? " · 人工补录" : ""}　更新：${dateLabel(index.updated_at)}`;
}
export function platformLine(project) {
  const publication = project.library?.publication || {};
  const labels = { douyin: "抖音", kuaishou: "快手", shipinhao: "视频号", xhs: "小红书" };
  const statuses = { published: "已发布", reviewing: "审核中", uploaded: "已上传", uploading: "上传中", pending: "待发布", uncertain: "待核实", failed: "失败", canceled: "已取消" };
  const platforms = Object.entries(publication.platforms || {});
  return platforms.length ? platforms.map(([p, s]) => `${labels[p] || p}：${statuses[s] || "待核实"}`).join(" · ")
    : (publication.history_platforms || []).map(p => `${labels[p] || p}：有历史发布`).join(" · ");
}
export function publicationControl(project) {
  const index = project.library || {};
  return el("div", { class: "library-publication" },
    el("button", { type: "button", class: `publication-badge ${index.publication?.status || "none"}`,
      "aria-label": `查看发布记录：${project.title || project.project_id}`, onclick: () => openIndex(project) },
      index.error ? "索引需处理" : index.publication?.label || "暂无发布记录"),
    el("small", { title: index.sync?.checked_at ? `上次同步：${dateLabel(index.sync.checked_at)}` : "" }, index.sync?.status === "connected" ? "发布系统已同步" : index.sync?.status === "stale" ? "离线 · 保留上次同步" : "发布系统未连接"));
}
function selectControl(label, key, options) {
  const select = el("select", { "aria-label": label }, options.map(([value, text]) => el("option", { value }, text)));
  select.value = filters[key];
  select.addEventListener("change", () => { filters[key] = select.value; rerender(); });
  return el("label", {}, el("span", {}, label), select);
}
export function mountLibraryTools(onFilter, onSaved) {
  rerender = onFilter; reload = onSaved;
  const search = el("input", { type: "search", placeholder: "搜索项目名称或编号", "aria-label": "搜索项目" });
  search.addEventListener("input", () => { filters.search = search.value.trim().toLowerCase(); rerender(); });
  const toolbar = el("section", { class: "library-filter-panel", "aria-label": "筛选项目" },
    el("div", { class: "library-filter-head" }, el("strong", {}, "按日期和发布进度找项目"),
      el("button", { type: "button", class: "project-manage", onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try { await reload(); } finally { button.disabled = false; }
      } }, "刷新发布状态")),
    el("div", { class: "library-filters" },
      el("label", {}, el("span", {}, "项目"), search),
      selectControl("创建日期", "date", [["all", "全部日期"], ["today", "今天创建"], ["yesterday", "昨天创建"], ["week", "最近 7 天"], ["unknown", "日期待确认"]]),
      selectControl("制作进度", "production", [["all", "全部进度"], ["draft", "草案"], ["producing", "制作中"], ["review", "有成片 · 待审核"], ["failed", "制作需处理"], ["attention", "制作进度待核实"]]),
      selectControl("发布状态", "publication", [["all", "全部状态"], ["none", "暂无发布记录"], ["pending", "待发布"], ["partial", "部分已发布"], ["published", "目标平台已发布"], ["history", "历史发布待核对"], ["attention", "发布需处理"]]),
      selectControl("排序", "sort", [["created", "创建时间 · 最新在前"], ["updated", "最近更新"]])),
    el("p", { class: "library-filter-note", id: "libraryFilterCount", "aria-live": "polite" }, "日期按北京时间显示；发布记录只用于登记和核对。"));
  document.getElementById("grid").before(toolbar);
}
export function renderProjectList(projects, card) {
  const visible = projects.filter(p => {
    const index = p.library || {}, created = day(index.created_at);
    if (filters.search && !`${p.title} ${p.project_id}`.toLowerCase().includes(filters.search)) return false;
    if (filters.date === "today" && created !== day(Date.now())) return false;
    if (filters.date === "yesterday" && created !== day(Date.now() - 86400000)) return false;
    if (filters.date === "week" && (!created || created < day(Date.now() - 6 * 86400000) || created > day(Date.now()))) return false;
    if (filters.date === "unknown" && created) return false;
    return (filters.production === "all" || filters.production === index.production?.status)
      && (filters.publication === "all" || filters.publication === index.publication?.status);
  }).sort((a, b) => {
    const key = filters.sort === "created" ? "created_at" : "updated_at";
    return (Date.parse(b.library?.[key]) || 0) - (Date.parse(a.library?.[key]) || 0) || a.project_id.localeCompare(b.project_id);
  });
  const grid = document.getElementById("grid");
  grid.replaceChildren();
  let lastGroup;
  for (const project of visible) {
    const key = filters.sort === "created" ? "created_at" : "updated_at";
    const group = relativeDay(project.library?.[key]);
    if (group !== lastGroup) {
      grid.append(el("h2", { class: "library-date-group" }, `${group} · ${filters.sort === "created" ? "创建" : "更新"}`));
      lastGroup = group;
    }
    grid.append(card(project));
  }
  if (!visible.length && projects.length) grid.append(el("p", { class: "hint" }, "没有符合当前筛选条件的项目。"));
  document.getElementById("libraryFilterCount").textContent = `显示 ${visible.length} / ${projects.length} 个项目 · 日期按北京时间显示 · 发布状态来自记录，点击可核对版本和来源`;
}
async function openIndex(project) {
  activeProject = project;
  modal.replaceChildren(el("p", {}, "正在读取项目记录…"));
  modal.showModal();
  try { detail = await getJSON(`/api/projects/${encodeURIComponent(project.project_id)}/library-index`); drawDialog(); }
  catch (_) { modal.replaceChildren(el("p", {}, "项目记录暂时无法读取，请稍后重试。"), el("button", { type: "button", onclick: () => modal.close() }, "关闭")); }
}
function inputField(label, type = "text", value = "") {
  const input = el("input", { type, "aria-label": label }); input.value = value;
  return { input, node: el("label", {}, el("span", {}, label), input) };
}
function localTime(value) {
  return day(value) ? `${day(value)}T${clockFormat.format(new Date(value))}` : "";
}
function toISO(value) { return value ? `${value}:00+08:00` : ""; }
function versionSelect(label, selected, auto = false) {
  const input = el("select", { "aria-label": label },
    el("option", { value: "" }, auto ? "自动使用最新成片" : "请选择成片版本"),
    detail.versions.map(v => el("option", { value: v.id }, `${v.label} · ${dateLabel(v.mtime * 1000)}`)));
  input.value = selected || "";
  return { input, node: el("label", {}, el("span", {}, label), input) };
}
async function save(payload, message) {
  if (saving) return;
  saving = true;
  modal.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = true; });
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(activeProject.project_id)}/library-index`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, revision: detail.revision }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "保存失败");
    detail = result; drawDialog(); await reload();
  } catch (error) { message.textContent = error.message; }
  finally { saving = false; modal.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = false; }); }
}
function drawDialog(edit = null) {
  const error = el("p", { class: "library-index-error", role: "alert" });
  const targetBoxes = Object.entries(detail.platform_labels).map(([id, name]) => {
    const input = el("input", { type: "checkbox", value: id, "aria-label": `目标平台 ${name}` });
    input.checked = detail.targets.includes(id);
    return { id, input, node: el("label", { class: "library-target" }, input, name) };
  });
  const version = versionSelect("当前管理的成片", detail.selected_version_id, true);
  const created = inputField("创建时间（北京时间，可补录）", "datetime-local", localTime(detail.created_at));
  const settings = el("form", { class: "library-index-settings", onsubmit: (event) => {
    event.preventDefault(); save({ kind: "settings", targets: targetBoxes.filter(t => t.input.checked).map(t => t.id),
      version_id: version.input.value, created_at: created.input.value !== localTime(detail.created_at) ? toISO(created.input.value) : "" }, error);
  } }, el("h3", {}, "发布目标与日期"), el("div", { class: "library-targets" }, targetBoxes.map(t => t.node)),
    el("div", { class: "library-index-fields" }, version.node, created.node),
    el("button", { type: "submit", class: "primary-action" }, "保存目标与日期"));
  const platform = el("select", { "aria-label": "发布平台" }, Object.entries(detail.platform_labels).map(([id, name]) => el("option", { value: id }, name)));
  platform.value = edit?.platform || "douyin";
  const status = el("select", { "aria-label": "发布状态" }, Object.entries(detail.status_labels).map(([id, name]) => el("option", { value: id }, name)));
  status.value = edit?.status || "pending";
  const account = inputField("发布账号名称或编号", "text", edit?.account || ""); account.input.required = true;
  const published = inputField("实际发布时间（北京时间）", "datetime-local", localTime(edit?.published_at));
  published.input.required = status.value === "published";
  status.addEventListener("change", () => { published.input.required = status.value === "published"; });
  const url = inputField("作品或后台链接（可选）", "url", edit?.url || "");
  const note = inputField("核对说明（可选）", "text", edit?.note || ""); note.input.maxLength = 1000;
  const recordVersion = versionSelect("本条记录对应的成片", edit?.version_id || ""); recordVersion.input.required = true;
  const add = el("details", { class: "library-manual-record", open: edit ? "" : null }, el("summary", {}, edit?.source === "manual" ? "修正人工记录" : "补录 / 核对发布记录"),
    el("p", {}, "仅登记已发生的情况；请选择实际发布的成片版本。历史路径相同不能证明文件内容相同。"),
    el("form", { onsubmit: (event) => {
      event.preventDefault(); save({ kind: "record", id: edit?.source === "manual" ? edit.id : undefined,
        platform: platform.value, account: account.input.value, status: status.value, version_id: recordVersion.input.value,
        published_at: toISO(published.input.value), url: url.input.value, note: note.input.value }, error);
    } }, el("div", { class: "library-index-fields" },
      el("label", {}, el("span", {}, "发布平台"), platform), account.node, recordVersion.node,
      el("label", {}, el("span", {}, "发布状态"), status), published.node, url.node, note.node),
      el("button", { type: "submit", class: "primary-action", disabled: !detail.versions.length ? "" : null }, "保存人工记录")));
  const rows = detail.records.map(record => el("article", { class: "library-record" },
    el("strong", {}, `${detail.platform_labels[record.platform] || record.platform} · ${detail.status_labels[record.status]} · 账号 ${record.account}`),
    el("p", {}, `成片：${record.version_path} · ${record.version_verified ? "版本已确认" : "历史版本待核对"}`),
    el("p", {}, `来源：${record.source === "manual" ? "人工确认" : `发布系统任务 #${record.task_id}`} · ${record.published_at ? "发布时间：" + dateLabel(record.published_at) : "发布时间未记录"}`),
    record.note ? el("p", {}, record.note) : null,
    record.url ? el("a", { href: record.url, target: "_blank", rel: "noopener noreferrer" }, "打开作品 / 后台") : null,
    el("button", { type: "button", class: "project-manage", onclick: () => drawDialog(record) }, record.source === "manual" ? "修正记录" : "核对并补录")));
  modal.replaceChildren(el("div", { class: "library-index-head" },
    el("h2", { id: "libraryIndexTitle" }, `${activeProject.title || activeProject.project_id} · 发布记录`),
    el("button", { type: "button", class: "project-manage", onclick: () => modal.close() }, "关闭")),
    el("p", {}, detail.sync.status === "connected" ? `发布系统只读同步：${dateLabel(detail.sync.checked_at)}` : `${detail.sync.message} ${detail.sync.checked_at ? "上次同步：" + dateLabel(detail.sync.checked_at) : ""}`),
    el("p", {}, "目标平台完成比例只统计当前成片的已确认记录；更换成片后，旧发布记录继续保留。"),
    error, settings, add, el("h3", {}, "发布历史"), ...(rows.length ? rows : [el("p", {}, "暂无发布记录，可补录人工确认结果。")])) ;
}
