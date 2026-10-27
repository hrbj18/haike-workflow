import React from 'react';
import type {Chapter, FullProps, Graphic} from './types';
import {rectStyle, textUnits, themeLayout} from './geometry';
import {PALETTES, SANS, SERIF} from './palettes';
import {ease} from './Shared';

type GraphicProps={p:FullProps;chapter:Chapter;graphic:Graphic;localFrame:number};
const itemSize=(text:string,width:number,request:number)=>Math.min(request,width/Math.max(1,textUnits(text)));
const intro=(p:FullProps,chapter:Chapter,g:Graphic)=>{
  const palette=PALETTES[p.paletteVariant];
  return <>
    {chapter.deck&&<div data-role="graphic-deck" style={{position:'absolute',left:0,top:0,width:'100%',fontFamily:SANS,fontSize:44,lineHeight:1.5,color:palette.ink}}>{chapter.deck}</div>}
    <div data-role="graphic-subheading" style={{position:'absolute',left:0,top:114,width:'100%',fontFamily:p.templateNumber===7?SERIF:SANS,
      fontSize:g.kind==='offer'?78:64,fontWeight:p.templateNumber===9?900:700,lineHeight:1.2,color:palette.ink,whiteSpace:'nowrap'}}>{g.heading}</div>
  </>;
};

export const TheatreGraphic:React.FC<GraphicProps>=({p,chapter,graphic:g,localFrame})=>{
  const l=themeLayout(p.paletteVariant).graphic, palette=PALETTES[p.paletteVariant];
  const twoWay=g.kind==='process'&&g.items.length===2;
  return <div data-role="graphic-body" data-graphic={g.id} data-system="theatre" style={{...rectStyle(l),fontFamily:SANS,color:palette.ink}}>
    {intro(p,chapter,g)}
    {twoWay?<>
      <svg width={l.w} height={600} style={{position:'absolute',top:210,left:0}} aria-hidden>
        <path d={`M 60 285 H ${l.w-60}`} stroke={palette.accent} strokeWidth={2} fill="none"/>
        <path d={`M ${l.w/2-18} 263 L ${l.w/2+18} 285 L ${l.w/2-18} 307`} stroke={palette.accent} strokeWidth={3} fill="none"/>
      </svg>
      {g.items.map((item,i)=><div key={i} data-role="graphic-item" style={{position:'absolute',left:i?l.w*.56:0,top:300,
        width:l.w*.44,height:360,border:`1.5px solid ${palette.accent}`,background:palette.mount,display:'flex',flexDirection:'column',justifyContent:'center',
        padding:40,boxSizing:'border-box',translate:`0px ${Math.round((1-ease((localFrame-5-i*5)/12))*16)}px`}}>
        <div style={{fontFamily:SERIF,fontSize:62,lineHeight:1.3,marginBottom:38}}>{String(i+1).padStart(2,'0')}</div>
        <div style={{fontSize:itemSize(item,l.w*.44-80,76),lineHeight:1.35,fontWeight:700,whiteSpace:'pre'}}>{item}</div>
      </div>)}
    </>:g.items.map((item,i)=>{
      const h=g.items.length===3?184:232, y=270+i*(h+44), offer=g.kind==='offer';
      return <div key={i} data-role="graphic-item" style={{position:'absolute',left:0,top:y,width:l.w,height:h,
        borderTop:`${offer?3:1.5}px solid ${palette.accent}`,padding:'24px 8px',boxSizing:'border-box',
        translate:`${Math.round((1-ease((localFrame-5-i*5)/12))*-18)}px 0px`,display:'flex',alignItems:'center',gap:38}}>
        <span style={{width:32,height:32,border:`2px solid ${palette.accent}`,display:'block',flexShrink:0}}/>
        <div style={{fontSize:itemSize(item,l.w-115,offer?88:g.kind==='metric'?108:80),lineHeight:1.25,fontWeight:700,whiteSpace:'pre'}}>{item}</div>
      </div>;
    })}
    <div style={{position:'absolute',left:0,bottom:24,width:l.w*.20,height:2,background:palette.accent}}/>
  </div>;
};

