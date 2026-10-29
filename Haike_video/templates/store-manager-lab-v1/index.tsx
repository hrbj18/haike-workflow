import React from 'react';
import {AbsoluteFill,Audio,Composition,OffthreadVideo,Sequence,staticFile,registerRoot,useCurrentFrame} from 'remotion';
type Shot={id:string;lane:string;src:string;from:number;frames:number;offset:number;fit:'contain'|'cover'};
type Props={style:number;durationFrames:number;avatar:string;audio:string;shots:Shot[];captions:{text:string;startMs:number;endMs:number}[]};
const ease=(x:number)=>1-Math.pow(1-Math.max(0,Math.min(1,x)),3);
const Box=({x,y,w,h,children,style={}}:{x:number;y:number;w:number;h:number;children?:React.ReactNode;style?:React.CSSProperties})=><div style={{position:'absolute',left:x,top:y,width:w,height:h,overflow:'hidden',...style}}>{children}</div>;
const Footage=({shots,lane}:{shots:Shot[];lane:string})=><>{shots.filter(s=>s.lane===lane).map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={15}><OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.offset*30)} muted style={{width:'100%',height:'100%',objectFit:s.fit}}/></Sequence>)}</>;
const Film:React.FC<Props>=(p)=>{
 const f=useCurrentFrame(),intro=ease(f/14),changed=f>=90;
 const palettes:{[id:number]:string[]}={14:['#172C57','#F45B69','#FFE3E5','#FFF9F5'],15:['#4B2D28','#70CFFF','#FFD277','#F8FCFF'],16:['#791E42','#BCF0D6','#EDADC6','#FFFAFD'],17:['#243ECB','#FFCB3D','#DDE9FF','#FFFFFF']};
 const [ink,accent,paper,white]=palettes[p.style];
 const avatar=<OffthreadVideo src={staticFile(p.avatar)} muted style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 40%'}}/>;
 const shot=(lane:string)=><Footage shots={p.shots} lane={lane}/>;
 const label=(text:string,x:number,y:number,size:number,color:string,extra:React.CSSProperties={})=><div style={{position:'absolute',left:x,top:y,fontSize:size,fontWeight:900,lineHeight:1.12,color,whiteSpace:'pre-line',...extra}}>{text}</div>;
 const cue=[...p.captions].reverse().find(c=>f/30*1000>=c.startMs&&f/30*1000<c.endMs+65);
 const pop=cue?ease((f-cue.startMs*.03)/6):1;
 return <AbsoluteFill style={{background:p.style===15?accent:p.style===16?paper:ink,fontFamily:'"Microsoft YaHei",sans-serif',overflow:'hidden'}}>
  {p.style===14&&<>
   <Box x={0} y={0} w={1440} h={365} style={{background:accent,clipPath:'polygon(0 0,100% 0,100% 74%,66% 74%,66% 100%,0 100%)'}}/>
   {label('屏幕之外',58,72,155,ink,{transform:`translateX(${-70*(1-intro)}px)`})}
   {label('见面才有感觉',65,260,73,white)}
   <Box x={50} y={410} w={840} h={1080} style={{background:paper}}>{shot('left')}</Box>
   <Box x={935} y={340} w={450} h={565} style={{background:white,borderBottom:`16px solid ${accent}`}}>{avatar}</Box>
   {label('把科技\n带到\n你身边',945,980,94,paper)}
   <Box x={935} y={1370} w={450} h={120} style={{background:accent,display:'flex',alignItems:'center',justifyContent:'center',color:ink,fontSize:44,fontWeight:900}}>到店 亲自体验</Box>
  </>}
  {p.style===15&&<>
   <Box x={0} y={0} w={1440} h={735} style={{background:accent}}/>
   <Box x={42} y={48} w={560} h={640} style={{borderRadius:'0 0 140px 0',background:white}}>{avatar}</Box>
   {label('刷到过，',650,110,117,ink,{fontFamily:'SimHei',transform:`translateY(${45*(1-intro)}px)`})}
   {label('见过吗？',650,280,142,ink,{fontFamily:'SimHei'})}
   {label('机器人就在家门口',660,555,43,ink)}
   <Box x={0} y={735} w={1440} h={785} style={{background:ink}}/>
   <Box x={35} y={770} w={670} h={710} style={{background:ink,clipPath:`inset(0 ${100*(1-intro)}% 0 0)`}}>{shot('left')}</Box>
   <Box x={735} y={770} w={670} h={710} style={{background:ink}}>{shot('right')}</Box>
   <Box x={0} y={1520} w={1440} h={280} style={{background:paper}}/>
  </>}
  {p.style===16&&<>
   <Box x={0} y={0} w={1440} h={390} style={{background:ink}}/>
   {label('科技的距离',60,60,150,accent,{fontFamily:'SimSun',letterSpacing:5})}
   {label('可以很近',69,238,87,white,{fontFamily:'SimSun'})}
   <Box x={0} y={390} w={850} h={1120} style={{background:white}}>{avatar}</Box>
   <Box x={850} y={390} w={590} h={1120} style={{background:accent}}/>
   <Box x={881} y={430} w={528} h={960} style={{background:ink,transform:`translateY(${60*(1-intro)}px)`}}>{shot('right')}</Box>
   {label('来店里，面对面',889,1420,43,ink)}
   <Box x={62} y={1305} w={650} h={125} style={{background:ink,display:'flex',alignItems:'center',justifyContent:'center',color:accent,fontSize:52,fontWeight:700}}>海客AI社区服务站</Box>
  </>}
  {p.style===17&&<>
   <Box x={0} y={0} w={1440} h={1800} style={{background:ink}}/>
   {label('现场',54,130,155,accent,{writingMode:'vertical-rl',letterSpacing:35,fontFamily:'SimHei'})}
   {label('见',1190,145,160,accent,{fontFamily:'SimHei'})}
   <Box x={295} y={80} w={815} h={1390} style={{background:white,clipPath:`inset(${8*(1-intro)}% 0 0 0)`}}>{changed?shot('left'):avatar}</Box>
   {!changed&&label('不只在屏幕里',345,1280,82,white,{background:ink,padding:'18px 22px'})}
   {changed&&<Box x={1118} y={1010} w={285} h={460} style={{background:white,borderTop:`12px solid ${accent}`}}>{avatar}</Box>}
   {changed&&label('就在\n身边',1145,540,90,paper)}
   <Box x={54} y={1100} w={170} h={370} style={{background:accent,display:'flex',justifyContent:'center',alignItems:'center',writingMode:'vertical-rl',color:ink,fontSize:48,fontWeight:900,letterSpacing:12}}>亲自体验</Box>
  </>}
  {cue&&<Box x={55} y={1558} w={1330} h={142} style={{background:p.style===16?ink:p.style===17?accent:p.style===14?paper:ink,color:p.style===16?accent:p.style===17?ink:p.style===14?ink:white,display:'flex',alignItems:'center',justifyContent:'center',fontSize:58,fontWeight:900,whiteSpace:'nowrap',transform:`translateY(${6*(1-pop)}px)`}}>{cue.text}</Box>}
  <div style={{position:'absolute',bottom:45,width:'100%',textAlign:'center',fontSize:30,fontWeight:700,color:p.style===15||p.style===16?ink:paper}}>广州增城翡翠绿洲 · 海客AI社区服务站</div>
  {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill>;
};
const defaults:Props={style:14,durationFrames:180,avatar:'avatar.mp4',audio:'',shots:[],captions:[]};
registerRoot(()=> <Composition id="HaikeStoreManager" component={Film} width={1440} height={1800} fps={30} durationInFrames={180} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:props.durationFrames})}/>);
