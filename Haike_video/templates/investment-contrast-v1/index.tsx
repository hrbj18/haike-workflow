import React from 'react';
import {AbsoluteFill, Audio, Composition, OffthreadVideo, Sequence, staticFile, registerRoot, useCurrentFrame, useVideoConfig} from 'remotion';

type Props={style:11|12|13;avatar:string;shop:string;interaction:string;audio:string};
const font='"Microsoft YaHei",sans-serif';
const ease=(v:number)=>1-Math.pow(1-Math.min(1,Math.max(0,v)),3);
const Video=({src,fit='contain'}:{src:string;fit?:'contain'|'cover'})=><OffthreadVideo src={staticFile(src)} muted style={{width:'100%',height:'100%',objectFit:fit}}/>;
const Frame:React.FC<{x:number;y:number;w:number;h:number;children:React.ReactNode;extra?:React.CSSProperties}>=({x,y,w,h,children,extra={}})=><div style={{position:'absolute',left:x,top:y,width:w,height:h,overflow:'hidden',...extra}}>{children}</div>;
const Label=({children,color,x,y,size=32}:{children:React.ReactNode;color:string;x:number;y:number;size?:number})=><div style={{position:'absolute',left:x,top:y,fontSize:size,fontWeight:700,color}}>{children}</div>;