export const FoldGraphic:React.FC<GraphicProps>=({p,chapter,graphic:g,localFrame})=>{
  const l=themeLayout(p.paletteVariant).graphic, palette=PALETTES[p.paletteVariant];
  return <div data-role="graphic-body" data-graphic={g.id} data-system="fold" style={{...rectStyle(l),fontFamily:SANS}}>
    {intro(p,chapter,g)}
    {g.items.map((item,i)=>{
      const x=i*36,h=g.items.length===3?174:230,y=264+i*(h+46),w=l.w-x;
      return <div key={i} data-role="graphic-item" style={{position:'absolute',left:x,top:y,width:w,height:h,
        background:palette.graphSurface,color:palette.graphText,boxSizing:'border-box',padding:'34px 58px',
        display:'flex',alignItems:'center',gap:38,translate:`${Math.round((1-ease((localFrame-4-i*4)/10))*-28)}px 0px`}}>
        {g.kind==='process'?<span style={{fontSize:44,lineHeight:1,fontWeight:500,flexShrink:0}}>{String(i+1).padStart(2,'0')}</span>:
          <svg width={24} height={32} viewBox="0 0 24 32" style={{flexShrink:0}} aria-hidden><path d="M0 0H24L0 32Z" fill={palette.graphText}/></svg>}
        <div style={{fontSize:itemSize(item,w-190,g.kind==='metric'?112:g.kind==='offer'?84:78),lineHeight:1.2,fontWeight:800,whiteSpace:'pre'}}>{item}</div>
        <div style={{position:'absolute',right:0,bottom:-22,width:0,height:0,borderLeft:'24px solid transparent',borderTop:`22px solid ${palette.mount}`}}/>
      </div>;
    })}
  </div>;
};

export const TypefieldGraphic:React.FC<GraphicProps>=({p,chapter,graphic:g,localFrame})=>{
  const l=themeLayout(p.paletteVariant).graphic, palette=PALETTES[p.paletteVariant];
  const columns=g.kind==='process'&&g.items.length===3;
  return <div data-role="graphic-body" data-graphic={g.id} data-system="typefield" style={{...rectStyle(l),fontFamily:SANS}}>
    {intro(p,chapter,g)}
    {columns?<>
      <div style={{position:'absolute',left:0,top:244,width:l.w,height:9,background:palette.accent}}/>
      {g.items.map((item,i)=><div key={i} data-role="graphic-item" style={{position:'absolute',left:i*(l.w/3+8),top:300,
        width:l.w/3-20,height:418,border:`3px solid ${palette.accent}`,padding:'44px 28px',boxSizing:'border-box',
        color:palette.ink,translate:`0px ${Math.round((1-ease((localFrame-4-i*4)/10))*22)}px`}}>
        <div style={{fontSize:42,lineHeight:1,fontWeight:500,marginBottom:82}}>{String(i+1).padStart(2,'0')}</div>
        <div style={{fontSize:itemSize(item,l.w/3-76,112),fontWeight:900,lineHeight:1.1,whiteSpace:'pre'}}>{item}</div>
      </div>)}
    </>:g.items.map((item,i)=>{
      const first=i===0,y=280+i*(g.items.length===3?204:260),h=g.items.length===3?166:206;
      return <div key={i} data-role="graphic-item" style={{position:'absolute',left:0,top:y,width:l.w,height:h,
        background:first?palette.accent:palette.canvas,color:first?palette.canvas:palette.accent,
        borderBottom:first?undefined:`4px solid ${palette.accent}`,padding:'26px 38px',boxSizing:'border-box',display:'flex',alignItems:'center',
        translate:`${Math.round((1-ease((localFrame-4-i*4)/9))*-20)}px 0px`}}>
        <div style={{fontSize:itemSize(item,l.w-76,first?g.kind==='metric'?150:110:84),fontWeight:900,lineHeight:1.1,whiteSpace:'pre'}}>{item}</div>
      </div>;
    })}
    <div style={{position:'absolute',left:0,bottom:26,width:156,height:10,background:palette.accent}}/>
  </div>;
};
