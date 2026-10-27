import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile} from 'remotion';
import {CaptionTrack, MaterialWindow, MotionTitle, PresenterWindow} from './shared';
import type {SceneProps} from './types';
import layout from './layout.json';
import {PointMotion} from './Motion';
const clamp = {extrapolateLeft:'clamp' as const,extrapolateRight:'clamp' as const};
const sans='"Microsoft YaHei",sans-serif';

export const RefinedDirections: React.FC<SceneProps> = ({p,chapter,chapterIndex,frame,fps}) => {
  const direction=p.art.direction,theme=layout.palette[direction];
  const green=direction==='community-showcase',blue=direction==='blue-editorial',dark=direction==='optical-cinema';
  const active=p.art.scenes.find(s=>frame/fps>=s.start && frame/fps<s.end);
  const offer=chapter.kind==='offer',cta=chapter.kind==='cta';
  const f=frame-Math.round(chapter.start*fps);
  const settle=interpolate(f,[0,12],[0,1],clamp);
  const close=p.art.portraitFraming==='close-4x5';
  const videoPosition=close?'50% 48%':'50% 54%';
  const displayFont=green&&!offer?'"KaiTi",sans-serif':dark&&!offer?'"SimSun",serif':sans;
  const top=offer?202:200;
  return <AbsoluteFill style={{background:theme.base,color:theme.ink,fontFamily:sans}}>
    {p.art.backgroundSrc&&<Img src={staticFile(p.art.backgroundSrc)} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',opacity:dark?.7:1}}/>}
    {dark&&<svg viewBox="0 0 1080 1920" style={{position:'absolute',inset:0,width:'100%',height:'100%'}}><defs><linearGradient id="copper-rim"><stop stopColor="#dcbe8999"/><stop offset="1" stopColor="#dcbe8900"/></linearGradient></defs><path d="M72 575C360 500 735 500 1008 575" stroke="url(#copper-rim)" strokeWidth="2" fill="none"/></svg>}
    <div style={{position:'absolute',left:80,right:80,top,zIndex:4}}>
      <MotionTitle lines={chapter.heading} frame={frame} fps={fps} start={chapter.start} color={theme.ink} font={displayFont} size={offer?118:112} align={dark?'center':'left'} width={920}/>
      <div style={{marginTop:24,color:theme.muted,fontSize:42,lineHeight:1.42,textAlign:dark?'center':'left',maxWidth:920,textWrap:'balance'}}>{chapter.deck}</div>
    </div>

    {active ? <>
      <div style={{position:'absolute',left:76,top:582,width:928,height:990,borderRadius:green?'70px 18px 18px 18px':dark?'100px 100px 8px 8px':6,border:`2px solid ${theme.accent}88`,background:theme.base}}/>
      <MaterialWindow scene={active} box={{x:80,y:586,w:920,h:982,radius:green?'68px 16px 16px 16px':dark?'98px 98px 6px 6px':4}}/>
      <div style={{position:'absolute',left:94,top:602,zIndex:8,padding:'9px 15px',background:dark?'#0c1015ee':'#f8f7eeee',color:theme.ink,fontSize:26,fontWeight:700}}>{active.sourceLabel}</div>
      <PresenterWindow p={p} box={{x:780,y:1192,w:210,h:356,radius:green?40:4}} objectPosition={videoPosition} scale={close?1.02:1}/>
      <div style={{position:'absolute',left:780,top:1550,width:210,height:3,background:theme.accent}}/>
    </> : green ? <>
      <PresenterWindow p={p} box={{x:offer?338:294,y:586,w:offer?662:706,h:984,radius:'300px 300px 28px 28px'}} objectPosition={videoPosition} scale={close?1.02:1}/>
      <div style={{position:'absolute',left:80,top:offer?756:774,width:180,display:'flex',flexDirection:'column',gap:34}}>
        {chapter.points.map((point,i)=><div key={point} style={{position:'relative',padding:'23px 8px',minHeight:122,borderRadius:i===1?'12px 60px 12px 60px':70,border:'1px solid #547d5144',background:'#fcfaf0f5',display:'flex',alignItems:'center',justifyContent:'center',fontSize:36,fontWeight:700,textAlign:'center',boxShadow:'0 7px 18px #42604b10',transform:`translateX(${(1-settle)*(i%2?24:-24)}px)`}}><PointMotion p={p} text={point} start={chapter.start} end={chapter.end} frame={frame} fps={fps}/><div style={{position:'absolute',height:3,bottom:18,left:60,right:60,background:i===1?'#df9943':'#c4cf9c'}}/></div>)}
      </div>
    </> : blue && offer ? <>
      <div style={{position:'absolute',left:80,top:610,width:572,height:950,padding:'42px 30px',boxSizing:'border-box',background:'#173fc9',color:'#fff',overflow:'hidden'}}>
        <div style={{fontSize:44,fontWeight:700,lineHeight:1.4}}>了解合作方案</div>
        <div style={{height:3,width:80,marginTop:30,background:'#e94c33'}}/>
        {chapter.points.map((point,i)=><div key={point} style={{marginTop:54,fontSize:61,fontWeight:700,lineHeight:1.4,translate:`${interpolate(f-i*3,[0,9],[-24,0],clamp)}px 0`}}><PointMotion p={p} text={point} start={chapter.start} end={chapter.end} frame={frame} fps={fps}/></div>)}
        <svg viewBox="0 0 560 120" style={{position:'absolute',left:0,bottom:22,width:560,height:120}}><path d="M20 100 180 20l180 80 180-80" stroke="#7293ff" strokeWidth="2" fill="none"/></svg>
      </div>
      <PresenterWindow p={p} box={{x:684,y:610,w:316,h:950,radius:6}} objectPosition="50% 48%"/>
    </> : <>
      <PresenterWindow p={p} box={{x:dark?126:80,y:590,w:dark?828:920,h:980,radius:dark?'155px 155px 6px 6px':6}} objectPosition={videoPosition} filter={dark?'saturate(.88)':undefined}/>
      {dark&&<div style={{position:'absolute',left:126,top:1260,width:828,height:310,background:'linear-gradient(transparent,#0b101399)'}}/>}
      <div style={{position:'absolute',left:dark?150:100,right:dark?150:100,top:1463,padding:'17px 20px',background:dark?'#0c1116dd':'#f9f8f2f5',borderTop:`1px solid ${theme.accent}77`,display:'flex',justifyContent:'space-around',color:theme.ink,fontSize:cta?42:35,fontWeight:700,lineHeight:1.4}}>{chapter.points.map(point=><div key={point}><PointMotion p={p} text={point} start={chapter.start} end={chapter.end} frame={frame} fps={fps}/></div>)}</div>
    </>}
    <CaptionTrack p={p} box={{x:80,y:1610,w:920,h:180}}/>
    {dark && <div style={{position:'absolute',left:80,right:80,top:1798,height:1,background:'#ac8b5a77'}}/>}
  </AbsoluteFill>;
};
