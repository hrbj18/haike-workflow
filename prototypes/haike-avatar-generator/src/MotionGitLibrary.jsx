import {useEffect,useState} from 'react';
import {api} from './studio-api.js';
import {Button,Notice} from './ui.jsx';
import {HallmarkDirections} from './HallmarkDirections.jsx';
import './motiongit-library.css';

const base='/api/studio/motiongit';
const labels={kicker:'上方小字',lines:'文字行',items:'内容项',src:'素材文件',thumbnail:'缩略图文件',sourceStart:'素材开始秒数',caption:'卡片说明',title:'标题',sub:'补充说明',text:'正文',word:'关键词',audio:'原片声音',hide:'隐藏人物',face:'人物构图（可选）',cx:'水平中心比例',cy:'垂直中心比例',w:'宽度比例',h:'高度比例',framing:'人物取景',callouts:'画面标注',x:'横向位置',y:'纵向位置',label:'标签',value:'数值',from:'开始帧',frames:'持续帧数',mode:'出镜方式',id:'编号',brand:'品牌',footer:'页脚',palette:'配色',fontAssets:'字体文件',display:'标题字体',body:'正文字体',presenter:'人物来源',presenterModes:'人物出镜安排',media:'素材清单',scenes:'场景清单',captions:'字幕时钟',durationFrames:'全片帧数',offset:'素材入点秒数',fit:'画面适配',orientation:'素材方向',module:'效果模块',theme:'主题',subtitle:'说明',mediaId:'主素材编号',secondaryMediaId:'副素材编号',selection:'选择动效时点',wallMediaIds:'素材墙卡片编号',cursorFrom:'光标开始帧',selectFrom:'选中开始帧',expandFrom:'放大开始帧',holdFrom:'稳定阅读开始帧',startMs:'字幕开始毫秒',endMs:'字幕结束毫秒',objectPosition:'素材对齐位置'};
const initialValue=s=>s?.default!==undefined?s.default:s?.enum?s.enum[0]:s?.type==='object'?Object.fromEntries(Object.entries(s.properties||{}).filter(([k,v])=>s.required?.includes(k)||v.default!==undefined).map(([k,v])=>[k,initialValue(v)])):s?.type==='array'?[]:s?.type==='boolean'?false:['number','integer'].includes(s?.type)?s.minimum||0:'';

function Field({label,schema={},value,onChange,depth=0}){
  if(schema.enum)return <label className="mg-field">{label}<select value={value??''} onChange={e=>onChange(schema.enum.find(v=>String(v)===e.target.value))}>{schema.enum.map((v,i)=><option key={String(v)} value={String(v)}>{schema.enumTitles?.[i]||String(v)}</option>)}</select></label>;
  if(schema.type==='boolean'||typeof value==='boolean')return <label className="mg-field"><span>{label}</span><input type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/></label>;
  if(schema.type==='object'||value&&typeof value==='object'&&!Array.isArray(value)){
    const keys=[...new Set([...Object.keys(schema.properties||{}),...Object.keys(value||{})])];
    return <fieldset className="mg-object"><legend>{label}</legend>{keys.map(k=><Field key={k} label={schema.properties?.[k]?.title||schema.properties?.[k]?.label||labels[k]||k} schema={schema.properties?.[k]||{}} value={value?.[k]} depth={depth+1} onChange={v=>onChange({...value,[k]:v})}/>)}</fieldset>;
  }
  if(schema.type==='array'||Array.isArray(value))return <fieldset className="mg-object"><legend>{label}</legend>{(value||[]).map((v,i)=><div className="mg-array" key={i}><Field label={`${i+1}`} schema={schema.items||{}} value={v} depth={depth+1} onChange={next=>onChange(value.map((old,j)=>j===i?next:old))}/><Button onClick={()=>onChange(value.filter((_,j)=>j!==i))}>移除</Button></div>)}<Button onClick={()=>onChange([...(value||[]),initialValue(schema.items||{})])}>添加一项</Button></fieldset>;
  const number=['number','integer'].includes(schema.type)||typeof value==='number';
  return <label className="mg-field"><span>{label}</span>{number?<input type="number" step={schema.type==='integer'?1:'any'} value={value??''} min={schema.minimum} max={schema.maximum} onChange={e=>onChange(e.target.value===''?'':Number(e.target.value))}/>:<textarea rows={depth<2?2:1} value={value??''} onChange={e=>onChange(e.target.value)}/>}<small>{schema.description}</small></label>;
}

