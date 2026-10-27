import React from 'react';
import {Audio, Video} from '@remotion/media';
import type {Caption} from '@remotion/captions';
import {AbsoluteFill, Composition, Img, Sequence, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import layout from './layout.json';

type Highlight = {x:number;y:number;width:number;start?:number;duration?:number};
type Scene = {kind:'presenter'|'material'|'screenshot'|'data';start:number;end:number;src?:string;mediaKind?:'image'|'video';fit?:'cover'|'contain'|'blur';offset?:number;assetWidth?:number;assetHeight?:number;dataTitle?:string;dataLabel?:string;rows?:string[];highlights?:Highlight[];generated?:boolean};
type Props = {duration:number;avatarSrc?:string;audioSrc?:string|null;titleLines:string[];sourceLabel:string;brand:string;englishLabel:string;emphasis?:string[];scenes?:Scene[];captions:Caption[]};
const fill:React.CSSProperties={position:'absolute',inset:0,width:'100%',height:'100%'};
const media=(src:string)=>staticFile(src);
const textSize=(text:string,size:number,width:number)=>Math.min(size,width/Math.max(1,Array.from(text).length));

const Presenter:React.FC<{src:string;circle?:boolean}>=({src,circle=false})=>{
  const {fps}=useVideoConfig();
  return <Video muted premountFor={fps} src={media(src)} style={{...fill,objectFit:'cover',objectPosition:`50% ${circle?layout.circle.portraitY:layout.window.portraitY}%`}}/>;
};

const Visual:React.FC<{scene:Scene}>=({scene})=>{
  const {fps}=useVideoConfig();
  if(!scene.src)return null;
  const item=(blurred:boolean)=>scene.mediaKind==='video'?<Video muted src={media(scene.src!)} trimBefore={Math.round((scene.offset||0)*fps)} premountFor={fps} style={{...fill,objectFit:blurred?'cover':scene.fit==='cover'?'cover':'contain',filter:blurred?`blur(${layout.window.blurPixels}px) brightness(.65)`:'none',scale:blurred?'1.1':'1'}}/>:<Img src={media(scene.src!)} style={{...fill,objectFit:blurred?'cover':scene.fit==='cover'?'cover':'contain',filter:blurred?`blur(${layout.window.blurPixels}px) brightness(.65)`:'none',scale:blurred?'1.1':'1'}}/>;
  return <Sequence from={Math.round(scene.start*fps)} durationInFrames={Math.max(1,Math.round((scene.end-scene.start)*fps))} layout="none">{scene.fit==='blur'&&item(true)}{item(false)}{scene.generated&&<div style={{position:'absolute',right:20,top:20,padding:'6px 12px',fontSize:22,background:'#0009'}}>AI 示意插画</div>}</Sequence>;
};

const Screenshot:React.FC<{scene:Scene;seconds:number}>=({scene,seconds})=>{
  const w=layout.window.width,h=layout.window.height-layout.window.screenshotCaptionReserve;
  const scale=Math.min(w/(scene.assetWidth||w),h/(scene.assetHeight||h));
  const iw=(scene.assetWidth||w)*scale,ih=(scene.assetHeight||h)*scale;
  return <div style={{position:'absolute',left:(w-iw)/2,top:(h-ih)/2,width:iw,height:ih}}>
    {scene.src&&<Img src={media(scene.src)} style={fill}/>}
    {(scene.highlights||[]).map((line,i)=><div key={i} style={{position:'absolute',left:line.x*iw,top:line.y*ih,width:line.width*iw*interpolate(seconds-scene.start,[line.start||0,(line.start||0)+(line.duration||layout.highlight.defaultSeconds)],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}),height:layout.highlight.height,background:layout.highlight.color,borderRadius:layout.highlight.height/2}}/>)}
  </div>;
};

