import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import type {Box, LabProps} from './types';
import {Brand, Caption, ease, metrics, phase, phaseStart, Rule, SERIF, SourceWindow, TextBlock} from './shared';

// Each layout is recomposed in its native ratio. These helpers interpolate
// layout geometry only; SourceWindow always contains the complete source.
const rect=(p:LabProps,x:number,y:number,w:number,h:number):Box=>({x:x*p.width,y:y*p.height,w:w*p.width,h:h*p.height});
const blend=(a:Box,b:Box,t:number):Box=>({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,w:a.w+(b.w-a.w)*t,h:a.h+(b.h-a.h)*t});
// The frozen input owns copy and editorial line breaks for each ratio.
const words=(p:LabProps,f:number):string=>phase(f)===3&&p.cta?p.cta:p.beatTitles[phase(f)]??p.headline;
const stableTitle=(f:number):React.CSSProperties=>({opacity:phase(f)===0?1:.88+.12*ease((f-phaseStart(f))/8)});
const sizedTitle=(text:string,w:number,requested:number)=>Math.min(requested,w/Math.max(...text.split('\n').map(s=>Array.from(s).length))*.94);
const positioned=(p:LabProps,f:number,states:Box[]):Box=>{
  const i=phase(f);
  return i===0?states[0]:blend(states[i-1],states[i],ease((f-phaseStart(f))/14));
};

export const Style07:React.FC<LabProps>=(p)=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,unit:u,wide,square}=m,i=phase(f);
  const night='#0E1820',light='#F6EDDE',copper='#C99867',depth='#273B45';
  const base=wide?rect(p,.34,.17,.59,.58):square?rect(p,.08,.33,.84,.42):p.ratio==='4x5'?rect(p,.10,.29,.79,.47):rect(p,.10,.31,.78,.44);
  const person=positioned(p,f,[base,{...base,x:base.x+W*.01,w:base.w-W*.01},{...base,x:base.x-W*.012,w:base.w+W*.012},{...base,y:base.y-H*.012,h:base.h+H*.012}]);
  const title=wide?rect(p,.065,.22,.255,.32):square?rect(p,.10,.105,.76,.18):rect(p,.10,.12,.76,.17);
  const text=words(p,f),font=sizedTitle(text,title.w,(wide?78:square?94:96)*u);
  const reveal=ease(f/14),side=wide?W*.023:W*.028;
  const cap=wide?rect(p,.065,.815,.865,.105):square?rect(p,.08,.805,.84,.115):rect(p,.085,.805,.80,.102);
  const lineProgress=i===3?1-ease((f-phaseStart(f))/12)*.36:1;
  return <AbsoluteFill style={{background:night}}>
    <div style={{position:'absolute',left:0,top:0,width:W*.035,height:H,background:'#17252D'}}/>
    <div style={{position:'absolute',right:0,top:0,width:W*.042,height:H,background:'#091116'}}/>
    <div style={{position:'absolute',left:person.x-W*.018,top:person.y-H*.012,width:person.w+W*.036,height:person.h+H*.024,border:`${u*1.5}px solid ${depth}`,boxSizing:'border-box'}}/>
    <SourceWindow props={p} box={person} border={`${u*1.5}px solid #46515A`} style={{boxShadow:`0 ${18*u}px ${40*u}px #00000055`}}/>
    <div style={{position:'absolute',left:person.x-(1-reveal)*side,top:person.y,width:side*(1-reveal*.78),height:person.h,background:'#111C23',pointerEvents:'none'}}/>
    <div style={{position:'absolute',right:W-person.x-person.w-(1-reveal)*side,top:person.y,width:side*(1-reveal*.78),height:person.h,background:'#111C23',pointerEvents:'none'}}/>
    <Rule x={person.x} y={person.y+person.h+H*.013} w={person.w*lineProgress} color={copper} thickness={u*2}/>
    <Brand props={p} color={light} x={W*.10} y={H*.052} w={W*.73}/>
    <TextBlock text={text} x={title.x} y={title.y} w={title.w} size={font} color={light} lineHeight={1.17} style={{letterSpacing:u*2,...stableTitle(f)}}/>
    <Rule x={title.x} y={title.y-u*15} w={W*(wide?.068:.12)} color={copper} thickness={u*3}/>
    <Caption props={p} box={cap} color={light} background='#15232D' accent={light} mode='rise'/>
  </AbsoluteFill>;
};

