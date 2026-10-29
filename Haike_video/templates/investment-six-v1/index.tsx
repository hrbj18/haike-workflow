import React from 'react';
import {AbsoluteFill,Audio,Composition,OffthreadVideo,Sequence,registerRoot,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';

type Shot={id:string;lane:string;src:string;from:number;frames:number;offset:number};
type Caption={text:string;startMs:number;endMs:number};
type Chapter={from:number;title:string;sub:string;points:string[]};
type Props={style:number;durationFrames:number;audio:string;shots:Shot[];captions:Caption[];chapters:Chapter[];avatar?:{src:string;from:number;frames:number};brand:string;closingFrom:number};
const colors:Record<number,string[]>={7:['#0C3967','#EAD0B0','#143F6B'],8:['#202425','#28CCC9','#284346'],9:['#0E0E0E','#FD7B99','#34232A'],11:['#5426C8','#E6FF59','#6944C9'],12:['#B9E9F2','#C73424','#FBECE3'],13:['#164B34','#FF8B35','#F9EACB']};
const Box:React.FC<{x:number;y:number;w:number;h:number;children?:React.ReactNode;css?:React.CSSProperties}>=({x,y,w,h,children,css})=><div style={{position:'absolute',left:x,top:y,width:w,height:h,overflow:'hidden',boxSizing:'border-box',...css}}>{children}</div>;
const Text=({value,x,y,w,size,color,css={}}:{value:string;x:number;y:number;w:number;size:number;color:string;css?:React.CSSProperties})=><div style={{position:'absolute',left:x,top:y,width:w,color,fontSize:size,fontWeight:900,lineHeight:1.15,whiteSpace:'pre-line',...css}}>{value}</div>;
export const InvestmentSix:React.FC<Props>=(p)=>{
 const f=useCurrentFrame(),{fps}=useVideoConfig(),[bg,ink,mount]=colors[p.style],ch=[...p.chapters].reverse().find(c=>c.from<=f)||p.chapters[0];
 const opening=!!p.avatar&&f>=p.avatar.from&&f<p.avatar.from+p.avatar.frames,closing=f>=p.closingFrom;
 const cue=p.captions.find(c=>f/fps*1000>=c.startMs&&f/fps*1000<c.endMs);
 const appear=1-Math.pow(1-Math.max(0,Math.min(1,(f-ch.from)/12)),3);
 const footage=(lane:string)=><>{lane==='left'&&opening?<Sequence from={p.avatar!.from} durationInFrames={p.avatar!.frames} premountFor={fps}><OffthreadVideo src={staticFile(p.avatar!.src)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>:p.shots.filter(s=>s.lane===lane).map(s=><Sequence key={s.id} from={s.from} durationInFrames={s.frames} premountFor={fps}><OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.offset*fps)} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>)}</>;
 const media=(lane:string,x:number,y:number,w:number,h:number,css:React.CSSProperties={})=><Box x={x} y={y} w={w} h={h} css={{background:mount,...css}}>{footage(lane)}</Box>;
 const title=(x:number,y:number,w:number,size:number)=> <Text value={ch.title} x={x} y={y} w={w} size={size} color={ink} css={{transform:`translateX(${-22*(1-appear)}px)`}}/>;
 const points=(x:number,y:number,w:number,size=54)=> <Box x={x} y={y} w={w} h={700}>{ch.points.map((t,i)=><div key={i} style={{marginBottom:35,paddingTop:22,borderTop:`2px solid ${ink}`,fontSize:size,fontWeight:700,lineHeight:1.35,color:ink}}>{t}</div>)}</Box>;
 return <AbsoluteFill style={{background:bg,color:ink,fontFamily:'"Microsoft YaHei",sans-serif',overflow:'hidden'}}>
  {p.style===7&&<>
   <Box x={24} y={0} w={10} h={1800} css={{background:ink}}/><Box x={1406} y={0} w={10} h={1800} css={{background:ink}}/>
   {title(100,180,1240,114)}<Box x={100} y={464} w={1240} h={3} css={{background:ink}}/>
   {!closing&&media('left',100,505,1240,930,{border:`2px solid ${ink}`})}
   <Text value={ch.sub} x={104} y={1455} w={1230} size={36} color={ink}/>
  </>}
  {p.style===8&&<>
   <svg width={1440} height={1800} style={{position:'absolute'}}><path d="M0 380L80 300V1460L0 1540Z M1345 190L1440 90V480L1345 570Z M1170 1800L1440 1610V1800Z" fill={ink}/></svg>
   {title(110,180,1200,110)}
   {!closing&&<>{points(112,610,390,54)}{media('left',560,465,770,1015)}</>}
  </>}
  {p.style===9&&<>
   <Box x={0} y={0} w={28} h={1800} css={{background:ink}}/><Box x={105} y={152} w={1230} h={3} css={{background:ink}}/>
   {title(105,200,1230,143)}
   {!closing&&media('left',105,565,1230,890,{border:`4px solid ${ink}`})}
   <Box x={105} y={1480} w={240} h={8} css={{background:ink}}/>
  </>}
  {p.style===11&&<>
   <Box x={1120} y={-210} w={600} h={600} css={{background:ink,borderRadius:'50%'}}/>
   {title(75,190,1270,125)}
   {!closing&&(opening?media('left',190,510,1060,1000,{borderRadius:530,border:`12px solid ${ink}`}):<>
    {media('left',90,510,800,1010,{borderRadius:400,border:`10px solid ${ink}`})}
    {media('right',960,1000,410,410,{borderRadius:205,border:`8px solid ${ink}`})}
    <Text value={ch.sub} x={975} y={590} w={360} size={69} color={ink}/>
   </>)}
  </>}
  {p.style===12&&<>
   <Box x={0} y={0} w={1440} h={125} css={{background:ink}}/>{title(60,190,1320,114)}
   {!closing&&<>{media('left',58,480,840,790)}{media('right',935,480,447,790)}</>}
   {!closing&&<Box x={58} y={1300} w={1324} h={200} css={{background:ink}}><Text value={ch.sub} x={40} y={45} w={1240} size={77} color={bg}/></Box>}
  </>}
  {p.style===13&&<>
   <svg width={1440} height={1800} style={{position:'absolute'}}><path d="M0 730L1440 545V1800H0Z" fill={ink}/></svg>
   {title(62,180,1315,120)}
   {!closing&&<>{media('left',64,650,640,840,{transform:'rotate(-2deg)',border:`10px solid ${mount}`})}{media('right',760,590,610,850,{transform:'rotate(2deg)',border:`10px solid ${mount}`})}</>}
  </>}
  <Text value={p.brand} x={p.style===12?58:100} y={55} w={1240} size={36} color={p.style===12?mount:ink}/>
  {closing&&<Box x={110} y={565} w={1220} h={870} css={{background:bg,border:`3px solid ${ink}`,padding:60}}>
    <div style={{fontSize:56,fontWeight:700,marginBottom:70,color:ink}}>把合作方式聊具体</div>
    {['实地了解门店','逐项确认支持','点击下方咨询'].map((t,i)=><div key={t} style={{color:ink,fontSize:i===2?100:78,fontWeight:900,padding:'34px 0',borderBottom:`2px solid ${ink}`}}>{t}</div>)}
  </Box>}
  <Box x={65} y={1560} w={1310} h={164} css={{background:p.style===13?bg:ink,borderRadius:p.style===11?80:0,display:'flex',alignItems:'center',justifyContent:'center',padding:'15px 26px'}}>
   <div style={{fontSize:62,lineHeight:1.25,fontWeight:800,color:p.style===13?mount:bg,whiteSpace:'nowrap'}}>{cue?.text||''}</div>
  </Box>
  <Text value="门店合作咨询 · 海客" x={100} y={1745} w={1240} size={26} color={p.style===13?bg:ink}/>
  <Audio src={staticFile(p.audio)}/>
 </AbsoluteFill>;
};
const Root=()=> <Composition id="HaikeInvestmentSix" component={InvestmentSix} width={1440} height={1800} fps={30} durationInFrames={900}
 defaultProps={{style:7,durationFrames:900,audio:'master.wav',shots:[],captions:[],chapters:[{from:0,title:'先看门店\n再聊合作',sub:'了解具体经营',points:['看产品','看体验','聊合作']}],brand:'海客AI社区服务店',closingFrom:780}}
 calculateMetadata={({props})=>({durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
