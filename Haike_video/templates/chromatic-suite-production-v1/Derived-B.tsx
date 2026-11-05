// Independent semantic HD derivative; original source identity is in SOURCE_MAP.json.
import React from 'react';
import {AbsoluteFill,Sequence,Video} from 'remotion';
import {useCurrentFrame,useGlobalFrame,useScene,Media} from './Runtime';
type Episode=any; type BaseEpisode=any;

const box=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const p=(f:number,a:number,b:number)=>Math.max(0,Math.min(1,(f-a)/(b-a)));
const smooth=(v:number)=>v<.5?4*v*v*v:1-Math.pow(-2*v+2,3)/2;
const out=(v:number)=>1-Math.pow(1-v,3);
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const fit:React.CSSProperties={width:'100%',height:'100%',objectFit:'cover'};
const purple='#4C23A8',yellow='#FFE033',lilac='#EAE0FF',red='#C9233A',blue='#BDEAF3',paper='#F8E9D4';
const sceneAt=(f:number,ends:number[])=>ends.findIndex(e=>f<e);
type MaterialSlot={src:string;from:number;to:number;sourceFrom:number;sourceTo:number;objectPosition:string;};
type VideoInput=Episode&{materialSlots:Record<string,MaterialSlot>};
function Clip({id,style=fit}:{episode:Episode;id:string;style?:React.CSSProperties}){return <Media id={id} style={style}/>;}
function Material({episode,id,style={},label}:{episode:Episode;id:string;style?:React.CSSProperties;label?:string}){
 return <div data-main-window={id} style={{position:'absolute',overflow:'hidden',...style}}><Clip episode={episode} id={id}/>{label&&<div style={{position:'absolute',bottom:0,left:0,right:0,fontSize:24,padding:'12px 16px',fontWeight:800,background:yellow,color:purple}}>{label}</div>}</div>;
}
function Presenter({episode,show,color,background,rounded=false}:{episode:Episode;show:boolean;color:string;background:string;rounded?:boolean}){
 // The video is mounted once on the global frame clock. Hiding its window never restarts it.
 return <div data-role="presenter" style={{...box(492,851,180,225),visibility:show?'visible':'hidden',border:`3px solid ${color}`,borderRadius:rounded?'92px 92px 3px 3px':2,overflow:'hidden',background}}>
  <Video data-avatar="true" src={episode.presenterClips![0].src} muted volume={0} pauseWhenBuffering style={{...fit,objectPosition:'50% 35%'}}/>
  <div style={{position:'absolute',bottom:0,left:0,right:0,background:color,color:background,fontSize:16,textAlign:'center',padding:6,fontWeight:700}}>{episode.presenterName} · AI数字人</div>
 </div>;
}
function Caption({episode,f,color,background}:{episode:Episode;f:number;color:string;background:string}){
 const cue=episode.captions.find(c=>f>=c.from&&f<c.to);
 return <div data-role="caption" style={{...box(48,1110,624,88),display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',padding:'12px 18px',background,color,fontSize:27,fontWeight:700,lineHeight:1.25}}>{cue?.lines?.join('\n')||cue?.text}</div>;
}
function Orbit({episode,f,final=false}:{episode:Episode;f:number;final?:boolean}){
 const t=Math.min(f,110),a=out(p(t,0,62)),sy=Math.sin(t/300*Math.PI*2),sx=Math.sin(t/300*Math.PI*2+Math.PI/2);
 const angles=[-137,-43,43,137];
 return <div style={{...box(22,285,676,555),perspective:900}}>
  <div data-element="orbit-camera" style={{position:'absolute',inset:0,transformStyle:'preserve-3d',transform:`rotateY(${-5+5*sy}deg) rotateX(${3*sx}deg) translateZ(${12*Math.sin(t/300*Math.PI*2+.6*Math.PI*2)}px)`}}>
   <div style={{...box(89-sy*9,28+sx*5,500,500),border:'3px solid '+lilac,borderRadius:'50%',opacity:.4,transform:'translateZ(-20px)'}}/>
   <div data-element="orbit-ring" style={{...box(89,28,500,500),border:`44px solid ${yellow}`,borderRadius:'50%',transform:`scale(${mix(.66,1,a)})`,opacity:mix(.5,1,a)}}/>
   {angles.map((deg,i)=>{const rad=(deg+mix(-38,0,a))*Math.PI/180;return <Material key={i} episode={episode} id={`08-${final?'outro':'intro'}-${i}`} style={{...box(338+Math.cos(rad)*236-116,278+Math.sin(rad)*190-82,232,164),border:`5px solid ${lilac}`,boxShadow:`5px 5px 0 ${purple}`,transform:`translateZ(${i%2?18:0}px) rotate(${i%2?5:-5}deg) scale(${mix(.75,1,a)})`,opacity:mix(.2,1,a)}}/>})}
   <div style={{...box(230,202,216,150),display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',fontSize:final?43:49,lineHeight:1.05,fontWeight:900,color:yellow,whiteSpace:'pre-line'}}>{final?'先体验\n再理解':'好奇\n入场'}</div>
  </div>
 </div>;
}
function Gallery({episode,f}:{episode:Episode;f:number}){
 // 08 two equal examples: wide -> stop A -> stop B -> wide. Camera alone moves.
 const centers=[275,875],wide={s:.53,x:360-.53*575,y:535-.53*520};
 let cam={...wide};
 const target=(x:number)=>({s:1.08,x:360-1.08*x,y:535-1.08*520});
 const step=(to:typeof cam,a:number,b:number)=>{const k=smooth(p(f,a,b));cam={s:mix(cam.s,to.s,k),x:mix(cam.x,to.x,k),y:mix(cam.y,to.y,k)}};
 step(target(centers[0]),22,55);step(target(centers[1]),107,143);step(wide,198,218);
 const active=f>=45&&f<125?0:f>=125&&f<215?1:-1;
 return <div style={{...box(0,282,720,560),overflow:'hidden',background:'#311568',perspective:1100}}>
  <div style={{...box(0,470,720,90),borderTop:`2px solid ${yellow}`,background:'#3B1B82'}}/>
  <div data-element="gallery-camera" style={{position:'absolute',inset:0,transformOrigin:'0 0',transform:`translate(${cam.x}px,${cam.y-282}px) scale(${cam.s})`,transformStyle:'preserve-3d'}}>
   {centers.map((cx,i)=><div key={i} style={{...box(cx-245,340,490,362),background:lilac,padding:8,transform:`perspective(1600px) rotateY(${i===0?7:-7}deg)`,filter:active!==-1&&active!==i?'brightness(.56)':'none'}}>
    <div style={{position:'absolute',inset:'8px 8px 66px',overflow:'hidden'}}><Clip episode={episode} id={`08-gallery-${i}`} style={{...fit,transform:`scale(${1+.025*p(f,i?143:55,i?198:107)})`}}/></div>
    <div style={{position:'absolute',left:20,bottom:16,fontSize:30,fontWeight:900,color:purple}}>{['看见互动','参与其中'][i]}</div>
   </div>)}
  </div>
  <div style={{...box(48,510,624,30),display:'flex',justifyContent:'space-between',color:lilac,fontSize:19}}><span>展厅 / 两个平等的观察面</span><span>{active===-1?'全景':`停靠 0${active+1}`}</span></div>
 </div>;
}
function TiltRecord({episode,f}:{episode:Episode;f:number}){
 const k=out(p(f,18,63)),hold=p(f,63,149),ry=mix(0,-17,k)-2*hold,rx=mix(0,4,k)-1*hold;
 return <div style={{...box(50,305,620,540),perspective:1000}}><div data-element="tilt-camera" style={{position:'absolute',inset:0,transformStyle:'preserve-3d',transform:`rotateY(${ry}deg) rotateX(${rx}deg) scale(${mix(1,.94,k)})`}}>
  <div style={{position:'absolute',inset:0,background:yellow,opacity:.4,transform:`translate3d(${mix(0,22,k)}px,${mix(0,13,k)}px,-24px)`}}/>
  <div style={{position:'absolute',inset:0,background:lilac,color:purple,border:`2px solid ${yellow}`,backfaceVisibility:'hidden'}}>
   <div style={{...box(24,18,568,34),fontSize:22,fontWeight:800}}>体验记录 / 把问题带进现场</div>
   <Material episode={episode} id="08-tilt" style={box(24,70,568,360)}/>
   <div style={{...box(24,451,568,68),fontSize:30,fontWeight:900,lineHeight:1.2}}>看一看，动一动。<br/>新的理解，就在这一刻。</div>
  </div>
 </div></div>;
}
function FoldCover({episode,f}:{episode:Episode;f:number}){
 const k=smooth(p(f,35,88));
 return <div style={{...box(72,305,578,522),perspective:1100,transform:`translateY(${mix(45,0,out(p(f,0,15)))}px)`}}>
  <div style={{position:'absolute',inset:0,background:paper,border:`2px solid ${red}`,padding:18}}>
   <Material episode={episode} id="09-fold-left" style={box(18,18,250,348)}/><Material episode={episode} id="09-fold-right" style={box(305,18,250,348)}/><div style={{...box(305,391,250,95),fontSize:32,fontWeight:900,color:red}}>从现场开始<br/><span style={{fontSize:24,fontWeight:600}}>翻开自己的观察记录</span></div>
  </div>
  <div data-element="fold-leaf" style={{position:'absolute',left:'50%',top:0,width:'50%',height:'100%',transformOrigin:'left center',transformStyle:'preserve-3d',transform:`rotateY(${-178*k}deg)`}}>
   <div style={{position:'absolute',inset:0,background:red,backfaceVisibility:'hidden',overflow:'hidden',border:`2px solid ${red}`}}><Clip episode={episode} id="09-fold-front" style={{width:578,height:348,objectFit:'cover',position:'absolute',left:-289,top:18}}/><div style={{...box(15,391,250,90),color:paper,fontSize:38,fontWeight:900}}>走进<br/>真实现场</div></div>
   <div style={{position:'absolute',inset:0,transform:'rotateY(180deg)',backfaceVisibility:'hidden',background:blue,border:`2px solid ${red}`}}><div style={{...box(20,24,245,470),borderLeft:`3px solid ${red}`,paddingLeft:18,color:red,fontSize:30,fontWeight:800,lineHeight:1.7}}>现场札记<br/>—<br/>先看见<br/>再靠近<br/>再体验</div></div>
  </div>
  <div style={{...box(286,0,3,522),background:red,opacity:.45}}/>
 </div>;
}
function ParkJournal({episode,f}:{episode:Episode;f:number}){
 const park=smooth(p(f,28,52)),deals=[63,104,145],labels=['观察人的反应','留意互动细节','亲手体验一次'];
 return <div style={{...box(0,302,720,574),overflow:'hidden'}}>
  <div data-element="park-source" style={{...box(70,0,578,540),transformOrigin:'0% 50%',transform:`translateX(${-22*park}px) scale(${mix(1,.42,park)})`,border:`2px solid ${red}`,background:paper,overflow:'hidden'}}>
   <div style={{position:'absolute',inset:0,transform:`translateY(${-f*.22}px)`}}><div style={{padding:20,fontSize:30,fontWeight:900}}>现场记录 / 观察页</div><Material episode={episode} id="09-park" style={box(18,79,538,300)}/><div style={{...box(22,408,530,230),fontSize:29,lineHeight:1.7}}>把视线留给真实的人。<br/>从表情到动作，<br/>从围观到参与，<br/>一页记录，一次发现。</div></div>
  </div>
  {deals.map((at,i)=>{const t=p(f,at,at+12),back=1+2.7*Math.pow(t-1,3)+1.7*Math.pow(t-1,2);return <div data-element={`deal-${i}`} key={i} style={{...box(315,30+i*162,357,132),opacity:out(p(f,at,at+6)),transform:`translateY(${18*(1-back)}px) scale(${mix(.94,1,back)})`,transformOrigin:'left center'}}><div style={{fontSize:31,fontWeight:900,color:paper,background:red,padding:'12px 16px'}}>{labels[i]}</div><div style={{fontSize:25,color:red,marginTop:14,opacity:p(f,at+12,at+29)}}>{['先看见，再产生好奇','问一问，让线索展开','把感受变成自己的理解'][i]}</div></div>})}
 </div>;
}
function ExposeVideo({episode,f}:{episode:Episode;f:number}){
 const cut=43,a=p(f,29,46),cross=smooth(p(f,cut,cut+12)),settle=out(p(f,cut,cut+17));
 const flash=f<cut?.12*Math.pow(p(f,cut-8,cut),3):.12*(1-out(p(f,cut,cut+13)));
 return <div style={{...box(64,304,592,548),background:paper,border:`2px solid ${red}`,overflow:'hidden'}}>
  <Material episode={episode} id="09-exposure-a" style={{position:'absolute',inset:16,opacity:1-cross,transform:`scale(${1.03+.47*a*a*a})`,filter:`blur(${3*a}px)`}}/>
  <Material episode={episode} id="09-exposure-b" style={{position:'absolute',inset:16,opacity:cross,transform:`scale(${mix(1.3,1.03,settle)+.01*p(f,60,149)})`,filter:`blur(${4*(1-settle)}px)`}}/>
  <div data-element="exposure" style={{position:'absolute',inset:0,background:`radial-gradient(ellipse at 50% 46%,${red},${red}66)`,opacity:flash}}/>
  <div style={{...box(16,459,556,68),background:red,color:paper,padding:14,fontSize:29,fontWeight:900}}>把眼前的瞬间，变成新线索</div>
 </div>;
}
function Desk({episode,f}:{episode:Episode;f:number}){
 const a=out(p(f,0,12)),b=out(p(f,39,51));
 return <div style={box(54,307,612,544)}>
  <div style={{...box(8,0,534,398),transform:`translateY(${40*(1-a)}px) rotate(-1.5deg)`,background:paper,border:`2px solid ${red}`,opacity:.25+.75*a,boxShadow:`5px 7px 0 ${red}22`}}><Material episode={episode} id="09-desk-a" style={{...box(16,16,498,272),transform:`scale(${1+.015*p(f,12,119)})`}}/><div style={{...box(20,314,490,55),color:red,fontSize:33,fontWeight:900}}>把发现带回生活<span style={{...box(0,44,231,5),background:red,transformOrigin:'left',transform:`scaleX(${out(p(f,24,34))})`}}/></div></div>
  <div data-element="desk-second" style={{...box(290,281,295,242),border:`2px solid ${red}`,background:blue,padding:12,opacity:b,transform:`translateX(${210*(1-b)}px) rotate(2deg)`}}><Clip episode={episode} id="09-desk-b" style={{width:'100%',height:158,objectFit:'cover'}}/><div style={{fontSize:25,fontWeight:900,color:red,paddingTop:12}}>体验，是理解的开始</div></div>
 </div>;
}

export {Orbit,Gallery,TiltRecord,FoldCover,ParkJournal,ExposeVideo,Desk};
