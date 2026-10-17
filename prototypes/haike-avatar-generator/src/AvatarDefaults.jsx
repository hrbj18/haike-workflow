import {useEffect,useRef,useState} from 'react';
import {RefreshCw,Settings2,Upload} from 'lucide-react';
import {Button,Dialog,Field,Notice} from './ui.jsx';
import {AUDIO_CENTER_API} from './audio-center-model.js';
import {avatarDefaultsDraft,avatarDefaultsPayload,requestAvatarDefaults} from './avatar-defaults-model.js';
import {MaterialLoginSummary,usePlatformSessions} from './PlatformAccounts.jsx';
import './avatar-defaults.css';

const labels={voice_id:'默认音色',portrait_file_id:'默认形象',speech_rate:'配音倍速',template_id:'默认模板',target_duration_seconds:'目标时长',max_charge_micros:'每条预算上限',allow_graphic_fallback:'图文配音降级选择'};

export function AvatarDefaultsFields({data,draft,setDraft,onUpload,busy=false,sessions}) {
  const upload=useRef(null),voice=data.voices?.find(item=>item.id===draft.voice_id);
  const patch=value=>setDraft(current=>({...current,...value}));
  return <fieldset className="avatar-defaults-fields" disabled={busy}>
    <div className="avatar-defaults-grid">
      <Field label="默认音色"><select value={draft.voice_id} onChange={event=>patch({voice_id:event.target.value})}><option value="">未设置</option>
        {(data.voices||[]).map(item=><option key={item.id} value={item.id} disabled={!item.available}>{item.name}{!item.available?'（暂不可用）':''}</option>)}
        {draft.voice_id&&!voice&&<option value={draft.voice_id}>已保存音色（待核对）</option>}</select></Field>
      <Field label="配音倍速" hint="0.5至2.0；只影响后续采用此预设的新任务。"><input type="number" min="0.5" max="2" step="0.05" placeholder="未设置" value={draft.speech_rate} onChange={event=>patch({speech_rate:event.target.value})}/></Field>
      <Field label="默认模板"><select value={draft.template_id} onChange={event=>patch({template_id:event.target.value})}><option value="">未设置</option>{(data.templates||[]).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
      <Field label="目标时长（秒）" hint="1至120秒，用于规划；成片仍以实际配音为准。"><input type="number" min="1" max="120" step="1" placeholder="未设置" value={draft.target_duration_seconds} onChange={event=>patch({target_duration_seconds:event.target.value})}/></Field>
      <Field label="每条预算上限（元）" hint="最多六位小数；留空表示未设置，需在执行前补全。"><input inputMode="decimal" placeholder="未设置" value={draft.budget} onChange={event=>patch({budget:event.target.value})}/></Field>
      <Field label="允许图文配音降级" hint="数字人不可用时允许改做图文配音，仍受本条预算约束。"><select value={draft.allow_graphic_fallback} onChange={event=>patch({allow_graphic_fallback:event.target.value})}><option value="">未设置</option><option value="allow">允许</option><option value="deny">不允许</option></select></Field>
    </div>
    <section className="avatar-defaults-network"><label className="checkbox-row"><input type="checkbox" checked={draft.network_materials_enabled===true} onChange={event=>patch({network_materials_enabled:event.target.checked})}/><strong>默认联网搜索画面素材</strong></label>
      <p className="helper">开启后搜索并采用相关网络画面；找不到合适素材时明确暂停，等待补充。与图文配音降级分别生效。</p>
      {draft.network_materials_enabled&&<MaterialLoginSummary {...sessions}/>}</section>
    <section className="avatar-defaults-portrait"><div><strong>默认形象</strong><p className="helper">上传已获授权的人物图，或明确采用所选音色的关联图。</p>
      <div className="avatar-defaults-actions"><Button onClick={()=>upload.current.click()}><Upload size={15}/>上传人物图</Button>
        {voice?.image_file_id&&<Button onClick={()=>patch({portrait_file_id:voice.image_file_id})}>采用音色关联图</Button>}
        {draft.portrait_file_id&&<Button onClick={()=>patch({portrait_file_id:''})}>清除形象</Button>}</div>
      <input ref={upload} type="file" accept=".png,.jpg,.jpeg,.webp" hidden aria-label="上传默认形象" onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file)onUpload(file);}}/>
      </div>{draft.portrait_file_id?<img src={`${AUDIO_CENTER_API}/media/${encodeURIComponent(draft.portrait_file_id)}`} alt="当前账号的默认形象"/>:<span className="helper">未设置人物图，可在单次任务中指定</span>}</section>
    <p className="helper">可以先保存不完整设置；必需项未补全时不会将预设标为可执行。明确指令优先，历史任务保留创建时的参数。</p>
  </fieldset>;
}

