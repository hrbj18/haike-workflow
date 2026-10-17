import {QuoteBilling} from './QuoteBilling.jsx';
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, Info, Music2, Pause, Play, Settings2, Upload, X, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { EXAMPLE_TEXT, TEMPLATES, validateInputs, availableVoicesFromAccount, defaultVoiceId, normalizeVoiceInput, normalizeAvatarMedia, hasAvatarAsset, localAvatarFile, avatarInputForSave } from "./generator-model.js";
import { readDraft, writeDraft } from "./draft-store.js";
import { api, upload } from "./studio-api.js";
import { ActionBar, Button, Dialog as Modal, Field, Heading, Notice, PreviewPanel, availableModels } from './ui.jsx';
import {Motion} from './Motion.jsx';
import {AvatarTemplatePicker} from './AvatarTemplatePicker.jsx';
import {AiMaterials,AI_DEFAULTS} from './AiMaterials.jsx';
import {DouyinRecovery} from './DouyinRecovery.jsx';
import { AUDIO_CENTER_API, normalizeCatalog, voiceImageUrl } from './audio-center-model.js';
import { openAudioCenter } from './studio-routes.js';
import {N1Settings} from './N1Settings.jsx';
import {N1_TEMPLATE_ID, n1Value, n1ForSave} from './n1-model.js';
import {TemplatePreview, TemplateSampleDialog} from './TemplatePreview.jsx';
import {PortraitRefinement} from './PortraitRefinement.jsx';
import {asrPolicy} from './asr-policy.js';
import {AvatarDefaultsDialog,AvatarDefaultsSummary} from './AvatarDefaults.jsx';
import {requestAvatarDefaults,avatarPresetInput,presetBudget,shouldApplyAvatarPreset} from './avatar-defaults-model.js';
import {NetworkMaterialChoice,usePlatformSessions} from './PlatformAccounts.jsx';

