import { Children, cloneElement, isValidElement, useEffect, useId, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ChevronDown, LoaderCircle, Upload, X, FileText } from 'lucide-react';

export function Button({children, variant = 'secondary', loading = false, className = '', disabled, href, ...props}) {
  const Tag = href ? 'a' : 'button';
  return <Tag {...(href ? {href} : {type:'button', disabled:disabled || loading})} {...props}
    className={`button ${variant === 'primary' ? 'primary' : variant === 'danger' ? 'danger' : variant === 'text' ? 'quiet' : ''} ${className}`}
    aria-busy={loading || undefined}>
    {loading && <LoaderCircle size={17} className="spinner" aria-hidden="true"/>}{children}
  </Tag>;
}
export function Heading({title, helper, children}) {
  return <header className="page-heading"><div className="page-title"><h1>{title}</h1>{helper && <p>{helper}</p>}</div>{children}</header>;
}
export function Notice({message, error = false, children}) {
  return message && <div className={`notice ${error ? 'notice-error' : 'notice-success'}`} role={error ? 'alert' : 'status'}>
    {error ? <AlertCircle size={18} aria-hidden="true"/> : <CheckCircle2 size={18} aria-hidden="true"/>}
    <div>{message}{children}</div>
  </div>;
}
export function Field({label, hint, error, children, className = ''}) {
  const id = useId(), hintId = `${id}-hint`;
  let assigned = false;
  const labelControl = nodes => Children.map(nodes, child => {
    if(!isValidElement(child)) return child;
    if(!assigned && ['input','select','textarea'].includes(child.type)) {
      assigned = true;
      return cloneElement(child, {id, 'aria-describedby':error || hint ? hintId : undefined, 'aria-invalid':error ? true : undefined});
    }
    return typeof child.type === 'string' && child.props.children ? cloneElement(child, {}, labelControl(child.props.children)) : child;
  });
  const controls = labelControl(children);
  return <div className={`field ${className}`}><label htmlFor={assigned ? id : undefined}>{label}</label>{controls}
    {(error || hint) && <p id={hintId} className={error ? 'field-error' : 'helper'} role={error ? 'alert' : undefined}>{error || hint}</p>}
  </div>;
}
export function PreviewPanel({label, metadata, children}) {
  const [expanded,setExpanded] = useState(false), id = useId();
  return <aside className="preview-panel" aria-label={label}><header className="panel-heading"><h2>版式参考</h2><span>{metadata}</span>
    <button type="button" className="preview-toggle text-button" aria-expanded={expanded} aria-controls={id} onClick={()=>setExpanded(!expanded)}>{expanded?'收起预览':'查看预览'}<ChevronDown size={16} className={expanded?'':'collapsed'}/></button>
  </header><div id={id} className={`preview-content ${expanded?'expanded':''}`}>{children}</div></aside>;
}
export function ActionBar({children, note, className = ''}) {
  return <footer className={`action-bar ${className}`}><div className="action-note">{note}</div><div className="action-buttons">{children}</div></footer>;
}
export function UploadField({label = '上传图片 / 视频', ariaLabel = label, hint, accept, value, onFile, onRemove, disabled, loading, className = ''}) {
  const input = useRef(null), [dragging, setDragging] = useState(false);
  const choose = file => { if(file && !disabled && !loading) onFile(file); };
  const thumb = value?.kind === 'image' ? (value.url || `/api/studio/assets/${value.id}`) : null;
  return <div className={`upload-field ${value ? 'has-file' : ''} ${dragging ? 'dragging' : ''} ${className}`}
    onDragOver={e => {e.preventDefault(); if(!disabled) setDragging(true);}}
    onDragLeave={() => setDragging(false)} onDrop={e => {e.preventDefault(); setDragging(false); choose(e.dataTransfer.files[0]);}}>
    <button type="button" className="upload-target" disabled={disabled || loading} onClick={() => input.current.click()} aria-label={value ? `替换${value.name}` : ariaLabel}>
      {thumb ? <img src={thumb} alt="已上传素材"/> : loading ? <LoaderCircle size={22} className="spinner"/> : value ? <FileText size={22}/> : <Upload size={22}/>}
      <span><strong>{loading ? '正在上传…' : value?.name || label}</strong><small>{value ? '点击替换' : hint || '点击或拖入文件'}</small></span>
    </button>
    {value && onRemove && <button type="button" className="icon-button remove-file" disabled={disabled || loading} aria-label={`移除${value.name}`} onClick={onRemove}><X size={16}/></button>}
    <input hidden ref={input} type="file" accept={accept} onChange={e => {choose(e.target.files[0]); e.target.value = '';}}/>
  </div>;
}
export function Dialog({title, description, onClose, children, wide = false, busy = false, footer}) {
  const ref = useRef(null), titleId = useId(), descriptionId = useId();
  useEffect(() => {
    const dialog = ref.current, previous = document.activeElement, oldOverflow = document.body.style.overflow;
    dialog.showModal(); document.body.style.overflow = 'hidden';
    return () => {dialog.close(); document.body.style.overflow = oldOverflow; if(previous?.isConnected) previous.focus();};
  }, []);
  const close = () => {if(!busy) onClose();};
  return <dialog ref={ref} className={`modal ${wide ? 'wide' : ''}`} aria-labelledby={titleId}
    aria-describedby={description ? descriptionId : undefined} aria-busy={busy || undefined}
    onCancel={e => {e.preventDefault(); close();}} onClick={e => {if(e.target === ref.current) close();}}>
    <header className="modal-heading"><div><h2 id={titleId}>{title}</h2>{description && <p id={descriptionId} className="helper">{description}</p>}</div>
      <button type="button" className="icon-button" disabled={busy} aria-label="关闭窗口" onClick={close}><X size={20}/></button></header>
    <div className="modal-body">{children}</div>
    {footer && <footer className="modal-footer">{footer}</footer>}
  </dialog>;
}
export function EmptyState({title, children, action, icon: Icon = FileText}) {
  return <div className="empty-state"><Icon size={28} aria-hidden="true"/><h3>{title}</h3><p>{children}</p>{action}</div>;
}

export const CAPABILITIES = [
  {model:'haike/cosyvoice',name:'海客配音',detail:'CosyVoice Flash'},
  {model:'haike/tencent-tts',name:'腾讯配音',detail:'精品音色'},
  {model:'haike/tencent-asr',name:'字幕识别',detail:'录音转文字'},
  {model:'haike/avatar',name:'数字人口播',detail:'人物视频生成'},
  {model:'haike/text',name:'文本与视觉',detail:'文案与图片理解'},
  {model:'haike/assets',name:'素材检索',detail:'图片与视频素材'},
];
export function availableModels(data) {return new Set((data?.capabilities?.items || []).map(x => x.model));}
