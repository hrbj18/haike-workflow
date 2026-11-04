import React from 'react';
import {AbsoluteFill,Audio,Img,OffthreadVideo,Sequence,staticFile,useCurrentFrame} from 'remotion';
import type {Media,Props,Scene} from './types';
const PAPER='#F5F6F0',INK='#0C0D10',BLUE='#3246F4',ORANGE='#FF5732';
const clamp=(n:number)=>Math.max(0,Math.min(1,n));
const ease=(t:number,a:number,d=.65)=>{const p=clamp((t-a)/d);return 1-Math.pow(1-p,3)};
const lerp=(a:number,b:number,p:number)=>a+(b-a)*p;
type Box=[number,number,number,number];
const CARD_HEIGHTS=[286,250,320,345,318,286,350,280,270,330,290,320,300,290];
const wallCard=(index:number,scroll:number):Box=>{
 let top=365-scroll;
 for(let i=index%4;i<index;i+=4)top+=CARD_HEIGHTS[i]+24;
 return [140+(index%4)*416,top,392,CARD_HEIGHTS[index]];
};
const mix=(a:Box,b:Box,p:number):Box=>a.map((n,i)=>lerp(n,b[i],p)) as Box;
const rect=(b:Box):React.CSSProperties=>({position:'absolute',left:b[0],top:b[1],width:b[2],height:b[3],boxSizing:'border-box'});
const txt=(size:number,color=INK,weight=700):React.CSSProperties=>({fontSize:size,color,fontWeight:weight,lineHeight:1.18,whiteSpace:'pre-wrap'});
const Shadow:React.FC<{children:React.ReactNode;style?:React.CSSProperties}>=({children,style})=><div style={{position:'absolute',borderRadius:24,background:'#FFF',boxShadow:'0 12px 34px #20252D15',overflow:'hidden',...style}}>{children}</div>;
const Arrow:React.FC<{color?:string;size?:number}>=({color='currentColor',size=28})=><svg width={size} height={size} viewBox="0 0 40 40"><path d="M20 5v27M9 23l11 11 11-11" stroke={color} strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const Cursor:React.FC<{x:number;y:number;click:number;opacity:number}>=({x,y,click,opacity})=><div style={{position:'absolute',left:x,top:y,zIndex:20,opacity,transform:`scale(${1-click*.12})`,transformOrigin:'4px 4px'}}><svg width="45" height="57" viewBox="0 0 45 57"><path d="M4 3v42l11-12 9 20 8-4-10-19 17-2Z" fill="#111" stroke="#FFF" strokeWidth="3"/></svg>{click>0&&<div style={{position:'absolute',left:-18,top:-18,width:42,height:42,borderRadius:'50%',border:`3px solid ${BLUE}`,opacity:1-click,transform:`scale(${1+click})`}}/>}</div>;
const Header:React.FC<{s:Scene;t:number}>=({s,t})=><><div style={{...rect([140,112,1640,105]),...txt(76),opacity:ease(t,s.start,.45),transform:`translateY(${lerp(28,0,ease(t,s.start,.45))}px)`}}>{s.title}</div><div style={{...rect([140,222,1640,52]),...txt(30,'#72767B',450),opacity:ease(t,s.start+.25,.5)}}>{s.subtitle}</div></>;
const Thumb:React.FC<{m:Media}>=({m})=><Img src={staticFile(m.thumbnail)} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',background:'#0B131D'}}/>;
const Orange:React.FC<{s:Scene;t:number}>=({s,t})=>{const i=Math.min(s.labels.length-1,Math.max(0,s.cues.filter(c=>c<=t).length-1));return <AbsoluteFill style={{background:ORANGE,opacity:1-ease(t,s.end-.3,.3)}}><div style={{position:'absolute',left:140,top:120,right:140,display:'flex',gap:140,...txt(31,'#FFF',600),opacity:.18}}>{s.labels.map(x=><span key={x}>{x}</span>)}</div><div style={{...rect([140,372,1640,230]),...txt(154,'#FFF',800),display:'flex',alignItems:'center',justifyContent:'center',letterSpacing:-4,transform:`translateY(${lerp(45,0,ease(t,s.cues[i],.35))}px)`,opacity:ease(t,s.cues[i],.3)}}>{s.labels[i]}</div><div style={{...rect([140,690,1640,90]),...txt(42,'#FFF',500),textAlign:'center',opacity:ease(t,s.start+.5)}}>{s.subtitle}</div></AbsoluteFill>};
const Gallery:React.FC<{p:Props;s:Scene;detail:Scene;t:number}>=({p,s,detail,t})=>{
 const scroll=Math.max(0,Math.min(t,detail.start)-s.start)*16;
 const hide=1-ease(t,detail.start,.65),photos=p.media.filter(m=>m.kind==='image');
 const chips=['认识AI','真实互动','亲手体验','学习伙伴'];
 const active=Math.min(3,Math.max(0,s.cues.filter(c=>c<=t).length-1));
 return <AbsoluteFill style={{opacity:hide}}><Header s={s} t={t}/>
  <div style={{position:'absolute',left:140,top:280,display:'flex',gap:16}}>{chips.map((x,i)=><div key={x} style={{border:'1px solid #DADDDD',borderRadius:32,padding:'12px 27px',background:i===active?BLUE:'#FFF',...txt(28,i===active?'#FFF':INK,650)}}>{x}</div>)}</div>
  <div style={{position:'absolute',left:140,top:365,width:1640,height:568,overflow:'hidden'}}>{CARD_HEIGHTS.map((height,i)=>{
   if(i===5)return null;
   const box=wallCard(i,scroll),m=photos[i%photos.length],enter=ease(t,s.start+i*.065,.5);
   return <Shadow key={i} style={{left:box[0]-140,top:box[1]-365,width:box[2],height,opacity:enter,transform:`translateY(${lerp(65,0,enter)}px)`}}>
    <div style={{...rect([12,12,368,height-70]),borderRadius:13,overflow:'hidden'}}><Thumb m={m}/></div>
    <div style={{...rect([20,height-43,352,37]),...txt(26)}}>{m.label}</div>
   </Shadow>;
  })}</div>
 </AbsoluteFill>;
};

