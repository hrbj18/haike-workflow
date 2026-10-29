import React,{createContext,useContext} from 'react';
import {Easing,Img,OffthreadVideo,Sequence,staticFile,useVideoConfig} from 'remotion';
import type {Context,Media,Palette,Props} from './types';
import {presenterPose} from './presenter-clock';

export const clamp=(v:number,a=0,b=1)=>Math.min(b,Math.max(a,v));
export const ease=(v:number)=>Easing.bezier(.22,1,.36,1)(clamp(v));
export const phase=(seconds:number,start:number,duration=.65)=>ease((seconds-start)/duration);
export const mix=(a:number,b:number,t:number)=>a+(b-a)*clamp(t);
export const rect=(x:number,y:number,w:number,h:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width:w,height:h});
export const text=(size:number,color:string,weight=600):React.CSSProperties=>({fontFamily:'DarkFullDisplay',fontSize:size,fontWeight:weight,color,lineHeight:1.12,whiteSpace:'pre-wrap'});
export const body=(size:number,color:string):React.CSSProperties=>({fontFamily:'DarkFullBody',fontSize:size,color,lineHeight:1.4});
export const palettes:Record<string,Palette>={
 reference:{bg:'#030303',paper:'#F5F5F2',ink:'#FFFFFF',muted:'#A7ABAD',accent:'#2155E7',accent2:'#A893FF',line:'#FFFFFF20',panel:'#111718',onAccent:'#FFFFFF'},
 hedgerow:{bg:'#173D30',paper:'#F3F0D9',ink:'#F3F0D9',muted:'#C3CCB1',accent:'#D3DC68',accent2:'#8AAE78',line:'#F3F0D933',panel:'#214A3B',onAccent:'#173D30'},
 cobalt:{bg:'#F1F4F8',paper:'#FFFFFF',ink:'#15232C',muted:'#566778',accent:'#1748E8',accent2:'#67C5E6',line:'#173D5928',panel:'#DCE5F1',onAccent:'#FFFFFF'},
 'native-story':{bg:'#18172F',paper:'#F6F5F1',ink:'#F7F5FF',muted:'#B8B8CA',accent:'#2862EA',accent2:'#AAA0FF',line:'#FFFFFF18',panel:'#111524',onAccent:'#FFFFFF'},
};
export const palette=(p:Props)=>palettes[p.variant];
export const cue=(c:Context,id:string,sourceAt:number)=>{
 if(c.s.cueTimes?.[id]!==undefined)return c.s.cueTimes[id];
 const start=c.s.sourceStart??0,duration=c.s.sourceDuration??c.s.frames/c.p.fps;
 return (sourceAt-start)*(c.s.frames/c.p.fps)/duration;
};
export const value=(c:Context,key:string,fallback:string)=>typeof c.s.content[key]==='string'?c.s.content[key] as string:fallback;
export const strings=(c:Context,key:string,fallback:string[])=>Array.isArray(c.s.content[key])?(c.s.content[key] as unknown[]).map(String):fallback;
export const mediaAt=(c:Context,index:number)=>c.p.media.find(m=>m.id===c.s.mediaIds[index%c.s.mediaIds.length]);
export const mainMedia=(c:Context)=>c.p.media.find(m=>m.id===c.s.mainMediaId)||mediaAt(c,0);
export const SceneClock=createContext<Context|null>(null);

/** Project-authored4:5 canvas. This is not an official native viewport override. */
export const StoryGround:React.FC<{c:Context;paper?:boolean;children?:React.ReactNode}>=({c,paper=false,children})=><div data-layout="native-story-4x5" style={{position:'absolute',inset:0,overflow:'hidden',background:paper?c.t.paper:'radial-gradient(ellipse at 22% 17%,#30294F 0%,#19182F 48%,#0E1428 100%)'}}><div style={{position:'absolute',inset:0,pointerEvents:'none',backgroundImage:`linear-gradient(${paper?'#14232C09':'#FFFFFF08'} 1px,transparent 1px),linear-gradient(90deg,${paper?'#14232C09':'#FFFFFF08'} 1px,transparent 1px)`,backgroundSize:'180px 180px'}}/>{children}</div>;