const DataBoard:React.FC<{scene:Scene;seconds:number}>=({scene,seconds})=><AbsoluteFill style={{background:'linear-gradient(145deg,#102951,#07172f)'}}>
  <div style={{position:'absolute',left:layout.data.left,top:layout.data.labelTop,fontSize:layout.data.labelSize,lineHeight:layout.data.lineHeight,fontWeight:800,color:layout.colors.yellow}}>{scene.dataLabel}</div>
  <div style={{position:'absolute',left:layout.data.left,top:layout.data.titleTop,fontSize:textSize(scene.dataTitle||'',layout.data.titleSize,layout.window.width-layout.data.left*2),fontWeight:800,lineHeight:layout.data.lineHeight,whiteSpace:'nowrap'}}>{scene.dataTitle}</div>
  {(scene.rows||[]).map((row,i)=><div key={i} style={{position:'absolute',left:0,right:0,top:layout.data.rowTop+i*layout.data.rowStep,opacity:interpolate(seconds-scene.start,[i*layout.data.rowRevealSeconds,i*layout.data.rowRevealSeconds+layout.data.rowFadeSeconds],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}),translate:`0px ${interpolate(seconds-scene.start,[i*layout.data.rowRevealSeconds,i*layout.data.rowRevealSeconds+layout.data.rowFadeSeconds],[layout.data.rowTravel,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}px`}}>
    <div style={{position:'absolute',left:layout.data.left,top:(layout.data.rowSize-layout.data.bulletSize)/2+5,width:layout.data.bulletSize,height:layout.data.bulletSize,background:layout.colors.yellow}}/>
    <div style={{position:'absolute',left:layout.data.textLeft,fontSize:textSize(row,layout.data.rowSize,layout.window.width-layout.data.textLeft-layout.data.left),fontWeight:700,whiteSpace:'nowrap',lineHeight:layout.data.lineHeight}}>{row}</div>
  </div>)}
</AbsoluteFill>;

const CaptionLine:React.FC<{cue:Caption;emphasis:string[]}>=({cue,emphasis})=>{
  const words=emphasis.filter(Boolean).sort((a,b)=>b.length-a.length);
  const parts:React.ReactNode[]=[];
  for(let pos=0;pos<cue.text.length;){const word=words.find(w=>cue.text.startsWith(w,pos));if(word){parts.push(<span key={pos} style={{color:layout.colors.yellow}}>{word}</span>);pos+=word.length;}else{parts.push(cue.text[pos]);pos++;}}
  return <div style={{position:'absolute',left:layout.caption.left,width:layout.caption.width,bottom:layout.caption.bottom,fontSize:layout.caption.size,fontWeight:800,lineHeight:layout.caption.lineHeight,textAlign:'center',color:'#fff',WebkitTextStroke:`${layout.caption.stroke}px #061022`,paintOrder:'stroke fill',textShadow:'0 3px 5px #0009',overflowWrap:'anywhere'}}>{parts}</div>;
};

