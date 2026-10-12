import { addToRemix } from "./published_remix.js";
const $ = (id) => document.getElementById(id);
const state = { videoId: null, eventId: null, selected: null, tags: {}, playUntil: null,
  playFrom: 0, range: null, openSequence: 0, searchSequence: 0, cases: [], saving: false };
const sourceLabels = { filename: "文件名", description: "作品摘要", transcript: "原声转写", candidate_tag: "标签候选",
  confirmed_tag: "人工确认标签", event_summary: "事件摘要" };
const statusLabels = { candidate: "待确认", confirmed: "人工确认", rejected: "已驳回" };
const transcriptLabels = { pending: "待转写", running: "转写中", completed: "已转写", failed: "转写失败" };
const eventSources = { manual: "人工标注", transcript_cue: "台词线索", interaction_import: "互动分析候选",
  visual_overview: "画面采样候选", joint_signals: "声画联合线索" };

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || data.error || `请求失败 ${response.status}`);
  return data;
}

const time = (value) => {
  const tenths = Math.round(Math.max(0, Number(value || 0)) * 10);
  return `${Math.floor(tenths / 600)}:${((tenths % 600) / 10).toFixed(1).padStart(4, "0")}`;
};

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function seek(seconds, play = false) {
  const player = $("player");
  const at = Number(seconds || 0);
  const sequence = state.openSequence;
  const apply = () => { if (sequence !== state.openSequence) return; player.currentTime = at; if (play) player.play().catch(() => {}); };
  if (player.readyState >= 1) apply();
  else player.addEventListener("loadedmetadata", apply, { once: true });
}

$("player").addEventListener("timeupdate", () => {
  if (state.playUntil != null && $("player").currentTime >= state.playUntil) {
    if ($("loop-range").checked) seek(state.playFrom, true);
    else { $("player").pause(); state.playUntil = null; }
  }
});

function playRange(start, end) {
  state.playFrom = Number(start);
  state.playUntil = Number(end);
  $("play-range").textContent = `当前片段 ${time(start)}–${time(end)}`;
  seek(start, true);
}

$("player").addEventListener("ended", () => {
  if ($("loop-range").checked && state.range) playRange(state.playFrom, state.playUntil ?? state.range.end);
});

async function openVideo(videoId, start = 0, end = null) {
  if (state.saving) return;
  const sequence = ++state.openSequence;
  const detail = await request(`/api/published-clips/videos/${encodeURIComponent(videoId)}`);
  if (sequence !== state.openSequence) return;
  state.selected = detail;
  state.videoId = videoId;
  state.eventId = null;
  $("video-title").textContent = detail.name;
  $("video-state").textContent = `时长 ${time(detail.duration_seconds)} · ${detail.width}×${detail.height} · ${transcriptLabels[detail.transcript_status] || detail.transcript_status} · ${detail.candidate_count} 个待确认片段 · ${detail.confirmed_count} 个已确认片段`;
  $("description-form").hidden = false;
  $("video-description").value = detail.description || "";
  $("description-message").textContent = "";
  const player = $("player");
  player.hidden = false;
  const address = `/api/published-clips/videos/${encodeURIComponent(videoId)}/media`;
  if (player.getAttribute("src") !== address) player.src = address;
  state.range = { start, end: end ?? detail.duration_seconds };
  playRange(start, end ?? detail.duration_seconds);
  $("play-range").textContent = end == null ? "" : `当前片段 ${time(start)}–${time(end)}；可手动播放前后文。`;
  $("new-event").hidden = false;
  $("review-controls").hidden = false;
  $("analyze-video").disabled = false;
  $("event-form").hidden = true;
  renderEvents(detail.events);
  renderTranscript(detail.transcript);
  showTruth();
  loadAnalysis(videoId, sequence);
}

