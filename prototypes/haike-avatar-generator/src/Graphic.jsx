import {useEffect, useState} from 'react';
import {ArrowRight, CheckCircle2, ChevronDown, AlertCircle, Save} from 'lucide-react';
import {api, upload} from './studio-api.js';
import {ActionBar, Button, Field, Heading, Notice, PreviewPanel, UploadField} from './ui.jsx';

const asset = name => `${import.meta.env.BASE_URL}assets/${name}`;
const EXAMPLE = {headlines:['海客科技','让创作更简单','图文视频工作流'], conclusion:'三个画面 · 一个观点', details:[['选择模板','准备文字与素材','按三景组织内容'],['统一接入','一个Key调用能力','成本和明细可查看'],['计划发布','选择成片和账号','按日历安排时间']], materials:[null,null,null], bgm:null};
export function Graphic() {
  const [draft,setDraft] = useState(null), [content,setContent] = useState(EXAMPLE), [title,setTitle] = useState('海客科技 · 图文视频');
  const [layout,setLayout] = useState({title_size:80,detail_size:52,accent:'#ffcd3c',background:'#050c16'});
  const [message,setMessage] = useState(''), [error,setError] = useState(''), [operation,setOperation] = useState(''), [job,setJob] = useState(null), [more,setMore] = useState(false);
  const busy = !!operation, missing = content.materials.filter(x => !x).length;
  const running = ['queued','running'].includes(job?.status);
  useEffect(() => {
    let live = true;
    const id = new URLSearchParams(location.search).get('draft');
    if(id) api(`/api/studio/drafts/${id}`).then(d => {if(live){setDraft(d);setContent({...EXAMPLE,...d.input});setTitle(d.title);setLayout(d.layout);}}).catch(e => {if(live)setError(e.message);});
    return () => {live = false;};
  }, []);
  function update(patch) {setContent(old => ({...old,...patch}));setMessage('');setError('');}
  async function persist(input = content) {
    const d = await api('/api/studio/drafts',{id:draft?.id,revision:draft?.revision,template_id:'graphic-news-v2',title,text:input.headlines.join('\n'),layout,input});
    setDraft(d); return d;
  }
  async function choose(file,index) {
    const music = index === 'bgm';
    if(file.size > 80*1024*1024 || !(music ? /\.(wav|mp3|m4a|ogg)$/i : /\.(png|jpe?g|mp4|mov)$/i).test(file.name)) {setError(music ? '请选择80 MB以内的WAV、MP3、M4A或OGG音乐。' : '请选择80 MB以内的JPG、PNG、MP4或MOV素材。');return;}
    setOperation(`upload-${index}`);setError('');setMessage('');
    try {
      const d = await persist(), a = await upload(d.id,file,music ? 'audio' : /\.(png|jpe?g)$/i.test(file.name) ? 'image' : 'video');
      const next = music ? {...content,bgm:a} : {...content,materials:content.materials.map((old,i) => i===index ? a : old)};
      setContent(next);setDraft(await api('/api/studio/drafts',{...d,input:next}));setMessage('素材已上传并保存。');
    } catch(e) {setError(e.message);} finally {setOperation('');}
  }
  async function save() {setOperation('save');setError('');try{await persist();setMessage('草稿已保存，可从我的作品继续编辑。');}catch(e){setError(e.message);}finally{setOperation('');}}
  async function generate() {setOperation('generate');setError('');try{const d=await persist();setJob(await api(`/api/studio/drafts/${d.id}/generate`,{revision:d.revision,confirmed:true}));setMessage('已进入本地制作队列，合成不收费。');}catch(e){setError(e.message);}finally{setOperation('');}}
  useEffect(() => {if(!running)return;const timer=setInterval(() => api(`/api/production-queue/jobs/${job.job_id}`).then(setJob).catch(e => setError(e.message)),2500);return () => clearInterval(timer);},[job?.job_id,running]);
  return <main className="workspace creation-workspace"><Heading title="图文视频" helper="文字与三个画面，组成一个观点。"/>
    <div className="editor-shell graphic-editor"><section className="editor-content" aria-label="图文制作内容">
      <div className="template-row"><h2>选择模板</h2><button className="template-tile selected" aria-pressed="true"><img src={asset('graphic-news.png')} alt="资讯三景原生模板排版"/><span><strong>资讯三景</strong><small>9:16 · 9秒 · 三段详情卡</small></span><CheckCircle2 size={20}/></button></div>
      <div className="editor-fields"><Field label="视频名称" className="major-field"><input value={title} maxLength={120} disabled={busy} onChange={e => {setTitle(e.target.value);setMessage('');}}/></Field>
        <section className="field-group"><h2>顶部标题</h2><div className="headline-fields">{content.headlines.map((t,i) => <Field key={i} label={['第一行','第二行','第三行'][i]}><input aria-label={`标题第${i+1}行`} value={t} maxLength={30} disabled={busy} onChange={e => update({headlines:content.headlines.map((old,j) => j===i ? e.target.value : old)})}/></Field>)}</div></section>
        <Field label="结论条" className="major-field"><input value={content.conclusion} maxLength={35} disabled={busy} onChange={e => update({conclusion:e.target.value})}/></Field>
        <section className="field-group scenes"><h2>三个画面</h2>{content.details.map((lines,i) => <div className="graphic-scene" key={i}>
          <div className="scene-label"><strong>画面 {i+1}</strong><small>{i*3}–{(i+1)*3} 秒</small></div>
          <UploadField label="上传图片 / 视频" ariaLabel={`上传画面${i+1}图片 / 视频`} hint="支持 JPG、PNG、MP4、MOV" accept="image/png,image/jpeg,video/mp4,video/quicktime" value={content.materials[i]} disabled={busy} loading={operation===`upload-${i}`} onFile={f => choose(f,i)} onRemove={() => update({materials:content.materials.map((old,j) => j===i ? null : old)})}/>
          <div className="textarea-wrap"><textarea aria-label={`画面${i+1}详情`} value={lines.join('\n')} rows={3} disabled={busy} maxLength={200} onChange={e => update({details:content.details.map((old,j) => j===i ? e.target.value.split('\n').slice(0,3) : old)})}/><small className="character-count">{[...lines.join('\n')].length}/200</small></div>
        </div>)}</section>
        <section className="more-settings"><button className="settings-toggle" aria-expanded={more} aria-controls="graphic-layout" onClick={() => setMore(!more)}><ChevronDown size={18} className={more?'':'collapsed'}/><strong>模板排版与音乐</strong><span>设置字体大小、颜色、背景音乐</span></button>
          {more && <div id="graphic-layout" className="settings-fields"><div className="layout-fields"><Field label="标题字号"><select value={layout.title_size} onChange={e => setLayout({...layout,title_size:Number(e.target.value)})}>{[64,72,80,88].map(n => <option key={n} value={n}>{n}px</option>)}</select></Field><Field label="详情字号"><select value={layout.detail_size} onChange={e => setLayout({...layout,detail_size:Number(e.target.value)})}>{[40,46,52,58].map(n => <option key={n} value={n}>{n}px</option>)}</select></Field><Field label="强调色"><input type="color" value={layout.accent} onChange={e => setLayout({...layout,accent:e.target.value})}/></Field><Field label="文字板底色"><input type="color" value={layout.background} onChange={e => setLayout({...layout,background:e.target.value})}/></Field></div><Field label="背景音乐（可选）"><UploadField label="上传背景音乐" hint="WAV、MP3、M4A、OGG" accept=".wav,.mp3,.m4a,.ogg" value={content.bgm} disabled={busy} loading={operation==='upload-bgm'} onFile={f => choose(f,'bgm')} onRemove={() => update({bgm:null})}/></Field></div>}
        </section>
        <Notice message={error} error/><Notice message={message}/>{job && <div className="job-state" role="status"><strong>{({queued:'排队中',running:'正在合成',completed:'已合成 · 待审核',failed:'合成失败'})[job.status]||job.status}</strong><p>{job.stage}</p>{job.error?.message && <p>{job.error.message}</p>}{job.result?.work_id && <Button href="/projects">查看成片与审核<ArrowRight size={16}/></Button>}</div>}
      </div>
    </section><PreviewPanel label="图文模板预览" metadata="1080 × 1920"><img className="reference-poster" src={asset('graphic-news.png')} alt="顶部三行标题、结论条、中间素材带和底部详情卡"/><p className="preview-note">参考现有排版，生成后使用你的内容。</p></PreviewPanel>
    <ActionBar note={<><strong>本地合成 · <em>¥0</em></strong>{missing>0 && <span className="missing-note"><AlertCircle size={17}/>请上传{missing===3?'三个':`${missing}个`}画面</span>}{running && <span>正在制作中</span>}</>}>
      <Button disabled={busy} loading={operation==='save'} onClick={save}>保存草稿</Button><Button variant="primary" disabled={busy || missing>0 || running || !title.trim() || content.headlines.some(t=>!t.trim())} loading={operation==='generate'} onClick={generate}>生成图文视频</Button>
    </ActionBar></div>
  </main>;
}