const Film:React.FC<Props>=(p)=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig(),intro=ease(f/12),switcher=ease((f-84)/10);
 const caption=f<5?'':f<77?'AI这么火，生意到底怎么落地？':f<87?'':f<143?'看这家海客AI社区服务店':'';
 const c=p.style===11?{bg:'#5426C8',ink:'#E6FF59',paper:'#F4F0FF'}:p.style===12?{bg:'#B9E9F2',ink:'#C73424',paper:'#FBECE3'}:{bg:'#164B34',ink:'#FF8B35',paper:'#F9EACB'};
 return <AbsoluteFill style={{background:c.bg,fontFamily:font,overflow:'hidden'}}>
 {p.style===11&&<>
   <div style={{position:'absolute',right:-190,top:-270,width:700,height:700,borderRadius:'50%',background:c.ink}}/>
   <Label x={68} y={54} size={32} color={c.paper}>海客AI社区服务店</Label>
   <div style={{position:'absolute',left:68,top:160,color:c.ink,fontSize:142,fontWeight:900,lineHeight:1.05,letterSpacing:-6,translate:`${Math.round(-40*(1-intro))}px 0`}}>AI这么火<br/>生意怎么落地？</div>
   {f<87?<Frame x={170} y={520} w={1100} h={1010} extra={{borderRadius:'50%',background:c.paper,outline:`15px solid ${c.ink}`,scale:.96+.04*intro}}><Video src={p.avatar} fit="cover"/></Frame>:<>
     <Frame x={105} y={526} w={650} h={1010} extra={{borderRadius:330,background:c.paper,outline:`12px solid ${c.ink}`,translate:`${Math.round(-30*(1-switcher))}px 0`}}><Sequence from={87} durationInFrames={63} premountFor={fps}><Video src={p.shop}/></Sequence></Frame>
     <Frame x={855} y={955} w={490} h={490} extra={{borderRadius:'50%',background:c.paper,outline:`10px solid ${c.ink}`}}><Sequence from={87} durationInFrames={63} premountFor={fps}><Video src={p.interaction} fit="cover"/></Sequence></Frame>
     <Label x={850} y={610} size={100} color={c.ink}>到店</Label><Label x={850} y={735} size={100} color={c.ink}>体验</Label>
   </>}
   <div style={{position:'absolute',left:65,top:1600,width:1310,height:130,borderRadius:70,background:c.ink,display:'flex',alignItems:'center',justifyContent:'center',color:c.bg,fontSize:60,fontWeight:900}}>{caption}</div>
 </>}
 {p.style===12&&<>
   <div style={{position:'absolute',left:0,top:0,width:1440,height:100,background:c.ink}}/>
   <Label x={58} y={27} size={32} color={c.paper}>海客AI社区服务店</Label>
   <div style={{position:'absolute',left:56,top:150,color:c.ink,fontSize:121,fontWeight:900,lineHeight:1.03,letterSpacing:-4}}>让AI走进<br/>真实的门店</div>
   <Frame x={58} y={440} w={850} h={760} extra={{background:c.ink}}>
     <Sequence from={0} durationInFrames={75} premountFor={fps}><Video src={p.shop}/></Sequence>
     <Sequence from={75} durationInFrames={75} premountFor={fps}><Video src={p.interaction}/></Sequence>
   </Frame>
   <Frame x={945} y={440} w={437} h={760} extra={{background:c.paper}}><Video src={p.avatar}/></Frame>
   <div style={{position:'absolute',left:58,top:1230,width:1324,height:246,background:c.ink,color:c.bg,padding:'34px 46px',boxSizing:'border-box',display:'flex',alignItems:'center',justifyContent:'space-between',translate:`${Math.round(50*(1-intro))}px 0`}}><span style={{fontSize:100,fontWeight:900}}>看得到</span><span style={{fontSize:85,fontWeight:400}}>能体验</span></div>
   <div style={{position:'absolute',left:58,top:1515,width:1324,height:3,background:c.ink}}/>
   <div style={{position:'absolute',left:58,top:1565,width:1324,color:c.ink,fontSize:62,fontWeight:900,lineHeight:1.35}}>{caption}</div>
   <Label x={58} y={1710} size={26} color={c.ink}>门店实景 · 产品体验</Label>
 </>}
 {p.style===13&&<>
   <svg width="1440" height="1800" style={{position:'absolute'}}><path d={`M0 ${720-40*intro} L1440 ${540-40*intro} V1800 H0Z`} fill={c.ink}/></svg>
   <Frame x={62} y={65} w={440} h={550} extra={{background:c.paper,rotate:'-3deg',outline:`10px solid ${c.paper}`}}><Video src={p.avatar}/></Frame>
   <Label x={560} y={78} color={c.paper} size={31}>海客AI社区服务店</Label>
   <div style={{position:'absolute',left:558,top:173,color:c.ink,fontSize:144,fontWeight:900,lineHeight:1.1,letterSpacing:-6}}>把AI<br/>带到身边</div>
   <Frame x={58} y={734} w={630} h={730} extra={{background:c.bg,rotate:'-3deg',outline:`10px solid ${c.paper}`}}>
     <Sequence from={0} durationInFrames={75} premountFor={fps}><Video src={p.shop}/></Sequence>
     {f>=75&&<div style={{padding:60,color:c.ink,fontSize:130,fontWeight:900,lineHeight:1.3}}>走近<br/>体验</div>}
   </Frame>
   <Frame x={758} y={650} w={620} h={840} extra={{background:c.bg,rotate:'3deg',outline:`10px solid ${c.paper}`}}>
     {f<75&&<div style={{padding:60,color:c.paper,fontSize:110,fontWeight:900,lineHeight:1.4}}>有门头<br/>有产品</div>}
     <Sequence from={75} durationInFrames={75} premountFor={fps}><Video src={p.interaction}/></Sequence>
   </Frame>
   <div style={{position:'absolute',left:54,top:1560,width:1332,height:150,background:c.bg,color:c.paper,display:'flex',alignItems:'center',justifyContent:'center',fontSize:60,fontWeight:900,rotate:'-1deg'}}>{caption}</div>
 </>}
 {p.audio&&<Audio src={staticFile(p.audio)} volume={1}/>}
 </AbsoluteFill>;
};
const Root=()=> <Composition id="HaikeContrastFive" component={Film} width={1440} height={1800} fps={30} durationInFrames={150} defaultProps={{style:11,avatar:'avatar.mp4',shop:'shop.mp4',interaction:'interaction.mp4',audio:'master.wav'}}/>;
registerRoot(Root);
