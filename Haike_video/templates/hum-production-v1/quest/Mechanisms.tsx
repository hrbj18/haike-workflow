import React from 'react';
import {AbsoluteFill,Img,staticFile} from 'remotion';
import type {Props,Scene} from '../types';
import {ease,pathAt,rankPositions} from './MotionState';
import layout from './layout.json';

const blue=layout.palette.accent,red=layout.palette.bad;
const display='HaikeProductionDisplay',body='HaikeProductionBody';

export const ExtraGraphics:React.FC<{p:Props;s:Scene;portrait:boolean;frame:number}>=({p,s,portrait,frame:f})=>{
  const q=s.quest!,W=portrait?936:1210;
  if(q.kind==='versus'&&q.variant==='panel')return <div style={{marginTop:65,padding:30,background:'#07080B',borderRadius:22,color:'white',display:'flex',gap:30,position:'relative',boxShadow:'0 16px 38px #0002'}}>{q.items.map((x,i)=><div key={i} style={{flex:1,opacity:ease(f,q.cues[i],q.cues[i]+15)}}><div style={{fontSize:20,color:'#8590A7',letterSpacing:3}}>PLAYER 0{i+1}</div><div style={{fontFamily:display,fontSize:portrait?46:48,marginTop:20,color:i?'#90A9FF':'white'}}>{x}</div><div style={{height:22,background:'#29303E',marginTop:30}}><div style={{height:'100%',width:`${(i?1:1-.75*ease(f,q.cues[1]+20,q.cues[1]+50))*100}%`,background:i?blue:red}}/></div></div>)}{q.accent&&<div style={{position:'absolute',right:20,bottom:-45,padding:'8px 20px',fontFamily:display,fontSize:50,color:red,border:'5px solid',transform:'rotate(-9deg)',opacity:ease(f,q.cues[1]+50,q.cues[1]+62)}}>{q.accent}</div>}</div>;
  if(q.kind==='unlock'&&q.variant==='tree'){
    const ys=q.items.length===2?(portrait?[150,410]:[100,320]):portrait?[110,290,470]:[70,210,350],rootY=portrait?290:210;
    return <svg width={W} height={portrait?650:440} style={{marginTop:45,overflow:'visible'}}><rect x="0" y={rootY-45} width="225" height="90" rx="18" fill="#101114"/><text x="112" y={rootY+15} fontFamily={display} fontSize="44" textAnchor="middle" fill="white">{q.accent}</text>{q.items.map((x,i)=>{const t=ease(f,q.cues[i],q.cues[i]+18);return <g key={i}><path d={`M225 ${rootY}C315 ${rootY} 320 ${ys[i]} 430 ${ys[i]}`} fill="none" stroke={t>.5?blue:'#CAD2E0'} strokeWidth="4"/><rect x="430" y={ys[i]-42} width={portrait?475:650} height="84" rx="14" fill={t>.5?blue:'#ECEEF3'}/><text x="456" y={ys[i]+13} fontFamily={body} fontSize={portrait?38:40} fill={t>.5?'white':'#929BAB'}>{t>.5?'✓':'○'} {x}</text></g>;})}</svg>;
  }
  if(q.kind==='comment'){
    const c=q.comment!,typed=c.body.slice(0,Math.floor(c.body.length*Math.max(0,Math.min(1,(f-c.from)/(c.until-c.from)))));
    return <div style={{marginTop:46}}>
      <div style={{padding:portrait?36:26,width:portrait?W:W*.84,boxSizing:'border-box',borderRadius:20,background:'#fff',color:'#101114',boxShadow:'0 12px 45px #0002',opacity:ease(f,0,15)}}>
        <div style={{display:'flex',alignItems:'center',gap:20,fontSize:portrait?30:24}}><span style={{width:42,height:42,borderRadius:'50%',display:'grid',placeItems:'center',background:blue,color:'white'}}>?</span>{c.author}<span style={{marginLeft:'auto',fontSize:18,color:'#8B92A4'}}>本期自拟提问</span></div>
        <div style={{marginTop:24,padding:24,minHeight:portrait?150:75,background:'#F3F4F0',borderRadius:10,fontSize:portrait?42:34,lineHeight:1.4,whiteSpace:'pre-wrap'}}>{typed}{f<c.until+12&&Math.floor(f/12)%2===0&&<span style={{color:blue}}>▍</span>}</div>
      </div>
      <div style={{display:'flex',gap:24,marginTop:portrait?40:24,alignItems:'flex-start'}}>{(c.photoIds||[]).map((id,i)=>{
        const m=p.media.find(x=>x.id===id)!,t=ease(f,(c.proofFrom||c.until)+i*6,(c.proofFrom||c.until)+i*6+15);
        return <div key={id} style={{width:portrait?260:245,padding:10,background:'white',boxShadow:'0 10px 25px #0002',opacity:t,transform:`translateY(${(1-t)*90}px) rotate(${[-5,3,-2][i]}deg)`}}><Img src={staticFile(m.thumbnail)} style={{width:'100%',height:portrait?340:140,objectFit:'contain',background:'#F3F4F0'}}/><div style={{fontSize:portrait?24:20,paddingTop:10,color:'#101114'}}>{m.label||'本期实拍'}</div></div>;
      })}</div>
    </div>;
  }
  if(q.kind==='ranking'){
    const r=q.ranking!,slots=rankPositions(q.items.length,r.orders,f),h=portrait?94:68;
    return <div style={{marginTop:42,padding:24,background:'#17191F',color:'white',border:'2px solid #363B48',borderRadius:20}}>
      <div style={{fontSize:portrait?25:22,color:'#A9B9EE',marginBottom:22}}>{r.note}</div>
      <div style={{position:'relative',height:q.items.length*h}}>{q.items.map((label,id)=>{
        const strike=r.strikes?.find(e=>e.index===id),t=strike?ease(f,strike.at,strike.at+12):0;
        return <div key={id} data-rank-id={id} style={{position:'absolute',left:0,right:0,top:0,height:h-10,transform:`translateY(${slots[id]*h}px)`,display:'flex',alignItems:'center',gap:24,padding:'0 20px',background:'#22252D',borderRadius:10,opacity:ease(f,q.cues[id],q.cues[id]+12),boxSizing:'border-box'}}>
          <span style={{fontSize:22,color:'#80899F',width:40}}>#{Math.round(slots[id])+1}</span><span style={{fontFamily:display,fontSize:portrait?42:36,color:slots[id]<.5?'#92A9FF':'#fff',flex:1,opacity:1-t*.5}}>{label}</span>
          {r.meters&&<div style={{width:'32%',height:10,background:'#3B404D'}}><div style={{height:'100%',width:`${r.meters[id]*100}%`,background:blue}}/></div>}
          <div style={{position:'absolute',left:20,top:'50%',width:`${t*94}%`,height:4,background:red,transform:'rotate(-1deg)'}}/>
        </div>;
      })}</div>
    </div>;
  }
  if(q.kind==='radar')return <div style={{marginTop:45,position:'relative',height:portrait?800:400}}>
    <svg width={portrait?750:500} height={portrait?750:400} viewBox="0 0 500 500">
      {[.35,.65,1].map(r=><circle key={r} cx="250" cy="250" r={200*r} fill="none" stroke="#273E72" strokeWidth="2"/>)}
      <path d="M250 50V450M50 250H450" stroke="#273E72"/>
      <g transform={`rotate(${f*2.6} 250 250)`}><path d="M250 250L450 250A200 200 0 0 0 391.4 108.6Z" fill="#4675E744"/><path d="M250 250L450 250" stroke="#92A9FF" strokeWidth="3"/></g>
      {q.items.map((x,i)=><g key={i} opacity={ease(f,q.cues[i],q.cues[i]+15)}><circle cx={[150,340,280][i]} cy={[160,220,370][i]} r="7" fill="#90A9FF"/><text x={[150,340,280][i]+14} y={[160,220,370][i]+6} fill="white" fontSize="22">{x}</text></g>)}
    </svg><div style={{fontSize:portrait?30:24,color:'#92A9FF'}}>动态扫描示意 · {q.accent}</div>
  </div>;
  if(q.kind==='editor')return <div style={{marginTop:45,display:'grid',gridTemplateColumns:portrait?'1fr':'1fr 1fr',gap:25}}>
    <div style={{padding:28,background:'#181C27',borderRadius:18,color:'#90A9FF',fontSize:portrait?30:27,lineHeight:1.6,fontFamily:'monospace'}}><div style={{fontSize:20,marginBottom:18,color:'#fff'}}>编辑流程示意</div>{q.code!.map((line,i)=><div key={i} style={{opacity:ease(f,15+i*6,30+i*6)}}><span style={{color:'#59667E'}}>{i+1} </span>{line}</div>)}</div>
    <div style={{background:'#F1F3F8',border:'2px solid #DCE2EE',padding:25,borderRadius:18,position:'relative'}}>{q.items.map((x,i)=><div key={i} style={{display:'flex',gap:15,alignItems:'center',height:portrait?85:70,opacity:ease(f,q.cues[i],q.cues[i]+15)}}><span style={{width:portrait?130:105,fontSize:portrait?30:25,color:'#101114'}}>{x}</span><div style={{flex:1,height:34,background:['#1455FF','#7C67D9','#D99E47','#67B59A'][i],borderRadius:6}}/></div>)}<div style={{position:'absolute',top:20,bottom:20,left:`${25+ease(f,15,s.frames-25)*68}%`,width:3,background:red}}/></div>
  </div>;
  return null;
};

