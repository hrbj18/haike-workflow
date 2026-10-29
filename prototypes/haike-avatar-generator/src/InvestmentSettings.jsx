import {Plus, Trash2} from 'lucide-react';
import {Button, Field} from './ui.jsx';
import {investmentValue} from './investment-model.js';
import './n1.css';

export function InvestmentSettings({value, title, onTitle, onChange, busy}) {
  const config = investmentValue(value), change = patch => onChange({...config, ...patch});
  const update = (index, patch) => change({emphasis: config.emphasis.map((e, i) => i === index ? {...e, ...patch} : e)});
  return <section className="n1-settings" aria-label="招商A模板设置">
    <header><h3>模板6 · 招商A</h3><p className="helper">紫蓝招商封面、玻璃项目牌和重点贴纸。保留人物原图背景，重点画面跟随实际口播。</p></header>
    <Field label="视频标题"><input value={title} maxLength={120} disabled={busy} onChange={e => onTitle(e.target.value)}/></Field>
    <div className="n1-brand-fields"><Field label="项目名称"><input value={config.brand} maxLength={14} disabled={busy} onChange={e => change({brand: e.target.value})}/></Field><Field label="封面标题" hint="最多32字；留空使用视频标题。"><textarea rows={2} value={config.headline} maxLength={32} disabled={busy} onChange={e => change({headline: e.target.value})}/></Field></div>
    <Field label="结尾引导"><textarea rows={2} value={config.cta} maxLength={32} disabled={busy} onChange={e => change({cta: e.target.value})}/></Field>
    <div className="n1-brand-fields"><label className="checkbox-row"><input type="checkbox" checked={config.opening} disabled={busy} onChange={e => change({opening: e.target.checked})}/>显示开头招商封面</label><label className="checkbox-row"><input type="checkbox" checked={config.closing} disabled={busy} onChange={e => change({closing: e.target.checked})}/>显示结尾引导封面</label></div>
    <p className="helper">填写口播中会说到的原词句。系统按真实字幕触发；没有识别到的词不会猜时间。多段制作时，可分别关闭重复的开头或结尾。</p>
    {config.emphasis.map((entry, index) => <article key={index} className="n1-scene" aria-label={`重点 ${index + 1}`}>
      <header className="n1-scene-heading"><strong>重点 {index + 1}</strong><Button disabled={busy} aria-label={`删除重点 ${index + 1}`} onClick={() => change({emphasis: config.emphasis.filter((_, i) => i !== index)})}><Trash2 size={16}/></Button></header>
      <div className="n1-brand-fields"><Field label="触发原文"><input value={entry.match || ''} maxLength={48} disabled={busy} onChange={e => update(index, {match: e.target.value})}/></Field><Field label="画面标题"><input value={entry.text || ''} maxLength={18} disabled={busy} onChange={e => update(index, {text: e.target.value})}/></Field></div>
      <Field label="重点形式"><select value={entry.kind || 'sticker'} disabled={busy} onChange={e => update(index, {kind: e.target.value})}><option value="sticker">红金闪电贴纸</option><option value="card">紫蓝信息卡</option></select></Field>
      <Field label="说明（可选）"><input value={entry.detail || ''} maxLength={48} disabled={busy} onChange={e => update(index, {detail: e.target.value})}/></Field>
      <Field label="注释（可选）"><input value={entry.footnote || ''} maxLength={64} disabled={busy} onChange={e => update(index, {footnote: e.target.value})}/></Field>
    </article>)}
    <Button disabled={busy || config.emphasis.length >= 32} onClick={() => change({emphasis: [...config.emphasis, {match: '', text: '', kind: 'sticker', detail: '', footnote: ''}]})}><Plus size={16}/>增加重点内容</Button>
  </section>;
}
