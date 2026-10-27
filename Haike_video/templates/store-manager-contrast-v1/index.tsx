import React from 'react';
import {AbsoluteFill,Audio,Composition,OffthreadVideo,Sequence,staticFile,registerRoot,useCurrentFrame,useVideoConfig} from 'remotion';
type Shot={id:string;lane:string;src:string;from:number;frames:number;offset:number;fit:'contain'|'cover'};
type Cue={text:string;startMs:number;endMs:number;timestampMs:number|null;confidence:number|null};
type Props={style:11|13;durationFrames:number;avatar:string;audio:string;shots:Shot[];captions:Cue[];chapters:{start:number;title:string[];side?:string[]}[]};
const font='"Microsoft YaHei",sans-serif';
const ease=(v:number)=>1-Math.pow(1-Math.min(1,Math.max(0,v)),3);
const Frame:React.FC<{x:number;y:number;w:number;h:number;extra?:React.CSSProperties;children:React.ReactNode}>=({x,y,w,h,extra,children})=><div style={{position:'absolute',left:x,top:y,width:w,height:h,overflow:'hidden',...extra}}>{children}</div>;
const Footage:React.FC<{shots:Shot[];lane:string}>=({shots,lane})=>{const {fps}=useVideoConfig();return <>{shots.filter(s=>s.lane===lane).map(s=><Sequence key={s.id} name={s.id} from={s.from} durationInFrames={s.frames} premountFor={fps}><OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.offset*fps)} muted style={{width:'100%',height:'100%',objectFit:s.fit}}/></Sequence>)}</>};
const Film:React.FC<Props>=(p)=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig(),t=f/fps,intro=ease(f/12);
 const chapter=[...p.chapters].reverse().find(c=>t>=c.start)||p.chapters[0];
 const cue=[...p.captions].reverse().find(c=>t*1000>=c.startMs&&t*1000<c.endMs+65);
 const pop=cue?ease((f-cue.startMs/1000*fps)/5):1;
 const c=p.style===13?{bg:'#164B34',accent:'#FF8B35',paper:'#F9EACB'}:{bg:'#5426C8',accent:'#E6FF59',paper:'#F4F0FF'};
 const avatar=<OffthreadVideo src={staticFile(p.avatar)} muted style={{width:'100%',height:'100%',objectFit:p.style===11?'cover':'contain',objectPosition:'50% 42%'}}/>;
 const hero=p.style===11&&(t<3.6||t>=26.5);
 return <AbsoluteFill style={{background:c.bg,fontFamily:font,overflow:'hidden'}}>
  {p.style===13?<>
   <svg width="1440" height="1800" style={{position:'absolute'}}><path d={`M0 ${720-40*intro} L1440 ${540-40*intro} V1800 H0Z`} fill={c.accent}/></svg>
   <Frame x={62} y={65} w={440} h={550} extra={{background:c.paper,rotate:'-3deg',outline:`10px solid ${c.paper}`}}>{avatar}</Frame>
   <div style={{position:'absolute',left:558,top:74,color:c.paper,fontSize:36,fontWeight:700}}>海客AI社区服务站</div>
   <div style={{position:'absolute',left:558,top:176,color:c.accent,fontSize:chapter.title[0].length>4?116:136,fontWeight:900,lineHeight:1.16,letterSpacing:-4}}>{chapter.title.map((x,i)=><React.Fragment key={i}>{i>0&&<br/>}{x}</React.Fragment>)}</div>
   <Frame x={58} y={734} w={630} h={730} extra={{background:c.bg,rotate:'-3deg',outline:`10px solid ${c.paper}`}}><Footage shots={p.shots} lane="left"/></Frame>
   <Frame x={758} y={650} w={620} h={840} extra={{background:c.bg,rotate:'3deg',outline:`10px solid ${c.paper}`}}><Footage shots={p.shots} lane="right"/></Frame>
  </>:<>
   <div style={{position:'absolute',right:-190,top:-270,width:700,height:700,borderRadius:'50%',background:c.accent}}/>
   <div style={{position:'absolute',left:68,top:54,fontSize:34,fontWeight:700,color:c.paper}}>海客AI社区服务站</div>
   <div style={{position:'absolute',left:68,top:165,color:c.accent,fontSize:112,fontWeight:900,lineHeight:1.15,letterSpacing:-3,translate:`${-40*(1-intro)}px 0`}}>{chapter.title.map((x,i)=><React.Fragment key={i}>{i>0&&<br/>}{x}</React.Fragment>)}</div>
   <Frame x={hero?170:855} y={hero?520:950} w={hero?1100:490} h={hero?1010:490} extra={{borderRadius:'50%',background:c.paper,outline:`${hero?15:10}px solid ${c.accent}`}}>{avatar}</Frame>
   {!hero&&<>
    <Frame x={105} y={526} w={650} h={1010} extra={{borderRadius:325,background:c.paper,outline:`12px solid ${c.accent}`}}><Footage shots={p.shots} lane="main"/></Frame>
    <div style={{position:'absolute',left:850,top:615,color:c.accent,fontSize:100,fontWeight:900,lineHeight:1.25}}>{chapter.side?.map((x,i)=><React.Fragment key={i}>{i>0&&<br/>}{x}</React.Fragment>)}</div>
   </>}
  </>}
  {cue&&<div style={{position:'absolute',left:65,top:1570,width:1310,height:132,borderRadius:p.style===11?70:0,background:p.style===11?c.accent:c.bg,color:p.style===11?c.bg:c.paper,display:'flex',alignItems:'center',justifyContent:'center',fontSize:62,fontWeight:900,whiteSpace:'nowrap',transform:`translateY(${8*(1-pop)}px) scale(${.99+.01*pop})`}}>{cue.text}</div>}
  <div style={{position:'absolute',left:65,bottom:35,width:1310,textAlign:'center',fontSize:30,fontWeight:700,color:p.style===13?c.bg:c.paper}}>广州增城翡翠绿洲 · 海客AI社区服务站</div>
  {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill>;
};
const defaults:Props={style:13,durationFrames:975,avatar:'avatar.mp4',audio:'',shots:[],captions:[],chapters:[{start:0,title:['把AI','带到身边']}]};
const Root=()=> <Composition id="HaikeStoreManager" component={Film} width={1440} height={1800} fps={30} durationInFrames={975} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