// The SVG graph remains outside per-scene Sequences. Background/title changes
// retain the graph ID, node order and the actor's accumulated route.
export const PersistentPath:React.FC<{p:Props;portrait:boolean;frame:number}>=({p,portrait,frame})=>{
  const index=p.scenes.findIndex(s=>frame>=s.from&&frame<s.from+s.frames),s=p.scenes[index];
  if(!s||s.quest?.kind!=='path')return null;
  const q=s.quest,state=pathAt(p.scenes,index,frame),dark=s.theme==='dark',W=portrait?936:1210;
  const pos=(i:number):[number,number]=>portrait?[70,330+i*528/(q.items.length-1)]:[70+i*(W-140)/(q.items.length-1),400];
  const from=pos(state.from),to=pos(state.to),arc=Math.abs(state.to-state.from)>1?state.progress*(1-state.progress):0;
  const x=from[0]+(to[0]-from[0])*state.progress-(portrait?320*arc:0),y=from[1]+(to[1]-from[1])*state.progress-(portrait?0:400*arc);
  return <div data-path-id={q.path!.id} style={{position:'absolute',left:portrait?72:100,top:portrait?210:200,width:W,height:portrait?1000:620,zIndex:8,color:dark?'white':'#101114'}}>
    <svg width={W} height={portrait?1000:620} style={{overflow:'visible'}}>
      <path d={q.items.map((_,i)=>`${i?'L':'M'}${pos(i).join(' ')}`).join(' ')} stroke={dark?'#414958':'#CBD3E3'} strokeWidth="4" strokeDasharray="5 10" fill="none"/>
      {state.legs.map((leg,i)=>{const a=pos(leg.from),b=pos(leg.to),jump=Math.abs(leg.to-leg.from)>1;
        return <path key={i} d={jump?`M${a}Q${portrait?a[0]-160:(a[0]+b[0])/2} ${portrait?(a[1]+b[1])/2:a[1]-200} ${b}`:`M${a}L${b}`} pathLength="1" stroke={blue} strokeWidth="5" strokeDasharray="1" strokeDashoffset={1-leg.progress} fill="none"/>;
      })}
      {q.items.map((label,i)=><g key={i} data-node-id={i}><circle cx={pos(i)[0]} cy={pos(i)[1]} r="30" fill={dark?'#151A25':'white'} stroke={state.visited.includes(i)?blue:dark?'#414958':'#CBD3E3'} strokeWidth="4"/><text x={pos(i)[0]} y={pos(i)[1]+9} textAnchor="middle" fill={state.visited.includes(i)?blue:dark?'white':'#101114'} fontSize="25">{String(i+1).padStart(2,'0')}</text><text x={portrait?125:pos(i)[0]} y={portrait?pos(i)[1]+14:pos(i)[1]+90} textAnchor={portrait?'start':'middle'} fill={dark?'white':'#101114'} fontFamily={body} fontSize={portrait?44:30}>{label}</text></g>)}
      <g transform={`translate(${x} ${y-70})`}><rect x="-44" y="-20" width="88" height="38" rx="12" fill={blue}/><text y="7" fill="white" textAnchor="middle" fontSize="19">YOU</text><path d="M-8 21L8 21L0 32Z" fill={blue}/></g>
    </svg><div style={{position:'absolute',left:portrait?125:0,top:portrait?960:610,width:portrait?170:W,fontFamily:display,fontSize:portrait?38:44,color:blue,overflowWrap:'break-word',whiteSpace:'pre-wrap'}}>{q.accent}</div>
  </div>;
};

