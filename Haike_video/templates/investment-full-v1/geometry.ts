import layout from './layout.json';
import type {Box, Chapter, FullProps, PaletteVariant} from './types';

export const rectStyle=(b:Box)=>({position:'absolute' as const,left:b.x,top:b.y,width:b.w,height:b.h});
export const themeLayout=(variant:PaletteVariant)=>layout.styles[variant];
export const chapterAt=(p:FullProps,frame:number):Chapter|undefined=>p.chapters.find(c=>frame>=c.startFrame&&frame<c.endFrame);
export const sourceAt=(p:FullProps,frame:number)=>p.sourceEdits.find(e=>frame>=e.startFrame&&frame<e.endFrame);
export const shotAt=(p:FullProps,frame:number)=>p.shots.find(s=>frame>=s.startFrame&&frame<s.endFrame);
export const inside=(b:Box)=>b.x>=0&&b.y>=0&&b.w>0&&b.h>0&&b.x+b.w<=layout.width&&b.y+b.h<=layout.height;
export const overlaps=(a:Box,b:Box)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
export const textUnits=(text:string)=>Array.from(text).reduce((sum,char)=>sum+(/\s/.test(char)?.3:/[\u0000-\u007f]/.test(char)?.56:/[，。！？、·：；—]/.test(char)?.65:1),0);
export const cyanMediaSidebarEnabled=(p:Pick<FullProps,'templateNumber'|'paletteVariant'>,c:Chapter|undefined)=>
  p.templateNumber===8&&p.paletteVariant==='cyan-charcoal'&&c?.kind==='media'&&c.points.length>0;
export const CYAN_MEDIA_INFO_STYLE={deckFontSize:46,deckLineHeight:1.5,deckMaxLines:2,deckGap:50,
  pointFontSize:48,pointLineHeight:1.45,pointPaddingTop:18,pointMarginBottom:27,pointBorderTop:1,maxPoints:2};
// Child boxes are local to the unchanged media window; the source stays full-frame contain.
export const cyanMediaSidebarBoxes=(box:Box)=>({
  picture:{x:box.w-24-box.h*9/16,y:0,w:box.h*9/16,h:box.h},
  notes:{x:36,y:100,w:570,h:box.h-140},
});
export const sidebarTextLines=(text:string,fontSize:number,width:number)=>text?
  text.split('\n').reduce((sum,line)=>sum+Math.max(1,Math.ceil(textUnits(line)*fontSize/width)),0):0;