function controlSchema(c){
  function field(s){return {...s,type:s.type==='media'?'string':s.type==='enum'?'string':s.type,enum:s.values,properties:s.props?Object.fromEntries(Object.entries(s.props).map(([k,v])=>[k,field(v)])):undefined,items:s.of?field({type:s.of,props:s.props}):undefined};}
  return {type:'object',properties:Object.fromEntries(Object.entries(c.props||{}).map(([k,v])=>[k,field(v)])),required:Object.entries(c.props||{}).filter(([,v])=>v.required).map(([k])=>k)};
}

function HumProductionFields({parameters:p,onChange,assets,onUpload,onImport,busy}){
  const props=p.props||{},audio=p.audio||{};
  const bound=new Map(assets.map(a=>[a.slot,a]));
  const setProps=next=>onChange({...p,props:{...props,...next}});
  const setAudio=next=>onChange({...p,audio:{...audio,...next}});
  function upload(label,slot,accept){return <label className="mg-upload">{label}{bound.has(slot)?' · 已绑定':''}<input type="file" disabled={busy||!slot} accept={accept} onChange={e=>{onUpload(e.target.files[0],slot);e.target.value='';}}/></label>;}
  const clips=props.presenterClips||[];
  const modes=props.presenterModes||[];
  const uniform=modes.length&&modes.every(m=>m.mode===modes[0].mode)?modes[0].mode:'custom';
  return <section className="mg-hum-inputs"><h4>完整口播模板 · 4:5</h4><p>时长跟随整条口播自动计算。保留级联入场、同卡点击展开、配乐和音效；素材不足时会指出需要补充的镜头。</p>
    <div className="mg-two"><Field label="视觉风格" schema={{enum:['hum','coral'],enumTitles:['Hum · 亲子剪纸','Coral · 温暖棉纸']}} value={props.visualStyle} onChange={v=>setProps({visualStyle:v})}/><Field label="品牌" value={props.brand} onChange={v=>setProps({brand:v})}/></div>
    <Field label="片尾邀请 / 页脚" value={props.footer} onChange={v=>setProps({footer:v})}/>
    <div className="mg-two"><Field label="口播绑定文件名" value={audio.voice} onChange={v=>setAudio({voice:v})}/><Field label="配乐绑定文件名" value={audio.music||''} onChange={v=>setAudio({music:v})}/></div>
    <div className="mg-actions">{upload('换完整口播',audio.voice,'.wav')}{audio.music&&upload('换配乐',audio.music,'.wav,.mp3,.m4a')}<label className="mg-upload">导入本期制作参数<input type="file" disabled={busy} accept=".json" onChange={e=>{onImport(e.target.files[0]);e.target.value='';}}/></label></div>
    <p>换口播时，一并更新实际字幕时码和人物同源片段。制作参数可直接由 Agent 根据新脚本生成，再在下方完整 JSON 中调整镜头、标题、字幕与音效时点。</p>
    <div className="mg-hum-cards">{(props.media||[]).map(m=><div className="mg-hum-card" key={m.id}><strong>{m.label||m.id}</strong><small>{m.id} · {m.src}</small><div className="mg-actions">{upload('换这张卡素材',m.src,'.mp4,.mov,.m4v,.png,.jpg,.jpeg,.webp')}{upload('换卡片封面',m.thumbnail,'.png,.jpg,.jpeg,.webp')}</div></div>)}</div>
    {clips.length>0?<><Field label="人物出镜" schema={{enum:['custom','large','small','hidden'],enumTitles:['沿用逐段安排','片段内大框','片段内小框','全程不出镜']}} value={uniform} onChange={mode=>{if(mode!=='custom')setProps({presenterModes:clips.map(c=>({clipId:c.id,from:c.from,frames:c.frames,mode})).sort((a,b)=>a.from-b.from)});}}/><div className="mg-actions">{clips.map(c=><span key={c.id}>{upload(`换人物 ${c.id}`,c.src,'.mp4,.mov,.m4v')}</span>)}</div></>:<p>当前为不出镜模板；需要人物时，在完整参数中绑定大框、小框或逐段出镜安排。</p>}
    <p>字体与音效也使用下方“导入口播／素材”上传，文件绑定名和完整参数保持一致。更换素材后需重新核对内容与取段。</p>
  </section>;
}

