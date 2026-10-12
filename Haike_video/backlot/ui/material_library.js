"use strict";
const $ = id => document.getElementById(id);
let currentMedia = null;
async function api(path, body) {
  const response = await fetch(`/api/material-library/${path}`, body === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const value = await response.json(); if (!response.ok) throw new Error(value.detail || "请求失败"); return value;
}
function bind(id, action) { $(id).onclick = async () => { $(id).disabled = true; $("message").textContent="处理中…"; try { await action(); $("message").textContent="已完成"; } catch(error) { $("message").textContent=error.message; } finally { $(id).disabled=false; } }; }
function node(tag, value) { const item=document.createElement(tag); if(value!==undefined) item.textContent=value; return item; }
function latestClips(clips) {
  const seen=new Set();return [...clips].sort((a,b)=>b.updated_at.localeCompare(a.updated_at)).filter(c=>{const key=`${c.media_id}:${c.start}:${c.end}`;if(seen.has(key))return false;seen.add(key);return true;});
}
function showResult(result) {
  $("selection").textContent=JSON.stringify(result,null,2);
  if(result.status === "ready") $("selection-status").textContent=`已选好三个镜头，共9秒；相关画面${result.related_seconds}秒。等级：${result.clips.map(c=>c.grade).join("、")}。`;
  else if(result.status === "needs_material") $("selection-status").textContent=`还需要素材确认或补采：${result.gaps.map(g=>g.reason).join("；")}。`;
  else if(result.status === "not_required") $("selection-status").textContent="已有素材满足需求，无需补采。";
  else if(result.status === "budget_exhausted") $("selection-status").textContent=result.reason;
  else if(result.status === "requested") $("selection-status").textContent=`第${result.round}轮补采需求已保存，搜索词见详细记录。`;
  else $("selection-status").textContent=`找到${result.available_count || 0}个已确认候选；按直接实体、同系列、同品牌、行业补充排序。`;
}
function showTask(task) {
  $("evidence").replaceChildren(node("p",task.instruction));
  for(const window of task.windows) for(const sheet of window.sheets) { const img=node("img");img.alt=`${window.id} ${sheet.kind} 区间证据`;img.src=`/api/material-library/evidence/${encodeURIComponent(task.id)}/images/${encodeURIComponent(sheet.file)}`;$("evidence").append(img); }
  $("submission").value=JSON.stringify(task.review_result || task.submission_template,null,2);
  $("submission").readOnly=Boolean(task.completed);$("submit").disabled=Boolean(task.completed);
  if(task.completed) $("evidence").prepend(node("p","已保存的证据。修改区间或裁切后生成新任务，原确认保留。"));
}
async function openClip(clip) {
  $("video").currentTime=clip.start;$("start").value=clip.start;$("end").value=clip.end;
  if(clip.metadata.crop) for(const k of ["x","y","w","h"]) $(k).value=clip.metadata.crop[k];
  if(clip.task_id) { const task=await api(`evidence/${encodeURIComponent(clip.task_id)}`);showTask(task);$("model").value=task.model;$("review-panel").open=true; }
}
async function refresh() { const s=await api("status"); $("stats").textContent=`${s.media} 条素材 · ${s.locations} 个位置 · ${s.clips} 个区间版本 · ${s.confirmed} 个已确认`; }
async function openMedia(id, start=0) {
  const media=await api(`media/${encodeURIComponent(id)}`); currentMedia=id; $("detail").hidden=false; $("title").textContent=media.title;
  $("video").src=`/api/material-library/media/${encodeURIComponent(id)}/video#t=${start}`; $("start").value=start; $("end").value=Math.min(start+3,media.duration);
  $("clips").replaceChildren();$("evidence").replaceChildren();$("submission").value="";$("submission").readOnly=false;$("submit").disabled=false;
  for(const clip of latestClips(media.clips)) { const status=clip.review_status === "confirmed" ? (clip.metadata.usable ? "可用" : "不可用") : "待确认";const b=node("button",`${clip.start.toFixed(2)}–${clip.end.toFixed(2)}秒 · ${clip.observation} · ${status}`); b.onclick=()=>openClip(clip).catch(e=>$("message").textContent=e.message);$("clips").append(b); }
}
async function search() {
  const data=await api(`search?query=${encodeURIComponent($("query").value)}`); $("results").replaceChildren();
  const table=node("table"); const head=node("tr"); for(const value of ["素材/片段","秒段/时长","状态"]) head.append(node("th",value)); table.append(head);
  for(const item of [...latestClips(data.clips),...data.media]) { const row=node("tr"), cell=node("td"), button=node("button",item.observation || item.title); button.onclick=()=>openMedia(item.media_id || item.id,item.start || 0).catch(e=>$("message").textContent=e.message); cell.append(button);const status=item.review_status === "confirmed" ? (item.metadata.usable ? "已确认可用" : "不可用") : item.review_status ? "待确认" : `${item.clip_count}个索引版本`;row.append(cell,node("td",item.start === undefined ? `${item.duration.toFixed(1)}秒` : `${item.start.toFixed(2)}–${item.end.toFixed(2)}秒`),node("td",status)); table.append(row); } $("results").append(table);
}
const planValue=()=>JSON.parse($("plan-json").value);
$("close-detail").onclick=()=>{ $("video").pause();$("detail").hidden=true; };
bind("import",async()=>{await api("import",{path:$("path").value,kind:$("kind").value});await refresh();await search();});
bind("sync",async()=>{await api("sync-published",{});await refresh();await search();});
bind("search",search);
bind("prepare",async()=>{
  if(!currentMedia) throw new Error("请先打开素材");
  const crop=Object.fromEntries(["x","y","w","h"].map(k=>[k,Number($(k).value)]));
  const task=await api("evidence",{model:$("model").value,windows:[{media_id:currentMedia,start:Number($("start").value),end:Number($("end").value),crop}]});
  showTask(task);
});
bind("submit",async()=>{await api("evidence/submit",JSON.parse($("submission").value));await refresh();await openMedia(currentMedia,Number($("start").value));});
bind("plan",async()=>{$("plan-json").value=JSON.stringify(await api("plan",{topic:$("topic").value}),null,2);});
bind("candidates",async()=>{const result=await api("candidates",planValue()); $("candidate-list").replaceChildren();for(const c of result.candidates){const b=node("button",`${c.grade}级 · ${c.start.toFixed(2)}秒 · 质量${c.quality} · ${c.observation}`);b.onclick=()=>openMedia(c.media_id,c.start).catch(e=>$("message").textContent=e.message);$("candidate-list").append(b);} showResult(result);});
bind("select",async()=>{showResult(await api("select",{plan:planValue()}));});
bind("acquire",async()=>{showResult(await api("acquisition",planValue()));});
bind("history",async()=>{$("history-content").textContent=JSON.stringify(await api("selections"),null,2);});
refresh().then(search).catch(e=>$("message").textContent=e.message);
api("plan",{topic:$("topic").value}).then(p=>$("plan-json").value=JSON.stringify(p,null,2)).catch(e=>$("message").textContent=e.message);