function renderEvents(events) {
  const host = $("events");
  host.replaceChildren();
  if (!events.length) { host.append(node("p", "muted", "还没有事件标记。可播放原片并手动添加。")); return; }
  for (const event of events) {
    const row = node("div", "event");
    row.append(node("strong", "", `${time(event.start_seconds)}–${time(event.end_seconds)}  ${event.summary}`));
    row.append(node("p", "", `${event.tags.map(t => state.tags[t] || t).join("、")} · ${statusLabels[event.review_status] || event.review_status} · ${eventSources[event.source_kind] || event.source_kind}`));
    if (event.evidence?.review_note) row.append(node("p", "muted", `核对依据：${event.evidence.review_note}`));
    const annotation = event.annotation || {};
    if (annotation.action || annotation.reaction) row.append(node("p", "evidence", `${state.actors?.[annotation.actor] || "待辨认"} · ${annotation.action || "动作待补充"} · 回应：${annotation.reaction || "待补充"}`));
    if (event.source_kind === "joint_signals") row.append(node("p", "evidence", `复核优先级 ${event.evidence.priority}（不是准确率）。${event.evidence.limitation}`));
    const play = node("button", "secondary", "播放");
    play.type = "button";
    play.addEventListener("click", () => { showForm(event); playRange(event.start_seconds, event.end_seconds); });
    const edit = node("button", "secondary", "核对 / 修改");
    edit.type = "button";
    edit.addEventListener("click", () => showForm(event));
    const add = node("button", "secondary", "加入选材篮"); add.type = "button";
    add.addEventListener("click", () => addToRemix({ video_id: state.videoId, source_name: state.selected.name,
      start_seconds: event.start_seconds, end_seconds: event.end_seconds, event_id: event.id, source_review_status: event.review_status }));
    row.append(play, edit, add);
    host.append(row);
  }
}

function renderTranscript(spans) {
  const host = $("transcript");
  host.replaceChildren();
  if (!spans.length) { host.append(node("p", "muted", "没有可用的转写。文件名和人工事件仍可检索。")); return; }
  for (const span of spans) {
    const row = node("div", "transcript-row");
    row.append(node("time", "", `${time(span.start_seconds)}–${time(span.end_seconds)}`));
    row.append(node("span", "", span.text));
    row.addEventListener("click", () => { state.range = { start: span.start_seconds, end: span.end_seconds }; playRange(span.start_seconds, span.end_seconds); });
    host.append(row);
  }
}