/** Shared header/caption contrast follows the same public cue clock as scenes. */
export const storyPaper=(c:Context)=>c.s.group==='s04'&&!(c.seconds>=cue(c,'wall_expand',45.55)&&c.seconds<cue(c,'cross_out',49))||c.s.group==='s08'&&c.seconds>=cue(c,'comments',100.1);
export const storyPresenterLarge=(c:Context)=>{if(!c.p.presenter)return 0;const pose=presenterPose(c.p.presenter,c.s.from+c.frame,c.p.fps);return pose.visible?pose.large:0;};

export const Material:React.FC<{m?:Media;live?:boolean;startOffset?:number;style?:React.CSSProperties;children?:React.ReactNode}>=({m,live=false,startOffset=0,style,children})=>{
 const {fps}=useVideoConfig();
 const c=useContext(SceneClock),windows=c?.s.videoWindows?.filter(w=>w.mediaId===m?.id)||[];
 if(!m)return <div style={{position:'absolute',inset:0,...style}}><Study kind={0} seconds={0}/>{children}</div>;
 return <div style={{position:'absolute',inset:0,overflow:'hidden',background:'#10242A',...style}}><Img src={staticFile(m.kind==='image'?m.src:m.thumbnail||m.src)} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain'}}/>{m.kind==='video'&&live&&windows.map((w,i)=><Sequence key={i} from={w.from} durationInFrames={w.frames} premountFor={fps}><OffthreadVideo src={staticFile(m.src)} trimBefore={Math.round((w.offset+startOffset)*fps)} muted style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>)}{children}</div>;
};

/** Independent editable demo artwork used where the reference's inner media is unavailable. */
export const Study:React.FC<{kind?:number;seconds:number;variant?:string}>=({kind=0,seconds,variant='reference'})=>{
 const light=kind%3===2,ink=light?'#12232B':'#DBE9EF',accent=kind%3===0?'#A08AF8':kind%3===1?'#72B5CD':'#D99AB7';
 const bars=[.23,.37,.6,.48,.78,.93,.75];
 return <svg viewBox="0 0 640 360" preserveAspectRatio="xMidYMid meet" style={{width:'100%',height:'100%',display:'block',background:light?'#E6EFF3':'#071217'}}>
 <rect x="18" y="18" width="604" height="324" rx="8" stroke={ink} strokeOpacity=".12" fill="none"/>
 <path d="M22 40 L40 22 M600 22 L618 40 M22 320 L40 338 M600 338 L618 320" fill="none" stroke={ink} strokeOpacity=".25"/>
 <text x="42" y="55" fill={ink} opacity=".4" fontSize="10" fontFamily="monospace">MOTION STUDY {String(kind+1).padStart(2,'0')}</text>
 <text x="42" y="105" fill={ink} fontSize="26" fontWeight="700" fontFamily="Arial">{['CONNECT','PROGRESS','COMPOSE'][kind%3]}</text>
 <text x="42" y="128" fill={ink} opacity=".4" fontSize="9" fontFamily="Arial">EDITABLE DEMO MEDIA</text>
 {kind%3===0?<g transform="translate(320 210)">{Array.from({length:8},(_,i)=>{const a=i*Math.PI/4+seconds*.18;return <g key={i}><line x1="0" y1="0" x2={Math.cos(a)*70} y2={Math.sin(a)*55} stroke={accent} opacity=".4"/><circle cx={Math.cos(a)*70} cy={Math.sin(a)*55} r={14+i%3*4} fill={accent} opacity={.5+i%3*.15}/></g>})}<circle r="33" fill={accent}/></g>:kind%3===1?<g>{bars.map((n,i)=><rect key={i} x={140+i*44} y={280-155*n*(.88+.12*Math.sin(seconds*1.2+i))} width="27" height={155*n*(.88+.12*Math.sin(seconds*1.2+i))} fill={accent} opacity={.45+i*.07} rx="6"/>)}<path d="M125 232 C185 100 220 260 290 190 S400 230 475 120" fill="none" stroke={ink} opacity=".6" strokeWidth="3"/></g>:<g>{[0,1,2].map(i=><g key={i} transform={`translate(${150+i*18} ${155+i*43})`}><rect width="245" height="35" rx="8" fill={accent} opacity={.6+i*.12}/><circle cx="19" cy="17" r="6" fill="#4F3D45" opacity=".7"/><rect x="38" y="12" width={150-i*22} height="8" rx="4" fill="#70515F" opacity=".5"/></g>)}</g>}
 <line x1="42" y1="310" x2="130" y2="310" stroke={accent}/><text x="42" y="329" fill={ink} opacity=".4" fontSize="8" fontFamily="monospace">STYLE + MOTION</text>
 </svg>;
};

