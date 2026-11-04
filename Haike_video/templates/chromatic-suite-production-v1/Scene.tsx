import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Composition,OffthreadVideo,Sequence,staticFile,useCurrentFrame as useRealFrame,delayRender,continueRender,cancelRender,registerRoot} from 'remotion';
import {Context,motionAt,Props} from './Runtime';
import {StickerMaterial} from './Derived-A';
import {Orbit,Gallery,TiltRecord,FoldCover,ParkJournal,ExposeVideo,Desk} from './Derived-B';
import {Impact,Filmstrip,Assemble,PosterRecap,RouteWorld,StepLine,Callout} from './Derived-C';

type Draw={p:Props;scene:any;motion:number};
export const ACTIONS:Record<string,React.FC<Draw>>={
 'haike.chromatic-07.fan-collect':({p,motion})=><StickerMaterial episode={p} f={motion} index={0}/>,
 'haike.chromatic-07.pop-evidence':({p,motion})=><StickerMaterial episode={p} f={motion-240} index={1}/>,
 'haike.chromatic-07.mark-attention':({p,motion})=><StickerMaterial episode={p} f={motion-420} index={2}/>,
 'haike.chromatic-07.stick-memory':({p,motion})=><StickerMaterial episode={p} f={motion-585} index={3}/>,
 'haike.chromatic-08.orbit-entry':({p,motion})=><Orbit episode={p} f={motion}/>,
 'haike.chromatic-08.gallery-tour':({p,motion})=><Gallery episode={p} f={motion-150}/>,
 'haike.chromatic-08.tilt-record':({p,motion})=><TiltRecord episode={p} f={motion-420}/>,
 'haike.chromatic-08.orbit-recap':({p,motion})=><Orbit episode={p} f={motion-570} final/>,
 'haike.chromatic-09.fold-open':({p,motion})=><FoldCover episode={p} f={motion}/>,
 'haike.chromatic-09.journal-park':({p,motion})=><ParkJournal episode={p} f={motion-210}/>,
 'haike.chromatic-09.exposure-evidence':({p,motion})=><ExposeVideo episode={p} f={motion-450}/>,
 'haike.chromatic-09.desk-recap':({p,motion})=><Desk episode={p} f={motion-600}/>,
 'haike.chromatic-six-10.impact':({p})=><Impact episode={p}/>,
 'haike.chromatic-six-10.relay':({p})=><Filmstrip episode={p}/>,
 'haike.chromatic-six-10.assemble':({p})=><Assemble episode={p}/>,
 'haike.chromatic-six-10.register':({p})=><PosterRecap episode={p}/>,
 'haike.chromatic-six-11.route-start':({p})=><><RouteWorld episode={p}/><div style={{...box(48,854,420,160),fontSize:35,fontWeight:700,lineHeight:1.35}}>起点：真实现场<br/><span style={{fontSize:23,color:'#C4D8E3',fontWeight:400}}>从第一眼，到第一步。</span></div></>,
 'haike.chromatic-six-11.route-travel':({p})=><><RouteWorld episode={p}/><Callout/></>,
 'haike.chromatic-six-11.step-stop':({p})=><><RouteWorld episode={p}/><StepLine/></>,
 'haike.chromatic-six-11.pull-overview':({p,motion})=><><RouteWorld episode={p} overview/><div style={{...box(480,352,172,150),fontSize:25,fontWeight:800,lineHeight:1.4,opacity:Math.max(0,Math.min(1,(motion-650)/10)),color:'#FFAD8F'}}>看见<br/>参与<br/>理解</div></>,
};
const box=(x:number,y:number,width:number,height:number):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height,boxSizing:'border-box'});
const palettes:Record<string,{bg:string;ink:string;accent:string;caption:string}>={
 'chromatic-07':{bg:'#FFF4DA',ink:'#245E37',accent:'#F4AFCB',caption:'#245E37'},
 'chromatic-08':{bg:'#4C23A8',ink:'#EAE0FF',accent:'#FFE033',caption:'#FFE033'},
 'chromatic-09':{bg:'#BDEAF3',ink:'#C9233A',accent:'#C9233A',caption:'#C9233A'},
 'chromatic-six-10':{bg:'#F5F4E8',ink:'#151512',accent:'#E3FF3B',caption:'#151512'},
 'chromatic-six-11':{bg:'#102C43',ink:'#F5F4E8',accent:'#FFAD8F',caption:'#173B53'},
};
function Presenter({p,f}:{p:Props;f:number}) {
 const clip=p.presenters.find(c=>f>=c.from&&f<c.to);if(!clip)return null;
 const number=Number(p.templateId.split('-').at(-1)),c=palettes[p.templateId],sticker=number===7;
 const b=number===7?[482,864,182,220]:number<10?[492,851,180,225]:[514,842,158,230];
 return <div data-role="presenter" style={{...box(b[0],b[1],b[2],b[3]),overflow:'hidden',border:`${sticker?7:number===11?2:3}px solid ${sticker?'white':c.accent}`,
  borderRadius:sticker?24:number===8?'92px 92px 3px 3px':2,boxShadow:sticker?'7px 8px 0 #245E37':undefined,background:c.bg,zIndex:30}}>
  <Sequence from={clip.from} durationInFrames={clip.to-clip.from} layout="none"><OffthreadVideo src={staticFile(clip.src)}
   startFrom={clip.sourceFrom} endAt={clip.sourceFrom+clip.to-clip.from} muted volume={0} playbackRate={1}
   style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/></Sequence>
  <div style={{position:'absolute',bottom:0,left:0,right:0,padding:6,fontSize:15,textAlign:'center',fontWeight:800,background:sticker?c.ink:c.accent,color:sticker?c.bg:c.bg}}>侯总 · AI数字人</div>
 </div>;
}
function Header({p,s,index}:{p:Props;s:any;index:number}) {
 const n=Number(p.templateId.split('-').at(-1)),c=palettes[p.templateId];
 if(n===10)return <div style={{...box(48,44,624,47),borderTop:`3px solid ${c.ink}`,borderBottom:`1px solid ${c.ink}`,display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:18,fontWeight:800}}><span>FIELD / 现场笔记</span><span style={{background:c.accent,padding:'4px 10px'}}>10 · BEAT</span></div>;
 if(n===7)return <><div style={{...box(0,0,720,286),background:c.accent,borderRadius:'0 0 90px 0'}}/><div style={{...box(46,40,628,25),display:'flex',justifyContent:'space-between',fontSize:17,fontWeight:900}}><span>好奇心 / 今日收集</span><span>07 — STICKER</span></div><div style={{...box(46,112,628,160),fontSize:61,fontWeight:900,lineHeight:1.08,whiteSpace:'pre-line'}}>{s.title}</div></>;
 if(n===8)return <><div style={{...box(48,38,624,30),display:'flex',justifyContent:'space-between',fontSize:18,fontWeight:700}}><span>海客现场 / ORBIT EXHIBITION</span><span>08</span></div><div style={{...box(48,88,624,4),background:c.accent}}/><div style={{...box(48,120,624,152),fontSize:61,fontWeight:900,lineHeight:1.06,whiteSpace:'pre-line',color:c.accent}}>{s.title}</div></>;
 if(n===9)return <><div style={{...box(22,0,10,1280),background:c.ink}}/><div style={{...box(48,39,624,38),borderBottom:`2px solid ${c.ink}`,display:'flex',justifyContent:'space-between',fontSize:18,fontWeight:800}}><span>海客 / 现场札记</span><span>FOLIO 09 · 0{index+1}</span></div><div style={{...box(64,120,600,150),fontSize:60,fontWeight:900,lineHeight:1.07,whiteSpace:'pre-line'}}>{s.title}</div></>;
 return <><div style={{...box(28,28,664,1224),border:'1px solid #7BA4BB55',pointerEvents:'none'}}/><div style={{...box(48,48,624,44),borderTop:'1px solid #52D3CC',borderBottom:'1px solid #7BA4BB55',display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:17,letterSpacing:2}}><span>FIELD ROUTE / 体验路线</span><span style={{color:c.accent}}>11—03</span></div><div style={{...box(48,142,624,140),fontSize:55,fontWeight:800,lineHeight:1.1,whiteSpace:'pre-line'}}>{s.title}</div></>;
}
export function SuiteDrawing(p:Props) {
 const f=useRealFrame(),s=p.scenes.find(s=>f>=s.from&&f<s.to);if(!s)throw Error('Missing semantic scene');
 const n=Number(p.templateId.split('-').at(-1)),index=p.scenes.indexOf(s),motion=motionAt(s.knots,f),Action=ACTIONS[s.actionId];
 if(!Action||p.version!=='1.2.0-candidate.1'||!s.actionId.startsWith('haike.'+p.templateId+'.'))throw Error('Unbound action identity');
 const c=palettes[p.templateId],caption=p.captions.find(v=>f>=v.from&&f<v.to),medical=f>=p.medicalFrom&&f<p.medicalTo;
 return <AbsoluteFill style={{background:c.bg,overflow:'hidden'}}><div data-template={p.templateId} data-action={s.actionId}
   style={{...box(0,0,720,1280),transform:'scale(1.5)',transformOrigin:'0 0',background:c.bg,color:c.ink,fontFamily:'HaikeSuiteHD',overflow:'hidden'}}>
  <Header p={p} s={s} index={index}/>
  <Context.Provider value={{p,s,globalFrame:f,motionFrame:motion}}><Action p={p} scene={s} motion={motion}/></Context.Provider>
  {(n===8||n===9)&&<div style={{...box(n===8?48:64,900,index===0||index===3?395:600,150),fontSize:32,fontWeight:800,lineHeight:1.3,whiteSpace:'pre-line'}}>{s.note}</div>}
  {n===11&&<div style={{...box(48,index===3?1085:1053,440,20),fontSize:index===3?13:16,color:'#52D3CC'}}>路线为体验顺序示意 · 非地理测绘</div>}
  {medical&&<><style>{n===10?'[data-native-note="assemble"]{visibility:hidden}':''}</style><div data-role="medical-disclaimer" style={{...box(48,n===11?690:1006,624,90),padding:'10px 12px',background:c.bg,color:c.ink,border:`1px solid ${c.accent}`,fontSize:21,fontWeight:800,lineHeight:1.5,whiteSpace:'pre-line',zIndex:25}}>{p.medicalOverlay}</div></>}
  <Presenter p={p} f={f}/>
  <div data-role="caption" style={{...box(n===7?44:48,1110,n===7?632:624,88),display:'flex',alignItems:'center',justifyContent:'center',padding:'12px 18px',fontSize:27,lineHeight:1.3,fontWeight:800,textAlign:'center',whiteSpace:'pre-line',background:c.caption,color:n===8?c.bg:n===9?'#F8E9D4':n===7?c.bg:c.bg==='#102C43'?c.ink:c.bg}}>{caption?.text||''}</div>
  <div style={{...box(48,1224,624,25),fontSize:16,display:'flex',justifyContent:'space-between'}}><span>{n===7?'好奇，是生活的贴纸。':n===8?'真实体验，是新的起点。':n===9?'把好奇，写进每一页。':'现场笔记 / 亲手体验'}</span><span>0{index+1} / 04</span></div>
  {(n===7||n>=10)&&<div style={{...box(n===7?0:48,n===7?1270:1252,(n===7?720:624)*(f+1)/p.durationInFrames,n===7?10:3),background:c.accent}}/>}
 </div></AbsoluteFill>;
}
export function ChromaticSuite(p:Props){const [hold]=useState(()=>delayRender('Bound suite font'));useEffect(()=>{new FontFace('HaikeSuiteHD',`url('${staticFile(p.font)}')`).load().then(face=>{document.fonts.add(face);continueRender(hold)}).catch(cancelRender);return()=>continueRender(hold)},[p.font,hold]);return <SuiteDrawing {...p}/>;}
function Root(){return <Composition id="ChromaticSuiteProduction" component={ChromaticSuite} width={1080} height={1920} fps={30} durationInFrames={1800} defaultProps={{} as any} calculateMetadata={({props})=>({durationInFrames:props.durationInFrames,width:1080,height:1920,fps:30})}/>;}
registerRoot(Root);