export const Style08:React.FC<LabProps>=(p)=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,unit:u,wide,square}=m,i=phase(f);
  const paper='#F3DDD2',ink='#173D42',coral='#CC624C',fold='#B84F3C',light='#FFF6ED';
  const base=wide?rect(p,.52,.12,.41,.64):square?rect(p,.34,.30,.59,.48):p.ratio==='4x5'?rect(p,.25,.26,.67,.51):rect(p,.17,.29,.75,.46);
  const person=positioned(p,f,[base,{...base,x:base.x-W*.018,w:base.w+W*.012},{...base,x:base.x+W*.008,y:base.y-H*.008},{...base,x:base.x-W*.01,y:base.y-H*.01,w:base.w+W*.01,h:base.h+H*.01}]);
  const title=wide?rect(p,.07,.20,.39,.32):square?rect(p,.07,.10,.86,.18):rect(p,.07,.105,.79,.18);
  const text=words(p,f),font=sizedTitle(text,title.w,(wide?98:square?78:100)*u);
  const entrance=ease(f/12),shift=i===0?0:Math.sin(i*.8)*W*.015;
  const corner=Math.min(person.w*.10,person.h*.10);
  const cap=wide?rect(p,.07,.815,.86,.105):square?rect(p,.07,.81,.86,.11):rect(p,.075,.805,.81,.104);
  return <AbsoluteFill style={{background:paper}}>
    <svg width={W} height={H} style={{position:'absolute',inset:0}} aria-hidden>
      <path d={`M 0 ${H*.38} L ${W*(wide?.49:.27)+shift} ${H*.14} L ${W*(wide?.49:.27)+shift} ${H*.77} L 0 ${H*.9} Z`} fill={coral}/>
      <path d={`M 0 ${H*.38} L ${W*(wide?.49:.27)+shift} ${H*.14} L ${W*.10} ${H*.47} Z`} fill={light}/>
      <path d={`M ${W*(wide?.49:.27)+shift} ${H*.14} L ${W*(wide?.53:.32)+shift} ${H*.20} L ${W*(wide?.53:.32)+shift} ${H*.74} L ${W*(wide?.49:.27)+shift} ${H*.77} Z`} fill={fold}/>
      <path d={`M ${W*.80} ${H*.96} L ${W} ${H*.69} L ${W} ${H} L ${W*.71} ${H} Z`} fill={coral}/>
      <path d={`M ${W*.80} ${H*.96} L ${W} ${H*.69} L ${W*.92} ${H} Z`} fill={fold}/>
    </svg>
    <div style={{position:'absolute',left:person.x-u*9,top:person.y-u*9,width:person.w+u*18,height:person.h+u*18,background:light,clipPath:`polygon(0 0,100% 0,100% calc(100% - ${corner}px),calc(100% - ${corner}px) 100%,0 100%)`}}/>
    <SourceWindow props={p} box={person}/>
    <svg width={W} height={H} style={{position:'absolute',inset:0,pointerEvents:'none'}} aria-hidden>
      <path d={`M ${person.x+person.w} ${person.y+person.h-corner} L ${person.x+person.w-corner} ${person.y+person.h} L ${person.x+person.w} ${person.y+person.h} Z`} fill={fold}/>
      <path d={`M ${person.x+person.w} ${person.y+person.h-corner} L ${person.x+person.w-corner} ${person.y+person.h-corner} L ${person.x+person.w-corner} ${person.y+person.h} Z`} fill={paper}/>
    </svg>
    <div style={{position:'absolute',left:W*(1.01-entrance*.03),top:H*.30,width:W*.12,height:H*.42,background:coral,transform:'skewY(-18deg)'}}/>
    <Brand props={p} color={ink} x={W*.07} y={H*.047} w={W*.79}/>
    <TextBlock text={text} x={title.x} y={title.y} w={title.w} size={font} color={ink} lineHeight={1.14} style={{letterSpacing:-u*.7,...stableTitle(f)}}/>
    <Caption props={p} box={cap} color={light} background={ink} accent={light} mode='wipe'/>
  </AbsoluteFill>;
};

