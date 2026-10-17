import {useEffect, useState} from 'react';
import {Play} from 'lucide-react';
import {Button, Dialog} from './ui.jsx';
const assetPath = name => `${import.meta.env.BASE_URL}assets/${name}`;

export function TemplatePreview({template, onPlay, showSample = true}) {
  const [active, setActive] = useState(0);
  useEffect(() => setActive(0), [template.id]);
  const selected = template.previews?.[active];
  return <div className="template-preview-gallery">
    <div className="poster-frame"><img src={assetPath(selected?.image || template.poster)} alt={`${template.name} · ${selected?.name || '版式参考'}`}/></div>
    {template.previews && <div className="template-preview-tabs" role="group" aria-label={`${template.name}画面模式`}>{template.previews.map((preview, index) => <button type="button" key={preview.id} aria-pressed={active === index} className={active === index ? 'selected' : ''} onClick={() => setActive(index)}>{preview.name}</button>)}</div>}
    <p className="preview-note">{selected?.description || template.previewNote || (template.sample ? '现有真实样片，生成后使用你的内容。' : '模板布局示意，生成后使用你的内容。')}</p>
    {showSample && template.sample && <Button className="preview-play" onClick={onPlay}><Play size={16}/>播放样片{template.previews ? ' · 无声' : ''}</Button>}
  </div>;
}

export function TemplateSampleDialog({template, autoPlay = true, onClose}) {
  if (!template.sample) return <Dialog title={`${template.name} · 版式示意`} onClose={onClose}><p className="helper">当前提供版式示意图，请上传你的人物和声音后生成。</p></Dialog>;
  return <Dialog title={`${template.name} · 样片`} wide onClose={onClose} footer={<Button href={assetPath(template.sample)} download={template.sampleDownload || `${template.name}-样片.mp4`}>下载样片</Button>}>
    <video className="sample-video" controls autoPlay={autoPlay} playsInline preload="metadata" poster={assetPath(template.poster)} src={assetPath(template.sample)}/>
    <p className="helper">{template.sampleNote || '模板真实样片，用于查看版式与动效。'}</p>
  </Dialog>;
}