export const MediaCard:React.FC<{c:Context;index:number;live?:boolean;kind?:number;label?:string;style?:React.CSSProperties}>=({c,index,live=false,kind=index,label,style})=>{
 const m=mediaAt(c,index),light=c.p.variant==='cobalt';
 return <div style={{position:'relative',width:'100%',height:'100%',background:c.t.panel,border:`1px solid ${c.t.line}`,borderRadius:light?3:8,overflow:'hidden',...style}}><div style={{position:'absolute',inset:0,bottom:label?34:0}}>{m?<Material m={m} live={live}/>:<Study kind={kind} seconds={c.seconds} variant={c.p.variant}/>}</div>{label&&<div style={{position:'absolute',bottom:8,left:12,right:12,...body(c.portrait?23:16,c.t.muted)}}>{label}</div>}</div>;
};

export const NativeWindow:React.FC<{c:Context;title?:string;children:React.ReactNode;style?:React.CSSProperties}>=({c,title,children,style})=><div style={{position:'relative',width:'100%',height:'100%',background:c.p.variant==='reference'?'#071114':c.t.paper,border:`1px solid ${c.t.line}`,borderRadius:c.p.variant==='cobalt'?4:10,overflow:'hidden',boxShadow:c.p.variant==='reference'?'0 0 55px #3556D42C':'0 22px 50px #07121724',...style}}><div style={{height:c.portrait?44:30,background:c.p.variant==='reference'?'#111B20':c.t.panel,display:'flex',alignItems:'center',padding:'0 15px',gap:7}}>{['#EE6A65','#E1B951','#64BD83'].map(color=><i key={color} style={{display:'block',width:6,height:6,borderRadius:'50%',background:color}}/>)}<span style={{...body(c.portrait?16:11,c.t.muted),marginLeft:10}}>{title||'原生动画 · 内容展示'}</span></div><div style={{position:'absolute',top:c.portrait?44:30,left:0,right:0,bottom:0}}>{children}</div></div>;

export const Heading:React.FC<{c:Context;children:React.ReactNode;x?:number;y?:number;size?:number;style?:React.CSSProperties}>=({c,children,x,y,size,style})=><div style={{...rect(x??(c.portrait?88:140),y??(c.portrait?215:145),c.p.width-(c.portrait?176:280),c.portrait?240:180),...text(size??(c.portrait?88:70),c.t.ink,c.p.variant==='hedgerow'?500:700),...style}}>{children}</div>;
export const Pill:React.FC<{c:Context;children:React.ReactNode;active?:boolean;style?:React.CSSProperties}>=({c,children,active=false,style})=><div style={{padding:c.portrait?'11px 23px':'8px 19px',borderRadius:999,background:active?c.t.accent:c.t.paper,color:active?c.t.onAccent:(c.p.variant==='reference'?'#111':c.t.bg),fontFamily:'DarkFullBody',fontWeight:700,fontSize:c.portrait?27:20,display:'inline-flex',alignItems:'center',justifyContent:'center',...style}}>{children}</div>;