function showForm(event = null) {
  if (state.saving) return;
  state.eventId = event?.id || null;
  $("form-title").textContent = event ? "核对 / 修改事件" : "新增事件";
  $("start").value = event?.start_seconds ?? Math.floor($("player").currentTime || 0);
  $("end").value = event?.end_seconds ?? Math.min(state.selected?.duration_seconds || 0, Number($("start").value) + 5);
  $("peak").value = event?.peak_seconds ?? "";
  const annotation = event?.annotation || {};
  $("event-actor").value = annotation.actor || "unknown";
  $("event-action").value = annotation.action || "";
  $("event-reaction").value = annotation.reaction || "";
  $("context-start").value = annotation.context_start ?? Math.max(0, Number($("start").value) - 3);
  $("context-end").value = annotation.context_end ?? Math.min(state.selected.duration_seconds, Number($("end").value) + 3);
  for (const channel of ["audio", "video", "transcript"]) $("checked-" + channel).checked = (annotation.channels || []).includes(channel);
  for (const field of ["start", "end"]) {
    $(field + "-slider").max = state.selected.duration_seconds;
    $(field + "-slider").value = $(field).value;
  }
  state.range = { start: Number($("start").value), end: Number($("end").value) };
  $("event-summary").value = event?.summary || "";
  $("review-note").value = event?.evidence?.review_note || "";
  $("review-status").value = event?.review_status || "confirmed";
  document.querySelectorAll("#tag-options input").forEach(input => {
    input.checked = !!event?.tags.includes(input.value);
  });
  $("form-message").textContent = "";
  $("event-form").hidden = false;
  $("event-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function search() {
  const sequence = ++state.searchSequence;
  const params = new URLSearchParams({ query: $("query").value.trim(), tag: $("tag").value,
    actor: $("actor-filter").value, reaction: $("reaction-filter").value.trim(), review_status: $("status-filter").value,
    confirmed_only: String($("confirmed").checked), limit: "200" });
  $("search-message").textContent = "正在搜索…";
  try {
    const results = await request(`/api/published-clips/search?${params}`);
    if (sequence !== state.searchSequence) return;
    $("count").textContent = `${results.length} 条`;
    const host = $("results");
    host.replaceChildren();
    for (const item of results) {
      const card = node("button", "result");
      card.type = "button";
      card.append(node("strong", "", item.name));
      card.append(node("span", "", `${time(item.start_seconds)}–${time(item.end_seconds)} · ${sourceLabels[item.match_source] || item.match_source}${item.review_status === "candidate" ? " · 待确认" : ""}${item.transcript_status ? " · " + (transcriptLabels[item.transcript_status] || item.transcript_status) + " · " + item.candidate_count + " 待确认 / " + item.confirmed_count + " 已确认" : ""}`));
      card.append(node("p", "", item.summary));
      card.addEventListener("click", async () => {
        try { await openVideo(item.video_id, item.start_seconds, item.end_seconds); }
        catch (error) { $("search-message").textContent = error.message; }
      });
      host.append(card);
    }
    if (!results.length) host.append(node("p", "muted", "没有匹配片段。可清空条件查看全部作品。"));
    $("search-message").textContent = "";
  } catch (error) { if (sequence === state.searchSequence) $("search-message").textContent = error.message; }
}

async function refreshStatus() {
  const status = await request("/api/published-clips/status");
  state.tags = status.tags || {};
  state.actors = status.actors || {};
  $("stats").textContent = `${status.videos} 条作品 · ${status.transcribed} 条已转写 · ${status.candidates} 个待确认事件 · ${status.confirmed} 个已确认事件`;
  return status;
}

async function init() {
  try {
    const status = await refreshStatus();
    for (const [value, label] of Object.entries(state.actors)) {
      for (const id of ["actor-filter", "event-actor"]) {
        const option = node("option", "", label); option.value = value; $(id).append(option);
      }
    }
    for (const [value, label] of Object.entries(state.tags)) {
      const option = node("option", "", label);
      option.value = value;
      $("tag").append(option);
      const wrap = node("label", "");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = value;
      wrap.append(input, document.createTextNode(label));
      $("tag-options").append(wrap);
    }
    if (!status.source_root) $("search-message").textContent = "尚未配置成片目录；请先运行本地索引 CLI 的 scan --source。";
    await search();
    await refreshBenchmark();
  } catch (error) { $("search-message").textContent = error.message; }
}

$("search").addEventListener("click", search);
$("query").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); search(); } });
$("tag").addEventListener("change", search);
$("confirmed").addEventListener("change", search);
$("actor-filter").addEventListener("change", search);
$("status-filter").addEventListener("change", search);
$("reaction-filter").addEventListener("keydown", event => { if (event.key === "Enter") search(); });
$("new-event").addEventListener("click", () => showForm());
$("description-form").addEventListener("submit", async event => {
  event.preventDefault();
  const videoId = state.videoId;
  try {
    await request(`/api/published-clips/videos/${encodeURIComponent(videoId)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: $("video-description").value.trim() }) });
    if (state.videoId === videoId) $("description-message").textContent = "已保存";
    await search();
  } catch (error) { $("description-message").textContent = error.message; }
});
$("cancel-event").addEventListener("click", () => { $("event-form").hidden = true; });
$("event-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (state.saving) return;
  const next = event.submitter?.id === "save-next";
  const savedId = state.eventId, videoId = state.videoId;
  const tags = [...document.querySelectorAll("#tag-options input:checked")].map(input => input.value);
  const payload = { start_seconds: Number($("start").value), end_seconds: Number($("end").value),
    peak_seconds: $("peak").value === "" ? null : Number($("peak").value),
    summary: $("event-summary").value.trim(), review_note: $("review-note").value.trim(),
    tags, review_status: $("review-status").value,
    annotation: { actor: $("event-actor").value, action: $("event-action").value.trim(), reaction: $("event-reaction").value.trim(),
      context_start: Number($("context-start").value), context_end: Number($("context-end").value),
      channels: ["audio", "video", "transcript"].filter(c => $("checked-" + c).checked) } };
  const base = `/api/published-clips/videos/${encodeURIComponent(state.videoId)}/events`;
  try {
    state.saving = true;
    await request(state.eventId ? `${base}/${state.eventId}` : base, { method: state.eventId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    state.saving = false;
    await openVideo(state.videoId, payload.start_seconds, payload.end_seconds);
    if (next && state.videoId === videoId) navigateCandidate(1, savedId);
    await search();
    await refreshStatus();
  } catch (error) { $("form-message").textContent = error.message; }
  finally { state.saving = false; }
});

function navigateCandidate(direction, fromId = state.eventId) {
  const events = state.selected?.events || [];
  const current = events.findIndex(e => e.id === fromId);
  const ordered = direction > 0 ? [...events.slice(current + 1), ...events.slice(0, current)] : [...events.slice(0, current)].reverse();
  const next = ordered.find(e => e.review_status === "candidate" && e.id !== fromId);
  if (!next) { $("play-range").textContent = "本片没有其他待核对候选，可切换下一条作品。"; return; }
  showForm(next); playRange(next.start_seconds, next.end_seconds);
}

function syncBoundary(field, value) {
  const duration = state.selected.duration_seconds;
  let start = Number($("start").value), end = Number($("end").value);
  if (field === "start") start = Math.max(0, Math.min(value, end - .1));
  else end = Math.min(duration, Math.max(value, start + .1));
  $("start").value = Math.round(start * 1000) / 1000; $("end").value = Math.round(end * 1000) / 1000;
  $("start-slider").value = start; $("end-slider").value = end;
  $("context-start").value = Math.min(Number($("context-start").value), start);
  $("context-end").value = Math.max(Number($("context-end").value), end);
  if ($("peak").value !== "") $("peak").value = Math.max(start, Math.min(end, Number($("peak").value)));
  state.range = { start, end }; state.playUntil = null;
  seek(field === "start" ? start : end);
}

for (const field of ["start", "end"]) {
  $(field + "-slider").addEventListener("input", () => syncBoundary(field, Number($(field + "-slider").value)));
  $(field).addEventListener("change", () => syncBoundary(field, Number($(field).value)));
}
$("expand-context").addEventListener("click", () => {
  $("context-start").value = Math.max(0, Number($("start").value) - 3);
  $("context-end").value = Math.min(state.selected.duration_seconds, Number($("end").value) + 3);
});
$("play-event").addEventListener("click", () => { if (state.range) playRange(state.range.start, state.range.end); });
$("play-context").addEventListener("click", () => {
  if (!state.range) return;
  const start = $("event-form").hidden ? Math.max(0, state.range.start - 3) : Number($("context-start").value);
  const end = $("event-form").hidden ? Math.min(state.selected.duration_seconds, state.range.end + 3) : Number($("context-end").value);
  if (end > start) playRange(start, end);
});
$("next-event").addEventListener("click", () => navigateCandidate(1));
$("previous-event").addEventListener("click", () => navigateCandidate(-1));
document.addEventListener("keydown", event => {
  if (!state.selected || event.ctrlKey || event.altKey || event.metaKey || state.saving ||
      event.target.closest("input,textarea,select,button,[contenteditable=true]")) return;
  const player = $("player");
  if (event.code === "Space") { event.preventDefault(); player.paused ? player.play().catch(() => {}) : player.pause(); }
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault(); state.playUntil = null;
    seek(Math.max(0, Math.min(state.selected.duration_seconds, player.currentTime + (event.key === "ArrowLeft" ? -.5 : .5))));
  }
  if (!["i", "o", "p"].includes(event.key.toLowerCase())) return;
  event.preventDefault();
  if ($("event-form").hidden) showForm();
  if (event.key.toLowerCase() === "p") $("peak").value = Math.max(Number($("start").value), Math.min(Number($("end").value), Math.round(player.currentTime * 10) / 10));
  else syncBoundary(event.key.toLowerCase() === "i" ? "start" : "end", Math.round(player.currentTime * 10) / 10);
});

async function loadAnalysis(videoId, sequence) {
  $("signal-chart").replaceChildren(); $("signal-caption").textContent = "";
  $("analysis-message").textContent = "读取分析状态…";
  try {
    const data = await request(`/api/published-clips/videos/${videoId}/analysis`);
    if (sequence !== state.openSequence) return;
    $("analysis-message").textContent = ({ pending: "尚未分析声画", running: "分析进行中，可稍后重新打开本片", failed: "分析失败：" + data.error, completed: "声画线索已就绪" })[data.status];
    if (!data.result) return;
    const result = data.result;
    $("signal-caption").textContent = `绿色：声音强度；橙色：画面变化。半秒采样，处理 ${result.elapsed_seconds} 秒。${result.limitation}`;
    for (const [field, color] of [["audio_db", "#176957"], ["motion", "#ce7a24"]]) {
      const values = result.points.filter(p => p[field] != null);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      path.setAttribute("points", values.map(p => `${p.time / result.duration_seconds * 800},${95 - (field === "audio_db" ? Math.max(0, (p[field] + 60) / 60) : Math.min(1, p[field] / .25)) * 90}`).join(" "));
      path.setAttribute("fill", "none"); path.setAttribute("stroke", color); path.setAttribute("stroke-width", "2");
      $("signal-chart").append(path);
    }
  } catch (error) { if (sequence === state.openSequence) $("analysis-message").textContent = error.message; }
}

$("analyze-video").addEventListener("click", async () => {
  const videoId = state.videoId, sequence = state.openSequence;
  $("analyze-video").disabled = true; $("analysis-message").textContent = "正在本地分析声音与连续采样画面…";
  try {
    await request(`/api/published-clips/videos/${videoId}/analysis`, { method: "POST" });
    if (sequence !== state.openSequence) return;
    const detail = await request(`/api/published-clips/videos/${videoId}`);
    if (sequence !== state.openSequence) return;
    state.selected = detail; renderEvents(detail.events);
    await loadAnalysis(videoId, sequence); await refreshStatus();
  } catch (error) { if (sequence === state.openSequence) $("analysis-message").textContent = error.message; }
  finally { if (sequence === state.openSequence) $("analyze-video").disabled = false; }
});

async function refreshBenchmark() {
  const data = await request("/api/published-clips/benchmark");
  state.cases = data.cases;
  const e = data.evaluation, pct = v => v == null ? "未评估" : `${Math.round(v * 100)}%`;
  $("benchmark-metrics").textContent = `完整真值 ${e.reviewed}/${e.total} · 精确率 ${pct(e.precision)} · 召回率 ${pct(e.recall)} · 误报 ${e.reviewed ? e.false_positive : "未评估"} / 漏检 ${e.reviewed ? e.false_negative : "未评估"} · 边界平均误差 ${e.mean_boundary_error_seconds == null ? "未评估" : e.mean_boundary_error_seconds.toFixed(2) + "秒"}。${e.quality_gate}；当前分析只提供线索。`;
  $("benchmark-cases").replaceChildren();
  for (const c of data.cases) {
    const button = node("button", "secondary", `${c.status === "reviewed" ? "已完整复核" : "待独立复核"} · ${c.stratum} · ${c.name}`);
    button.type = "button";
    button.addEventListener("click", () => openVideo(c.video_id).catch(error => { $("search-message").textContent = error.message; }));
    $("benchmark-cases").append(button);
  }
}

function showTruth() {
  const item = state.cases.find(c => c.video_id === state.videoId);
  $("truth-form").hidden = !item;
  if (!item) return;
  $("truth-events").replaceChildren();
  for (const truth of item.truth) addTruthRow(truth);
  $("truth-note").value = item.note || "";
  $("truth-audio").checked = item.channels.includes("audio"); $("truth-video").checked = item.channels.includes("video");
  $("truth-complete").checked = item.status === "reviewed";
  $("truth-message").textContent = "";
}

function addTruthRow(truth = null) {
  const row = node("div", "truth-row");
  for (const [field, label] of [["start_seconds", "真值开始秒数"], ["end_seconds", "真值结束秒数"]]) {
    const wrap = node("label", "", label), input = document.createElement("input");
    input.type = "number"; input.min = "0"; input.step = "0.001"; input.required = true;
    input.dataset.field = field;
    input.value = truth?.[field] ?? (field === "start_seconds" ? Math.floor($("player").currentTime) : Math.min(state.selected.duration_seconds, Math.floor($("player").currentTime) + 3));
    wrap.append(input); row.append(wrap);
  }
  const tags = node("fieldset", "tag-options"); tags.append(node("legend", "", "真实事件标签"));
  for (const [key, label] of Object.entries(state.tags)) {
    if (["activity_candidate", "emotion_candidate"].includes(key)) continue;
    const wrap = node("label", ""), input = document.createElement("input"); input.type = "checkbox"; input.value = key;
    input.checked = !!truth?.tags.includes(key); wrap.append(input, document.createTextNode(label)); tags.append(wrap);
  }
  const remove = node("button", "secondary", "移除这条标注"); remove.type = "button"; remove.addEventListener("click", () => row.remove());
  row.append(tags, remove); $("truth-events").append(row);
}
$("add-truth").addEventListener("click", () => addTruthRow());

$("truth-form").addEventListener("submit", async event => {
  event.preventDefault();
  const videoId = state.videoId;
  try {
    const truth = [...$("truth-events").querySelectorAll(".truth-row")].map(row => {
      return { start_seconds: Number(row.querySelector('[data-field="start_seconds"]').value),
        end_seconds: Number(row.querySelector('[data-field="end_seconds"]').value),
        tags: [...row.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value) };
    });
    await request(`/api/published-clips/benchmark/${videoId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      truth, note: $("truth-note").value, status: $("truth-complete").checked ? "reviewed" : "pending",
      channels: ["audio", "video"].filter(c => $("truth-" + c).checked) }) });
    if (videoId === state.videoId) $("truth-message").textContent = "已保存；只有完整复核才计入评估。";
    await refreshBenchmark();
  } catch (error) { if (videoId === state.videoId) $("truth-message").textContent = error.message; }
});

$("add-current-remix").addEventListener("click", () => {
  if (!state.selected || !state.range) return;
  addToRemix({ video_id: state.videoId, source_name: state.selected.name, start_seconds: state.range.start,
    end_seconds: state.range.end, source_review_status: "unreviewed" });
});
window.addEventListener("remix-source-preview", event => {
  const row = event.detail;
  openVideo(row.video_id, row.start_seconds, row.end_seconds).catch(error => { $("search-message").textContent = error.message; });
});
init();
