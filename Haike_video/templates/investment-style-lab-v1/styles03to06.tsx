import React from 'react';
import {AbsoluteFill,useCurrentFrame} from 'remotion';
import type {LabProps,Box} from './types';
import {Brand,Caption,TextBlock,SourceWindow,Rule,ReadableBeat,metrics,phase,phaseStart,ease,SERIF,MONO} from './shared';

// 03: An architectural elevation. Mineral planes hold a tall window and an
// cantilevered beam; the text occupies the structural negative space.
export const Style03:React.FC<LabProps>=p=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,wide,square,margin:a}=m;
  const enter=ease(f/24),change=ease((f-phaseStart(f))/18),idx=phase(f);
  const pic:Box=wide?{x:W*.40,y:H*.155,w:W*.54,h:H*.64}:square?{x:W*.40,y:H*.30,w:W*.52,h:H*.48}:{x:W*.23,y:H*.31,w:W*.69,h:H*.49};
  return <AbsoluteFill style={{background:'#e9e1d3',color:'#343b3b'}}>
    <div style={{position:'absolute',inset:0,background:'repeating-linear-gradient(0deg, transparent 0px, transparent 79px, #8275610b 80px)'}}/>
    <svg width={W} height={H} style={{position:'absolute',left:0,top:0}}>
      <path d={`M ${a} ${H*.81} H ${W*.16} V ${H*.68} H ${W*.22} V ${H*.56} H ${W*.29}`} fill="none" stroke="#ad6e44" strokeWidth={m.unit*28} strokeDasharray={`${W*3}`} strokeDashoffset={W*3*(1-enter)}/>
      <rect x={a} y={H*.822} width={(pic.x+pic.w-a)*enter} height={m.unit*16} fill="#826b49"/>
      <line x1={a} x2={W-a} y1={H*.89} y2={H*.89} stroke="#aa9a83" strokeWidth={1}/>
    </svg>
    <div style={{position:'absolute',left:pic.x-W*.018,top:pic.y+H*.025,width:pic.w,height:pic.h,background:'#c4ad89',transform:`translateX(${(1-change)*-12}px)`}}/>
    <SourceWindow props={p} box={pic} style={{boxShadow:`${m.unit*10}px ${m.unit*15}px 0 #d7c9b6`}}/>
    <Brand props={p} color="#434941"/>
    <TextBlock text="COMMUNITY / A NEW POSSIBILITY" x={a} y={H*.091} w={W*.8} size={m.labelSize*.68} color="#716c60" font={MONO} weight={400}/>
    <ReadableBeat props={p} box={{x:a,y:H*(wide?.25:square?.13:.16),w:W*(wide?.32:.86),h:H*.2}} color="#283e3a" font={SERIF} size={wide?m.heroSize*.95:m.heroSize}/>
    <TextBlock text={String(idx+1).padStart(2,'0')} x={a} y={H*(wide?.56:square?.38:.38)} w={W*.14} size={m.heroSize*.68} color="#92816b" font={MONO} weight={400}/>
    <Rule x={a} y={H*.84} w={W*.16} color="#826b49" thickness={m.unit*4}/>
    <Caption props={p} box={{x:a,y:H*.886,w:W-2*a,h:H*.068}} background="#283e3a" accent="#f0d8a9" mode="wipe"/>
  </AbsoluteFill>;
};

// 04: A dark recording stage with orbital bands; accents are short and
// rhythmic, and the readable caption is deliberately stable after entrance.
export const Style04:React.FC<LabProps>=p=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,wide,square,margin:a}=m,idx=phase(f);
  const pulse=ease((f-phaseStart(f))/12);
  const pic=wide?{x:W*.055,y:H*.17,w:W*.53,h:H*.64}:square?{x:W*.11,y:H*.34,w:W*.66,h:H*.45}:{x:W*.11,y:H*.31,w:W*.78,h:H*.48};
  return <AbsoluteFill style={{background:'#15101e'}}>
    <div style={{position:'absolute',width:W*.73,height:H*.48,left:W*.50,top:H*.12,border:`${m.unit*55}px solid #55358e`,borderRadius:'50%',transform:`rotate(-23deg) scale(${.94+pulse*.06})`,opacity:.53}}/>
    <svg width={W} height={H} style={{position:'absolute'}}>{[0,1,2].map(i=><ellipse key={i} cx={W*.48} cy={H*.55} rx={W*(.35+i*.055)} ry={H*(.26+i*.035)} transform={`rotate(-18 ${W*.48} ${H*.55})`} fill="none" stroke={i===1?'#d8ff79':'#9169d4'} strokeWidth={m.unit*(i===1?3:1.5)} opacity={.7-i*.14}/>)}</svg>
    <SourceWindow props={p} box={pic} radius={pic.w*.47} border={`${m.unit*2}px solid #c9a8ff`}/>
    <Brand props={p} color="#f2e8ff"/>
    <TextBlock text="CREATORS × COMMUNITY" x={a} y={H*.10} w={W*.84} size={m.labelSize*.78} color="#bba7d5" font={MONO}/>
    <ReadableBeat props={p} box={{x:wide?W*.63:a,y:H*(wide?.29:square?.15:.17),w:W*(wide?.31:.85),h:H*.2}} color="#f7f1ff" accent="#d8ff79" size={wide?m.heroSize*.95:m.heroSize*.94}/>
    <div style={{position:'absolute',left:wide?W*.64:W*.72,top:H*(wide?.64:.78),width:W*.20,height:m.unit*52,display:'flex',alignItems:'center',gap:m.unit*7}}>{Array.from({length:11},(_,i)=><div key={i} style={{width:m.unit*7,height:m.unit*(7+((i*13+idx*9)%31)),background:i%3===0?'#d8ff79':'#a880e8'}}/>)}</div>
    <Caption props={p} box={{x:a,y:H*.886,w:W-2*a,h:H*.069}} background="#d8ff79" color="#20152f" accent="#58348b" mode="stamp"/>
  </AbsoluteFill>;
};

