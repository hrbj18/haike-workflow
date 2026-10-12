/* Material-led editor. Form values update a local draft; polling never overwrites edits. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let state = null, source = null, quote = null, presenterQuote = null, presenterGeneration = null;
  const base = () => `/api/material-commentaries/${state.draft.id}`;
  async function api(url, method="GET", payload) {
    const r = await fetch(url, {method, headers:{"Content-Type":"application/json"}, ...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
    const data = await r.json();
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请求未完成，请检查填写内容");
    return data;
  }
  function action(id, handler) { $(id).onclick = async () => { const button=$(id); button.disabled=true; try { await handler(); } catch(e) { $("message").textContent=e.message; } finally { button.disabled=false; } }; }
  function msg(value) { $("message").textContent=value; }
  const evidenceName = (e) => `${e.title} · ${e.start.toFixed(2)}—${e.end.toFixed(2)} 秒`;
  async function projects(selected) {
    const rows=await api("/api/material-commentaries");
    $("projects").innerHTML='<option value="">选择已有项目</option>'+rows.map(r=>`<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("");
    if(selected) $("projects").value=selected;
  }
  async function open(id) {
    state=await api(`/api/material-commentaries/${encodeURIComponent(id)}`);
    state.layouts=[];
    if(state.draft.payload.segments.some(s=>s.presenter_layout)) {
      try {state.layouts=(await api(base()+"/layout/plan")).layouts;} catch(e) {state.layoutWarning=e.message;}
    }
    $("editor").hidden=false; history.replaceState(null,"",`?project=${encodeURIComponent(id)}`);
    const p=state.draft.payload;
    $("editorial-plan").value=p.editorial?JSON.stringify(p.editorial,null,2):"";
    renderEvents();
    for(const [dom,key] of [["title","title"]]) $(dom).value=state.draft[key];
    for(const [dom,key] of [["format","format"],["content-kind","content_kind"],["intent","intent"],["structure","structure"],["lufs","target_lufs"]]) $(dom).value=p[key];
    const caption=p.subtitle_style;
    $("caption-custom").checked=!!caption;
    $("caption-size").value=caption?.font_size??64;
    $("caption-color").value=caption?.text_color??"#ffffff";
    $("caption-highlight").value=caption?.highlight_color??"#ffd54a";
    $("caption-terms").value=(caption?.highlight_terms||[]).join("，");
    $("caption-strip").checked=caption?.strip_punctuation??true;
    presenterQuote=null;presenterGeneration=null;$("generate-presenter").hidden=true;
    renderEvidence(); renderAudio(); renderPresenters(); renderSegments(); renderVersions(state.versions); msg(state.layoutWarning||"已打开草稿，先查看素材观察，再编排段落。");
  }
  function collect() {
    const p=state.draft.payload;
    $("segments").querySelectorAll("[data-index]").forEach(card=>card.querySelectorAll("[data-json]").forEach(el=>{const s=p.segments[Number(card.dataset.index)];if(el.value.trim())s[el.dataset.json]=JSON.parse(el.value);else delete s[el.dataset.json];}));
    const editorial=$("editorial-plan").value.trim();
    if(editorial)p.editorial=JSON.parse(editorial);else delete p.editorial;
    state.draft.title=$("title").value;
    for(const [dom,key] of [["format","format"],["content-kind","content_kind"],["intent","intent"],["structure","structure"]]) p[key]=$(dom).value;
    p.target_lufs=Number($("lufs").value);
    if($("caption-custom").checked) p.subtitle_style={font_size:Number($("caption-size").value),
      text_color:$("caption-color").value,highlight_color:$("caption-highlight").value,
      highlight_terms:$("caption-terms").value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean),
      outline_size:p.subtitle_style?.outline_size??3,shadow:p.subtitle_style?.shadow??1,
      strip_punctuation:$("caption-strip").checked};
    else delete p.subtitle_style;
    p.music=$("music").value ? {audio_id:$("music").value,gain_db:Number($("music-gain").value),allow_source_music_mix:$("allow-source-music").checked} : null;
  }
  async function save() { collect(); const saved=await api(base(),"PUT",state.draft); state.draft.revision=saved.revision; state.draft.updated_at=saved.updated_at; msg(`已保存 · 版本 ${state.draft.revision}`); }
  async function refreshAssets() { const fresh=await api(base()); state.observations=fresh.observations; state.audio=fresh.audio; state.alignments=fresh.alignments; state.presenters=fresh.presenters; state.versions=fresh.versions; renderEvidence();renderAudio();renderPresenters();renderSegments();renderVersions(state.versions); }
  function renderPresenters() {
    const selected=$("presenter-audio").value;
    $("presenter-audio").innerHTML='<option value="">选择已有旁白</option>'+state.audio.filter(a=>a.kind==="narration").map(a=>`<option value="${a.id}">${esc(a.text)} · ${a.duration.toFixed(2)}秒</option>`).join("");
    $("presenter-audio").value=selected;
    $("presenter-list").innerHTML=(state.presenters||[]).map(p=>`<article class="card"><h3>${esc(p.name)}</h3><video controls muted preload="metadata" src="${base()}/presenters/${p.id}/media"></video><p>${esc(state.audio.find(a=>a.id===p.audio_id)?.text||"")}</p><p class="muted">${esc(p.provenance)}</p></article>`).join("");
  }
  function renderEvidence() {
    $("evidence").innerHTML=state.observations.map(e=>`<article class="card" data-evidence="${e.id}"><h3>${esc(evidenceName(e))}</h3><video controls preload="metadata" src="${base()}/evidence/${e.id}/source.mp4"></video><details><summary>区间抽帧</summary><img alt="带源时间码的区间抽帧" src="${base()}/evidence/${e.id}/sheet.jpg"></details>${e.review ? `<span class="badge">${e.review.usable?"已确认可用":"不可用"}</span><p>${esc(e.review.observation)}</p><p class="muted">${esc(e.review.context)}</p>` : `<label>画面观察<textarea data-review="observation" rows="2"></textarea></label><label>前后文与人物关系<textarea data-review="context" rows="2"></textarea></label><label>原声台词（听辨后填写）<textarea data-review="transcript" rows="2"></textarea></label><label>尚未确认<textarea data-review="unknowns" rows="2"></textarea></label><label>原字幕<select data-review="source_subtitles"><option value="unknown">未确认</option><option value="none">无</option><option value="present">有</option></select></label><label>原配乐<select data-review="source_music"><option value="unknown">未确认</option><option value="none">无</option><option value="present">有</option></select></label><label class="check"><input type="checkbox" data-review="viewed">已查看画面和上下文</label><label class="check"><input type="checkbox" data-review="audio_reviewed">已回听原声</label><button data-confirm>确认该区间可用</button>`}</article>`).join("");
    $("evidence").querySelectorAll("[data-confirm]").forEach(button=>button.onclick=async()=>{
      button.disabled=true;collect();const card=button.closest("[data-evidence]"), payload={reviewer:"human-editor",usable:true};
      card.querySelectorAll("[data-review]").forEach(el=>payload[el.dataset.review]=el.type==="checkbox"?el.checked:el.value);
      try { await api(`${base()}/evidence/${card.dataset.evidence}/review`,"POST",payload);await refreshAssets();msg("区间观察已保存，可加入解说段落。"); }catch(e){msg(e.message);button.disabled=false;}
    });
  }
  function renderAudio() {
    const p=state.draft.payload;
    $("alignment-audio").innerHTML=state.audio.filter(a=>a.kind==="narration").map(a=>`<option value="${a.id}">${esc(a.text)}</option>`).join("");
    $("alignment-list").innerHTML=(state.alignments||[]).map(a=>`<p>${esc(a.text)} · ${a.cues.length} 句<br><code>${esc(a.id)}</code></p>`).join("");
    $("audio-list").innerHTML=state.audio.map(a=>`<article class="card"><strong>${a.kind==="music"?"背景音乐":"配音"} · ${a.duration.toFixed(2)} 秒</strong><p>${esc(a.text||a.provenance)}</p><audio controls preload="none" src="${base()}/audio/${a.id}/media"></audio></article>`).join("");
    $("music").innerHTML='<option value="">不添加</option>'+state.audio.filter(a=>a.kind==="music").map(a=>`<option value="${a.id}">${esc(a.provenance)} · ${a.duration.toFixed(1)} 秒</option>`).join("");
    $("music").value=p.music?.audio_id||"";$("music-gain").value=p.music?.gain_db??-18;$("allow-source-music").checked=!!p.music?.allow_source_music_mix;
  }
  function renderSegments() {
    const rows=state.draft.payload.segments, observed=state.observations.filter(e=>e.review?.usable);
    $("segments").innerHTML=rows.map((s,i)=>`<article class="segment" data-index="${i}"><div class="segment-head"><h3>段落 ${i+1}</h3><div><button data-move="-1" ${i===0?"disabled":""}>上移</button> <button data-move="1" ${i===rows.length-1?"disabled":""}>下移</button> <button data-remove class="danger">移除</button></div></div>
      <div class="row"><label>本段作用<input data-field="purpose" value="${esc(s.purpose)}" placeholder="自由填写，例如保留完整问答"></label><label>声音方式<select data-field="mode"><option value="narration">旁白，源音静音</option><option value="original">现场原声</option><option value="mixed">旁白＋压低原声</option></select></label><label>原声音量（dB）<input data-field="source_gain_db" type="number" min="-60" max="0" value="${s.source_gain_db}"></label></div>
      <label>素材依据与编排理由<textarea data-field="basis" rows="2">${esc(s.basis)}</textarea></label><label>解说文案<textarea data-field="text" rows="2">${esc(s.text)}</textarea></label>
      <label>匹配配音<select data-field="audio_id"><option value="">尚未选择 / 原声段无需配音</option>${state.audio.filter(a=>a.kind==="narration").map(a=>`<option value="${a.id}">${esc(a.text)} · ${a.duration.toFixed(2)}秒</option>`).join("")}</select></label>
      <details><summary>本段可选出镜与字幕避让${s.presenter?" · 已启用":""}</summary><label>出镜角色<select data-presenter ${s.mode==="original"?"disabled":""}><option value="">本段不出镜</option>${(state.presenters||[]).filter(p=>p.audio_id===s.audio_id).map(p=>`<option value="${p.id}" ${s.presenter?.asset_id===p.id?"selected":""}>${esc(p.name)}</option>`).join("")}</select></label>
      ${s.presenter?`<div class="row">${[["x","左边距",0,100],["y","上边距",0,100],["diameter","圆形直径（画面宽度）",10,35]].filter(([key])=>!s.presenter_layout||key==='diameter').map(([key,label,min,max])=>`<label>${label} %<input data-presenter-geometry="${key}" type="number" min="${min}" max="${max}" step="0.1" value="${s.presenter[key]*100}"></label>`).join("")}</div><label>字幕与素材人物避让说明<input data-presenter-review value="${esc(s.presenter.layout_review)}"></label><label>出镜素材裁切（x、y、w、h，0—1）<textarea data-presenter-crop rows="2">${esc(JSON.stringify(s.presenter.crop||{x:0,y:0,w:1,h:1}))}</textarea></label>`:""}
      ${s.presenter?`<label class="check"><input type="checkbox" data-auto-layout ${s.presenter_layout?'checked':''}>按素材自动选左上或右上，字幕同步避让</label><button data-apply-layout>根据素材自动选位</button>
      <p class="muted">保持所选大小；两侧都不安全或画面判断未完成时隐藏雅雅，解说保留。缺少判断时会准备图片，待制作助手读取。结果基于上次保存的镜头，修改后请重新检查。</p>
      ${(s.presenter_layout?state.layouts||[]:[]).find(p=>p.segment_id===s.id)?.shots.map(p=>{const lock=s.presenter_layout?.locks?.find(l=>l.shot_index===p.shot_index&&(l.cut_index===p.cut_index||l.cut_index===undefined));return `<div class="card"><strong>镜头 ${p.shot_index+1}${p.cut_index?' · 换镜 '+p.cut_index:''}：${({left:'左上',right:'右上',hidden:'暂时隐藏'})[p.position]}</strong><p>${esc(p.reasons.join('；'))}</p><p>新增字幕：中心横向 ${Math.round(p.subtitle_layout.x*100)}%，基线纵向 ${Math.round(p.subtitle_layout.y*100)}%，保持字号。</p>${p.warnings.length?`<p>${esc(p.warnings.join('；'))}</p>`:''}<label>位置选择<select data-lock-shot="${p.shot_index}" data-lock-cut="${p.cut_index}"><option value="">自动判断</option>${[['left','锁定左上'],['right','锁定右上'],['hidden','锁定隐藏']].map(([v,label])=>`<option value="${v}" ${lock?.position===v?'selected':''}>${label}</option>`).join('')}</select></label></div>`;}).join('')||''}`:''}
      <p class="muted">只选择与本段配音对应的嘴型素材。原片烧录字幕保持原样；仅调整新增字幕。</p><label>字幕首选位置（x、y、max_width，0—1；自动模式以镜头结果为准）<textarea data-json="subtitle_layout" rows="2">${esc(s.subtitle_layout?JSON.stringify(s.subtitle_layout):"")}</textarea></label></details>
      <div class="shots">${s.shots.map((shot,j)=>`<div class="shot" data-shot="${j}"><select data-source aria-label="镜头证据"><option value="">选择已确认区间</option>${observed.map(e=>`<option value="${e.id}" ${shot.evidence_id===e.id?"selected":""}>${esc(evidenceName(e))}</option>`).join("")}</select><div class="row"><label>源起点<input data-time="start" type="number" step="0.001" value="${shot.start}"></label><label>源终点<input data-time="end" type="number" step="0.001" value="${shot.end}"></label><button data-delete-shot>移除镜头</button></div></div>`).join("")}</div><button data-add-shot>＋ 添加镜头</button>
      <div class="row"><label>新字幕<select data-field="subtitle_mode"><option value="estimated">按文案估时（待校准）</option><option value="timed">逐句时间戳</option><option value="none">不添加</option></select></label><label>位置<select data-field="subtitle_position"><option value="bottom">下方安全区</option><option value="top">上方安全区</option></select></label></div>
      <label>原字幕处理说明<input data-field="source_subtitle_note" value="${esc(s.source_subtitle_note)}" placeholder="有原字幕时说明保留理由，并将新增字幕置顶"></label>
      <details><summary>逐句字幕（每行：起点 | 终点 | 文字，时间相对本段）</summary><textarea data-cues rows="3">${esc((s.subtitles||[]).map(c=>`${c.start} | ${c.end} | ${c.text}`).join("\n"))}</textarea></details>
      <details><summary>事件、逐句配镜与声音切口</summary><label>关联事件<input data-field="event_id" value="${esc(s.event_id||"")}"></label><label>语音对齐编号<input data-field="alignment_id" value="${esc(s.alignment_id||"")}"></label><label>逐句配镜依据<textarea data-json="sentence_links" rows="3">${esc(s.sentence_links===undefined?"":JSON.stringify(s.sentence_links,null,2))}</textarea></label><label>独立原声（起止来自原片，offset 为相对本段进入时间；负值提前进入）<textarea data-json="source_audio" rows="3">${esc(s.source_audio===undefined?"":JSON.stringify(s.source_audio,null,2))}</textarea></label></details></article>`).join("");
    $("segments").querySelectorAll("[data-index]").forEach(card=>{
      const index=Number(card.dataset.index),s=rows[index];
      card.querySelector("[data-presenter]").onchange=e=>{collect();if(e.target.value){s.presenter={asset_id:e.target.value,x:.62,y:.05,diameter:.35,layout_review:"依据素材空间保护记录自动选位；未知时隐藏"};s.presenter_layout={mode:'auto',protection_ids:[],locks:[]};}else{delete s.presenter;delete s.presenter_layout;}renderSegments();};
      const auto=card.querySelector('[data-auto-layout]');if(auto)auto.onchange=()=>{collect();if(auto.checked)s.presenter_layout={mode:'auto',protection_ids:[],locks:[]};else delete s.presenter_layout;renderSegments();};
      const apply=card.querySelector('[data-apply-layout]');if(apply)apply.onclick=async()=>{apply.disabled=true;try{await save();const r=await api(base()+'/layout/apply','POST',{revision:state.draft.revision});state.draft=r.draft;state.layouts=r.layouts;renderSegments();msg(r.pending_tasks.length?`已准备 ${r.pending_tasks.length} 个素材空间判断窗口，待制作助手读取；相关镜头暂时隐藏雅雅，解说保留。`:'已按素材自动选位，保留手动锁定。请查看选位理由和待审画面。');}catch(e){msg(e.message);apply.disabled=false;}};
      card.querySelectorAll('[data-lock-shot]').forEach(el=>el.onchange=()=>{const shot=Number(el.dataset.lockShot),cut=Number(el.dataset.lockCut);s.presenter_layout.locks=s.presenter_layout.locks.filter(l=>!(l.shot_index===shot&&(l.cut_index===cut||l.cut_index===undefined)));if(el.value)s.presenter_layout.locks.push({shot_index:shot,cut_index:cut,position:el.value});msg('位置选择已修改，保存后重新检查。');});
      card.querySelectorAll("[data-presenter-geometry]").forEach(el=>{el.disabled=!!s.presenter_layout&&['x','y'].includes(el.dataset.presenterGeometry);el.oninput=()=>s.presenter[el.dataset.presenterGeometry]=Number(el.value)/100;});
      const review=card.querySelector("[data-presenter-review]");if(review)review.oninput=()=>s.presenter.layout_review=review.value;
      const crop=card.querySelector("[data-presenter-crop]");if(crop)crop.onchange=()=>{try{s.presenter.crop=JSON.parse(crop.value);}catch(e){msg("出镜裁切格式错误，请修正后保存。");}};
      const modeSelect=card.querySelector('[data-field="subtitle_mode"]');
      modeSelect.add(new Option("跟随实际语音时间戳","aligned"));
      card.querySelectorAll("[data-json]").forEach(el=>el.onchange=()=>{try{if(el.value.trim())s[el.dataset.json]=JSON.parse(el.value);else delete s[el.dataset.json];}catch(e){msg("逐句配镜或原声清单格式错误，请修正后保存。");}});
      card.querySelectorAll("[data-field]").forEach(el=>{
        const field=el.dataset.field; if(el.tagName==="SELECT") el.value=s[field]??"";
        el.oninput=()=>{s[field]=el.type==="number"?Number(el.value):el.value;if(field==="audio_id"){delete s.presenter;delete s.presenter_layout;renderSegments();}if(field==="mode") { if(s.mode==="original"){s.text="";s.audio_id=null;s.subtitle_mode="none";delete s.presenter;delete s.presenter_layout;} s.source_gain_db=s.mode==="mixed"?-18:0;renderSegments(); }};
      });
      card.querySelectorAll("[data-move]").forEach(b=>b.onclick=()=>{const j=index+Number(b.dataset.move);[rows[index],rows[j]]=[rows[j],rows[index]];renderSegments();});
      card.querySelector("[data-remove]").onclick=()=>{rows.splice(index,1);renderSegments();};
      card.querySelector("[data-add-shot]").onclick=()=>{const e=observed[0];if(!e){msg("请先确认至少一个素材区间");return;}s.shots.push({evidence_id:e.id,start:e.start,end:e.end});renderSegments();};
      card.querySelectorAll("[data-shot]").forEach(el=>{
        const j=Number(el.dataset.shot),shot=s.shots[j];
        const label=document.createElement("label");label.textContent="重复镜头理由（回调、对照等）";
        const input=document.createElement("input");input.value=shot.repeat_reason||"";input.oninput=()=>{if(input.value.trim())shot.repeat_reason=input.value;else delete shot.repeat_reason;};label.append(input);el.append(label);
        el.querySelector("[data-source]").onchange=(ev)=>{const e=observed.find(x=>x.id===ev.target.value);if(e){Object.assign(shot,{evidence_id:e.id,start:e.start,end:e.end});renderSegments();}};
        el.querySelectorAll("[data-time]").forEach(input=>input.oninput=()=>shot[input.dataset.time]=Number(input.value));
        el.querySelector("[data-delete-shot]").onclick=()=>{s.shots.splice(j,1);renderSegments();};
      });
      card.querySelector("[data-cues]").onchange=(event)=>{s.subtitles=event.target.value.split("\n").filter(x=>x.trim()).map(line=>{const [start,end,...content]=line.split("|");return {start:Number(start),end:Number(end),text:content.join("|").trim()};});};
    });
  }
  function renderVersions(rows) {
    const labels={queued:"排队中",running:"制作中",completed:"待人工审核",failed:"制作失败",paused:"已暂停",cancelled:"已取消"};
    $("versions").innerHTML=rows.map(v=>{const status=v.status==="completed"?"completed":(v.queue_job?.status||v.status);return `<article class="version"><h3>版本 ${v.revision} · ${esc(labels[status]||status)}</h3><p>${esc(v.stage||v.queue_job?.stage||"")}</p>${v.error?`<p>${esc(typeof v.error==="string"?v.error:v.error.message)}</p>`:""}${v.status==="completed"?`<video controls preload="metadata" src="${base()}/versions/${v.signature}/preview.mp4"></video><p><a href="${base()}/versions/${v.signature}/preview.mp4?download=true">下载待审视频</a><a href="${base()}/versions/${v.signature}/subtitles.srt?download=true">下载字幕</a></p><p class="muted">${esc((v.warnings||[]).join("；"))}</p>`:""}</article>`;}).join("")||'<p class="muted">保存并通过预检后，即可生成第一版预览。</p>';
  }
  function renderEvents(){
    $("event-cards").innerHTML=(state.draft.payload.editorial?.events||[]).map(e=>`<article class="card"><h3>${esc(e.summary)}</h3><p>前因：${esc(e.setup)}</p><p>动作：${esc(e.action)} → 结果：${esc(e.result)}</p><p>口吻：${esc(e.tone)}</p><p>原声价值：${esc(e.original_reason)}</p><p class="muted">${esc(e.context)}</p></article>`).join("");
  }
  action("audit-editorial",async()=>{await save();renderEvents();const r=await api(base()+"/editorial");$("editorial-result").textContent=r.enabled?`候选 ${r.coverage.total} 条，已观察 ${r.coverage.reviewed}，排除 ${r.coverage.excluded}，待处理 ${r.coverage.pending}；草稿请求窗口重复 ${r.repeated_windows.length}，长镜头 ${r.long_shots.length}（实际采用范围以预检为准）。`:r.next_action;});
  action("compare",async()=>{const r=await api(base()+"/compare","POST",{baseline_project_id:$("baseline-project").value.trim()});$("comparison-result").textContent=`${r.same_source_pool?"相同素材集合":"素材集合不同，不能视作严格同源对照"}\n旧版 ${r.baseline.duration.toFixed(2)} 秒 / ${r.baseline.shot_count} 镜头 / 原声 ${(r.baseline.original_audio_ratio*100).toFixed(0)}%\n新版 ${r.target.duration.toFixed(2)} 秒 / ${r.target.shot_count} 镜头 / 原声 ${(r.target.original_audio_ratio*100).toFixed(0)}%\n${r.note}`;});
  action("create",async()=>{const d=await api("/api/material-commentaries","POST",{title:$("new-title").value});await projects(d.id);await open(d.id);});
  $("projects").onchange=()=>{if($("projects").value)open($("projects").value).catch(e=>msg(e.message));};
  action("search",async()=>{const data=await api(`/api/material-commentaries/sources/search?query=${encodeURIComponent($("query").value)}`);$("sources").innerHTML=data.media.map(m=>`<article class="card"><h3>${esc(m.title)}</h3><p>${m.duration.toFixed(1)} 秒 · ${m.width}×${m.height}</p><button data-media="${m.id}">查看与选区间</button></article>`).join("")||"暂无匹配素材，请先到素材库登记。";$("sources").querySelectorAll("[data-media]").forEach(b=>b.onclick=()=>{source=data.media.find(m=>m.id===b.dataset.media);$("source-range").hidden=false;$("source-title").textContent=source.title;$("source-video").src=`/api/material-library/media/${source.id}/video`;$("start").value=0;$("end").value=Math.min(10,source.duration);});});
  action("prepare",async()=>{if(!source)return;collect();msg("正在准备区间视频与抽帧…");const crop=Object.fromEntries(["x","y","w","h"].map(k=>[k,Number($("crop-"+k).value)]));await api(base()+"/evidence","POST",{media_id:source.id,start:Number($("start").value),end:Number($("end").value),crop,review_revision:$("review-revision").value});await refreshAssets();msg("证据已准备，请查看并填写观察。");});
  action("add-segment",async()=>{state.draft.payload.segments.push({id:"segment-"+crypto.randomUUID().slice(0,8),purpose:"",basis:"",mode:"narration",text:"",audio_id:null,source_gain_db:0,subtitle_mode:"estimated",subtitle_position:"bottom",source_subtitle_note:"",subtitles:[],shots:[]});renderSegments();});
  action("import-audio",async()=>{collect();await api(base()+"/audio/import","POST",{path:$("audio-path").value,text:$("audio-text").value,kind:$("audio-kind").value,provenance:"用户导入音轨"});await refreshAssets();msg("音轨已登记，请在对应段落选择。");});
  action("import-alignment",async()=>{const r=await api(base()+"/audio/alignment","POST",{audio_id:$("alignment-audio").value,tencent_metadata_path:$("alignment-path").value});state.alignments=(await api(base())).alignments;renderAudio();msg(`字幕已按实际配音校准，${r.cues.length}句。请在段落中选择语音对齐编号。`);});
  action("load-voices",async()=>{const data=await api("/api/audio-center");$("voice").innerHTML=data.profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · ${esc(p.provider_name||p.provider_id||"")}</option>`).join("");});
  action("quote",async()=>{quote=await api(base()+"/audio/quote","POST",{profile_id:$("voice").value,text:$("audio-text").value});$("quote-result").textContent=`${quote.profile.provider_id} / ${quote.profile.model_id||quote.profile.provider_voice_id||quote.profile.name}，语速 ${quote.profile.speech_rate||1}，${quote.characters} 字，估算 USD ${quote.estimated_cost_usd}。${quote.billing_note}`;$("generate").hidden=false;});
  action("generate",async()=>{if(!quote)return;collect();await api(base()+"/audio/generate","POST",{profile_id:$("voice").value,text:$("audio-text").value,quote_signature:quote.signature,confirmed:true,max_characters:quote.characters,max_estimated_cost_usd:quote.estimated_cost_usd});$("generate").hidden=true;await refreshAssets();msg("配音已登记，可用于文案相同的段落。");});
  action("load-presenter-roles",async()=>{const r=await api("/api/avatar-roles");$("presenter-role").innerHTML='<option value="">选择与配音对应的角色</option>'+r.roles.filter(p=>p.references.some(a=>a.slot==="front")).map(p=>`<option value="${p.role_id}">${esc(p.name)} · ${esc(p.voice_binding?.profile_name||"未关联音色")}</option>`).join("");});
  const presenterRequest=()=>({audio_id:$("presenter-audio").value,role_id:$("presenter-role").value,budget_limit_cny:Number($("presenter-budget").value),prior_cost_cny:Number($("presenter-prior").value),max_runtime_seconds:900});
  action("quote-presenter",async()=>{presenterQuote=await api(base()+"/presenters/quote","POST",presenterRequest());$("presenter-quote-result").textContent=`${presenterQuote.name}：${presenterQuote.audio.text}。本次出镜预留 ${presenterQuote.reserved_cost_cny.toFixed(2)} 元，配音费用 ${presenterQuote.prior_cost_cny.toFixed(2)} 元，总上限 ${presenterQuote.budget_limit_cny.toFixed(2)} 元。${presenterQuote.billing_note}`;$("generate-presenter").hidden=false;});
  action("generate-presenter",async()=>{if(!presenterQuote)return;collect();const r=await api(base()+"/presenters/generate","POST",{...presenterRequest(),quote_signature:presenterQuote.signature,confirmed:true});presenterGeneration=presenterQuote.generation_id;$("generate-presenter").hidden=true;$("presenter-progress").textContent=`已排队：${r.job_id}`;});
  action("refresh-presenter",async()=>{collect();if(presenterGeneration){const r=await api(base()+"/presenters/jobs/"+presenterGeneration);$("presenter-progress").textContent=r.stage+(r.result?.actual_cost_cny!==undefined?` · 费用 ${r.result.actual_cost_cny} 元`:"");}await refreshAssets();});
  action("import-presenter",async()=>{collect();await api(base()+"/presenters/import","POST",{path:$("presenter-path").value,audio_id:$("presenter-audio").value,name:$("presenter-name").value,provenance:$("presenter-provenance").value});await refreshAssets();msg("出镜素材已登记，请在配音对应的段落中启用。");});
  action("save",save);
  action("preflight",async()=>{await save();const r=await api(base()+"/preflight","POST",{revision:state.draft.revision});$("preflight-result").textContent=r.status==="ready"?`可生成：${r.segment_count} 段，共 ${r.duration.toFixed(2)} 秒。${r.warnings.join("；")}`:`段落 ${r.segment_id} 缺少 ${r.missing_seconds.toFixed(2)} 秒画面。${r.next_action}`;});
  action("render",async()=>{await save();const r=await api(base()+"/render","POST",{revision:state.draft.revision});msg(`已进入统一队列：${r.job_id}`);renderVersions((await api(base())).versions);});
  action("refresh",async()=>{renderVersions((await api(base())).versions);msg("预览进度已刷新，未改动当前编辑内容。");});
  action("export",async()=>{collect();const url=URL.createObjectURL(new Blob([JSON.stringify(state.draft,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="commentary-draft.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  projects().then(async()=>{const id=new URLSearchParams(location.search).get("project");if(id){$("projects").value=id;await open(id);}}).catch(e=>msg(e.message));
})();
