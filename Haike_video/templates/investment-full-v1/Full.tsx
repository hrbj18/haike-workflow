import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Chapter, FullProps} from './types';
import {BINDING, PALETTES, SANS} from './palettes';
import {assertProps, chapterAt, themeLayout} from './geometry';
import {Avatar, Brand, CaptionPlate, ease, Headline, MasterAudio, PresenterNotes, Shots} from './Shared';
import {FoldGraphic, TheatreGraphic, TypefieldGraphic} from './Graphics';

const Background:React.FC<{p:FullProps;chapter:Chapter;localFrame:number}> = ({p,chapter,localFrame})=>{
  const palette=PALETTES[p.paletteVariant], frame=useCurrentFrame(), l=themeLayout(p.paletteVariant);
  const pulse=p.soundEvents.reduce((value,e)=>{
    const age=frame-e.startFrame;
    return age>=0&&age<8?Math.max(value,Math.pow(1-age/8,2)*Math.min(1,e.strength*2)):value;
  },0);
  if(p.templateNumber===7)return <>
    <div style={{position:'absolute',left:0,top:0,width:36,height:1800,background:palette.mount}}/>
    <div style={{position:'absolute',right:0,top:0,width:44,height:1800,background:palette.mount}}/>
    <div style={{position:'absolute',left:102,top:164,width:156+24*ease(localFrame/14),height:3+pulse*3,background:palette.accent}}/>
    <div style={{position:'absolute',left:100,top:1458,width:1240,height:1.5,background:palette.accent}}/>
    {chapter.kind==='presenter'&&<svg width={1440} height={1800} style={{position:'absolute',inset:0}} aria-hidden>
      <path d={`M ${l.presenter.x-20} 1450 V 408 H ${l.presenter.x+l.presenter.w+20} V 1450`} stroke={palette.accent} strokeWidth="1" fill="none"/>
      <path d={`M 102 1320 H 330 V ${1320-120*ease(localFrame/14)}`} stroke={palette.accent} strokeWidth="2" fill="none"/>
    </svg>}
  </>;
  if(p.templateNumber===8)return <svg width={1440} height={1800} style={{position:'absolute',inset:0}} aria-hidden>
    <path d="M0 360 L82 286 L82 1454 L0 1548Z" fill={palette.accent}/>
    <path d="M82 286 L114 322 L114 1418 L82 1454Z" fill={palette.mount}/>
    <path d={`M1350 172 L1440 ${80+44*(1-ease(localFrame/12))} V 470 L1350 560Z`} fill={palette.accent}/>
    <path d="M1316 660 L1440 532 V1380 L1316 1452Z" fill={palette.mount}/>
    <path d="M1150 1800 L1440 1604 V1800Z" fill={palette.accent}/>
    <path d="M1150 1800 L1440 1604 L1360 1800Z" fill={palette.mount}/>
    <path d="M100 163 H380" fill="none" stroke={palette.accent} strokeWidth={4+pulse*3}/>
  </svg>;
  return <>
    <div style={{position:'absolute',left:0,top:0,width:28+pulse*6,height:1800,background:palette.accent}}/>
    <div style={{position:'absolute',left:104,top:157,width:1232,height:3,background:palette.accent}}/>
    {chapter.kind==='presenter'&&<div aria-hidden style={{position:'absolute',left:42,top:1050,fontFamily:SANS,fontSize:404,fontWeight:900,lineHeight:.8,
      color:palette.mount,letterSpacing:-36,whiteSpace:'nowrap'}}>AI</div>}
    <div style={{position:'absolute',left:104,top:1458,width:196+Math.round(ease(localFrame/10)*40),height:9,background:palette.accent}}/>
  </>;
};

export const FullVideo:React.FC<FullProps>=(p)=>{
  if(BINDING[p.paletteVariant]!==p.templateNumber)throw new Error('Full template number and palette binding do not match');
  assertProps(p);
  const frame=useCurrentFrame(), chapter=chapterAt(p,frame);
  if(!chapter)throw new Error('No current chapter on the full timeline');
  const palette=PALETTES[p.paletteVariant], localFrame=frame-chapter.startFrame;
  const graphic=p.graphics.find(g=>g.chapterId===chapter.id);
  const showAvatar=chapter.kind==='presenter'&&frame<p.contentEndFrame;
  return <AbsoluteFill data-role="investment-full" data-template={p.templateNumber} data-chapter={chapter.id} data-chapter-kind={chapter.kind}
    style={{background:palette.canvas,fontFamily:SANS,overflow:'hidden',color:palette.ink}}>
    <Background p={p} chapter={chapter} localFrame={localFrame}/>
    <Avatar p={p} visible={showAvatar}/>
    <Shots p={p}/>
    <Brand p={p}/>
    <Headline p={p} chapter={chapter} localFrame={localFrame}/>
    {showAvatar&&<PresenterNotes p={p} chapter={chapter}/>} 
    {chapter.kind==='graphic'&&graphic&&(p.templateNumber===7?<TheatreGraphic p={p} chapter={chapter} graphic={graphic} localFrame={localFrame}/>:
      p.templateNumber===8?<FoldGraphic p={p} chapter={chapter} graphic={graphic} localFrame={localFrame}/>:<TypefieldGraphic p={p} chapter={chapter} graphic={graphic} localFrame={localFrame}/>)}
    <CaptionPlate p={p}/>
    <MasterAudio p={p}/>
  </AbsoluteFill>;
};