export const PhotoConstellation:React.FC<{p:Props;s:Scene;portrait:boolean;frame:number}>=({p,s,portrait,frame:f})=>{
  const points=portrait?[[120,970],[790,920],[110,1240],[800,1250],[790,620]]:[[1260,170],[1780,200],[1220,500],[1770,530],[1450,70]];
  return <>{(s.quest?.photoIds||[]).map((id,i)=>{const m=p.media.find(x=>x.id===id)!,t=ease(f,15+i*5,30+i*5),[x,y]=points[i];return <div key={id} style={{position:'absolute',left:x,top:y,width:portrait?155:120,height:portrait?220:155,padding:8,background:'#fff',boxShadow:'0 10px 30px #0003',opacity:t,zIndex:2,transform:`translateY(${(1-t)*65}px) rotate(${[-8,6,-4,8,2][i]}deg)`}}><Img src={staticFile(m.thumbnail)} style={{width:'100%',height:'100%',objectFit:'contain'}}/></div>;})}</>;
};

export const SceneTransition:React.FC<{p:Props;frame:number}>=({p,frame})=>{
  const i=p.scenes.findIndex(s=>frame>=s.from&&frame<s.from+s.frames),s=p.scenes[i],next=p.scenes[i+1],kind=next?.quest?.transition;
  if(!s||!next||!kind)return null;
  const n=layout.timing.transitionFrames,f=frame-(s.from+s.frames-n);if(f<0)return null;
  const W=p.width||1080,H=p.height||1920,background=next.quest!.kind==='world'?blue:next.theme==='dark'||['boot','books','radar'].includes(next.quest!.kind)?'#101114':'#fff';
  const t=Math.min(1,(f+1)/n),cols=Math.ceil(W/60),rows=Math.ceil(H/60);
  return <AbsoluteFill style={{zIndex:10,pointerEvents:'none'}}>{kind==='iris'?<svg width={W} height={H}><circle cx={W} cy={H*.5} r={Math.hypot(W,H*.5)*ease(t,0,1)} fill={background}/></svg>:<>{Array.from({length:cols*rows},(_,j)=>{const c=j%cols,r=Math.floor(j/cols),delay=(1-c/Math.max(1,cols-1))*.48+(r%2)*.06,scale=ease(t,delay,delay+.38)*1.05;return <div key={j} style={{position:'absolute',left:c*60,top:r*60,width:60,height:60,background,transform:`scale(${scale})`}}/>;})}</>}</AbsoluteFill>;
};