export function AvatarDefaultsDialog({onClose}) {
  const sessions=usePlatformSessions();
  const [data,setData]=useState(null),[draft,setDraft]=useState(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const alive=useRef(false),active=useRef(null),working=useRef(false);
  async function load() {
    if(active.current)return;
    const controller=new AbortController();active.current=controller;setLoading(true);setError('');
    try {const value=await requestAvatarDefaults({signal:controller.signal}),next=avatarDefaultsDraft(value);
      if(alive.current&&!controller.signal.aborted){setData(value);setDraft(next);}}
    catch(e){if(alive.current&&!controller.signal.aborted)setError(e.message||'默认设置读取失败，请重新读取。');}
    finally {if(active.current===controller){active.current=null;if(alive.current)setLoading(false);}}
  }
  useEffect(()=>{alive.current=true;void load();return()=>{alive.current=false;active.current?.abort();};},[]);
  async function save(event) {
    event.preventDefault();if(working.current)return;
    let body;try {body=avatarDefaultsPayload(draft);}catch(e){setError(e.message);return;}
    working.current=true;setBusy(true);setError('');setNotice('');
    try {const value=await requestAvatarDefaults({body}),next=avatarDefaultsDraft(value);if(alive.current){setData(value);setDraft(next);setNotice(value.ready?'默认设置已保存；仅影响后续采用此预设的新任务。':'默认设置已保存，开始任务前仍需补全未设置的参数。');window.dispatchEvent(new Event('haike:avatar-defaults-changed'));}}
    catch(e){if(alive.current)setError(e.status===409?'账号或设置版本已变化，请重新读取后核对；当前编辑内容仍保留。':`${e.message} 保存结果未确认时，请重新读取后核对。`);}
    finally {working.current=false;if(alive.current)setBusy(false);}
  }
  async function upload(file) {
    if(working.current)return;
    if(!/\.(png|jpe?g|webp)$/i.test(file.name)||!file.size||file.size>10*1024*1024){setError('请选择10MB以内的PNG、JPG或WebP人物图片。');return;}
    working.current=true;setBusy(true);setError('');setNotice('');
    try {const response=await fetch(`${AUDIO_CENTER_API}/upload?${new URLSearchParams({kind:'image',filename:file.name})}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
      const value=await response.json();if(!response.ok||typeof value.id!=='string')throw new Error(value.detail||'人物图上传未完成。');
      if(alive.current){setDraft(current=>({...current,portrait_file_id:value.id}));setNotice('人物图已上传，请保存默认设置。');}}
    catch(e){if(alive.current)setError(e.message||'人物图上传未完成，请重试。');}
    finally {working.current=false;if(alive.current)setBusy(false);}
  }
  return <Dialog title="数字人口播默认设置" description="未在单次指令中指定的参数，使用已保存的预设。" wide busy={busy} onClose={onClose}
    footer={<><Button disabled={busy||loading} onClick={load}><RefreshCw size={15}/>重新读取</Button><Button disabled={busy} onClick={onClose}>关闭</Button><Button type="submit" form="avatar-defaults-form" variant="primary" loading={busy} disabled={!draft||loading}>保存默认设置</Button></>}>
    <Notice message={error} error/><Notice message={notice}/>
    {data&&<p className="helper">{data.scope_type==='local_machine'?'仅保存到本机内部服务。':'按当前海客账号保存；同账号更换Key保留预设。'} 保存不会开始制作或发布。</p>}
    {draft?<form id="avatar-defaults-form" onSubmit={save}><AvatarDefaultsFields data={data} draft={draft} setDraft={setDraft} onUpload={upload} busy={busy||loading} sessions={sessions}/>
      {data.missing_fields?.length>0&&<p className="helper">上次读取尚待配置：{data.missing_fields.map(key=>labels[key]||'参数').join('、')}。</p>}</form>:
      <p role="status">{loading?'正在读取当前账号的默认设置…':'暂时无法读取默认设置；没有覆盖已有预设。'}</p>}
  </Dialog>;
}

export function AvatarDefaultsSummary({data,loading=false,error='',onEdit,onApply,busy=false,hasDraft=false,sessions}) {
  const v=data?.values||{},voice=data?.voices?.find(item=>item.id===v.voice_id),template=data?.templates?.find(item=>item.id===v.template_id);
  return <section className="surface avatar-preset-summary" aria-label="数字人口播默认设置">
    <div className="avatar-preset-heading"><div><h2><Settings2 size={19}/> 默认设置</h2><p className="helper">新任务采用预设，明确指定的参数优先；已有草稿和任务保持原参数。</p></div>
      <div className="avatar-defaults-actions"><Button onClick={onEdit}>编辑默认设置</Button><Button disabled={busy||!data?.ready} onClick={onApply}>{hasDraft?'新建并采用预设':'采用默认设置'}</Button></div></div>
    {loading?<p role="status">正在读取当前账号预设…</p>:error?<p role="alert">{error}</p>:<>
      <p className="avatar-preset-values">{voice?.name||'音色未设置'} · {v.speech_rate==null?'倍速未设置':`${v.speech_rate}倍速`} · {template?.name||'模板未设置'} · {v.target_duration_seconds==null?'目标时长未设置':`目标${v.target_duration_seconds}秒`} · {v.max_charge_micros==null?'预算未设置':`每条上限${v.max_charge_micros/1000000}元`} · {v.allow_graphic_fallback===true?'允许图文备用':v.allow_graphic_fallback===false?'保留数字人形式':'备用路线未设置'}</p>
      <p className="helper">联网画面素材：{v.network_materials_enabled===true?'默认开启 · 无合适素材时等待补充':'默认关闭'}</p>
      {v.network_materials_enabled===true&&<MaterialLoginSummary {...sessions}/>}
      {!data?.ready&&<p className="helper">预设尚未完整，编辑后可用于新任务；不会自动开始制作或收费。</p>}</>}
  </section>;
}

export function AvatarDefaultsSettings() {
  const [open,setOpen]=useState(false);
  useEffect(()=>{const changed=()=>setOpen(false);window.addEventListener('haike:gateway-changed',changed);return()=>window.removeEventListener('haike:gateway-changed',changed);},[]);
  return <><section className="surface audio-settings-entry"><div><h2><Settings2 size={20}/> 数字人口播默认设置</h2><p className="helper">形象、音色、倍速、模板、预算与联网素材。明确指令优先；保存不会开始制作或发布。</p></div><Button onClick={()=>setOpen(true)}>编辑默认设置</Button></section>
    {open&&<AvatarDefaultsDialog onClose={()=>setOpen(false)}/>}</>;
}
