import React from 'react';
import {Audio, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Box, Chapter, FullProps} from './types';
import {PALETTES, SANS, SERIF} from './palettes';
import {assertCyanMediaSidebar, CYAN_MEDIA_INFO_STYLE, cyanMediaSidebarEnabled, rectStyle, textUnits, themeLayout} from './geometry';
import layout from './layout.json';

export const clamp=(v:number)=>Math.min(1,Math.max(0,v));
export const ease=(v:number)=>1-Math.pow(1-clamp(v),3);
export const Headline:React.FC<{p:FullProps;chapter:Chapter;localFrame:number}> = ({p,chapter,localFrame})=>{
  const palette=PALETTES[p.paletteVariant], l=themeLayout(p.paletteVariant);
  const box=chapter.kind==='media'?l.mediaHeading:l.presenterHeading;
  const lines=chapter.heading, max=Math.max(...lines.map(textUnits));
  const requested=p.templateNumber===9?112:p.templateNumber===8?100:94;
  const size=Math.min(requested,(box.w-8)/Math.max(1,max),box.h/(lines.length*1.12));
  return <div data-role="chapter-heading" data-chapter={chapter.id} style={{...rectStyle(box),fontFamily:p.templateNumber===7?SERIF:SANS,
    color:palette.ink,fontSize:size,fontWeight:p.templateNumber===9?900:700,lineHeight:1.12,letterSpacing:p.templateNumber===9?-1.6:0,
    translate:`0px ${Math.round((1-ease(localFrame/8))*12)}px`,whiteSpace:'pre',overflow:'visible'}}>
    {lines.join('\n')}
  </div>;
};

export const Brand:React.FC<{p:FullProps}> = ({p})=> <div data-role="brand" style={{...rectStyle(layout.brand),fontFamily:SANS,
  fontSize:layout.brand.fontSize,fontWeight:600,color:PALETTES[p.paletteVariant].ink,lineHeight:1.35,whiteSpace:'nowrap'}}>{p.brand}</div>;

export const Avatar:React.FC<{p:FullProps;visible:boolean}> = ({p,visible})=>{
  const {fps}=useVideoConfig(), box=themeLayout(p.paletteVariant).presenter, palette=PALETTES[p.paletteVariant];
  if(!visible)return null;
  const src=p.presenterVideo?.src||p.avatarSrc;
  const edits=p.presenterVideo?p.presenterVideo.segments.map(s=>({...s,sourceStartFrame:s.sourceOffsetFrames})):p.sourceEdits;
  return <div data-role="presenter-window" data-visible={String(visible)} style={{...rectStyle(box),visibility:visible?'visible':'hidden',background:palette.mount,
    outline:p.templateNumber===9?`7px solid ${palette.accent}`:p.templateNumber===7?`1.5px solid ${palette.accent}`:undefined,
    outlineOffset:p.templateNumber===7?12:p.templateNumber===9?0:undefined,overflow:'hidden'}}>
    {edits.map(edit=><Sequence key={edit.id} name={edit.id} from={edit.startFrame} durationInFrames={edit.endFrame-edit.startFrame} premountFor={fps}>
      <OffthreadVideo data-role="avatar-source" src={staticFile(src)} startFrom={edit.sourceStartFrame} muted
        style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain'}}/>
    </Sequence>)}
  </div>;
};

