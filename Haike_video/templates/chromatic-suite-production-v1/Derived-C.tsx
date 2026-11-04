// Independent semantic HD derivative; original source identity is in SOURCE_MAP.json.
import React from 'react';
import {AbsoluteFill,Sequence,Video} from 'remotion';
import {useCurrentFrame,useGlobalFrame,useScene,Media} from './Runtime';
type Episode=any; type BaseEpisode=any;

const B={paper:'#F5F4E8',ink:'#151512',acid:'#E3FF3B'};
const N={paper:'#102C43',ink:'#F5F4E8',peach:'#FFAD8F',teal:'#52D3CC'};
const box=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height,boxSizing:'border-box'});
const p=(f:number,a:number,b:number)=>Math.max(0,Math.min(1,(f-a)/(b-a)));
const smooth=(t:number)=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
const out=(t:number)=>1-Math.pow(1-t,4);
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const cover:React.CSSProperties={width:'100%',height:'100%',objectFit:'cover',display:'block'};
type Clip={from:number;to:number;sourceStart:number;src:string;fit:'contain'|'cover';objectPosition:string};
type VideoEpisode=Episode & {videoSlots:Record<string,Clip[]>};
function Material({slot}:{episode:Episode;slot:string}){return <Media id={slot}/>;}
function Presenter({episode,navy=false}:{episode:Episode;navy?:boolean}){
 const f=useCurrentFrame(),visible=f<150||f>=570;
 const clip=episode.presenterClips?.find(c=>f>=c.from&&f<c.to)||episode.presenterClips?.[0];
 if(!clip)return null;
 // Kept mounted through the middle: global frame advances continuously, no loop or scene restart.
 return <div data-role="presenter" data-visible={visible} style={{...box(514,842,158,230),visibility:visible?'visible':'hidden',overflow:'hidden',border:`${navy?2:3}px solid ${navy?N.peach:B.ink}`,background:navy?N.paper:B.paper,zIndex:8}}>
  <Video data-avatar src={clip.src} muted volume={0} pauseWhenBuffering style={{...cover,objectPosition:'50% 35%'}}/>
  <div data-role="presenter-label" style={{position:'absolute',left:0,right:0,bottom:0,background:navy?N.peach:B.acid,color:navy?N.paper:B.ink,padding:'6px 0',fontSize:15,textAlign:'center',fontWeight:800}}>{episode.presenterName} · AI数字人</div>
 </div>;
}
function Caption({episode,navy=false}:{episode:Episode;navy?:boolean}){
 const f=useCurrentFrame(),c=episode.captions.find(c=>f>=c.from&&f<c.to);
 return <><div data-element="caption" style={{...box(48,1110,624,88),display:'flex',alignItems:'center',justifyContent:'center',padding:'12px 18px',fontSize:27,lineHeight:1.3,fontWeight:700,textAlign:'center',background:navy?'#173B53':B.ink,color:navy?N.ink:B.paper,border:navy?`1px solid ${N.teal}`:'none'}}>{c?.text}</div>
 <div style={{...box(48,1222,624,26),fontSize:15,display:'flex',justifyContent:'space-between'}}><span>现场笔记 / 静音动效样片</span><span>{String(Math.floor(f/30)).padStart(2,'0')} / 24</span></div>
 <div style={{...box(48,1252,624,3),background:navy?'#33576B':'#C9C9BE'}}/><div style={{...box(48,1252,624*(f+1)/720,3),background:navy?N.peach:B.ink}}/></>;
}
function Evidence({episode,index,style,navy=false}:{episode:Episode;index:number;style:React.CSSProperties;navy?:boolean}){
 return <div data-video-window={index} style={{overflow:'hidden',border:`${navy?1:3}px solid ${navy?N.ink:B.ink}`,...style}}><Material episode={episode} slot={navy?`route-${index}`:index===0?'impact':'assemble'}/>{navy&&<div style={{position:'absolute',inset:6,border:'1px solid #FFFFFF70',pointerEvents:'none'}}/>}</div>;
}
function Impact({episode}:{episode:Episode}){
 const f=useCurrentFrame(),slam=out(p(f,9,15)),corner=out(p(f,9,18)),reveal=smooth(p(f,34,58));
 return <><div data-element="headline" style={{...box(48,142,624,190),fontSize:76,fontWeight:900,lineHeight:1.06,letterSpacing:-4,transformOrigin:'left center',opacity:slam,transform:`scale(${mix(1.08,1,slam)})`}}>把好奇<br/><span style={{display:'inline-block',background:f>=18?B.acid:'transparent',transformOrigin:'left center',transform:`scale(${f<18?1:mix(1.13,1,out(p(f,18,23)))})`}}>带到现场</span></div>
  <Evidence episode={episode} index={0} style={{...box(0,382,720,414),clipPath:`inset(0 ${(1-reveal)*100}% 0 0)`}}/>
  <div style={{...box(48,813,420,28),fontSize:18,letterSpacing:2}}>01 / 不隔着屏幕看热闹</div>
  <div style={{...box(48,877,410,146),fontSize:45,fontWeight:900,lineHeight:1.18,opacity:p(f,62,72)}}>先看见真实<br/>再产生好奇。</div>
  {[[34,118,-1,-1],[650,322,1,1]].map(([x,y,dx,dy],i)=><div key={i} style={{...box(x+dx*10*(1-corner),y+dy*10*(1-corner),36,36),border:`3px solid ${B.ink}`,borderRight:i?undefined:0,borderBottom:i?undefined:0,borderLeft:i?0:undefined,borderTop:i?0:undefined,opacity:corner}}/>)}</>;
}
const relayCuts=[0,66,138,210],relayPhotos=[2,4,6,1,3],verbs=['看见','参与','交流','发现'];
function Filmstrip({episode}:{episode:Episode}){
 const f=useCurrentFrame()-150;
 let pos=0;for(let i=1;i<4;i++)pos+=smooth(p(f,relayCuts[i],relayCuts[i]+14));
 return <><div style={{...box(48,134,624,120),fontSize:52,fontWeight:900,lineHeight:1.12}}>换一个视角<br/>现场会回答</div>
  <div data-element="filmstrip" data-position={pos} style={{...box(0,326,720,474),overflow:'hidden',background:B.ink}}>
   <div style={{position:'absolute',left:75-pos*594,top:22,display:'flex',gap:24}}>{relayPhotos.map((n,i)=><div key={i} style={{position:'relative',width:570,height:430,flexShrink:0,border:`${i%2?7:3}px solid ${i%2?B.paper:B.acid}`,boxSizing:'border-box'}}><Material episode={episode} slot={`relay-${i}`}/><span style={{position:'absolute',bottom:0,left:0,padding:'8px 14px',background:i%2?B.paper:B.acid,color:B.ink,fontSize:18,fontWeight:800}}>{String(i+1).padStart(2,'0')} / 现场切片</span></div>)}</div>
  </div>
  <div style={{...box(48,856,624,32),fontSize:24,textAlign:'center'}}>同一个现场，可以</div>
  <div data-element="relay-word" style={{...box(48,908,624,94),textAlign:'center'}}>{verbs.map((v,i)=>{
   const incoming=i===0?p(f,6,14):out(p(f,relayCuts[i]+7,relayCuts[i]+15));
   const outgoing=i<3?1-p(f,relayCuts[i+1],relayCuts[i+1]+6):1;
   return <div key={v} style={{position:'absolute',left:0,right:0,fontSize:76,lineHeight:1,fontWeight:900,opacity:incoming*outgoing,transform:`translateY(${(1-incoming)*16}px)`}}><span style={{background:i===3?B.acid:'transparent',padding:'0 20px'}}>{v}</span></div>;
  })}</div>
  <div style={{...box(48,1038,624,22),fontSize:20,textAlign:'center',letterSpacing:2}}>走近一点，发现就多一点。</div></>;
}
function Assemble({episode}:{episode:Episode}){
 const f=useCurrentFrame()-438,t=p(f,18,42),k=smooth(t),scale=f<18?mix(2.3,2.43,p(f,0,18)):mix(2.43,1,smooth(p(f,18,30))),lift=out(p(f,48,64));
 return <><div style={{...box(48,136,624,30),fontSize:20,letterSpacing:2}}>03 / 不是走过，是亲自参与</div>
  <div data-element="lead-assemble" style={{...box(48+258*(1-k),252-22*lift,624,90),fontSize:54,lineHeight:1.2,fontWeight:900,whiteSpace:'nowrap',transformOrigin:'54px 50%',transform:`scale(${scale})`}}><span style={{background:B.acid}}>体验</span>{['连接','新发现'].map((w,i)=><span key={w} style={{display:'inline-block',marginLeft:18,opacity:p(f,25+i*4,27+i*4),transform:`translateX(${28*(1-out(p(f,25+i*4,37+i*4)))}px)`}}>{w}</span>)}</div>
  <div style={{...box(48,356,624,35),fontSize:24,opacity:lift}}>把看到的，变成理解的。</div>
  <Evidence episode={episode} index={2} style={{...box(48,458,624,450),opacity:p(f,65,73)}}/>
  <div data-native-note="assemble" style={{...box(48,950,624,98),fontSize:33,fontWeight:800,lineHeight:1.3,opacity:p(f,74,83)}}>人和人之间的互动<br/>是现场最值得记录的细节。</div></>;
}
function PosterRecap({episode}:{episode:Episode}){
 const f=useCurrentFrame()-570,k=out(p(f,0,6));
 return <><div data-element="headline" style={{...box(48,132,624,146),fontSize:62,fontWeight:900,lineHeight:1.1,transformOrigin:'left center',transform:`scale(${mix(1.08,1,k)})`}}>把新发现<br/><span style={{display:'inline-block',background:f>=9?B.acid:'transparent',transformOrigin:'left center',transform:`scale(${f<9?1:mix(1.13,1,out(p(f,9,14)))})`}}>带回生活</span></div>
  <div data-element="register" style={{...box(48,332,624,414),overflow:'hidden',background:B.ink}}><div style={{...box(0,0,624,414),display:'flex',gap:3}}>{[0,2,4].map((n,i)=><div key={n} style={{position:'relative',width:206,flexShrink:0,height:414}}><Material episode={episode} slot={`recap-${i}`}/><span style={{position:'absolute',bottom:0,left:0,right:0,background:f>36+i*9?B.acid:B.paper,color:B.ink,padding:'13px 8px',fontSize:27,fontWeight:900,textAlign:'center'}}>{['看见','参与','理解'][i]}</span></div>)}</div></div>
  <div style={{...box(48,797,624,3),background:B.ink}}/>
  <div style={{...box(48,845,416,180),fontSize:46,fontWeight:900,lineHeight:1.23}}>从现场出发<br/>带着发现回来<span style={{display:'block',fontSize:20,marginTop:20,fontWeight:500}}>保持好奇 / 下一次继续</span></div></>;
}
// Route world is a schematic experience sequence, never geographic claims.
const stops=[{x:110,y:400,px:170,py:24,n:0,name:'走进现场'},{x:650,y:930,px:10,py:554,n:4,name:'亲手体验'},{x:110,y:1460,px:170,py:1084,n:2,name:'留下发现'}];
const paths=['M110 400 Q730 550 650 930','M650 930 Q-10 1090 110 1460'];
function Pin({x,y,at,f,label}:{x:number;y:number;at:number;f:number;label:string}){
 const d=p(f,at,at+8),r=out(p(f,at+10,at+18)),s=f<at+8?1:f<at+10?1.3:mix(1.3,1,r),sy=f<at+8?1:f<at+10?.7:mix(.7,1,r);
 return <g opacity={f>=at?1:0}><g transform={`translate(${x} ${y-52*(1-d*d*d)}) scale(${s} ${sy})`}><path d="M0 0 C-8 -16 -21 -24 -21 -38 A21 21 0 1 1 21 -38 C21 -24 8 -16 0 0" fill={N.peach}/><circle cy={-38} r={8} fill={N.paper}/></g><text x={x>400?x-32:x+32} textAnchor={x>400?'end':'start'} y={y+38} fill={N.ink} fontSize={24} fontWeight={700} opacity={p(f,at+10,at+16)}>{label}</text></g>;
}
function RouteWorld({episode,overview=false}:{episode:Episode;overview?:boolean}){
 const f=useCurrentFrame();
 const shift=f<180?0:f<390?530*smooth(p(f,180,224)):530+530*smooth(p(f,390,432));
 const pull=p(f,540,647),scale=overview?mix(1,.52,pull):1;
 const x=overview?mix(0,100,pull):0,y=overview?mix(-1060,0,pull):-shift;
 const draw=[smooth(p(f,100,210)),smooth(p(f,390,426))];
 return <div data-element="route-camera" data-world-scale={scale} style={{...box(0,300,720,overview?790:494),overflow:'hidden'}}>
  <div style={{...box(0,0,760,1540),transformOrigin:'0 0',transform:`translate(${x}px,${y}px) scale(${scale})`}}>
   <svg width={760} height={1540} style={{position:'absolute',inset:0}}>
    {paths.map((d,i)=><React.Fragment key={i}><path d={d} fill="none" stroke="#35596E" strokeWidth={2} strokeDasharray="5 12"/><path d={d} pathLength={1} fill="none" stroke={N.peach} strokeWidth={5} strokeDasharray={1} strokeDashoffset={1-draw[i]}/></React.Fragment>)}
    {stops.map((s,i)=><Pin key={s.name} x={s.x} y={s.y} at={[8,210,426][i]} f={f} label={`0${i+1} / ${s.name}`}/>)}
   </svg>
   {stops.map((s,i)=>{const a=[34,232,446][i],k=out(p(f,a,a+22));return <div key={s.name} data-stop={i} style={{...box(s.px,s.py,500,354),transformOrigin:'0 100%',transform:`scale(${mix(.02,1,k)})`,opacity:k}}><Evidence episode={episode} index={s.n} navy style={{...box(0,0,500,354)}}/><div style={{...box(16,305,468,34),padding:'6px 12px',background:N.paper,color:N.ink,fontSize:20}}>FIG. 0{i+1} / {s.name}</div></div>;})}
  </div>
 </div>;
}
function StepLine(){
 const f=useCurrentFrame()-390,progress=smooth(p(f,60,94)),ats=[.1,.5,.9].map(v=>{let lo=0,hi=1;for(let n=0;n<25;n++){const m=(lo+hi)/2;if(smooth(m)<v)lo=m;else hi=m;}return 60+34*(lo+hi)/2;});
 return <div data-element="step-timeline" style={{...box(60,842,420,210)}}><div style={{...box(8,0,2,192),background:N.teal,transformOrigin:'top',transform:`scaleY(${progress})`}}/>{['先看见','再参与','才理解'].map((s,i)=>{const pop=out(p(f,ats[i],ats[i]+6)),ring=p(f,105,112)*(i===2?1:0);return <React.Fragment key={s}><div style={{...box(1,19.2+i*76.8-7,16,16),border:`${ring*3}px solid ${N.peach}`,background:ring?N.paper:N.teal,borderRadius:'50%',transform:`scale(${pop*(1+.25*ring)})`}}/><div style={{...box(38,19.2+i*76.8-17,360,40),fontSize:28,fontWeight:700,opacity:p(f,ats[i]+2,ats[i]+10)}}>{s}</div></React.Fragment>;})}</div>;
}
function Callout(){
 const f=useCurrentFrame()-180;
 return <div data-element="callout" style={{...box(0,0,720,1100)}}><svg width={720} height={1100} style={{position:'absolute',inset:0}}><circle cx={10} cy={636} r={7} fill={N.teal} opacity={p(f,72,78)}/><path d="M10 636 L244 870 H48" fill="none" stroke={N.teal} strokeWidth={3} pathLength={1} strokeDasharray={1} strokeDashoffset={1-out(p(f,78,90))}/></svg><div style={{...box(48,875,624,132),paddingTop:8,fontSize:32,fontWeight:700,clipPath:`inset(0 ${(1-out(p(f,90,99)))*100}% 0 0)`}}>现场，正在发生。<span style={{display:'block',fontSize:22,fontWeight:400,marginTop:10,color:'#C4D8E3'}}>沿着体验走，理解才会发生。</span></div></div>;
}

export {Impact,Filmstrip,Assemble,PosterRecap,RouteWorld,StepLine,Callout};