export const DeepblueN1:React.FC<Props>=p=>{
  const {fps}=useVideoConfig();const frame=useCurrentFrame(),seconds=frame/fps;
  const scene=p.scenes?.find(s=>seconds>=s.start&&seconds<s.end)||{kind:'presenter',start:0,end:p.duration} as Scene;
  const avatar=p.avatarSrc||'avatar.mp4';
  const cue=p.captions.find(c=>frame/fps*1000>=c.startMs&&frame/fps*1000<c.endMs);
  return <AbsoluteFill style={{fontFamily:layout.fontFamily,color:layout.colors.white,background:`linear-gradient(180deg,${layout.colors.top} 0%,${layout.colors.middle} 48%,${layout.colors.bottom} 100%)`,overflow:'hidden'}}>
    {layout.curves.map((curve,i)=><div key={i} style={{position:'absolute',left:curve.left,top:curve.top,width:curve.width,height:curve.height,borderRadius:'50%',background:`linear-gradient(160deg,#99b5e7 0%,#7489bc00 75%)`,rotate:`${curve.rotation}deg`,opacity:curve.opacity}}/>)}
    {p.titleLines.map((line,i)=><div key={i} style={{position:'absolute',left:layout.title.left,width:layout.title.width,top:layout.title.tops[i],fontSize:textSize(line,layout.title.sizes[i],layout.title.width),lineHeight:layout.title.lineHeight,fontWeight:900,whiteSpace:'nowrap',textAlign:'center',color:i===0?layout.colors.yellow:'#fff',opacity:i===0?interpolate(frame,[0,layout.title.fadeSeconds*fps],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'}):1}}>{line}</div>)}
    <div style={{position:'absolute',left:layout.source.left,top:layout.source.top,fontSize:layout.source.size,lineHeight:layout.source.lineHeight,opacity:.8}}>{p.sourceLabel}</div>
    <div style={{position:'absolute',left:layout.window.left,top:layout.window.top,width:layout.window.width,height:layout.window.height,borderRadius:layout.window.radius,overflow:'hidden',background:'#071326'}}>
      {scene.kind==='presenter'?<><div style={{...fill,filter:`blur(${layout.window.blurPixels}px) brightness(.7)`,scale:'1.1'}}><Presenter src={avatar}/></div><div style={{position:'absolute',left:(layout.window.width-layout.window.clearWidth)/2,top:0,width:layout.window.clearWidth,height:'100%'}}><Presenter src={avatar}/></div></>:scene.kind==='material'?<Visual scene={scene}/>:scene.kind==='screenshot'?<Screenshot scene={scene} seconds={seconds}/>:<DataBoard scene={scene} seconds={seconds}/>}
      {cue&&<CaptionLine cue={cue} emphasis={p.emphasis||[]}/>}
    </div>
    {scene.kind!=='presenter'&&<div style={{position:'absolute',left:layout.circle.left,top:layout.circle.top,width:layout.circle.diameter,height:layout.circle.diameter,border:`${layout.circle.border}px solid white`,boxSizing:'border-box',borderRadius:'50%',overflow:'hidden'}}><Presenter src={avatar} circle/></div>}
    <div style={{position:'absolute',left:layout.brand.left,top:layout.brand.top,width:layout.brand.width,height:layout.brand.height,borderRadius:layout.brand.radius,border:`1px solid ${layout.brand.border}`,boxSizing:'border-box',background:'linear-gradient(100deg,#263d64,#102344)',display:'flex',alignItems:'center',justifyContent:'center',gap:layout.brand.gap}}>
      <div style={{width:layout.brand.markSize,height:layout.brand.markSize,borderRadius:layout.brand.markRadius,background:layout.colors.yellow,color:'#162342',fontSize:layout.brand.markFontSize,fontWeight:900,display:'flex',alignItems:'center',justifyContent:'center'}}>H</div><div style={{fontSize:Math.min(layout.brand.fontSize,(layout.brand.width-layout.brand.markSize-layout.brand.paddingAllowance)/Math.max(1,p.brand.length)),fontWeight:800,whiteSpace:'nowrap'}}>{p.brand}</div>
    </div>
    <div style={{position:'absolute',left:layout.english.left,top:layout.english.top,width:layout.english.width,fontSize:textSize(p.englishLabel,layout.english.size,layout.english.width),lineHeight:layout.english.lineHeight,fontWeight:900,textAlign:'center',opacity:layout.english.opacity,whiteSpace:'nowrap'}}>{p.englishLabel}</div>
    <div style={{position:'absolute',left:0,right:0,top:layout.bottomLine.top,height:layout.bottomLine.height,background:layout.colors.yellow}}/>
    {p.audioSrc!==null&&<Audio src={media(p.audioSrc||'narration.wav')} premountFor={fps}/>}
  </AbsoluteFill>;
};

const Root=()=> <Composition id="HaikeDeepblueN1" component={DeepblueN1} width={layout.canvas.width} height={layout.canvas.height} fps={layout.canvas.fps} durationInFrames={layout.canvas.fps*5} defaultProps={{duration:5,titleLines:['海客科技','',''],sourceLabel:'素材来源于网络',brand:'海客科技',englishLabel:'HAIKE',captions:[],scenes:[]}} calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round(props.duration*layout.canvas.fps))})}/>;
registerRoot(Root);