function Production({draft,save,assetRevision}){
  const [job,setJob]=useState(null),[bound,setBound]=useState(null),[view,setView]=useState(null),[message,setMessage]=useState(''),[opened,setOpened]=useState([]),[reviewed,setReviewed]=useState(false),[pending,setPending]=useState(false);
  const signature=JSON.stringify([draft.parameters,draft.output_profile,draft.title,assetRevision]);
  useEffect(()=>{setJob(null);setBound(null);setView(null);setOpened([]);setReviewed(false);},[signature]);
  useEffect(()=>{if(draft.id)api(`${base}/drafts/${draft.id}/productions`).then(v=>{const previous=v.productions[0];if(previous?.job){setBound(previous);setJob(previous.job);}}).catch(e=>setMessage(e.message));},[draft.id,draft.revision,assetRevision]);
  useEffect(()=>{if(!job||['completed','failed','cancelled'].includes(job.status))return;const timer=setInterval(async()=>{try{setJob(await api(`${base}/jobs/${job.job_id}`));}catch(e){setMessage(e.message);}},2000);return()=>clearInterval(timer);},[job?.job_id,job?.status]);
  useEffect(()=>{if(job?.status==='completed'&&bound)api(`${base}/productions/${bound.project_id}/${bound.render_id}`).then(v=>{setView(v);setReviewed(v.reviewed);}).catch(e=>setMessage(e.message));},[job?.status,bound]);
  async function produce(phase){setPending(true);setMessage('');try{const d=await save();const v=await api(`${base}/drafts/${d.id}/produce`,{revision:d.revision,phase,render_id:d.revision===draft.revision?bound?.render_id:undefined});setBound(v);setJob(v.job);}catch(e){setMessage(e.message);}finally{setPending(false);}}
  async function review(){setPending(true);try{await api(`${base}/productions/${bound.project_id}/${bound.render_id}/review`,{preview_sha256:view.preview_sha256,reviewer:'workbench-user',inspected_images:view.images.map(i=>i.name)});setReviewed(true);setMessage('本期预览抽样已确认，连续播放与听审仍在成片阶段完成。');}catch(e){setMessage(e.message);}finally{setPending(false);}}
  return <section className="mg-production"><h4>预览与成片</h4><p>制作进入现有统一队列。画面变更后生成新的预览与版本。</p><div className="mg-actions"><Button disabled={pending} onClick={()=>produce('preview')}>生成本期预览</Button>{draft.workflow==='poster-kit'&&<Button disabled={pending||!reviewed} onClick={()=>produce('render')}>导出成片</Button>}</div>{job&&<p role="status">{job.stage} · {job.status}{job.status==='paused'?'（生产队列忙时稍后重试原草稿）':''}</p>}<Notice message={message}/>{view?.sample&&<video controls preload="metadata" src={view.sample} style={{maxWidth:'100%',maxHeight:600}}/>}
  {view?.sample&&<p><a href={view.sample} download={`${draft.title}.mp4`}>下载当前成片</a>{view.nomusic&&<> · <a href={view.nomusic} download={`${draft.title}-无配乐.mp4`}>下载无配乐备选（保留口播与音效）</a></>}</p>}
  {view?.images?.length>0&&<><p>静态预览：逐张打开检查文字、素材完整性与字幕。此处不代表已连续观看动效。</p><div className="mg-preview-grid">{view.images.map(i=><button key={i.name} onClick={()=>{window.open(i.url,'_blank','noopener');setOpened(old=>[...new Set([...old,i.name])]);}}><img loading="lazy" src={i.url} alt={i.name}/><span>{i.name}{opened.includes(i.name)?' · 已打开':''}</span></button>)}</div><Button disabled={pending||opened.length!==view.images.length||reviewed} onClick={review}>{reviewed?'本期预览已确认':'已检查全部预览，确认抽样画面'}</Button></>}
  </section>;
}

