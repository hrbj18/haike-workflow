// Independent semantic HD derivative; original source identity is in SOURCE_MAP.json.
import React,{createContext,useContext} from 'react';
import {AbsoluteFill,Sequence,Video} from 'remotion';
import {useCurrentFrame,useGlobalFrame,useScene,Media} from './Runtime';
type BaseEpisode=any;

export type Episode=BaseEpisode&{materialClips:{src:string;starts:number[];frames:number;objectPosition:string}[]};
const MaterialPhase=createContext(0);

const b=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const q=(f:number,a:number,z:number)=>Math.max(0,Math.min(1,(f-a)/(z-a)));
const smooth=(v:number)=>v*v*(3-2*v);
const lerp=(a:number,z:number,v:number)=>a+(z-a)*v;
const out=(v:number)=>1-Math.pow(1-v,4);
const back=(v:number)=>1+2.7*Math.pow(v-1,3)+1.7*Math.pow(v-1,2);
const cover:React.CSSProperties={width:'100%',height:'100%',objectFit:'cover'};
const blue='#1635F2',orange='#FF6B1A',cream='#FFF1C9',pink='#F4AFCB',green='#245E37',paper='#FFF4DA';
function Material({n}:{episode:Episode;n:number}){return <Media id={String(n)}/>;}
function Presenter({episode,show,sticker=false}:{episode:Episode;show:boolean;sticker?:boolean}){
 const f=useCurrentFrame(),clip=episode.presenterClips?.find(v=>f>=v.from&&f<v.to)||episode.presenterClips?.[0];
 return <div data-role="presenter" data-visible={show} style={{...b(sticker?482:496,864,sticker?182:176,220),visibility:show?'visible':'hidden',overflow:'hidden',background:'#fff',border:sticker?'7px solid white':`3px solid ${orange}`,borderRadius:sticker?24:'0 26px 0 0',boxShadow:sticker?`7px 8px 0 ${green}`:undefined,zIndex:30}}>
  <Video data-avatar="true" src={clip?.src||episode.presenter!} muted volume={0} pauseWhenBuffering onSeeked={e=>{e.currentTarget.dataset.decodedFrame=String(Math.round(e.currentTarget.currentTime*30))}} onLoadedData={e=>{e.currentTarget.dataset.decodedFrame=String(Math.round(e.currentTarget.currentTime*30))}} style={{...cover,objectPosition:'50% 35%'}}/>
  <div style={{position:'absolute',bottom:0,left:0,right:0,background:sticker?green:blue,color:paper,padding:6,fontSize:15,textAlign:'center',fontWeight:800}}>{episode.presenterName} · AI数字人</div>
 </div>;
}
function Caption({episode,ink,bg}:{episode:Episode;ink:string;bg:string}){const f=useCurrentFrame(),cue=episode.captions.find(c=>f>=c.from&&f<c.to);return <div data-element="caption" style={{...b(44,1110,632,88),background:ink,color:bg,fontSize:27,lineHeight:1.3,fontWeight:800,padding:'14px 18px',display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center'}}>{cue?.lines?.join('\n')||cue?.text||''}</div>}

// Source-space robot head / child's hand centers measured on source165/210/255/300/329.
// Map through same604x454 cover crop at50%/58%; SVG inherits card rotation.
const anchors=[[0,64,412,130,395],[45,76,411,128,410],[90,99,412,144,400],[135,116,413,172,390],[164,124,429,190,395]];
function MovingAnnotation(){
 const draw=useCurrentFrame()-420,f=useGlobalFrame()-useScene().from;if(f>164)return null;let k=0;while(k<anchors.length-2&&f>anchors[k+1][0])k++;
 const a=anchors[k],z=anchors[k+1],t=q(f,a[0],z[0]),s=604/360,offset=(640*s-454)*.58;
 const x=lerp(a[1],z[1],t)*s,y=lerp(a[2],z[2],t)*s-offset,hx=lerp(a[3],z[3],t)*s,hy=lerp(a[4],z[4],t)*s-offset;
 const circle=`M${x-48} ${y-8} C${x-64} ${y-48} ${x+47} ${y-58} ${x+54} ${y-4} C${x+64} ${y+48} ${x-52} ${y+55} ${x-49} ${y-8} C${x-51} ${y-51} ${x+49} ${y-48} ${x+54} ${y-4}`;
 return <svg data-element="moving-annotation" data-anchor-x={x} data-anchor-y={y} viewBox="0 0 604 454" style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}><Mark f={draw} from={20} to={37} d={circle}/><Mark f={draw} from={65} to={77} d={`M${hx+144} ${hy+85} Q${hx+78} ${hy+95} ${hx+12} ${hy+12}`}/><Mark f={draw} from={77} to={82} d={`M${hx+14} ${hy+42} L${hx+12} ${hy+12} L${hx+43} ${hy+20}`}/></svg>;
}
function StickerPhoto({episode,n,x,y,w,h,rotation=0,scale=1,opacity=1,label,annotate=false}:{episode:Episode;n:number;x:number;y:number;w:number;h:number;rotation?:number;scale?:number;opacity?:number;label?:string;annotate?:boolean}){return <div data-element={`sticker-${n}`} style={{...b(x,y,w,h),background:'#fff',padding:8,borderRadius:22,boxShadow:`8px 9px 0 ${green}`,transform:`rotate(${rotation}deg) scale(${scale})`,transformOrigin:'50% 60%',opacity,overflow:'hidden'}}><div style={{position:'relative',height:label?'calc(100% - 38px)':'100%',overflow:'hidden',borderRadius:14}}><Material episode={episode} n={n}/>{annotate&&<MovingAnnotation/>}</div>{label&&<div style={{fontSize:23,fontWeight:900,color:green,paddingTop:7,textAlign:'center'}}>{label}</div>}</div>}
function Mark({d,from,to,f}:{d:string;from:number;to:number;f:number}){return <path d={d} fill="none" stroke={pink} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1-smooth(q(f,from,to))}/>}
const titles07=['把好奇\n贴进今天','现场的快乐\n一张张收好','停一下\n发现小细节','带一点新鲜\n回到生活'];
function StickerMaterial({episode,f,index}:{episode:Episode;f:number;index:number}){
 if(index===0){const fan=out(q(f,28,52)),flat=smooth(q(f,82,104));return <>{[0,2,4].map((n,k)=>{const angle=(k-1)*18,rad=angle*Math.PI/180;const dx=lerp((k-1)*8,Math.sin(rad)*500,fan),dy=lerp((k-1)*-4,(1-Math.cos(rad))*500,fan);return <StickerPhoto key={n} episode={episode} n={n} x={lerp(231+dx,16+k*218,flat)} y={lerp(440+dy,430,flat)} w={258} h={300} rotation={lerp(lerp((k-1)*3,angle,fan),0,flat)} scale={lerp(1,.78,flat)} label={['先看','再问','试试'][k]} opacity={q(f,4+k*3,16+k*3)}/>})}<div style={{...b(50,820,400,112),fontSize:36,lineHeight:1.25,fontWeight:900}}>每个瞬间，<br/>都值得亲自打开。</div><div style={{...b(56,930,340,70),borderRadius:40,border:'6px solid white',background:green,color:paper,fontSize:28,fontWeight:900,padding:'12px 20px',transform:'rotate(-4deg)',boxShadow:`5px 6px 0 ${green}`}}>今日收集 / 好奇心</div></>}
 if(index===1){const spots=[[45,320,400,300,-4],[292,505,350,282,5],[62,718,390,282,-3]];return <>{spots.map(([x,y,w,h,r],k)=>{const t=q(f,12+k*4,21+k*4);return <StickerPhoto key={k} episode={episode} n={[1,3,5][k]} x={x} y={y} w={w} h={h} rotation={lerp(r-6,r,back(t))} scale={lerp(.8,1,back(t))} opacity={q(f,12+k*4,17+k*4)} label={['走进人群','看看互动','留下笑容'][k]}/>})}<div style={{...b(490,920,176,90),fontSize:28,lineHeight:1.3,fontWeight:900}}>快乐，<br/>有迹可循。</div></>}
 if(index===2)return <><StickerPhoto episode={episode} n={2} x={50} y={322} w={620} h={470} rotation={-2} annotate/><div style={{...b(52,852,390,150),fontSize:40,fontWeight:900,lineHeight:1.25}}>它在动，<br/>孩子也在回应。</div><div style={{...b(494,906,160,60),background:green,color:paper,borderRadius:30,padding:12,fontSize:24,fontWeight:900,transform:'rotate(4deg)'}}>看见互动</div></>;
 return <><StickerPhoto episode={episode} n={0} x={48} y={326} w={542} h={400} rotation={-3} scale={lerp(.8,1,back(q(f,4,13)))} opacity={q(f,4,9)}/><StickerPhoto episode={episode} n={7} x={305} y={623} w={350} h={220} rotation={5} scale={lerp(.8,1,back(q(f,9,18)))} opacity={q(f,9,14)}/><div style={{...b(60,855,365,146),fontSize:42,fontWeight:900,lineHeight:1.26,opacity:q(f,27,41)}}>体验过，<br/>才有自己的发现。</div><div style={{...b(62,753,212,62),background:green,color:paper,border:'6px solid #fff',boxShadow:`5px 6px 0 ${green}`,borderRadius:32,transform:`rotate(-5deg) scale(${lerp(.8,1,back(q(f,20,29)))})`,fontSize:27,fontWeight:900,textAlign:'center',padding:10,opacity:q(f,20,25)}}>收藏新发现</div></>;
}

export {StickerMaterial};