export const Shots:React.FC<{p:FullProps}> = ({p})=>{
  const {fps}=useVideoConfig(), frame=useCurrentFrame(), box=themeLayout(p.paletteVariant).media, palette=PALETTES[p.paletteVariant];
  const current=p.shots.find(s=>frame>=s.startFrame&&frame<s.endFrame);
  return <>
    {p.shots.map(shot=>{
      const chapter=p.chapters.find(c=>shot.startFrame>=c.startFrame&&shot.endFrame<=c.endFrame);
      const sidebar=cyanMediaSidebarEnabled(p,chapter)&&chapter?assertCyanMediaSidebar(box,chapter):null;
      const source=shot.kind==='video'?<OffthreadVideo data-role="broll-source" src={staticFile(shot.src)} startFrom={shot.sourceOffsetFrames} muted
        style={{width:'100%',height:'100%',objectFit:sidebar?'contain':shot.fit}}/>:
        <Img data-role="broll-source" src={staticFile(shot.src)} style={{width:'100%',height:'100%',objectFit:sidebar?'contain':shot.fit}}/>;
      const info=CYAN_MEDIA_INFO_STYLE;
      return <Sequence key={shot.id} name={shot.id} from={shot.startFrame} durationInFrames={shot.endFrame-shot.startFrame} premountFor={fps}>
      <div data-role="material-window" data-shot={shot.id} style={{...rectStyle(box),background:palette.mount,
        border:p.templateNumber===9?`5px solid ${palette.accent}`:p.templateNumber===7?`1.5px solid ${palette.accent}`:undefined,
        padding:p.templateNumber===9?9:p.templateNumber===7?9:0}}>
        {sidebar&&chapter?<>
          <div data-role="media-portrait-right" data-shot={shot.id} style={rectStyle(sidebar.picture)}>{source}</div>
          <div data-role="media-info-sidebar" data-chapter={chapter.id} style={{...rectStyle(sidebar.notes),fontFamily:SANS,color:palette.ink}}>
            {chapter.deck&&<div data-role="media-info-deck" style={{fontSize:info.deckFontSize,lineHeight:info.deckLineHeight,fontWeight:500,
              whiteSpace:'pre-wrap',wordBreak:'break-all',marginBottom:info.deckGap}}>{chapter.deck}</div>}
            {chapter.points.map((point,i)=><div key={i} data-role="media-info-point" data-point-index={i} style={{fontSize:info.pointFontSize,
              lineHeight:info.pointLineHeight,fontWeight:700,whiteSpace:'pre-wrap',wordBreak:'break-all',paddingTop:info.pointPaddingTop,
              marginBottom:info.pointMarginBottom,borderTop:`${info.pointBorderTop}px solid ${palette.accent}`}}>{point}</div>)}
          </div>
        </>:source}
      </div>
    </Sequence>;
    })}
    {current&&<div data-role="source-label" style={{position:'absolute',left:box.x,top:box.y+box.h+21,width:box.w,height:45,
      fontFamily:SANS,fontSize:29,lineHeight:1.4,fontWeight:500,color:palette.ink,whiteSpace:'nowrap'}}>{current.sourceLabel}</div>}
  </>;
};

export const CaptionPlate:React.FC<{p:FullProps}> = ({p})=>{
  const frame=useCurrentFrame(), {fps}=useVideoConfig(), time=frame/fps;
  const cue=p.cues.find(c=>time+1e-8>=c.start&&time<c.end-1e-8);
  if(!cue)return null;
  const palette=PALETTES[p.paletteVariant], age=frame-cue.start*fps;
  const reveal=(cue.end-cue.start)*fps<layout.caption.minCueFramesForReveal?1:ease(age/layout.caption.revealFrames);
  return <div data-role="caption-plate" style={{...rectStyle(layout.caption),background:palette.captionSurface,
    display:'flex',alignItems:'center',justifyContent:'center',padding:'18px 24px',boxSizing:'border-box'}}>
    <div data-role="caption-text" style={{fontFamily:SANS,color:palette.captionText,fontSize:layout.caption.fontSize,fontWeight:900,
      lineHeight:layout.caption.lineHeight,letterSpacing:-.6,whiteSpace:'pre',textAlign:'center',translate:`0px ${Math.round((1-reveal)*10)}px`}}>{cue.text}</div>
  </div>;
};

export const PresenterNotes:React.FC<{p:FullProps;chapter:Chapter}> = ({p,chapter})=>{
  const palette=PALETTES[p.paletteVariant], x=p.templateNumber===9?104:100, w=p.templateNumber===7?300:p.templateNumber===8?340:374;
  return <div data-role="presenter-notes" style={{position:'absolute',left:x,top:p.templateNumber===9?580:550,width:w,color:palette.ink,fontFamily:SANS}}>
    {chapter.deck&&<div style={{fontSize:46,lineHeight:1.5,fontWeight:500,wordBreak:'break-all',marginBottom:50}}>{chapter.deck}</div>}
    {chapter.points.map((point,i)=><div key={i} style={{fontSize:48,lineHeight:1.45,fontWeight:700,marginBottom:27,whiteSpace:'pre-wrap',wordBreak:'break-all',
      paddingTop:18,borderTop:`${p.templateNumber===9?5:1}px solid ${palette.accent}`}}>{point}</div>)}
  </div>;
};

export const MasterAudio:React.FC<{p:FullProps}> = ({p})=>p.audioSrc?<Audio src={staticFile(p.audioSrc)} volume={1}/>:null;
