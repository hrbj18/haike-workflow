import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, Info, Music2, Pause, Play, Settings2, Upload, X, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { EXAMPLE_TEXT, TEMPLATES, validateInputs } from "./generator-model.js";
import { readDraft, writeDraft } from "./draft-store.js";
import { api, upload } from "./studio-api.js";
import { ActionBar, Button, Dialog as Modal, Field, Heading, Notice, PreviewPanel, availableModels } from './ui.jsx';
import {Motion} from './Motion.jsx';
import {AvatarModeBar} from './AvatarModeBar.jsx';

const sampleAudio = { name: "海客介绍口播.wav", duration: 6.56, type: "audio/wav" };
const samplePortrait = { name: "人物示例.png", type: "image/png" };
const assetPath = name => `${import.meta.env.BASE_URL}assets/${name}`;
const initial = () => ({ templateId: TEMPLATES[2].id, text: EXAMPLE_TEXT, soundMode: "audio", audio: sampleAudio, portrait: samplePortrait, voiceId: '', rate: 1, title: "", subtitles: true });
function useAssetUrl(asset, fallback) {
  const [url, setUrl] = useState(fallback);
  useEffect(() => {
    if (!asset?.file) { setUrl(asset?.url || fallback); return; }
    const next = URL.createObjectURL(asset.file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [asset, fallback]);
  return url;
}
function Step({ number, title, helper, children, action, className = "" }) {
  return <section className={`input-step ${className}`} aria-labelledby={`step-${number}`}><span className="step-number" aria-hidden="true">{number}</span><div className="step-body"><header className="step-title"><div><h3 id={`step-${number}`}>{title}</h3><p className="helper">{helper}</p></div>{action}</header>{children}</div></section>;
}
export function App() {
  return new URLSearchParams(location.search).get('mode') === 'motion' ? <Motion/> : <BasicAvatar/>;
}
function BasicAvatar() {
  const [serverDraft, setServerDraft] = useState(null);
  const [quote, setQuote] = useState(null), [budget, setBudget] = useState('10.00'), [job, setJob] = useState(null);
  const uploaded = useRef(new WeakMap());
  const [layout, setLayout] = useState({ title_size: 60, accent: "#316dd6" });
  const [input, setInput] = useState(initial);
  const [voices, setVoices] = useState([]);
  const [voiceStatus, setVoiceStatus] = useState("loading");
  const [accountState, setAccountState] = useState(null);
  const [modal, setModal] = useState(null);
  const [more, setMore] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [samplePlaying, setSamplePlaying] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState(null);
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [draftLoading, setDraftLoading] = useState(true);
  const textUpload = useRef(null), audioUpload = useRef(null), portraitUpload = useRef(null), textArea = useRef(null), audio = useRef(null);
  const audioTicket = useRef(0), imageTicket = useRef(0), textTicket = useRef(0);
  const templateGrid = useRef(null);
  const template = TEMPLATES.find(t => t.id === input.templateId) || TEMPLATES[2];
  const audioUrl = useAssetUrl(input.audio, assetPath("narration.wav"));
  const portraitUrl = useAssetUrl(input.portrait, assetPath("presenter.png"));
  const update = patch => { setInput(previous => ({ ...previous, ...patch })); setSaved(false); setError(null); setQuote(null); };
  const updateLayout = patch => {setLayout(old=>({...old,...patch}));setSaved(false);setQuote(null);setError(null);};
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/studio/account", { signal: controller.signal }).then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(data => {
      setAccountState(data);
      const available = (data.capabilities?.items || []).filter(v => v.capability === 'tts').map(v => ({ id: v.model, name: v.name, model: v.model, rate: 1 }));
      setVoices(available); setVoiceStatus(available.length ? "ready" : "empty");
      setInput(old=>({...old,voiceId:available.some(v=>v.id===old.voiceId)?old.voiceId:available[0]?.id||old.voiceId}));
    }).catch(e => { if (e.name !== "AbortError") {setVoiceStatus("offline");setAccountState({error:true});} });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    let live = true;
    const id = new URLSearchParams(location.search).get('draft');
    const fromServer = async id => {const d=await api(`/api/studio/drafts/${id}`);if(live){setServerDraft(d);setLayout(d.layout);}return {version:1,input:{...d.input,templateId:d.template_id,text:d.text,title:d.title}};};
    const restore = id ? fromServer(id) : readDraft().then(d=>d?.studioDraftId?fromServer(d.studioDraftId):d);
    restore.then(draft => {
      if (!live || !draft) return;
      if (draft.version !== 1 || !draft.input || typeof draft.input.text !== "string" || !TEMPLATES.some(t => t.id === draft.input.templateId)) throw new Error();
      setInput(old=>({ ...initial(), ...draft.input, voiceId: draft.input.voiceId?.startsWith('haike/')?draft.input.voiceId:old.voiceId })); setSaved(true); setToast("已恢复保存的制作项目。");
    }).catch(() => { if (live) setToast("未能读取本地草稿，你可以继续填写并重新保存。"); }).finally(() => { if (live) setDraftLoading(false); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => { audio.current?.pause(); setPlaying(false); }, [audioUrl, input.soundMode]);
  useEffect(() => {
    const grid = templateGrid.current;
    if (!grid) return;
    const showSelected = () => {
      if (grid.scrollWidth > grid.clientWidth) {
        const selected = grid.querySelector(".selected");
        if (selected) grid.scrollLeft = selected.offsetLeft - grid.offsetLeft;
      }
    };
    showSelected();
    const observer = new ResizeObserver(showSelected);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [input.templateId]);
  async function importText(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(txt|docx)$/i.test(file.name) || file.size > 5 * 1024 * 1024) { setError({ field: "text", message: "请上传 5 MB 以内的 DOCX 或 TXT 文案。" }); return; }
    const ticket = ++textTicket.current; setImporting(true);
    try {
      let text;
      if (/\.docx$/i.test(file.name)) {
        const mammoth = await import("mammoth/mammoth.browser.js");
        const result = await (mammoth.default || mammoth).extractRawText({ arrayBuffer: await file.arrayBuffer() });
        text = result.value.trim();
      } else {
        const bytes = await file.arrayBuffer();
        try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
        catch { text = new TextDecoder("gb18030").decode(bytes); }
        text = text.replace(/^\uFEFF/, "").trim();
      }
      if (!text) throw new Error("empty");
      if ([...text].length > 5000) throw new Error("long");
      if (ticket === textTicket.current) { update({ text }); setToast(`已导入 ${file.name}，可以继续修改文案。`); }
    } catch (e) {
      if (ticket === textTicket.current) setError({ field: "text", message: e.message === "long" ? "口播文案最多5,000字，请精简后重新上传。" : "无法读取这份文案，请检查文件，或复制正文粘贴到文案框。" });
    } finally { if (ticket === textTicket.current) setImporting(false); }
  }
  async function importAudio(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(wav|mp3|m4a|ogg)$/i.test(file.name) || file.size > 50 * 1024 * 1024) { setError({ field: "audio", message: "请上传 50 MB 以内的 WAV、MP3、M4A 或 OGG 音频。" }); return; }
    const ticket = ++audioTicket.current;
    const url = URL.createObjectURL(file), probe = new Audio();
    try {
      const duration = await new Promise((resolve, reject) => {
        probe.onloadedmetadata = () => resolve(probe.duration);
        probe.onerror = reject; probe.src = url;
      });
      if (!Number.isFinite(duration) || duration <= 0 || duration > 120) throw new Error();
      if (ticket === audioTicket.current) { update({ audio: { name: file.name, type: file.type, duration, file }, soundMode: "audio" }); setModal(null); setToast("音频已就绪，将直接用于制作，无需重复生成配音。"); }
    } catch { if (ticket === audioTicket.current) setError({ field: "audio", message: "音频无法播放或超过120秒，请使用可播放的口播音频。" }); }
    finally { probe.src = ""; URL.revokeObjectURL(url); }
  }
  async function importPortrait(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(jpg|jpeg|png)$/i.test(file.name) || !["image/jpeg", "image/png"].includes(file.type) || file.size > 10 * 1024 * 1024) { setError({ field: "portrait", message: "请上传 10 MB 以内的 JPG 或 PNG 人物图片。" }); return; }
    const ticket = ++imageTicket.current, url = URL.createObjectURL(file);
    try {
      const img = new Image(); img.src = url; await img.decode();
      if (Math.min(img.naturalWidth, img.naturalHeight) < 256) throw new Error();
      if (ticket === imageTicket.current) { update({ portrait: { name: file.name, type: file.type, file } }); setToast("图片已载入。请确保人物正面清晰、没有严重遮挡。"); }
    } catch { if (ticket === imageTicket.current) setError({ field: "portrait", message: "图片无法读取或尺寸过小，请上传宽高至少 256 像素的图片。" }); }
    finally { URL.revokeObjectURL(url); }
  }
  async function playAudio() {
    if (playing) { audio.current.pause(); setPlaying(false); return; }
    try { await audio.current.play(); setPlaying(true); }
    catch { setToast("音频未能播放，请重新选择文件后再试。"); }
  }
  async function persistServer() {
    await writeDraft(input, serverDraft?.id);
    let d=await api('/api/studio/drafts',{id:serverDraft?.id,revision:serverDraft?.revision,template_id:input.templateId,title:input.title||input.text.split(/[。！？\n]/)[0].slice(0,16),text:input.text,layout,input:{soundMode:input.soundMode,voiceId:input.voiceId,rate:input.rate,subtitles:input.subtitles}});
    setServerDraft(d);
    const assets={};
    for (const [name,kind,sample] of [['audio','audio','narration.wav'],['portrait','image','presenter.png']]) {
      const value=input[name]; if(name==='audio'&&input.soundMode!=='audio')continue;
      if(value?.id&&serverDraft){assets[name]=value;continue;}
      let file=value?.file;
      if(!file){const r=await fetch(assetPath(sample));if(!r.ok)throw new Error('示例素材无法读取，请上传自己的文件');file=new File([await r.blob()],value?.name||sample,{type:value?.type});}
      const cached=uploaded.current.get(file);
      const a=cached?.draftId===d.id?cached.asset:await upload(d.id,file,kind);
      uploaded.current.set(file,{draftId:d.id,asset:a});assets[name]={...a,duration:value?.duration,type:value?.type};
    }
    d=await api('/api/studio/drafts',{...d,input:{...d.input,...assets}});setServerDraft(d);
    const next={...input,...Object.fromEntries(Object.entries(assets).map(([name,value])=>[name,{...input[name],...value}]))};setInput(next);await writeDraft(next,d.id);setSaved(true);return d;
  }
  async function saveDraft(){setSaving(true);setError(null);try{await persistServer();setToast('制作项目已保存到工作台，可从我的作品继续编辑。');}catch(e){setError({field:'draft',message:e.message});}finally{setSaving(false);}}
  async function confirmGeneration() {
    const problem = validateInputs(input, voices);
    if (problem) { setError(problem); if (problem.field === "text") textArea.current.focus(); return; }
    audio.current?.pause(); setPlaying(false); setSaving(true);setError(null);
    try{const d=await persistServer();const q=await api(`/api/studio/drafts/${d.id}/quote`,{revision:d.revision});setQuote(q);setBudget((Math.max(q.known_max_micros/1000000,q.needs_audio_quote?10:1)).toFixed(2));setModal('confirm');}
    catch(e){setError({field:'api',message:e.message});}finally{setSaving(false);}
  }
  async function saveRequest() {
    if (saving) return;
    setSaving(true);
    try {const j=await api(`/api/studio/drafts/${serverDraft.id}/generate`,{revision:quote.revision,quote_id:quote.id,max_charge_micros:Math.round(Number(budget)*1000000),confirmed:true});setJob(j);setModal('saved');}
    catch(e){setError({field:'api',message:e.message});setModal(null);}
    finally { setSaving(false); }
  }
  useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;const timer=setInterval(()=>api(`/api/production-queue/jobs/${job.job_id}`).then(setJob).catch(e=>setError({message:e.message})),2500);return()=>clearInterval(timer);},[job?.job_id,job?.status]);
  async function retry(){setSaving(true);try{setJob(await api(`/api/production-queue/jobs/${job.job_id}/retry`,{}));}catch(e){setError({message:e.message});}finally{setSaving(false);}}
  const seconds = Math.round(input.audio?.duration || 0);
  const audioTime = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const models = availableModels(accountState);
  const blocked = accountState === null ? '正在读取模型能力…' : accountState.error ? '暂时无法验证模型能力' : !models.has('haike/avatar') ? '数字人模型尚未开通' : input.subtitles && !models.has('haike/tencent-asr') ? '字幕识别尚未开通' : '';
  const inProgress = ['queued','running'].includes(job?.status);
  return <main className="workspace creation-workspace">
    <Heading title="数字人口播" helper="选择模板，放入文案、声音和人物图片。"/>
    <AvatarModeBar/>
    <div className="editor-shell avatar-editor"><section className="editor-content" aria-label="填写制作内容" aria-busy={draftLoading}>
      <div ref={templateGrid} className="template-grid" role="group" aria-label="选择视频模板">
        {TEMPLATES.map(t => <button key={t.id} className={`template-tile ${t.id === input.templateId ? "selected" : ""}`} aria-pressed={t.id === input.templateId} onClick={() => {update({templateId:t.id});setSamplePlaying(false);}}>
          <div className="template-cover"><img src={assetPath(t.poster)} alt={`${t.name}${t.kind}`}/><span>{t.kind}</span></div>
          <div className="template-copy"><strong>{t.name}</strong><p>{t.ratio} · {t.description}</p></div>
        </button>)}
      </div>
      <div className="avatar-fields">
        <Step number="1" title="文案" helper="上传文案或直接粘贴内容" className="text-step" action={<div className="upload-text"><Button disabled={importing||draftLoading} loading={importing} onClick={()=>textUpload.current.click()}><Upload size={16}/>上传文案</Button><span>DOCX / TXT</span></div>}>
          <label className="sr-only" htmlFor="script-text">口播文案</label><div className="textarea-wrap"><textarea id="script-text" ref={textArea} value={input.text} disabled={draftLoading||importing} onChange={e=>update({text:e.target.value})} placeholder="粘贴你的口播文案…" aria-invalid={error?.field==="text"}/><small className="character-count">{[...input.text].length.toLocaleString()} / 5,000</small></div>
        </Step>
        <Step number="2" title="声音" helper="使用已有音频，或选择海客音色配音" className="sound-step">
          <div className="sound-tabs" role="group" aria-label="声音来源"><button aria-pressed={input.soundMode==="audio"} className={input.soundMode==="audio"?"active":""} onClick={()=>update({soundMode:"audio"})}>使用音频</button><button aria-pressed={input.soundMode==="voice"} className={input.soundMode==="voice"?"active":""} onClick={()=>update({soundMode:"voice"})}>选择音色配音</button></div>
          {input.soundMode==="audio" ? <><div className="audio-row"><div className="audio-file"><Music2 size={20}/><div><strong>{input.audio?.name||"尚未选择音频"}</strong><small>{audioTime}</small></div></div><Button onClick={playAudio} disabled={!input.audio} aria-label={playing?"暂停音频":"播放音频"}>{playing?<Pause size={16}/>:<Play size={16}/>}</Button><Button onClick={()=>setModal("audio")}>选择 / 上传音频</Button></div><p className="helper after-input">已有音频直接用于制作，不重复生成配音。最长120秒。</p></> :
          <><Field label="配音模型"><select value={input.voiceId} onChange={e=>update({voiceId:e.target.value})} disabled={voiceStatus!=="ready"}>{voices.length?voices.map(v=><option key={v.id} value={v.id}>{v.name} · 平台预设音色</option>):<option value={input.voiceId}>{voiceStatus==="loading"?"正在读取配音模型…":"当前没有可用配音模型"}</option>}</select></Field><p className="helper after-input">使用网关预设音色，生成前核对报价。已有音频不产生配音费。</p></>}
        </Step>
        <Step number="3" title="人物图片" helper="人物正面清晰，JPG / PNG" className="portrait-step">
          <div className="portrait-row"><img src={portraitUrl} alt="已选择的人物图片"/><div className="portrait-description"><strong>{input.portrait?.name||"尚未上传图片"}</strong><small>至少256 × 256像素</small></div><Button onClick={()=>portraitUpload.current.click()}><Upload size={16}/>上传 / 更换图片</Button></div>
        </Step>
      </div>
      <section className="more-settings"><button className="settings-toggle" onClick={()=>setMore(!more)} aria-expanded={more} aria-controls="more-fields"><ChevronDown size={18} className={more?'':'collapsed'}/><strong>模板排版配置</strong><span>标题、字号、强调色与字幕</span></button>
        {more&&<div id="more-fields" className="settings-fields"><Field label="视频标题"><input value={input.title} maxLength={36} placeholder="自动取文案首句，建议16字以内" onChange={e=>update({title:e.target.value})}/></Field><div className="layout-fields"><Field label="标题字号"><select value={layout.title_size} onChange={e=>updateLayout({title_size:Number(e.target.value)})}>{[48,54,60,66].map(n=><option key={n} value={n}>{n}px</option>)}</select></Field><Field label="强调色"><input type="color" value={layout.accent} onChange={e=>updateLayout({accent:e.target.value})}/></Field></div><label className="checkbox-row"><input type="checkbox" checked={input.subtitles} onChange={e=>update({subtitles:e.target.checked})}/>显示字幕</label>{input.soundMode==="voice"&&<Field label="配音语速"><select value={input.rate} onChange={e=>update({rate:Number(e.target.value)})}>{[.8,1,1.2,1.5].map(n=><option key={n} value={n}>{n.toFixed(2)}×</option>)}</select></Field>}<p className="helper">画幅和人物位置跟随模板；配置效果在生成后查看。</p><Button variant="text" onClick={()=>{setInput(initial());setSaved(false);setQuote(null);setError(null);setToast("已载入示例内容，保存后更新草稿。");}}>载入示例内容</Button></div>}
      </section>
      <div className="notice-stack avatar-notices"><Notice message={error?.message} error/>{blocked&&<Notice message={blocked} error={accountState!==null}><a href="/settings">查看 API 设置<ArrowRight size={14}/></a></Notice>}</div>
      {job&&<div className="job-state"><strong>{({queued:'排队中',running:'正在制作',completed:'已合成 · 待审核',failed:'需要处理',canceled:'已取消'})[job.status]||job.status}</strong><p>{job.stage}</p>{job.result?.work_id&&<Button href="/projects">观看并审核成片</Button>}{job.retryable&&<Button disabled={saving} onClick={retry}>恢复原任务</Button>}</div>}
    </section><PreviewPanel label="模板效果预览" metadata={template.ratio}><div className="poster-frame"><img src={assetPath(template.poster)} alt={`${template.name} · ${template.kind}`}/></div><p className="preview-note">{template.sample?"现有真实样片，生成后使用你的内容。":"模板布局示意，生成后使用你的内容。"}</p>{template.sample&&<Button className="preview-play" onClick={()=>{setModal("sample");setSamplePlaying(true);}}><Play size={16}/>播放样片</Button>}</PreviewPanel>
    <ActionBar note={<span><Info size={16}/> {blocked||'生成前确认本次调用费用'}</span>}><Button disabled={saving||draftLoading||importing} loading={saving&&modal!=="confirm"} onClick={saveDraft}>{saved?"草稿已保存":"保存草稿"}</Button><Button variant="primary" disabled={importing||saving||draftLoading||inProgress||!!blocked} onClick={confirmGeneration}>生成数字人口播<ArrowRight size={17}/></Button></ActionBar></div>
    <input hidden type="file" ref={textUpload} accept=".txt,.docx" onChange={importText} aria-label="文案文件"/><input hidden type="file" ref={audioUpload} accept=".wav,.mp3,.m4a,.ogg" onChange={importAudio} aria-label="音频文件"/><input hidden type="file" ref={portraitUpload} accept="image/jpeg,image/png" onChange={importPortrait} aria-label="人物图片文件"/>
    <audio ref={audio} src={input.soundMode==="voice"?assetPath("narration.wav"):audioUrl} onEnded={()=>setPlaying(false)} onError={()=>setPlaying(false)}/>
    <div className={`toast ${toast?"visible":""}`} role="status">{toast&&<><CheckCircle2 size={18}/>{toast}</>}</div>
    {modal==="sample"&&<Modal title={`${template.name} · 真实样片`} wide onClose={()=>{setModal(null);setSamplePlaying(false);}} footer={<Button href={assetPath(template.sample)} download="海客科技-模板3-现有样片.mp4">下载现有样片</Button>}><video className="sample-video" controls autoPlay={samplePlaying} poster={assetPath(template.poster)} src={assetPath(template.sample)}/><p className="helper">项目现有7秒样片，用于查看版式。</p></Modal>}
    {modal==="audio"&&<Modal title="选择音频" description="使用已有口播录音，无需重复生成配音。" onClose={()=>setModal(null)} footer={<><Button onClick={()=>setModal(null)}>取消</Button><Button variant="primary" onClick={()=>audioUpload.current.click()}><Upload size={17}/>上传音频</Button></>}><button className="library-audio" onClick={()=>{update({audio:sampleAudio,soundMode:"audio"});setModal(null);}}><Music2 size={24}/><span><strong>海客介绍口播.wav</strong><small>项目现有样音 · 6.56秒</small></span><span>选择</span></button><p className="helper">支持WAV、MP3、M4A、OGG；50 MB以内，最长120秒。</p></Modal>}
    {modal==="confirm"&&quote&&<Modal title="生成确认与费用" description="核对模板、素材与本次调用上限。" busy={saving} onClose={()=>setModal(null)} footer={<><Button disabled={saving} onClick={()=>setModal(null)}>返回修改</Button><Button variant="primary" loading={saving} onClick={saveRequest} disabled={Number(budget)<=0||!Number.isFinite(Number(budget))}>确认费用并生成<ArrowRight size={17}/></Button></>}>
      <dl className="summary-list"><div><dt>模板</dt><dd>{template.name} · {template.ratio}</dd></div><div><dt>声音</dt><dd>{input.soundMode==="audio"?input.audio.name:voices.find(v=>v.id===input.voiceId)?.name}</dd></div><div><dt>人物</dt><dd>{input.portrait.name}</dd></div>{quote.items.map(q=><div key={q.stage}><dt>{({tts:'配音',avatar:'数字人',asr:'字幕识别'})[q.stage]}</dt><dd>上限 ¥{(q.max_charge_micros/1000000).toFixed(4)}<p className="helper">{q.model}</p></dd></div>)}</dl>
      {quote.needs_audio_quote&&<p className="helper">数字人与字幕按配音实际时长报价，超出剩余上限即停止，保留已完成配音。</p>}
      <Field label="本次全部调用费用上限（元）"><input type="number" min=".01" max="1000" step=".01" value={budget} disabled={saving} onChange={e=>setBudget(e.target.value)}/></Field><p className="helper">确认后将提交真实收费调用；本地排版不收费。实际费用与冻结额度可到账户中心查看。</p>
    </Modal>}
    {modal==="saved"&&<Modal title="制作任务已提交" onClose={()=>setModal(null)} footer={<Button variant="primary" onClick={()=>setModal(null)}>查看进度<ArrowRight size={17}/></Button>}><div className="success-content"><CheckCircle2 size={36}/><h3>已进入制作队列</h3><p>完成后从我的作品观看并审核成片。中断时恢复原任务，保留已完成的模型调用。</p></div></Modal>}
  </main>;
}
