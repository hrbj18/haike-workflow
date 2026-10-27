import React from 'react';
import {OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Box, LabProps} from './types';
import {paletteMount} from './palettes';
import layout from './layout.json';

export const SANS = '"Microsoft YaHei", sans-serif';
export const SERIF = '"SimSun", "Microsoft YaHei", serif';
export const MONO = '"Consolas", "Microsoft YaHei", monospace';
export const clamp = (x: number, a=0, b=1) => Math.max(a,Math.min(b,x));
export const ease = (x: number) => 1-Math.pow(1-clamp(x),3);
export const boxStyle = (b:Box):React.CSSProperties => ({position:'absolute',left:b.x,top:b.y,width:b.w,height:b.h});
export const phase = (f:number) => f<layout.beatStartFrames[1]?0:f<layout.beatStartFrames[2]?1:f<layout.beatStartFrames[3]?2:3;
export const phaseStart = (f:number) => layout.beatStartFrames[phase(f)];
export const metrics = (p:LabProps) => {
  const wide=p.ratio==='16x9', square=p.ratio==='1x1';
  return {wide,square,tall:!wide&&!square,W:p.width,H:p.height,
    margin:p.width*(wide?.052:.062), unit:Math.min(p.width,p.height)/1080,
    heroSize:p.width*(wide?.044:square?.064:.086),
    labelSize:Math.min(p.width,p.height)*.024,
    captionSize:Math.min(p.width,p.height)*.043};
};

export const SourceWindow:React.FC<{props:LabProps;box:Box;radius?:number;border?:string;style?:React.CSSProperties;clipPath?:string}>=({props:p,box,radius=0,border,style,clipPath})=>{
  const mount:Record<number,string>={3:'#d7c9b6',4:'#15101e',5:'#f4f5e9',6:'#f5ead6',7:'#0e1820',8:'#fff6ed',9:'#f4f3ee',10:'#fff8ec'};
  return <div data-role="source-window" style={{...boxStyle(box),borderRadius:radius,overflow:'hidden',border,background:paletteMount(p,mount[p.templateNumber]),clipPath,...style}}>
    <OffthreadVideo src={staticFile(p.avatarSrc)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/>
  </div>;
};

export const TextBlock:React.FC<{text:string;x:number;y:number;w:number;size:number;color:string;font?:string;weight?:number;lineHeight?:number;align?:'left'|'center'|'right';style?:React.CSSProperties}>=({text,x,y,w,size,color,font=SANS,weight=700,lineHeight=1.18,align='left',style})=><div data-role="text-block" style={{position:'absolute',left:x,top:y,width:w,fontSize:size,color,fontFamily:font,fontWeight:weight,lineHeight,textAlign:align,whiteSpace:'pre-line',wordBreak:'keep-all',overflowWrap:'normal',...style}}>{text}</div>;

export const Brand:React.FC<{props:LabProps;color:string;x?:number;y?:number;w?:number}>=({props:p,color,x,y,w})=>{
  const m=metrics(p);
  return <TextBlock text={p.brand} x={x??m.margin} y={y??p.height*.043} w={w??p.width*.76} size={m.labelSize} color={color} weight={700} style={{letterSpacing:m.unit*1.5}}/>;
};

export const Rule:React.FC<{x:number;y:number;w:number;color:string;vertical?:boolean;thickness?:number}>=({x,y,w,color,vertical=false,thickness=1})=><div style={{position:'absolute',left:x,top:y,width:vertical?thickness:w,height:vertical?w:thickness,background:color}}/>;

export function breakCaption(text:string,maxChars:number):string[] {
  if(text.includes('\n'))return text.split('\n');
  if(text.length<=maxChars)return [text];
  const chars=Array.from(text), target=Math.ceil(chars.length/2);
  let cut=target;
  for(let d=0;d<=3;d++){
    const candidates=[target-d,target+d];
    const found=candidates.find(i=>i>0&&i<=maxChars&&chars.length-i<=maxChars&&/[，、。：；！？,!?]/u.test(chars[i-1]));
    if(found){cut=found;break;}
  }
  return [chars.slice(0,cut).join(''),chars.slice(cut).join('')];
}

export const Caption:React.FC<{props:LabProps;box:Box;color?:string;background?:string;accent?:string;mode?:'wipe'|'rise'|'stamp'|'focus';font?:string}>=({props:p,box,color='#fff',background='#15191d',accent='#ffe077',mode='rise',font=SANS})=>{
  const f=useCurrentFrame(),{fps}=useVideoConfig(),t=f/fps;
  const cue=p.cues.find(c=>t>=c.start&&t<c.end);
  if(!cue)return null;
  const age=f-cue.start*fps,m=metrics(p), enter=(cue.end-cue.start)*fps<30?1:ease(age/7),size=Math.min(m.captionSize,box.w/Math.min(16,Math.max(8,cue.text.length))*.89);
  const lines=breakCaption(cue.text,Math.max(8,Math.floor(box.w/(size*1.02))));
  const height=Math.max(box.h,size*lines.length*1.33+m.unit*24),y=Math.min(box.y,p.height-m.unit*45-height);
  return <div data-role="caption" data-text={cue.text} style={{...boxStyle({...box,y,h:height}),display:'flex',alignItems:'center',justifyContent:'center',zIndex:70,padding:`${m.unit*12}px ${m.unit*20}px`,boxSizing:'border-box',background,color,fontFamily:font,fontSize:size,fontWeight:700,lineHeight:1.33,textAlign:'center',whiteSpace:'pre-line',borderRadius:mode==='stamp'?0:m.unit*3,opacity:mode==='focus'?.68+.32*enter:1,transform:mode==='rise'?`translateY(${(1-enter)*12*m.unit}px)`:mode==='stamp'?`scale(${1+(1-enter)*.055})`:undefined,clipPath:mode==='wipe'?`inset(0 ${(1-enter)*100}% 0 0)`:undefined}}>
    <div>{lines.map((line,i)=><div key={i}>{line.split(/([0-9]+(?:[.×x][0-9]+)*|AI|九万八|三十个平方)/g).map((part,j)=><span key={j} style={{color:/^(?:[0-9]|AI|九万八|三十)/.test(part)?accent:color}}>{part}</span>)}</div>)}</div>
  </div>;
};

export const ReadableBeat:React.FC<{props:LabProps;box:Box;color:string;font?:string;size?:number;accent?:string}>=({props:p,box,color,font=SANS,size,accent})=>{
  const f=useCurrentFrame(),m=metrics(p),idx=phase(f),enter=ease((f-phaseStart(f))/16);
  const title=idx===3&&p.cta?p.cta:p.beatTitles[idx]??p.headline;
  const requestedSize=size??m.heroSize,max=Math.max(4,Math.floor(box.w/requestedSize));
  const text=title.includes('\n')?title:breakCaption(title,max).join('\n');
  const fontSize=Math.min(requestedSize,box.w/Math.max(...text.split('\n').map(line=>Array.from(line).length))*.95);
  return <TextBlock text={text} x={box.x} y={box.y+(1-enter)*m.unit*20} w={box.w} size={fontSize} color={idx===2&&accent?accent:color} font={font} style={{opacity:idx===0?1:enter}}/>;
};