export const Style09:React.FC<LabProps>=(p)=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,unit:u,wide,square}=m,i=phase(f);
  const paper='#F4F3EE',ink='#151515';
  const base=wide?rect(p,.66,.09,.26,.68):square?rect(p,.45,.14,.40,.65):p.ratio==='4x5'?rect(p,.38,.22,.49,.56):rect(p,.27,.28,.61,.48);
  const person=positioned(p,f,[base,{...base,x:base.x-W*.012,w:base.w+W*.012},{...base,x:base.x-W*.025,w:base.w+W*.025},{...base,y:base.y-H*.012,h:base.h+H*.012}]);
  const title=wide?rect(p,.065,.18,.54,.48):square?rect(p,.065,.20,.34,.45):rect(p,.065,.115,.79,.18);
  const text=words(p,f),font=sizedTitle(text,title.w,(wide?134:square?110:110)*u);
  const cap=wide?rect(p,.065,.815,.865,.105):square?rect(p,.065,.815,.87,.105):rect(p,.065,.805,.82,.105);
  const bar=i<2?W*.022:W*(.022+.026*ease((f-162)/8));
  const ambientX=wide?W*.04:W*.002;
  return <AbsoluteFill style={{background:paper}}>
    <div style={{position:'absolute',left:ambientX+(i===0?1-ease(f/8):0)*W*.02,top:wide?H*.56:H*.41,fontSize:(wide?345:square?610:510)*u,fontFamily:'"Microsoft YaHei", sans-serif',fontWeight:900,letterSpacing:-u*35,lineHeight:.85,color:i===3?'#DAD9D4':'#D0CFCA',whiteSpace:'nowrap',pointerEvents:'none'}}>AI</div>
    <div style={{position:'absolute',left:0,top:0,width:bar,height:H,background:ink}}/>
    <Rule x={W*.065} y={H*.093} w={W*.865} color={ink} thickness={u*2}/>
    <div style={{position:'absolute',left:person.x-u*8,top:person.y-u*8,width:person.w+u*16,height:person.h+u*16,background:ink}}/>
    <SourceWindow props={p} box={person}/>
    <Brand props={p} color={ink} x={W*.065} y={H*.044} w={W*.78}/>
    <TextBlock text={text} x={title.x} y={title.y} w={title.w} size={font} color={ink} weight={900} lineHeight={1.08} style={{letterSpacing:-u*1.5,...stableTitle(f)}}/>
    <Rule x={title.x} y={wide?H*.716:square?H*.728:H*.739} w={W*(wide?.30:square?.22:.16)} color={ink} thickness={u*7}/>
    <Caption props={p} box={cap} color='#FFFFFF' background={ink} accent='#FFFFFF' mode='wipe'/>
  </AbsoluteFill>;
};

export const Style10:React.FC<LabProps>=(p)=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,unit:u,wide,square}=m,i=phase(f);
  const paper='#EEE3D0',ink='#3A2328',wine='#682F43',light='#FFF8EC';
  const base=wide?rect(p,.53,.13,.39,.64):square?rect(p,.44,.15,.47,.62):p.ratio==='4x5'?rect(p,.32,.26,.58,.51):rect(p,.20,.29,.70,.46);
  const person=positioned(p,f,[base,{...base,x:base.x-W*.01,y:base.y+H*.004},{...base,x:base.x-W*.015,w:base.w+W*.015},{...base,x:base.x-W*.022,w:base.w+W*.022}]);
  const title=wide?rect(p,.09,.24,.35,.34):square?rect(p,.09,.22,.29,.37):rect(p,.09,.13,.76,.15);
  const text=words(p,f),font=sizedTitle(text,title.w,(wide?99:square?92:95)*u);
  const cap=wide?rect(p,.09,.815,.83,.103):square?rect(p,.09,.815,.82,.105):rect(p,.09,.805,.80,.103);
  const open=ease(f/14),spine=wide?W*.027:square?W*.035:W*.055;
  const endSpine=i===3?spine*(1-.20*ease((f-270)/12)):spine;
  const frameExpansion=i===2?ease((f-162)/12)*W*.006:i>2?W*.006:0;
  return <AbsoluteFill style={{background:paper}}>
    <div style={{position:'absolute',left:0,top:0,width:endSpine,height:H,background:wine}}/>
    <div style={{position:'absolute',left:endSpine,top:0,width:u*3,height:H,background:'#D0BAA9'}}/>
    <div style={{position:'absolute',left:wide?W*.472:square?W*.402:W*.08,top:wide?H*.12:square?H*.14:H*.115,width:u*1.5,height:wide?H*.65:square?H*.64:H*.65,background:'#BDAA99'}}/>
    <div style={{position:'absolute',left:person.x-u*10-frameExpansion,top:person.y-u*10,width:person.w+u*20+frameExpansion*2,height:person.h+u*20,border:`${u*1.5}px solid #A58A7F`,background:light,boxSizing:'border-box'}}/>
    <SourceWindow props={p} box={person}/>
    <div style={{position:'absolute',left:wide?W*.055:square?W*.055:W*.075,top:wide?H*.12:H*.10,width:(1-open)*W*.045,height:wide?H*.65:H*.68,background:wine,pointerEvents:'none'}}/>
    <Brand props={p} color={wine} x={W*.09} y={H*.047} w={W*.78}/>
    <TextBlock text={text} x={title.x} y={title.y} w={title.w} size={font} color={ink} font={SERIF} lineHeight={1.17} style={{letterSpacing:u*1.4,...stableTitle(f)}}/>
    <Rule x={title.x} y={wide?H*.708:square?H*.735:H*.768} w={W*(wide?.12:square?.16:.23)} color={wine} thickness={u*3}/>
    <Caption props={p} box={cap} color={ink} background={light} accent={wine} mode='focus'/>
  </AbsoluteFill>;
};