// This single DOM object owns the selected wall card, expanded detail, side
// thumbnail and closing handoff. Its identity is retained through all phases.
const PersistentHero:React.FC<{p:Props;t:number;wall:Scene;detail:Scene;quote:Scene;notice:Scene;brand:Scene}>=({p,t,wall,detail,quote,notice,brand})=>{
 const photos=p.media.filter(m=>m.kind==='image'),selected=photos[5]||photos[0];if(!selected)return null;
 const wallScroll=Math.max(0,Math.min(t,detail.start)-wall.start)*16;
 const origin=wallCard(5,wallScroll),hero:Box=[140,310,1000,562],quoteBox:Box=[140,335,830,467],noticeBox:Box=[140,345,600,338];
 let box=mix(origin,hero,ease(t,detail.start+.2,.9));box=mix(box,quoteBox,ease(t,quote.start,.75));box=mix(box,noticeBox,ease(t,notice.start,.7));
 const alpha=ease(t,wall.start+.325,.5)*(1-ease(t,brand.start,.45));
 const windows=p.scenes.flatMap(s=>s.windows||[]),caption=t<detail.start?selected.label:t<quote.start?'真实门店 · 原速实拍':t<notice.start?'本期真实活动画面':'到店体验 · 信息参考';
 return <div data-object-id="selected-experience" style={{...rect(box),borderRadius:24,overflow:'hidden',zIndex:4,opacity:alpha,background:'#FFF',boxShadow:'0 15px 44px #151B2620',outline:t>detail.start&&t<detail.start+.3?`4px solid ${BLUE}`:undefined}}><div style={{position:'absolute',left:12,top:12,right:12,bottom:t<detail.start?58:58,borderRadius:14,overflow:'hidden'}}><Thumb m={selected}/>{windows.map((w,i)=>{const m=p.media.find(m=>m.id===w.mediaId)!;return <Sequence key={i} from={Math.round(w.start*p.fps)} durationInFrames={Math.round((w.end-w.start)*p.fps)} layout="none"><OffthreadVideo src={staticFile(m.src)} trimBefore={Math.round(w.offset*p.fps)} muted style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',background:'#0B131D'}}/></Sequence>})}</div><div style={{...rect([22,box[3]-48,box[2]-44,38]),...txt(t<detail.start?26:27,INK,600)}}>{caption}</div></div>
};
const Detail:React.FC<{s:Scene;t:number}>=({s,t})=>{
 const n=ease(t,s.start+.65,.6),focus=Math.min(s.labels.length-1,Math.max(0,s.cues.filter(c=>c<=t).length-1));
 const click=clamp((t-(s.end-2))/.38);
 return <AbsoluteFill style={{opacity:n*(1-ease(t,s.end-.18,.18))}}><Header s={s} t={t}/>
  <div style={{...rect([1200,330,580,550]),opacity:n,transform:`translateX(${lerp(55,0,n)}px)`}}>
   <div style={{...rect([0,0,580,132]),...txt(55)}}>{s.labels[focus]}</div>
   <div style={{...rect([0,142,580,80]),...txt(26,'#73777D',500)}}>在真实门店认识AI。<br/>当前画面为门店与亲子互动实拍。</div>
   <div style={{position:'absolute',left:0,top:242,width:580,display:'flex',flexWrap:'wrap',gap:12}}>{s.labels.map((x,i)=><div key={x} style={{padding:'10px 18px',borderRadius:28,background:i===focus?BLUE:'#ECEEF0',...txt(23,i===focus?'#FFF':INK,600)}}>{x}</div>)}</div>
   <div data-object-id="guide-button" style={{...rect([0,382,580,83]),borderRadius:48,background:BLUE,display:'flex',alignItems:'center',justifyContent:'center',gap:19,...txt(32,'#FFF'),transform:`scale(${1-.025*Math.sin(click*Math.PI)})`}}>保存到店指引 <Arrow color="#FFF"/></div>
   <div style={{...rect([0,493,580,40]),...txt(24,'#73777D',450)}}>陈家林路63号 · 未来汇一楼</div>
  </div>
 </AbsoluteFill>;
};
const Quote:React.FC<{s:Scene;t:number}>=({s,t})=><AbsoluteFill style={{opacity:ease(t,s.start,.55)*(1-ease(t,s.end-.2,.2))}}><Header s={s} t={t}/><Shadow style={{...rect([1030,335,750,467]),padding:'44px 48px'}}><div style={{...txt(84,BLUE),lineHeight:.8}}>“</div><div style={{marginTop:15,...txt(55)}}>{s.labels[0]}</div><div style={{marginTop:32,...txt(26,'#73777D',500)}}>原稿情境转述 · 非实拍采访</div><div style={{marginTop:26,...txt(28,BLUE)}}>{s.labels[1]}</div></Shadow></AbsoluteFill>;
const Notice:React.FC<{s:Scene;t:number}>=({s,t})=><AbsoluteFill style={{opacity:ease(t,s.start,.55)*(1-ease(t,s.end-.2,.2))}}><Header s={s} t={t}/><Shadow style={{...rect([820,330,960,510]),padding:'54px 48px'}}><div style={txt(57)}>AI体质检测：<br/>非医疗诊断。</div><div style={{marginTop:32,...txt(38)}}>不看病不卖药，给您个参考。</div><div style={{display:'flex',alignItems:'center',gap:18,marginTop:43,...txt(28,BLUE)}}><Arrow color={BLUE}/>陈家林路63号 · 未来汇一楼</div></Shadow></AbsoluteFill>;
const Brand:React.FC<{p:Props;s:Scene;t:number}>=({p,s,t})=><AbsoluteFill style={{background:'#050505',opacity:ease(t,s.start,.5)}}><div style={{...rect([140,312,1640,170]),...txt(126,'#F7F8F1',800),textAlign:'center',opacity:ease(t,s.start+.15,.65),letterSpacing:-3}}>{p.brand}</div><div style={{...rect([140,520,1640,100]),...txt(48,'#C1C2BC',550),textAlign:'center',opacity:ease(t,s.start+.55)}}>{s.title}</div><div style={{position:'absolute',left:500,top:675,width:920,height:84,borderRadius:44,background:'#E1FF45',display:'flex',alignItems:'center',justifyContent:'center',...txt(36),opacity:ease(t,s.start+.9)}}>陈家林路63号 · 未来汇一楼</div><div style={{...rect([140,829,1640,78]),...txt(29,'#B1B5B4',450),textAlign:'center',opacity:ease(t,s.start+1.2)}}>AI体质检测：非医疗诊断。不看病不卖药，给您个参考。</div></AbsoluteFill>;
export const PromoReference:React.FC<Props>=p=>{
 const f=useCurrentFrame(),t=f/p.fps;
 const sc=p.scenes.find(s=>t>=s.start&&t<s.end)||p.scenes[p.scenes.length-1];
 const find=(recipe:Scene['recipe'])=>p.scenes.find(s=>s.recipe===recipe)!;
 if(!sc)return <AbsoluteFill style={{background:PAPER}}/>;
 const orange=find('orange'),wall=find('wall'),detail=find('detail'),quote=find('quote'),notice=find('notice'),brand=find('brand');
 const cap=p.captions.find(c=>c.s<=t&&c.e>t),cursorAge=ease(t,wall.end-1.1,.8);
 const selected=wallCard(5,(detail.start-wall.start)*16);
 const selecting=t>=wall.end-1.1&&t<detail.start+1;
 const saving=t>=detail.end-2.7&&t<detail.end-.6,saveAge=ease(t,detail.end-2.7,.65);
 const clicked=selecting?clamp((t-(detail.start+.2))/.35):clamp((t-(detail.end-2))/.38);
 const cursorX=saving?lerp(1050,1490,saveAge):lerp(1570,selected[0]+204,cursorAge);
 const cursorY=saving?lerp(850,753,saveAge):lerp(800,selected[1]+110,cursorAge);
 return <AbsoluteFill style={{background:PAPER}}>
  {p.audio&&<Audio src={staticFile(p.audio)}/>}
  <Gallery p={p} s={wall} detail={detail} t={t}/><Detail s={detail} t={t}/>
  <Quote s={quote} t={t}/><Notice s={notice} t={t}/>
  <PersistentHero p={p} t={t} wall={wall} detail={detail} quote={quote} notice={notice} brand={brand}/>
  <Cursor x={cursorX} y={cursorY} click={clicked} opacity={selecting||saving?1:0}/>
  <Brand p={p} s={brand} t={t}/>{t<orange.end&&<Orange s={orange} t={t}/>}
  <div style={{position:'absolute',top:52,right:70,padding:'10px 22px',borderRadius:28,background:t<brand.start?'#EEEFE9':'#FFFFFF12',display:'flex',alignItems:'center',gap:13,...txt(22,t<brand.start?INK:'#DDD',600),zIndex:20}}><i style={{width:11,height:11,borderRadius:'50%',background:ORANGE}}/>海客AI · 亲手体验</div>
  {cap&&<div style={{position:'absolute',left:90,right:90,bottom:39,textAlign:'center',...txt(46,t<orange.end||t>=brand.start?'#FFF':INK,600),zIndex:30,textShadow:t<orange.end||t>=brand.start?'0 2px 5px #0005':undefined}}>{cap.text}</div>}
 </AbsoluteFill>;
};