export const assertCyanMediaSidebar=(box:Box,c:Chapter)=>{
  const {picture,notes}=cyanMediaSidebarBoxes(box), s=CYAN_MEDIA_INFO_STYLE;
  const within=(b:Box)=>b.x>=0&&b.y>=0&&b.w>0&&b.h>0&&b.x+b.w<=box.w&&b.y+b.h<=box.h;
  if(!within(picture)||!within(notes)||overlaps(picture,notes))throw new Error('Cyan media sidebar overlaps the full portrait source');
  if(c.points.length>s.maxPoints)throw new Error('Cyan media sidebar requires at most2 supporting points');
  const deckLines=sidebarTextLines(c.deck,s.deckFontSize,notes.w);
  if(deckLines>s.deckMaxLines)throw new Error('Cyan media sidebar deck exceeds2 readable lines');
  const height=deckLines*s.deckFontSize*s.deckLineHeight+(deckLines?s.deckGap:0)+c.points.reduce((sum,point)=>
    sum+sidebarTextLines(point,s.pointFontSize,notes.w)*s.pointFontSize*s.pointLineHeight+s.pointPaddingTop+s.pointBorderTop+s.pointMarginBottom,0);
  if(height>notes.h)throw new Error('Cyan media sidebar text exceeds its reading box');
  return {picture,notes,deckLines,estimatedTextHeight:height};
};
export const readingBoxes=(p:FullProps,c:Chapter)=>{
  const l=themeLayout(p.paletteVariant);
  return {heading:c.kind==='media'?l.mediaHeading:l.presenterHeading,
    subject:c.kind==='presenter'?l.presenter:c.kind==='media'?l.media:l.graphic,caption:layout.caption};
};
export const assertProps=(p:FullProps)=>{
  const clock=p.duration===30&&p.durationInFrames===900||p.templateNumber===8&&p.duration===45&&p.durationInFrames===1350;
  if(p.width!==1440||p.height!==1800||p.fps!==30||!clock||p.ratio!=='4x5')throw new Error('Full investment requires 1440×1800,30fps; cyan08 also supports explicit1350f');
  if(p.contentEndFrame+p.tailHoldFrames!==p.durationInFrames)throw new Error('Content end and explicit tail hold do not cover the declared clock');
  let end=0;
  for(const chapter of p.chapters){
    if(chapter.startFrame!==end||chapter.endFrame<=chapter.startFrame)throw new Error('Chapter clock has a gap or overlap');
    if(chapter.heading.length<1||chapter.heading.length>2||chapter.heading.some(s=>textUnits(s)>10.5))throw new Error('Chapter heading requires1–2 short lines,each≤10.5 CJK em units');
    if(chapter.points.length>3)throw new Error('Chapter has more than3 supporting points');
    if(cyanMediaSidebarEnabled(p,chapter))assertCyanMediaSidebar(themeLayout(p.paletteVariant).media,chapter);
    const boxes=readingBoxes(p,chapter);
    if(!inside(boxes.heading)||!inside(boxes.subject)||overlaps(boxes.heading,boxes.subject)||overlaps(boxes.subject,boxes.caption))throw new Error('Reading geometry collision');
    if(chapter.kind==='graphic'&&!p.graphics.some(g=>g.chapterId===chapter.id))throw new Error('Graphic chapter has no source-bound graphic');
    end=chapter.endFrame;
  }
  if(end!==p.durationInFrames)throw new Error('Chapter coverage must end at the declared frame count');
  if(p.presenterVideo){
    const windows:{startFrame:number;endFrame:number}[]=[];
    for(const c of p.chapters.filter(c=>c.kind==='presenter')){
      const last=windows[windows.length-1];
      if(last&&last.endFrame===c.startFrame)last.endFrame=c.endFrame;
      else windows.push({startFrame:c.startFrame,endFrame:c.endFrame});
    }
    if(!p.presenterVideo.src||p.presenterVideo.segments.length!==windows.length)throw new Error('Presenter override must cover every visible interval');
    let sourceEnd=0;
    p.presenterVideo.segments.forEach((s,i)=>{
      const w=windows[i];
      if(s.startFrame!==w.startFrame||s.endFrame!==w.endFrame||!Number.isInteger(s.sourceOffsetFrames)||s.sourceOffsetFrames<sourceEnd)
        throw new Error('Presenter override crosses or misses a visible interval');
      sourceEnd=s.sourceOffsetFrames+s.endFrame-s.startFrame;
    });
  }
  for(const cue of p.cues){
    const lines=cue.text.split('\n');
    if(lines.length>2||lines.some(s=>Array.from(s).length>18))throw new Error('Caption exceeds2 lines or18 characters per line');
  }
  for(const graphic of p.graphics){
    if(graphic.items.length<1||graphic.items.length>3||graphic.items.some(s=>Array.from(s.replace(/\n/g,'')).length>18))throw new Error('Graphic needs1–3 items,each≤18 characters');
  }
  if(p.tailHoldFrames){
    const last=p.chapters[p.chapters.length-1];
    if(last.kind!=='graphic'||last.startFrame>p.contentEndFrame||!p.graphics.some(g=>g.chapterId===last.id&&g.kind==='offer'))throw new Error('Tail hold must be covered by graphic offer');
    if(p.sourceEdits.some(e=>e.endFrame>p.contentEndFrame)||p.shots.some(s=>s.endFrame>p.contentEndFrame))throw new Error('Media enters explicit tail hold');
  }
};
