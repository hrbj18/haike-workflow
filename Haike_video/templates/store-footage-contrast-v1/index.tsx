import React from 'react';
import {AbsoluteFill,Audio,Composition,OffthreadVideo,Sequence,staticFile,registerRoot,useCurrentFrame} from 'remotion';
type Shot={id:string;lane:string;src:string;from:number;frames:number;offset:number;fit:'contain'|'cover'};
type Chapter={from:number;title:string;side:string;sub:string;secondary?:string};
type Props={style:number;durationFrames:number;audio:string;shots:Shot[];captions:{text:string;startMs:number;endMs:number}[];chapters?:Chapter[];avatar?:{src:string;from:number;frames:number}};
const ease=(x:number)=>1-Math.pow(1-Math.max(0,Math.min(1,x)),3);
const Box=({x,y,w,h,children,style={}}:{x:number;y:number;w:number;h:number;children?:React.ReactNode;style?:React.CSSProperties})=><div style={{position:'absolute',left:x,top:y,width:w,height:h,overflow:'hidden',...style}}>{children}</div>;
const Footage=({shots,lane}:{shots:Shot[];lane:string})=><>{shots.filter(s=>s.lane===lane).map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={15}><OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.offset*30)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>)}</>;
const Film:React.FC<Props>=(p)=>{
 const f=useCurrentFrame(),intro=ease(f/12);
 const palettes:{[id:number]:string[]}={18:['#4928B8','#FF782E','#FFE4CB','#FFFFFF'],19:['#BF234B','#C6F4FA','#163852','#FFFFFF'],20:['#203C69','#D7F451','#5B9FE6','#F8FCFF'],21:['#006D71','#FF9DC3','#FFE5F0','#FFFFFF']};
 const [ink,accent,paper,white]=palettes[p.style];
 const speaking=p.avatar&&f>=p.avatar.from&&f<p.avatar.from+p.avatar.frames;
 const shot=(lane:string)=>lane==='left'&&speaking?<Sequence from={p.avatar!.from} durationInFrames={p.avatar!.frames}><OffthreadVideo src={staticFile(p.avatar!.src)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>:<Footage shots={p.shots} lane={lane}/>;
 const chapter=p.chapters?.filter(c=>c.from<=f).slice(-1)[0];
 const text=(value:string,x:number,y:number,size:number,color:string,extra:React.CSSProperties={})=><div style={{position:'absolute',left:x,top:y,fontSize:size,fontWeight:900,lineHeight:1.08,color,whiteSpace:'pre-line',...extra}}>{value}</div>;
 const cue=[...p.captions].reverse().find(c=>f/30*1000>=c.startMs&&f/30*1000<c.endMs+65),pop=cue?ease((f-cue.startMs*.03)/6):1;
 return <AbsoluteFill style={{background:accent,fontFamily:'"Microsoft YaHei",sans-serif'}}>
  {p.style===18&&<>
   {text(chapter?.title||'别只在屏幕里看',60,55,145,ink,{fontFamily:'SimHei',letterSpacing:-4,transform:`translateX(${-45*(1-intro)}px)`})}
   <Box x={0} y={260} w={1440} h={1270} style={{background:ink}}/>
   <Box x={380} y={295} w={1005} h={1200} style={{background:paper}}>{shot('left')}</Box>
   {text(chapter?.side||'来\n现\n场',68,345,205,accent,{fontFamily:'SimHei',lineHeight:1.22})}
   {text(chapter?.sub||'看得见\n摸得着',75,1190,63,white,{lineHeight:1.45})}
  </>}
  {p.style===19&&<>
   {text(chapter?.title||'一边是科技',58,48,115,ink,{fontFamily:'SimHei'})}
   {text(chapter?.side||'一边是好奇的你',300,193,112,paper,{fontFamily:'SimHei'})}
   <Box x={38} y={390} w={674} h={1090} style={{background:ink,transform:`translateY(${30*(1-intro)}px)`}}>{shot('left')}</Box>
   <Box x={728} y={390} w={674} h={1090} style={{background:paper,transform:`translateY(${-30*(1-intro)}px)`}}>{shot('right')}</Box>
   <Box x={38} y={390} w={260} h={78} style={{background:ink}}>{text('现场看见',25,14,42,white)}</Box>
   <Box x={1142} y={1402} w={260} h={78} style={{background:paper}}>{text('亲自体验',25,14,42,white)}</Box>
  </>}
  {p.style===20&&<>
   <Box x={0} y={0} w={1440} h={1800} style={{background:ink}}/>
   {text('海客AI社区服务站',52,35,44,accent)}
   <Box x={0} y={120} w={1440} h={1070} style={{background:paper}}/>
   <Box x={330} y={120} w={780} h={1070} style={{background:ink}}>{shot('left')}</Box>
   {text(speaking?'店长说':chapter?.side||'从线上',58,190,66,ink,{writingMode:'vertical-rl',letterSpacing:20})}
   {text(speaking?'面对面':chapter?.secondary||'到身边',1285,660,66,ink,{writingMode:'vertical-rl',letterSpacing:20})}
   <Box x={0} y={1190} w={1440} h={330} style={{background:accent,transform:`translateX(${50*(1-intro)}px)`}}/>
   {text(chapter?.title||'真见面，才新鲜',50,1230,160,ink,{fontFamily:'SimHei',letterSpacing:-6})}
   {text(chapter?.sub||'把屏幕里的科技，带进生活',62,1430,46,ink)}
  </>}
  {p.style===21&&<>
   <Box x={450} y={0} w={990} h={1280} style={{background:ink}}>{shot('left')}</Box>
   {text(chapter?.title||'把\n好奇心\n带过来',45,75,110,ink,{fontFamily:'SimHei',lineHeight:1.3})}
   <Box x={38} y={660} w={600} h={835} style={{background:paper,border:`12px solid ${accent}`,transform:`translateY(${40*(1-intro)}px)`}}>{shot('right')}</Box>
   <Box x={675} y={1280} w={765} h={240} style={{background:ink}}/>
   {text(chapter?.sub||'家门口的\n科技体验',720,1310,81,accent,{lineHeight:1.15})}
  </>}
  {cue&&<Box x={55} y={1560} w={1330} h={140} style={{background:p.style===20?accent:ink,color:p.style===20?ink:white,display:'flex',alignItems:'center',justifyContent:'center',fontSize:58,fontWeight:900,whiteSpace:'nowrap',transform:`translateY(${6*(1-pop)}px)`}}>{cue.text}</Box>}
  <div style={{position:'absolute',bottom:44,width:'100%',textAlign:'center',fontSize:30,fontWeight:700,color:p.style===20?white:ink}}>广州增城翡翠绿洲 · 海客AI社区服务站</div>
  {p.audio&&<Audio src={staticFile(p.audio)}/>}
 </AbsoluteFill>;
};
const defaults:Props={style:18,durationFrames:180,audio:'',shots:[],captions:[]};
registerRoot(()=> <Composition id="HaikeStoreManager" component={Film} width={1440} height={1800} fps={30} durationInFrames={180} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:props.durationFrames})}/>);