// 05: A botanical field guide. The bound page, ruled annotation rail and
// organic line work make the film feel observed rather than manufactured.
export const Style05:React.FC<LabProps>=p=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,wide,square,margin:a}=m;
  const pic=wide?{x:W*.47,y:H*.13,w:W*.47,h:H*.69}:square?{x:W*.38,y:H*.32,w:W*.53,h:H*.47}:{x:W*.17,y:H*.31,w:W*.69,h:H*.49};
  return <AbsoluteFill style={{background:'#e3e9d8'}}>
    <div style={{position:'absolute',left:wide?0:W*.04,top:H*.15,width:W*(wide?.40:.11),height:H*.65,background:'#cad5bd'}}/>
    <svg width={W} height={H} style={{position:'absolute'}}>
      {[0,1,2,3,4].map(i=><g key={i} transform={`translate(${W*.06+i*W*.018},${H*.45+i*H*.055}) rotate(${-25+i*9})`} opacity=".55"><path d={`M0,0 Q${W*.10},${-H*.06} ${W*.14},${-H*.03} Q${W*.12},${H*.025} 0,0`} fill="none" stroke="#6f805c" strokeWidth={m.unit*1.8}/><path d={`M0,0 L${W*.14},${-H*.03}`} stroke="#6f805c" strokeWidth={m.unit}/></g>)}
    </svg>
    <div style={{position:'absolute',left:pic.x-W*.02,top:pic.y-H*.012,width:pic.w+W*.04,height:pic.h+H*.024,background:'#f4f5e9',transform:'rotate(-1.5deg)'}}/>
    <SourceWindow props={p} box={pic} style={{border:`${m.unit*5}px solid #f5f5e9`,boxShadow:`${m.unit*11}px ${m.unit*14}px 0 #bcc8a9`}}/>
    <Rule x={pic.x-m.unit*10} y={pic.y} w={pic.h} vertical color="#66805a" thickness={m.unit*2}/>
    <Brand props={p} color="#304f37"/>
    <Rule x={a} y={H*.098} w={W-2*a} color="#839a73"/>
    <TextBlock text="社区生意 · 观察手记" x={a} y={H*.118} w={W*.8} size={m.labelSize*.83} color="#53724b" font={SERIF} weight={400}/>
    <ReadableBeat props={p} box={{x:a,y:H*(wide?.26:square?.13:.18),w:W*(wide?.34:.84),h:H*.2}} color="#244731" font={SERIF} size={wide?m.heroSize*.94:m.heroSize*.98}/>
    <Caption props={p} box={{x:a,y:H*.886,w:W-2*a,h:H*.069}} background="#f6f5e9" color="#244731" accent="#9a542b" font={SERIF} mode="rise"/>
  </AbsoluteFill>;
};

// 06: A designed ticket. Perforations and oversize indexing establish a
// compact offer format without inventing prices, terms or proof claims.
export const Style06:React.FC<LabProps>=p=>{
  const f=useCurrentFrame(),m=metrics(p),{W,H,wide,square,margin:a}=m,idx=phase(f);
  const pic=wide?{x:W*.43,y:H*.19,w:W*.50,h:H*.60}:square?{x:W*.30,y:H*.34,w:W*.61,h:H*.43}:{x:W*.12,y:H*.34,w:W*.76,h:H*.44};
  const lift=ease(f/20);
  return <AbsoluteFill style={{background:'#b76825'}}>
    <div style={{position:'absolute',left:W*.045,top:H*.027,width:W*.91,height:H*.95,background:'#f5ead6',boxShadow:`0 ${m.unit*8}px ${m.unit*28}px #44210444`,transform:`translateY(${(1-lift)*m.unit*26}px)`}}/>
    <div style={{position:'absolute',left:W*.075,right:W*.075,top:H*.15,borderTop:`${m.unit*2}px dashed #b9986c`}}/>
    {[.15,.83].map(y=><React.Fragment key={y}><div style={{position:'absolute',left:W*.025,top:H*y-m.unit*21,width:m.unit*42,height:m.unit*42,borderRadius:'50%',background:'#b76825'}}/><div style={{position:'absolute',right:W*.025,top:H*y-m.unit*21,width:m.unit*42,height:m.unit*42,borderRadius:'50%',background:'#b76825'}}/></React.Fragment>)}
    <Brand props={p} color="#5c371c" x={W*.09} y={H*.063}/>
    <TextBlock text="COMMUNITY / PARTNER" x={W*.09} y={H*.112} w={W*.8} size={m.labelSize*.65} color="#926331" font={MONO}/>
    <TextBlock text={`0${idx+1}`} x={W*.08} y={H*(wide?.23:square?.25:.315)} w={W*.25} size={m.heroSize*1.5} color="#e8d0ab" font={MONO}/>
    <SourceWindow props={p} box={pic} border={`${m.unit*2}px solid #b59065`}/>
    <ReadableBeat props={p} box={{x:W*.09,y:H*(wide?.24:square?.18:.195),w:W*(wide?.30:.83),h:H*.2}} color="#643716" size={m.heroSize*.88}/>
    <Rule x={W*.085} y={H*.83} w={W*.83} color="#b9986c" thickness={m.unit}/>
    <Rule x={W*.09} y={H*.86} w={W*.2} color="#987248" thickness={m.unit*4}/>
    <Caption props={p} box={{x:W*.08,y:H*.89,w:W*.84,h:H*.064}} background="#623615" color="#fff4dd" accent="#f8cb76" mode="stamp"/>
  </AbsoluteFill>;
};
