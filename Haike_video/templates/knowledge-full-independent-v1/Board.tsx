import React from 'react';
import {AbsoluteFill,OffthreadVideo,Sequence,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import type {Props,Scene} from './types';

const clamp=(n:number)=>Math.max(0,Math.min(1,n));
const ease=(n:number)=>1-Math.pow(1-clamp(n),3);
const rough=(x:number,y:number,w:number,h:number)=>`M${x+3} ${y} Q${x+w*.45} ${y-3} ${x+w} ${y+2} L${x+w-2} ${y+h} Q${x+w*.52} ${y+h+3} ${x} ${y+h-2} Z`;
const stroke=(progress:number)=>({strokeDasharray:1,strokeDashoffset:1-clamp(progress),pathLength:1});
const lineBreak=(text:string,limit:number)=>text.length>limit?[text.slice(0,limit),text.slice(limit)]:[text];

export const Board:React.FC<Props>=p=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig(),t=frame/fps;
 const s=p.scenes.find(v=>t>=v.start&&t<v.end)||p.scenes[p.scenes.length-1];
 const chalk=p.theme==='chalkboard',ink=chalk?'#eee8cf':'#243139',accent=chalk?'#d7c16b':'#e26341',blue=chalk?'#a3c9d7':'#428b9b',paper=chalk?'#17342d':'#f4efdd';
 const elapsed=t-s.start,enter=ease(elapsed/.55),active=s.cues.filter(v=>v<=t).length;
 const at=(index:number)=>ease((t-(s.cues[index]??s.start+index*.5))/.55);
 const textStyle={fontFamily:'KnowledgeFull',fill:ink};
 const label=(text:string,x:number,y:number,size=39,color=ink,anchor:'start'|'middle'='middle')=><text key={text+x+y} x={x} y={y} textAnchor={anchor} fill={color} fontSize={size} fontFamily="KnowledgeFull">{lineBreak(text,14).map((v,i)=><tspan key={i} x={x} dy={i?size*1.35:0}>{v}</tspan>)}</text>;
 const box=(x:number,y:number,w:number,h:number,progress:number,color=ink,fill='none')=><path d={rough(x,y,w,h)} fill={fill} stroke={color} strokeWidth={chalk?3:3.5} {...stroke(progress)}/>;
 const arrow=(x1:number,y1:number,x2:number,y2:number,progress:number,color=accent)=><g opacity={progress}><path d={`M${x1} ${y1} Q${(x1+x2)/2+18} ${(y1+y2)/2-12} ${x2} ${y2}`} fill="none" stroke={color} strokeWidth={5} {...stroke(progress)}/><path d={`M${x2-12} ${y2-10} L${x2} ${y2} L${x2-14} ${y2+10}`} fill="none" stroke={color} strokeWidth={5}/></g>;
 const media=(index:number,x:number,y:number,w:number,h:number)=>{
  const m=s.media?.[index];if(!m)return null;
  return <Sequence key={index} from={Math.round(s.start*fps)} durationInFrames={Math.round((s.end-s.start)*fps)} layout="none"><div style={{position:'absolute',left:x,top:y,width:w,height:h,border:`5px solid ${ink}`,background:paper,transform:`rotate(${chalk?0:index%2?-2:1.4}deg)`,boxShadow:chalk?'none':'8px 10px 0 #24313924'}}><OffthreadVideo src={staticFile(m.src)} startFrom={Math.round(m.offset*fps)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/><div style={{position:'absolute',bottom:10,left:12,right:12,textAlign:'center',fontSize:28,background:paper,color:ink,padding:6}}>{m.label}</div></div></Sequence>;
 };
 const note=(text:string,i:number,x:number,y:number,w=760)=>{
  const progress=at(i);return <g key={i} opacity={progress} transform={`translate(${(1-progress)*32} ${(1-progress)*10})`}>
   {!chalk&&<path d={rough(x,y,w,130)} fill={i%2?'#dce9dc':'#f8dca1'} stroke={ink} strokeWidth={2}/>}
   {chalk&&box(x,y,w,130,progress,i%2?blue:ink)}
   <circle cx={x+51} cy={y+63} r={25} fill="none" stroke={accent} strokeWidth={3} {...stroke(progress)}/>
   {label(String(i+1),x+51,y+75,30,accent)}{label(text,x+110,y+74,38,ink,'start')}
  </g>;
 };
 const content=()=>{
  if(s.recipe==='question')return chalk?<g>{box(180,760,720,330,enter,ink)}{label(s.labels[0],540,920,48)}{arrow(540,1110,540,1290,at(1))}{box(180,1310,720,150,at(1),accent)}{label(s.labels[1]||'',540,1405,48,accent)}</g>:<g><text x={540} y={850} fill={accent} textAnchor="middle" fontFamily="KnowledgeFull" fontSize={260} opacity={enter}>?</text>{box(135,1020,810,155,at(0),blue)}{label(s.labels[0],540,1112,48)}{arrow(540,1200,540,1330,at(1))}{label(s.labels[1]||'',540,1410,50,accent)}</g>;
  if(s.recipe==='steps')return chalk?<g>{box(315,690,450,125,enter,blue)}{label('从认识到实践',540,770,42,blue)}{s.labels.map((v,i)=>{const x=215+i*325;return <g key={i}>{arrow(540,830,x,1040,at(i),i===2?accent:ink)}{box(x-130,1060,260,230,at(i),i===2?accent:ink)}{label(v,x,1155,34,i===2?accent:ink)}</g>})}{label('真实体验，让抽象知识落地',540,1470,42,accent)}</g>:<g>{s.labels.map((v,i)=><React.Fragment key={i}>{note(v,i,160,680+i*235)}{i<s.labels.length-1&&arrow(540,825+i*235,540,895+i*235,at(i+1),blue)}</React.Fragment>)}</g>;
  if(s.recipe==='compare')return chalk?<g>{box(130,760,340,220,at(0),blue)}{label(s.labels[0],300,885,42,blue)}{arrow(490,870,600,870,at(1))}{box(620,760,340,220,at(1),accent)}{label(s.labels[1],790,885,42,accent)}{arrow(790,1000,570,1260,at(1))}{box(180,1290,720,180,at(1),ink)}{label(s.labels[2]||'',540,1390,39)}{arrow(170,1300,300,1000,at(1),blue)}</g>:<g>{box(120,720,380,460,at(0),blue)}{box(580,720,380,460,at(1),accent)}{label(s.labels[0],310,905,43)}{label(s.labels[1],770,905,43,accent)}{arrow(510,1000,570,1000,at(1))}{label(s.labels[2]||'',540,1330,43,accent)}</g>;
  if(s.recipe==='quote')return <g opacity={enter}><text x={125} y={800} fill={accent} fontSize={180}>“</text>{lineBreak(s.labels[0],11).map((v,i)=>label(v,540,900+i*100,58))}<path d="M180 1160 Q540 1145 900 1160" stroke={accent} strokeWidth={7} fill="none" {...stroke(at(0))}/>{label(s.labels[1]||'',540,1250,30,blue)}</g>;
  if(s.recipe==='notice')return <g>{box(110,700,860,640,enter,accent)}{label('非医疗诊断',540,840,62,accent)}{s.labels.map((v,i)=>label(v,540,960+i*100,41,i===0?ink:blue))}</g>;
  if(s.recipe==='invitation')return <g>{box(125,760,830,410,enter,blue)}{s.labels.map((v,i)=>label(v,540,870+i*100,i?40:58,i?ink:accent))}{arrow(540,1220,540,1390,at(1))}{label('这个周末，一家人来坐坐',540,1480,41,accent)}</g>;
  // Evidence is an actual time-bearing source window, framed by authored notes.
  return <g>{box(110,645,860,700,enter,blue)}{label(s.labels[0]||'',540,1450,45,accent)}{arrow(780,1400,720,1320,at(0),accent)}</g>;
 };
 const cap=p.captions.find(c=>t>=c.s&&t<c.e);
 const presenter=p.presenter?.windows.find(w=>t>=w.start&&t<w.end);
 return <AbsoluteFill style={{background:paper,fontFamily:'KnowledgeFull',color:ink}}>
  <svg width="1080" height="1920" viewBox="0 0 1080 1920" style={{position:'absolute',inset:0}}>
   <defs><pattern id="texture" width={chalk?23:44} height={chalk?29:44} patternUnits="userSpaceOnUse">{chalk?<path d="M2 7l12 1 M17 20l4-1" stroke="#f3efd9" opacity=".025"/>:<path d="M44 0H0V44" stroke="#8b9a8d" strokeWidth=".7" opacity=".24"/>}</pattern></defs>
   <rect width="1080" height="1920" fill="url(#texture)"/>
   {!chalk&&<path d="M89 0V1920" stroke="#dc8d7b" opacity=".5"/>}
   {chalk&&<path d="M40 1750H1040" stroke="#b8b38b" strokeWidth="8" opacity=".3"/>}
   <text x="110" y="120" {...textStyle} fontSize="28" letterSpacing="3">{p.brand}</text>
   <text x="970" y="120" {...textStyle} fontSize="26" textAnchor="end">{String(p.scenes.indexOf(s)+1).padStart(2,'0')} / {p.scenes.length}</text>
   <g opacity={enter} transform={`translate(0 ${(1-enter)*24})`}>
    {lineBreak(s.title,11).map((v,i)=>label(v,540,250+i*84,66))}
    <path d="M150 450 Q540 438 930 450" stroke={accent} strokeWidth={5} fill="none" {...stroke(enter)}/>
    {label(s.subtitle,540,530,31,blue)}{content()}
   </g>
   <g opacity=".65">{label(chalk?'粉笔讲解 · 独立实现':'手绘笔记 · 独立实现',540,1730,25)}</g>
   <rect x="110" y="1770" width={860*t/(p.durationFrames/fps)} height="5" fill={accent}/>
  </svg>
  {s.recipe==='evidence'&&media(0,145,685,790,610)}
  {presenter&&p.presenter&&<Sequence from={Math.round(presenter.start*fps)} durationInFrames={Math.round((presenter.end-presenter.start)*fps)} layout="none"><div style={{position:'absolute',right:42,top:565,width:250,height:310,borderRadius:chalk?'50%':'18px',overflow:'hidden',border:`5px solid ${blue}`,background:paper}}><OffthreadVideo src={staticFile(p.presenter.src)} startFrom={Math.round(presenter.offset*fps)} muted style={{width:'100%',height:'100%',objectFit:'cover'}}/><div style={{position:'absolute',bottom:4,width:'100%',fontSize:20,textAlign:'center',background:paper,color:ink}}>AI数字人讲述</div></div></Sequence>}
  {cap&&<div style={{position:'absolute',left:80,right:80,bottom:55,minHeight:75,textAlign:'center',fontSize:44,lineHeight:1.35,fontWeight:600,background:chalk?'#17342de8':'#f4efdde8',padding:'14px 18px',borderRadius:12}}>{cap.text}</div>}
 </AbsoluteFill>;
};
