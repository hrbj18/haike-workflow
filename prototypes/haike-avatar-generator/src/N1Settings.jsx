import {useState} from 'react';
import {ChevronDown, Plus, Trash2} from 'lucide-react';
import {Button, Field, UploadField} from './ui.jsx';
import {N1_SCENE_KINDS, n1Value, newN1Scene} from './n1-model.js';
import './n1.css';

export function N1Settings({value, title = '', onTitle, onChange, onFile, busy, audioDuration}) {
  const config = n1Value(value), [open, setOpen] = useState(false);
  const change = patch => onChange({...config, ...patch});
  const sceneChange = (index, patch) => change({scenes: config.scenes.map((scene, i) => i === index ? {...scene, ...patch} : scene)});
  return <section className="n1-settings" aria-label="深蓝视窗 N1 设置">
    <header><h3>深蓝视窗 N1</h3><p className="helper">三行标题、深蓝主窗与人物圆框。没有画面安排时，整片使用主持人模式。</p></header>
    <Field label="视频标题"><input value={title} maxLength={36} disabled={busy} placeholder="用于作品名称和自动标题" onChange={event => onTitle(event.target.value)}/></Field>
    <div className="n1-title-fields">{['主标题 · 黄色', '副标题 · 第一行', '副标题 · 第二行'].map((label, index) => <Field key={label} label={label} hint={index === 0 ? '最多16字；三行留空时自动取视频标题。' : '最多20字，可以留空。'}><input value={config.titleLines[index]} maxLength={index === 0 ? 16 : 20} disabled={busy} placeholder={index === 0 ? '自动取视频标题' : '可选副标题'} onChange={event => change({titleLines: config.titleLines.map((line, i) => i === index ? event.target.value : line)})}/></Field>)}</div>
    <Field label="来源声明" hint="按实际素材来源填写；留空时不显示。"><input value={config.sourceLabel} maxLength={40} disabled={busy} onChange={event => change({sourceLabel: event.target.value})} placeholder="例如：来源：本人提供"/></Field>
    <div className="n1-brand-fields"><Field label="品牌名称"><input value={config.brand} maxLength={8} disabled={busy} onChange={event => change({brand: event.target.value})}/></Field><Field label="背景淡英文"><input value={config.englishLabel} maxLength={40} disabled={busy} onChange={event => change({englishLabel: event.target.value})}/></Field></div>
    <div className="n1-scene-section"><button type="button" className="settings-toggle" aria-expanded={open} aria-controls="n1-scenes" onClick={() => setOpen(!open)}><ChevronDown size={18} className={open ? '' : 'collapsed'}/><strong>画面安排</strong><span>{config.scenes.length ? `${config.scenes.length} 个画面` : '默认全片主持人'}</span></button>
      {open && <div id="n1-scenes" className="n1-scenes"><p className="helper">按口播的实际秒数安排画面，未安排的区间使用主持人。{Number.isFinite(audioDuration) ? `当前音频${audioDuration.toFixed(2)}秒。` : '配音后会核对实际时长，超出范围会提示调整。'}请仅上传有权使用的素材。</p>
        {config.scenes.map((scene, index) => <article className="n1-scene" key={index} aria-label={`画面 ${index + 1}`}>
          <header className="n1-scene-heading"><strong>画面 {index + 1}</strong><Button disabled={busy} aria-label={`删除画面 ${index + 1}`} onClick={() => change({scenes: config.scenes.filter((_, i) => i !== index)})}><Trash2 size={16}/></Button></header>
          <Field label="画面模式"><select value={scene.kind} disabled={busy} onChange={event => sceneChange(index, {kind: event.target.value, ...(event.target.value === 'data' && !scene.rows?.length ? {rows: ['']} : {})})}>{N1_SCENE_KINDS.map(kind => <option value={kind.id} key={kind.id}>{kind.name}</option>)}</select></Field>
          <div className="n1-scene-timing"><Field label="开始（秒）"><input type="number" min="0" max="120" step=".01" value={scene.start} disabled={busy} onChange={event => sceneChange(index, {start: event.target.value === '' ? '' : Number(event.target.value)})}/></Field><Field label="结束（秒）"><input type="number" min="0" max="120" step=".01" value={scene.end} disabled={busy} onChange={event => sceneChange(index, {end: event.target.value === '' ? '' : Number(event.target.value)})}/></Field></div>
          {['material', 'screenshot'].includes(scene.kind) && <><UploadField label={scene.kind === 'screenshot' ? '上传来源截图' : '上传图片 / 视频'} ariaLabel={`上传画面 ${index + 1} 的素材`} value={scene.asset} disabled={busy} accept={scene.kind === 'screenshot' ? '.jpg,.jpeg,.png' : '.jpg,.jpeg,.png,.mp4,.mov'} hint={scene.kind === 'screenshot' ? 'JPG / PNG，最多80 MB' : 'JPG / PNG / MP4 / MOV，最多80 MB'} onFile={file => onFile(index, file)} onRemove={() => sceneChange(index, {assetId: undefined, asset: undefined})}/>
            <div className="n1-brand-fields"><Field label="素材呈现"><select value={scene.fit || 'contain'} disabled={busy} onChange={event => sceneChange(index, {fit: event.target.value})}><option value="contain">完整显示</option><option value="cover">铺满裁切</option><option value="blur">完整显示＋模糊底</option></select></Field>{scene.asset?.kind === 'video' && <Field label="素材起点（秒）"><input type="number" min="0" max="600" step=".1" value={scene.offset || 0} disabled={busy} onChange={event => sceneChange(index, {offset: Number(event.target.value)})}/></Field>}</div></>}
          {scene.kind === 'data' && <><div className="n1-brand-fields"><Field label="数据板标题"><input value={scene.dataTitle || ''} maxLength={16} disabled={busy} placeholder="关键数据" onChange={event => sceneChange(index, {dataTitle: event.target.value})}/></Field><Field label="数据说明"><input value={scene.dataLabel || ''} maxLength={12} disabled={busy} placeholder="数据口径 / 单位" onChange={event => sceneChange(index, {dataLabel: event.target.value})}/></Field></div>
            <div className="n1-data-rows">{(scene.rows?.length ? scene.rows : ['']).map((row, rowIndex) => <div key={rowIndex}><Field label={`数据第 ${rowIndex + 1} 行`}><input value={row} maxLength={17} disabled={busy} onChange={event => sceneChange(index, {rows: (scene.rows?.length ? scene.rows : ['']).map((line, i) => i === rowIndex ? event.target.value : line)})}/></Field><Button aria-label={`移除数据第 ${rowIndex + 1} 行`} disabled={busy || !(scene.rows?.length > 1)} onClick={() => sceneChange(index, {rows: scene.rows.filter((_, i) => i !== rowIndex)})}><Trash2 size={15}/></Button></div>)}</div>
            <Button disabled={busy || scene.rows?.length >= 4} onClick={() => sceneChange(index, {rows: [...(scene.rows || []), '']})}><Plus size={15}/>增加数据行</Button></>}
        </article>)}
        <Button disabled={busy || config.scenes.length >= 16} onClick={() => change({scenes: [...config.scenes, newN1Scene(config.scenes)]})}><Plus size={16}/>增加画面</Button>
      </div>}
    </div>
  </section>;
}