export function MotionGitLibrary(){
  const [packages,setPackages]=useState([]),[selected,setSelected]=useState(null),[workflow,setWorkflow]=useState('native'),[draft,setDraft]=useState(null),[saved,setSaved]=useState([]),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[assets,setAssets]=useState([]),[control,setControl]=useState(''),[raw,setRaw]=useState('');
  async function refresh(){const [p,d]=await Promise.all([api(`${base}/packages`),api(`${base}/drafts`)]);setPackages(p.packages);setSaved(d.drafts);}
  useEffect(()=>{refresh().catch(e=>setMessage(e.message));},[]);
  useEffect(()=>{if(draft?.id)api(`${base}/drafts/${draft.id}/assets`).then(v=>setAssets(v.assets)).catch(e=>setMessage(e.message));},[draft?.id]);
  async function run(fn){setBusy(true);setMessage('');try{await fn();}catch(e){setMessage(e.message);}finally{setBusy(false);}}
  async function importFile(file){if(!file)return;await run(async()=>{const response=await fetch(`${base}/packages?${new URLSearchParams({filename:file.name})}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const p=await response.json();if(!response.ok)throw new Error(p.detail||'导入未完成');setSelected(p);setDraft(null);await refresh();setMessage('原包已私有保存，导入阶段未执行模板。');});}
  async function verify(){await run(async()=>{const p=await api(`${base}/packages/${selected.id}/verify`,{});setSelected(p);await refresh();setMessage('身份已核验，已读取此包实际开放的参数和控件。');});}
  function create(w){setWorkflow(w);setAssets([]);setRaw('');const s=selected.workflows[w].schema;const parameters=w==='poster-kit'?{duration:20,layout:'landscape',language:'zh',voiceover:'',music:'',presenter:{hide:true},segments:[],captions:[]}:initialValue(s);setDraft({package_id:selected.id,workflow:w,revision:0,title:'店长账号新视频',output_profile:w==='hum-production'?'4:5':'native',parameters});}
  const route=selected?.workflows?.[workflow];
  const p=draft?.parameters;
  const change=parameters=>setDraft({...draft,parameters});
  async function save(){const old=saved.find(d=>d.id===draft.id);if(old&&JSON.stringify(old)===JSON.stringify(draft))return draft;const next=await api(`${base}/drafts`,draft);setDraft(next);await refresh();setMessage(`草稿第${next.revision}版已保存。`);return next;}
  async function uploadAsset(file,slot){if(!file)return;await run(async()=>{const d=await save();const response=await fetch(`${base}/drafts/${d.id}/assets?${new URLSearchParams({filename:slot||file.name})}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});const value=await response.json();if(!response.ok)throw new Error(value.detail||'素材未导入');setAssets(old=>[...old.filter(a=>a.slot!==value.slot),value]);setMessage(workflow==='hum-production'?`已绑定 ${value.slot}。更新对应字幕 / 来源记录后，重新检查并生成本期成片。`:'素材已保存。将下方文件绑定名填入对应的src、voiceover、music或subtitles字段。');});}
  async function importHumParameters(file){if(!file)return;await run(async()=>{const value=JSON.parse(await file.text());const input=value.parameters||value;const next=Object.fromEntries(['props','audio','provenance','shotPlan'].filter(k=>k in input).map(k=>[k,input[k]]));if(!next.props||!next.audio||!next.provenance)throw new Error('制作参数须含 props、audio 和 provenance');setDraft(old=>({...old,title:value.title||old.title,parameters:next,output_profile:'4:5'}));setRaw('');setMessage('本期制作参数已载入，核对文件绑定后保存并生成。');});}
  function addControl(){const c=route.controls[control];if(!c)return;const t0=p.segments.at(-1)?.t1||0,t1=t0+Math.max(c.minDur||3,3);change({...p,duration:Math.max(p.duration,t1),segments:[...p.segments,{control,variant:c.variants?.[0],t0,t1,props:initialValue(controlSchema(c))}]});}
  return <section className="mg-library">
    <div className="mg-heading"><div><h3>MotionGit 模板接入</h3><p>导入原包，查看真实替换范围，再绑定自己的口播和素材。</p></div><label className="mg-upload">导入 .motion<input type="file" accept=".motion" disabled={busy} onChange={e=>importFile(e.target.files[0])}/></label></div>
    <Notice message={message}/>{busy&&<p role="status">正在处理，请保留当前工程…</p>}
    <HallmarkDirections draft={draft} onSelect={art_direction=>setDraft({...draft,art_direction})}/>
    <div className="mg-workspace"><aside><h4>本机模板包</h4>{packages.map(item=><button key={item.id} className={selected?.id===item.id?'active':''} onClick={()=>{setSelected(item);setDraft(null);setMessage('');}}><strong>{item.name}</strong><small>v{item.version} · {item.verification==='verified'?'身份已核验':'待核验'}</small></button>)}{!packages.length&&<p>导入后会保留原包和独立草稿。</p>}<h4>已保存草稿</h4>{saved.map(d=><button key={d.id} onClick={()=>{setSelected(packages.find(p=>p.id===d.package_id));setWorkflow(d.workflow);setDraft(d);setAssets([]);setRaw('');}}>{d.title}<small>第{d.revision}版 · {d.workflow}</small></button>)}</aside>
    <div className="mg-editor">{!selected?<p>选择模板包开始。</p>:<><h3>{selected.name}</h3><p>版本 {selected.version} · {selected.runtime} · {(selected.bytes/1024/1024).toFixed(1)} MiB</p>{selected.verification!=='verified'&&<Button disabled={busy||selected.support==='inspection-only'} onClick={verify}>核验并读取可编辑内容</Button>}{selected.support==='inspection-only'&&<p>当前版本支持只读分析，运行适配待补。</p>}
    <div className="mg-actions">{Object.entries(selected.workflows||{}).map(([key,w])=><Button key={key} onClick={()=>create(key)}>{key==='native'?'新建原生参数草稿':`新建${w.description}草稿`}</Button>)}</div>
    {draft&&route&&<><label className="mg-field">视频名称<input value={draft.title} onChange={e=>setDraft({...draft,title:e.target.value})}/></label><p>路线：{workflow} · 原包与本期内容分开保存。结构检查后仍需实际预览。</p>{workflow==='poster-kit'&&<Field label="输出画幅" schema={{enum:['native','4:5']}} value={draft.output_profile||'native'} onChange={v=>setDraft({...draft,output_profile:v})}/>}<p>{draft.output_profile==='4:5'?'4:5使用竖屏原生布局的顶部视窗；先在实际适配预览中检查主体与字幕完整。':''}</p>
    {workflow==='poster-kit'?<><div className="mg-two"><Field label="全片时长（秒）" schema={{type:'number',minimum:.1}} value={p.duration} onChange={v=>change({...p,duration:v})}/><Field label="原生画幅" schema={route.schema.properties.layout} value={p.layout} onChange={v=>change({...p,layout:v})}/></div><Field label="口播文件绑定名" value={p.voiceover} onChange={v=>change({...p,voiceover:v})}/><Field label="配乐文件绑定名" value={p.music} onChange={v=>change({...p,music:v})}/><Field label="人物" schema={route.schema.properties.presenter} value={p.presenter} onChange={v=>change({...p,presenter:v})}/>
    <div className="mg-actions"><select aria-label="动效控件" value={control} onChange={e=>setControl(e.target.value)}><option value="">选择真实控件</option>{Object.entries(route.controls).map(([key,c])=><option key={key} value={key}>{c.label||key}</option>)}</select><Button onClick={addControl}>添加镜头</Button><span>{Object.keys(route.controls).length}个已声明控件</span></div>
    {p.segments.map((s,i)=><fieldset className="mg-object" key={i}><legend>镜头{i+1} · {route.controls[s.control]?.label||s.control}</legend><div className="mg-two"><Field label="开始（秒）" schema={{type:'number'}} value={s.t0} onChange={v=>change({...p,segments:p.segments.map((v,j)=>j===i?{...s,t0:v}:v)})}/><Field label="结束（秒）" schema={{type:'number'}} value={s.t1} onChange={v=>change({...p,segments:p.segments.map((v,j)=>j===i?{...s,t1:v}:v)})}/></div><Field label="动效变体" schema={{enum:route.controls[s.control]?.variants||[]}} value={s.variant} onChange={v=>change({...p,segments:p.segments.map((v2,j)=>j===i?{...s,variant:v}:v2)})}/><Field label="镜头内容与素材" schema={controlSchema(route.controls[s.control]||{})} value={s.props} onChange={v=>change({...p,segments:p.segments.map((v2,j)=>j===i?{...s,props:v}:v2)})}/><Button onClick={()=>change({...p,segments:p.segments.filter((_,j)=>j!==i)})}>移除镜头</Button></fieldset>)}
    </>:workflow==='hum-production'?<HumProductionFields parameters={p} onChange={change} assets={assets} onUpload={uploadAsset} onImport={importHumParameters} busy={busy}/>:<Field label="模板开放参数" schema={route.schema} value={p} onChange={change}/>}
    <div className="mg-actions"><Button variant="primary" disabled={busy} onClick={()=>run(save)}>保存草稿</Button><Button disabled={busy} onClick={()=>run(async()=>{const d=await save();const v=await api(`${base}/drafts/${d.id}/check`,{});setMessage(v.valid?'参数结构检查通过；实际运行与画面待核验。':'参数待调整');})}>检查参数</Button>{draft.id&&<Button disabled={busy} onClick={()=>run(async()=>{const old=await save(),next=await api(`${base}/drafts/${old.id}/clone`,{});setDraft(next);await refresh();setMessage('完整镜头和素材绑定已复制，可替换内容制作新视频。');})}>复制为新视频</Button>}<label className="mg-upload">导入口播／素材<input type="file" disabled={busy} accept=".mp4,.mov,.webm,.png,.jpg,.jpeg,.webp,.wav,.mp3,.srt,.json,.ttf,.otf" onChange={e=>uploadAsset(e.target.files[0])}/></label></div>
    {assets.map(a=><p key={a.name} className="mg-binding"><strong>{a.original_name}</strong><code>{a.slot} / {a.name}</code></p>)}
    <details open={workflow==='hum-production'}><summary>完整参数与字幕时钟</summary><p>{workflow==='hum-production'?'可编辑标题、素材卡、shotPlan镜头权重、实际字幕时钟、人物片段与音效。总时长从口播自动生成。':'高级字段直接使用此包实际schema；修改后保存、检查并重新预览。'}</p><textarea aria-label="完整制作参数JSON" className="mg-json" value={raw||JSON.stringify(p,null,2)} onChange={e=>setRaw(e.target.value)}/><Button onClick={()=>{try{change(JSON.parse(raw||JSON.stringify(p)));setRaw('');setMessage('完整参数已应用，尚未保存。');}catch{setMessage('JSON格式无效');}}}>应用完整参数</Button></details>
    {workflow!=='native'&&<Production draft={draft} save={save} assetRevision={JSON.stringify(assets)}/>}
    </>}</>}</div></div>
  </section>;
}