const assetPath = name => `${import.meta.env.BASE_URL}assets/${name}`;
const initial = () => {const q=new URLSearchParams(location.search),style=q.get('style');return { templateId: TEMPLATES.some(t=>t.id===q.get('template'))?q.get('template'):TEMPLATES[2].id, text: EXAMPLE_TEXT, soundMode: "audio", audio: null, portrait: null, modelId:'haike/cosyvoice', voiceId: '', rate: 1, title: "", subtitles: true,network_materials_enabled:false,ai:{...AI_DEFAULTS,enabled:!!style},motion:style?{style,layout:q.get('layout')==='landscape'?'landscape':'portrait'}:null };};
export function useAssetUrl(asset, fallback) {
  const [url, setUrl] = useState(fallback);
  useEffect(() => {
    const file = localAvatarFile(asset);
    if (!file) { setUrl(asset?.url || fallback); return; }
    let next;
    try { next = URL.createObjectURL(file); }
    catch { setUrl(asset?.url || fallback); return; }
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
  const sessions=usePlatformSessions();
  const [serverDraft, setServerDraft] = useState(null);
  const [storyboard,setStoryboard]=useState(null),[motionPreview,setMotionPreview]=useState(null);
  const [quote, setQuote] = useState(null), [budget, setBudget] = useState(''), [job, setJob] = useState(null);
  const [preset,setPreset]=useState(null),[presetLoading,setPresetLoading]=useState(true),[presetError,setPresetError]=useState(''),[presetOpen,setPresetOpen]=useState(false);
  const presetHandled=useRef(false),restoredDraft=useRef(false),editVersion=useRef(0),presetRequest=useRef(0);
  const uploaded = useRef(new WeakMap());
  const [layout, setLayout] = useState({ title_size: 60, accent: "#316dd6" });
  const [input, setInput] = useState(initial);
  const [voiceCatalog, setVoiceCatalog] = useState({items:[],preferences:{}});
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
  const [refinementPending,setRefinementPending]=useState(false);
  const selectedPortraitId=useRef(null);
  selectedPortraitId.current=input.portrait?.id;
  const [draftLoading, setDraftLoading] = useState(true);
  const textUpload = useRef(null), audioUpload = useRef(null), portraitUpload = useRef(null), textArea = useRef(null), audio = useRef(null);
  const audioTicket = useRef(0), imageTicket = useRef(0), textTicket = useRef(0);
  const templateGrid = useRef(null);
  const template = TEMPLATES.find(t => t.id === input.templateId) || TEMPLATES[2];
  const isN1 = input.templateId === N1_TEMPLATE_ID;
  const audioUrl = useAssetUrl(input.audio);
  const portraitUrl = useAssetUrl(input.portrait, assetPath("portrait-placeholder.svg"));
  const voices = availableVoicesFromAccount(accountState,voiceCatalog);
  const selectedVoice = voices.find(v=>v.id===input.voiceId&&v.model===input.modelId);
  const update = patch => { editVersion.current++;setInput(previous => ({ ...previous, ...patch })); setSaved(false); setError(null); setQuote(null); };
  const updateLayout = patch => {setLayout(old=>({...old,...patch}));setSaved(false);setQuote(null);setError(null);};
  function rememberDraft(draft){
    const query=new URLSearchParams(location.search);query.delete('new');query.delete('template');query.set('draft',draft.id);
    history.replaceState(history.state,'',`/avatar?${query}`);window.dispatchEvent(new Event('haike:navigate'));
  }
  useEffect(()=>{
    let live=true,controller;
    const load=async()=>{controller?.abort();const request=new AbortController();controller=request;setPresetLoading(true);setPresetError('');
      try{const value=await requestAvatarDefaults({signal:request.signal});if(live&&controller===request)setPreset(value);}
      catch(e){if(live&&controller===request&&!request.signal.aborted){setPreset(null);setPresetError(e.message);}}
      finally{if(live&&controller===request)setPresetLoading(false);}};
    void load();window.addEventListener('haike:avatar-defaults-changed',load);window.addEventListener('haike:gateway-changed',load);
    return()=>{live=false;controller?.abort();window.removeEventListener('haike:avatar-defaults-changed',load);window.removeEventListener('haike:gateway-changed',load);};
  },[]);
  async function applyPreset(data,{newTask=false,preserveTemplate=false}={}) {
    const ticket=++presetRequest.current,version=editVersion.current;
    setSaving(true);setPresetError('');
    try{
      let portrait=null;
      if(data.values.portrait_file_id){
        const response=await fetch(`${AUDIO_CENTER_API}/media/${encodeURIComponent(data.values.portrait_file_id)}`);
        if(!response.ok)throw new Error('默认人物图读取失败，请保留原预设后重试。');
        let blob=await response.blob(),type=blob.type.split(';')[0];
        if(!['image/png','image/jpeg','image/webp'].includes(type)||!blob.size||blob.size>10*1024*1024)throw new Error('默认人物图需为10MB以内的PNG、JPG或WebP。');
        const bitmap=await createImageBitmap(blob);
        try{
          if(Math.min(bitmap.width,bitmap.height)<256)throw new Error('默认人物图宽高需至少256像素。');
          if(type==='image/webp'){
            const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;canvas.getContext('2d').drawImage(bitmap,0,0);
            blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('默认人物图转换失败，请重新上传。')),'image/png'));type='image/png';
          }
        }finally{bitmap.close();}
        const file=new File([blob],`默认人物图.${type==='image/png'?'png':'jpg'}`,{type});portrait={name:file.name,type,file};
      }
      if(ticket!==presetRequest.current||version!==editVersion.current)return;
      if(newTask){setServerDraft(null);setJob(null);setStoryboard(null);restoredDraft.current=false;history.replaceState(history.state,'','/avatar?new=1');window.dispatchEvent(new Event('haike:navigate'));}
      setInput(previous=>({...avatarPresetInput(newTask?{...initial(),text:previous.text}:previous,data),...(preserveTemplate?{templateId:previous.templateId}:{}),portrait}));
      setBudget(String(data.values.max_charge_micros/1000000));setSaved(false);setQuote(null);setError(null);
      setToast(newTask?'已新建制作内容并采用预设；原项目保持不变。':'已采用默认设置；明确修改的参数优先。');
    }catch(e){setPresetError(e.message);}
    finally{if(ticket===presetRequest.current)setSaving(false);}
  }
  useEffect(()=>{
    const q=new URLSearchParams(location.search);
    if(!draftLoading&&shouldApplyAvatarPreset({restored:restoredDraft.current,edited:editVersion.current>0,explicit:q.has('style')||q.has('draft'),handled:presetHandled.current,ready:preset?.ready})){
      presetHandled.current=true;void applyPreset(preset,{preserveTemplate:q.has('template')});
    }
  },[draftLoading,preset]);
  useEffect(()=>()=>{presetRequest.current++;},[]);
  useEffect(() => {
    let controller;
    const load=()=>{controller?.abort();controller=new AbortController();setAccountState(null);fetch('/api/studio/account',{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(setAccountState).catch(e=>{if(e.name!=='AbortError')setAccountState({error:true});});};
    load();window.addEventListener('haike:gateway-changed',load);
    return()=>{controller?.abort();window.removeEventListener('haike:gateway-changed',load);};
  }, []);
  useEffect(()=>{
    let live=true;
    let generation=0;
    const load=async()=>{const request=++generation;setVoiceStatus('loading');setVoiceCatalog({items:[],preferences:{}});try{const value=normalizeCatalog(await api(AUDIO_CENTER_API));if(!live||request!==generation)return;setVoiceCatalog(value);setVoiceStatus(value.items.some(v=>v.available)?'ready':'empty');setInput(old=>{if(old.requiresVoiceSelection)return old;const id=defaultVoiceId(old.voiceId,value.items,value.preferences.voice_id),selected=value.items.find(v=>v.id===id);return selected?{...old,voiceId:id,modelId:selected.model,rate:old.voiceId?old.rate:Number(selected.preferences?.speech_rate||1)}:old;});}catch{if(live&&request===generation){setVoiceStatus('offline');setVoiceCatalog({items:[],preferences:{}});}}};
    const selected=e=>{if(!live)return;update({...e.detail,soundMode:'voice',requiresVoiceSelection:false});};
    load();window.addEventListener('haike:voices-changed',load);window.addEventListener('haike:voice-selected',selected);window.addEventListener('haike:gateway-changed',load);
    return()=>{live=false;window.removeEventListener('haike:voices-changed',load);window.removeEventListener('haike:voice-selected',selected);window.removeEventListener('haike:gateway-changed',load);};
  },[]);
  useEffect(() => {
    let live = true;
    const id = new URLSearchParams(location.search).get('draft');
    const fromServer = async id => {const d=await api(`/api/studio/drafts/${id}`);if(live){setServerDraft(d);setLayout(d.layout);}try{const r=await api(`/api/studio/drafts/${id}/avatar-job`);if(live)setJob(r.job);if(!r.job){const p=await api(`/api/studio/drafts/${id}/ai-preview`);if(live)setStoryboard(p.plan);}}catch{}return {version:1,input:{...d.input,templateId:d.template_id,text:d.text,title:d.title}};};
    const q=new URLSearchParams(location.search);
    const restore = id ? fromServer(id) : q.has('new')||q.has('style')||q.has('template')?Promise.resolve(null):readDraft().then(d=>d?.studioDraftId?fromServer(d.studioDraftId):d);
    restore.then(draft => {
      if (!live || !draft) return;
      if (draft.version !== 1 || !draft.input || typeof draft.input.text !== "string" || !TEMPLATES.some(t => t.id === draft.input.templateId)) throw new Error();
      const restored={...initial(),...normalizeAvatarMedia(normalizeVoiceInput(draft.input))};
      if(restored.templateId===N1_TEMPLATE_ID){restored.motion=null;restored.ai={...AI_DEFAULTS,...restored.ai,enabled:false};}
      restoredDraft.current=true;setInput(restored); setSaved(true); setToast("已恢复保存的制作项目；保留原参数。");
    }).catch(() => { if (live) setToast("未能读取本地草稿，你可以继续填写并重新保存。"); }).finally(() => { if (live) setDraftLoading(false); });
    return () => { live = false; };
  }, []);
  useEffect(()=>{setMotionPreview(null);if(!input.motion)return;let live=true;api(`/api/studio/motion/catalog?layout=${input.motion.layout}`).then(c=>{if(live)setMotionPreview(c.styles.find(s=>s.id===input.motion.style)?.preview);}).catch(()=>{});return()=>{live=false;};},[input.motion?.style,input.motion?.layout]);
  useEffect(()=>{if(!serverDraft||!job)return;const revision=Number(job.parent_job_id?.replace('studio-',''));api(`/api/studio/drafts/${serverDraft.id}/storyboard${Number.isInteger(revision)&&revision>0?'?revision='+revision:''}`).then(r=>setStoryboard(r.plan)).catch(()=>{});},[job?.status,job?.stage,serverDraft?.id]);
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
      if (ticket === imageTicket.current) {
        setSaving(true);
        update({portrait:{name:file.name,type:file.type,file}});
        const content={...avatarInputForSave(input,AI_DEFAULTS),
          ...(input.audio?.id?{audio:input.audio}:{}),...(input.portrait?.id?{portrait:input.portrait}:{})};
        let d=await api('/api/studio/drafts',{id:serverDraft?.id,revision:serverDraft?.revision,template_id:input.templateId,
          title:input.title||input.text.split(/[。！？\n]/)[0].slice(0,16)||'人物图片',text:input.text,layout,input:content});
        setServerDraft(d);
        const asset=await upload(d.id,file,'image');
        if(ticket!==imageTicket.current)return;
        d=await api('/api/studio/drafts',{...d,input:{...d.input,portrait:asset}});
        uploaded.current.set(file,{draftId:d.id,asset});setServerDraft(d);rememberDraft(d);
        setInput(old=>({...old,portrait:{...asset,type:file.type,file}}));
        setToast('原图已保存，正在准备预设优化报价。');
      }
    } catch(e) { if (ticket === imageTicket.current) setError({ field: "portrait", message: e.message||"图片无法读取或尺寸过小，请上传宽高至少 256 像素的图片。" }); }
    finally { URL.revokeObjectURL(url);if(ticket===imageTicket.current)setSaving(false); }
  }
  async function playAudio() {
    if (playing) { audio.current.pause(); setPlaying(false); return; }
    try { await audio.current.play(); setPlaying(true); }
    catch { setToast("音频未能播放，请重新选择文件后再试。"); }
  }
  async function persistServer() {
    if(input.soundMode==='audio'&&!hasAvatarAsset(input.audio))throw new Error('请先上传口播音频，再保存或生成。');
    if(!hasAvatarAsset(input.portrait))throw new Error('请先上传人物正面图片，再保存或生成。');
    await writeDraft(input, serverDraft?.id);
    let d=await api('/api/studio/drafts',{id:serverDraft?.id,revision:serverDraft?.revision,template_id:input.templateId,title:input.title||input.text.split(/[。！？\n]/)[0].slice(0,16),text:input.text,layout,input:avatarInputForSave(input,AI_DEFAULTS)});
    setServerDraft(d);
    const assets={};
    for (const [name,kind] of [['audio','audio'],['portrait','image']]) {
      const value=input[name]; if(name==='audio'&&input.soundMode!=='audio')continue;
      if(value?.id&&serverDraft){assets[name]=value;continue;}
      let file=localAvatarFile(value);
      if(!file)throw new Error(name==='audio'?'请重新上传口播音频。':'请重新上传人物正面图片。');
      const cached=uploaded.current.get(file);
      const a=cached?.draftId===d.id?cached.asset:await upload(d.id,file,kind);
      uploaded.current.set(file,{draftId:d.id,asset:a});assets[name]={...a,duration:value?.duration,type:value?.type};
    }
    d=await api('/api/studio/drafts',{...d,input:{...d.input,...assets}});setServerDraft(d);
    const next={...input,...Object.fromEntries(Object.entries(assets).map(([name,value])=>[name,{...input[name],...value}]))};setInput(next);await writeDraft(next,d.id);rememberDraft(d);setSaved(true);return d;
  }
  async function saveDraft(){setSaving(true);setError(null);try{await persistServer();setToast('制作项目已保存到工作台，可从我的作品继续编辑。');}catch(e){setError({field:'draft',message:e.message});}finally{setSaving(false);}}
  function resetTemplate(){
    if(isN1){update({n1:n1ForSave()});setToast('已恢复默认版式，人物、声音与文案已保留。');return;}
    setInput(initial());setSaved(false);setQuote(null);setError(null);setToast('已载入示例内容，保存后更新草稿。');
  }
  async function importMaterial(file){if(!/\.(jpg|jpeg|png|mp4|mov)$/i.test(file.name)||file.size>80*1024*1024)throw new Error('素材支持JPG、PNG、MP4、MOV，最多80MB');setSaving(true);try{const d=await persistServer(),a=await upload(d.id,file,/\.(mp4|mov)$/i.test(file.name)?'video':'image'),ai={...AI_DEFAULTS,...input.ai,materials:[...(input.ai?.materials||[]),{id:a.id,name:a.name,kind:a.kind,url:a.url,offset:0,mode:'prefer',note:'',rights_confirmed:false}]},savedDraft=await api('/api/studio/drafts',{...d,input:{...d.input,ai}});setServerDraft(savedDraft);update({ai});setStoryboard(null);setToast('素材已上传，请填写说明并确认使用权。');}finally{setSaving(false);}}
  async function importN1Material(index,file){
    const scene=input.n1?.scenes?.[index],screenshot=scene?.kind==='screenshot';
    if(!scene)return;
    if(!(screenshot?/\.(jpg|jpeg|png)$/i:/\.(jpg|jpeg|png|mp4|mov)$/i).test(file.name)||file.size>80*1024*1024){setError({field:'n1',message:screenshot?'截图支持JPG、PNG，最多80MB。':'素材支持JPG、PNG、MP4、MOV，最多80MB。'});return;}
    setSaving(true);setError(null);
    try{const d=await persistServer(),asset=await upload(d.id,file,/\.(mp4|mov)$/i.test(file.name)?'video':'image'),config=n1Value(input.n1),n1={...config,scenes:config.scenes.map((value,i)=>i===index?{...value,assetId:asset.id,asset:{id:asset.id,name:asset.name,kind:asset.kind,url:asset.url}}:value)},savedDraft=await api('/api/studio/drafts',{...d,input:{...d.input,n1:n1ForSave(n1)}});setServerDraft(savedDraft);update({n1});await writeDraft({...input,n1},d.id);setSaved(true);setToast('画面素材已上传并保存，可继续调整时间与内容。');}
    catch(e){setError({field:'n1',message:e.message});}finally{setSaving(false);}
  }
  async function planPreview({analysisMode='agent'}={}) {
    setSaving(true);setError(null);
    try {
      const d=analysisMode==='agent'&&saved&&serverDraft?serverDraft:await persistServer();
      if(analysisMode==='agent') {
        const r=await api(`/api/studio/drafts/${d.id}/agent-materials?revision=${d.revision}`);
        setStoryboard(r.plan||null);
        setToast(r.message||(r.plan?'当前Agent的分镜结果已读取，请核对内容安排。':'素材已准备，等待当前Agent实际分析并提交结果。'));
      } else {
        const r=await api(`/api/studio/drafts/${d.id}/ai-preview`,{revision:d.revision,confirmed:true});
        setStoryboard(r.plan);setToast('AI分镜建议已生成；实际时间将在声音就绪后对齐。');
      }
    } catch(e) {setError({field:'ai',message:e.message});}
    finally {setSaving(false);}
  }
  async function confirmGeneration() {
    if(refinementPending){setError({field:'portrait',message:'请先确认采用优化图，或选择使用原图继续。'});return;}
    const problem = validateInputs(input, voices);
    if (problem) { setError(problem); if (problem.field === "text") textArea.current.focus(); return; }
    audio.current?.pause(); setPlaying(false); setSaving(true);setError(null);
    try{const d=saved&&serverDraft?serverDraft:await persistServer();const q=await api(`/api/studio/drafts/${d.id}/quote`,{revision:d.revision});setQuote(q);setBudget(presetBudget(input));setModal('confirm');}
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
  async function skipDouyin(){setSaving(true);try{setJob(await api(`/api/studio/ai/jobs/${job.job_id}/skip-douyin`,{confirmed:true}));}catch(e){setError({message:e.message});}finally{setSaving(false);}}
  async function useLinkedPortrait(){
    if(!selectedVoice||!voiceImageUrl(selectedVoice))return;
    setImporting(true);setError(null);
    try{const response=await fetch(voiceImageUrl(selectedVoice));if(!response.ok)throw new Error();const blob=await response.blob();const type=blob.type.split(';')[0];if(!['image/png','image/jpeg'].includes(type))throw new Error();const file=new File([blob],`${selectedVoice.name}-人物图.${type==='image/png'?'png':'jpg'}`,{type});await importPortrait({target:{files:[file],value:''}});}
    catch{setError({field:'portrait',message:'关联人物图无法读取，请刷新音色或上传自己的图片。'});}finally{setImporting(false);}
  }
  const seconds = Math.round(input.audio?.duration || 0);
  const audioTime = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const internal=accountState?.mode==='internal_local';
  const estimateBilling=internal||quote?.estimate_only||quote?.items?.some(q=>q.estimate_only);
  const models = availableModels(accountState);
  const asr=asrPolicy(accountState);
  const blocked = accountState === null ? '正在读取模型能力…' : accountState.error ? '暂时无法验证模型能力' : !models.has('haike/avatar') ? '数字人模型尚未开通' : input.soundMode==='voice'&&!selectedVoice ? (voiceStatus==='loading'?'正在读取音色…':'请选择当前账号可用的海客音色') : (input.subtitles||(!isN1&&input.ai?.enabled)) && !asr.ready ? '字幕识别尚未就绪' : '';
  const inProgress = ['queued','running'].includes(job?.status);
  return <main className="workspace creation-workspace">
    <Heading title="数字人口播" helper="选择模板，放入文案、声音和人物图片。"><Button href="/task-center">查看任务进度与结果</Button></Heading>
    <AvatarDefaultsSummary data={preset} loading={presetLoading} error={presetError} sessions={sessions} onEdit={()=>setPresetOpen(true)} busy={saving||importing||draftLoading||inProgress} hasDraft={!!serverDraft||restoredDraft.current} onApply={()=>{presetHandled.current=true;void applyPreset(preset,{newTask:!!serverDraft||restoredDraft.current});}}/>
    <p className="helper">本次使用：{template.name} · {input.soundMode==='audio'?'已选音频（不重复配音）':`${selectedVoice?.name||'待选音色'} · ${input.rate}倍速`}。{restoredDraft.current?'当前草稿沿用原参数。':'本次明确修改的参数优先。'}</p>
    <div className="editor-shell avatar-editor"><section className="editor-content" aria-label="填写制作内容" aria-busy={draftLoading}>
      <AvatarTemplatePicker templateId={input.templateId} motion={isN1?null:input.motion} onChoose={choice=>{update({...choice,ai:{...AI_DEFAULTS,...input.ai,enabled:choice.templateId===N1_TEMPLATE_ID?false:choice.motion?true:input.ai?.enabled||false}});setSamplePlaying(false);setStoryboard(null);}}/>
      <div className="avatar-fields">
        <Step number="1" title="文案" helper="上传文案或直接粘贴内容" className="text-step" action={<div className="upload-text"><Button disabled={importing||draftLoading} loading={importing} onClick={()=>textUpload.current.click()}><Upload size={16}/>上传文案</Button><span>DOCX / TXT</span></div>}>
          <label className="sr-only" htmlFor="script-text">口播文案</label><div className="textarea-wrap"><textarea id="script-text" ref={textArea} value={input.text} disabled={draftLoading||importing} onChange={e=>update({text:e.target.value})} placeholder="粘贴你的口播文案…" aria-invalid={error?.field==="text"}/><small className="character-count">{[...input.text].length.toLocaleString()} / 5,000</small></div>
        </Step>
        <Step number="2" title="声音" helper="使用已有音频，或选择海客音色配音" className="sound-step">
          <div className="sound-tabs" role="group" aria-label="声音来源"><button aria-pressed={input.soundMode==="audio"} className={input.soundMode==="audio"?"active":""} onClick={()=>update({soundMode:"audio"})}>使用音频</button><button aria-pressed={input.soundMode==="voice"} className={input.soundMode==="voice"?"active":""} onClick={()=>update({soundMode:"voice"})}>选择音色配音</button></div>
          {input.soundMode==="audio" ? <><div className="audio-row"><div className="audio-file"><Music2 size={20}/><div><strong>{input.audio?.name||"尚未选择音频"}</strong><small>{audioTime}</small></div></div><Button onClick={playAudio} disabled={!input.audio} aria-label={playing?"暂停音频":"播放音频"}>{playing?<Pause size={16}/>:<Play size={16}/>}</Button><Button onClick={()=>setModal("audio")}>选择 / 上传音频</Button></div><p className="helper after-input">已有音频直接用于制作，不重复生成配音。最长120秒。</p></> :
          <><Field label="海客音色"><select value={input.voiceId} onChange={e=>{const voice=voices.find(v=>v.id===e.target.value);if(voice)update({voiceId:voice.id,modelId:voice.model,rate:voice.rate,requiresVoiceSelection:false});}} disabled={voiceStatus!=="ready"}><option value="">{voiceStatus==='loading'?'正在读取音色…':'请选择音色'}</option>{input.voiceId&&!selectedVoice&&<option value={input.voiceId} disabled>已保存音色不可用 · 请重新选择</option>}{voices.map(v=><option key={v.id} value={v.id}>{v.name} · {v.kind==='public'?'公共音色':'我的音色'}</option>)}</select></Field>{input.modelId==='haike/tencent-tts'&&<Notice message="此草稿的旧配音服务已停用。请选择海客音色，或切换到上传音频后继续。"/>}<div className="avatar-voice-actions"><Button onClick={()=>openAudioCenter(input.voiceId)}>管理音色与克隆声音</Button>{selectedVoice&&voiceImageUrl(selectedVoice)&&<Button onClick={useLinkedPortrait} disabled={importing}>使用关联人物图</Button>}<p className="helper">生成前先确认报价；已有音频不产生配音费。关联人物图需明确采用后才会替换当前图片。</p></div></>}
        </Step>
        <Step number="3" title="人物图片" helper="人物正面清晰，JPG / PNG" className="portrait-step">
          <div className="portrait-row"><img src={portraitUrl} alt={input.portrait?'已选择的人物图片':'通用人物示意，请上传图片'}/><div className="portrait-description"><strong>{input.portrait?.name||"尚未上传图片"}</strong><small>至少256 × 256像素</small></div><Button onClick={()=>portraitUpload.current.click()}><Upload size={16}/>上传 / 更换图片</Button></div>
          <PortraitRefinement key={input.portrait?.id||'no-portrait'} draftId={serverDraft?.id} portrait={input.portrait} onPending={setRefinementPending} onAdopt={(d,sourceId)=>{if(selectedPortraitId.current!==sourceId)return;setServerDraft(d);update({portrait:d.input.portrait});setToast('已采用优化图，原图保留在项目中。');}}/>
        </Step>
      </div>
      <NetworkMaterialChoice enabled={input.network_materials_enabled} onChange={network_materials_enabled=>{update({network_materials_enabled});setStoryboard(null);}} busy={saving||draftLoading||inProgress} sessions={sessions}/>
      {isN1?<N1Settings value={input.n1} title={input.title} onTitle={title=>update({title})} onChange={n1=>update({n1})} onFile={importN1Material} busy={saving||draftLoading||importing} audioDuration={input.soundMode==='audio'?Number(input.audio?.duration):undefined}/>:<AiMaterials value={input.ai} networkRequired={input.network_materials_enabled===true} networkPolicyExplicit={typeof input.network_materials_enabled==='boolean'} busy={saving||draftLoading} onFile={importMaterial} onPlan={planPreview} onChange={ai=>{update({ai});setStoryboard(null);}} plan={storyboard}/>}
      <section className="more-settings"><button className="settings-toggle" onClick={()=>setMore(!more)} aria-expanded={more} aria-controls="more-fields"><ChevronDown size={18} className={more?'':'collapsed'}/><strong>{isN1?'字幕与声音设置':'模板排版配置'}</strong><span>{isN1?'字幕与配音倍率':'标题、字号、强调色与字幕'}</span></button>
        {more&&<div id="more-fields" className="settings-fields">{!isN1&&<><Field label="视频标题"><input value={input.title} maxLength={36} placeholder="自动取文案首句，建议16字以内" onChange={e=>update({title:e.target.value})}/></Field><div className="layout-fields"><Field label="标题字号"><select value={layout.title_size} onChange={e=>updateLayout({title_size:Number(e.target.value)})}>{[48,54,60,66].map(n=><option key={n} value={n}>{n}px</option>)}</select></Field><Field label="强调色"><input type="color" value={layout.accent} onChange={e=>updateLayout({accent:e.target.value})}/></Field></div></>}<label className="checkbox-row"><input type="checkbox" checked={input.subtitles} onChange={e=>update({subtitles:e.target.checked})}/>显示字幕</label>{input.soundMode==="voice"&&<Field label="配音倍率"><input type="number" min="0.5" max="2" step="0.05" value={input.rate} onChange={e=>update({rate:Number(e.target.value)})}/></Field>}<p className="helper">画幅和人物位置跟随模板；配置效果在生成后查看。</p><Button variant="text" onClick={resetTemplate}>{isN1?'恢复默认版式':'载入示例内容'}</Button></div>}
      </section>
      <div className="notice-stack avatar-notices"><Notice message={internal?'内部备用服务，按每次报价确认':''}/><Notice message={error?.message} error/>{blocked&&<Notice message={blocked} error={accountState!==null}><a href="/settings">查看 API 设置<ArrowRight size={14}/></a></Notice>}</div>
      {job&&<div className="job-state"><strong>{({queued:'排队中',running:'正在制作',completed:'已合成 · 待审核',failed:'需要处理',canceled:'已取消'})[job.status]||job.status}</strong><p>{job.stage}</p>{job.result?.work_id&&<Button href="/projects">观看并审核成片</Button>}{job.retryable&&<Button disabled={saving} onClick={retry}>恢复原任务</Button>}{!input.network_materials_enabled&&job.status==='failed'&&/抖音/.test(job.stage)&&<Button disabled={saving} onClick={skipDouyin}>跳过抖音并恢复原任务</Button>}</div>}
      <DouyinRecovery job={job} onJob={setJob}/>
    </section><PreviewPanel label="模板效果预览" metadata={!isN1&&input.motion?(input.motion.layout==='portrait'?'9:16':'16:9'):template.ratio}>{!isN1&&input.motion?<><div className="poster-frame"><img src={motionPreview||assetPath(template.poster)} alt={`${input.motion.style} · 版式参考`}/></div><p className="preview-note">上游风格参考；AI按本期原文、素材与实际时钟安排动作。</p><Button href="/avatar?mode=motion">进入专业分镜编辑</Button></>:<TemplatePreview template={template} onPlay={()=>{setModal('sample');setSamplePlaying(true);}}/>}</PreviewPanel>
    <ActionBar note={<span><Info size={16}/> {blocked||(refinementPending?'请先选择优化图或原图':'生成前确认本次调用费用')}</span>}><Button disabled={saving||draftLoading||importing} loading={saving&&modal!=="confirm"} onClick={saveDraft}>{saved?"草稿已保存":"保存草稿"}</Button><Button variant="primary" disabled={importing||saving||draftLoading||inProgress||!!blocked||refinementPending} onClick={confirmGeneration}>生成数字人口播<ArrowRight size={17}/></Button></ActionBar></div>
    <input hidden type="file" ref={textUpload} accept=".txt,.docx" onChange={importText} aria-label="文案文件"/><input hidden type="file" ref={audioUpload} accept=".wav,.mp3,.m4a,.ogg" onChange={importAudio} aria-label="音频文件"/><input hidden type="file" ref={portraitUpload} accept="image/jpeg,image/png" onChange={importPortrait} aria-label="人物图片文件"/>
    <audio ref={audio} src={input.soundMode==="audio"?audioUrl:undefined} onEnded={()=>setPlaying(false)} onError={()=>setPlaying(false)}/>
    <div className={`toast ${toast?"visible":""}`} role="status">{toast&&<><CheckCircle2 size={18}/>{toast}</>}</div>
    {modal==="sample"&&<TemplateSampleDialog template={template} autoPlay={samplePlaying} onClose={()=>{setModal(null);setSamplePlaying(false);}}/>}
    {modal==="audio"&&<Modal title="选择音频" description="使用已有口播录音，无需重复生成配音。" onClose={()=>setModal(null)} footer={<><Button onClick={()=>setModal(null)}>取消</Button><Button variant="primary" onClick={()=>audioUpload.current.click()}><Upload size={17}/>上传音频</Button></>}>{hasAvatarAsset(input.audio)?<div className="library-audio"><Music2 size={24}/><span><strong>{input.audio.name}</strong><small>当前已选择的口播音频</small></span></div>:<p className="helper">请上传你的口播录音后继续。</p>}<p className="helper">支持WAV、MP3、M4A、OGG；50 MB以内，最长120秒。</p></Modal>}
    {modal==="confirm"&&quote&&<Modal title="生成确认与费用" description="核对模板、素材与本次调用上限。" busy={saving} onClose={()=>setModal(null)} footer={<><Button disabled={saving} onClick={()=>setModal(null)}>返回修改</Button><Button variant="primary" loading={saving} onClick={saveRequest} disabled={Number(budget)<=0||!Number.isFinite(Number(budget))}>确认费用并生成<ArrowRight size={17}/></Button></>}>
      <dl className="summary-list"><div><dt>模板</dt><dd>{template.name} · {template.ratio}</dd></div><div><dt>声音</dt><dd>{input.soundMode==="audio"?input.audio.name:voices.find(v=>v.id===input.voiceId)?.name}</dd></div><div><dt>人物</dt><dd>{input.portrait.name}</dd></div>{quote.items.map(q=><div key={q.stage}><dt>{({tts:'配音',avatar:'数字人',asr:'字幕识别'})[q.stage]}</dt><dd>{internal||q.estimate_only?'采购估算':'上限'} ¥{(q.max_charge_micros/1000000).toFixed(4)}</dd></div>)}</dl>
      {estimateBilling&&quote.items.filter(q=>q.provider||q.provider_model).map(q=><section key={q.stage}><strong>{({tts:'配音',avatar:'数字人',asr:'字幕识别'})[q.stage]}</strong><QuoteBilling quote={q} internal/></section>)}{estimateBilling&&<p className="helper">{quote.billing_note||'费用为供应商采购估算，不代表供应商账单硬封顶。每项调用以当次确认的服务与预算执行。'}</p>}{quote.needs_audio_quote&&<p className="helper">{estimateBilling?'数字人与字幕按配音实际时长再次报价；超出批准预算将停止，保留已完成配音。':'数字人与字幕按配音实际时长报价，超出剩余上限即停止，保留已完成配音。'}</p>}
      {quote.ai_trial&&<p className="helper">制作前核对素材分析与分镜结果，画面素材按本次选择采用；最终成片仍需观看审核。</p>}
      <Field label={estimateBilling?'本次批准采购预算（元）':'本次全部调用费用上限（元）'}><input type="number" min=".01" max="1000" step=".01" value={budget} disabled={saving} onChange={e=>setBudget(e.target.value)}/></Field><p className="helper">{estimateBilling?'确认后将提交真实供应商调用；本地排版不收费，采购估算与实际扣费可能不同。':'确认后将提交真实收费调用；本地排版不收费。实际费用与冻结额度可到账户中心查看。'}</p>
    </Modal>}
    {modal==="saved"&&<Modal title="制作任务已提交" onClose={()=>setModal(null)} footer={<Button variant="primary" onClick={()=>setModal(null)}>查看进度<ArrowRight size={17}/></Button>}><div className="success-content"><CheckCircle2 size={36}/><h3>已进入制作队列</h3><p>完成后从我的作品观看并审核成片。中断时恢复原任务，保留已完成的模型调用。</p></div></Modal>}
    {presetOpen&&<AvatarDefaultsDialog onClose={()=>setPresetOpen(false)}/>}
  </main>;
}
