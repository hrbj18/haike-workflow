import React from 'react';
import {annotationIndex,clamp,illuminatedPath,mix,smooth,state,track} from './physics';
import type {Chapter,Props} from './types';

const ink='#DEDCCD',blue='#9BBACB',gold='#CFBD69',dark='#152C26';
const roughCircle=(x:number,y:number,r:number)=>Array.from({length:121},(_,i)=>{
 const a=i/120*Math.PI*2,rr=r+Math.sin(i*3.7)*.7+Math.sin(i*1.3)*.4;
 return (i?'L':'M')+(x+Math.cos(a)*rr)+','+(y+Math.sin(a)*rr)
}).join('')+'Z';
export const Label:React.FC<{x:number;y:number;children:React.ReactNode;size?:number;color?:string;anchor?:'start'|'middle'|'end'}>=({x,y,children,size=30,color=ink,anchor='middle'})=><text x={x} y={y} textAnchor={anchor} fill={color} fontSize={size} fontFamily="ChalkKai, KaiTi, serif">{children}</text>;

type ShadowGeometry={radius:number;dx:number;dy:number};
export const Moon:React.FC<{x:number;y:number;r:number;phase:number;blocked?:number;shadow?:ShadowGeometry;id?:string}>=({x,y,r,phase,blocked=0,shadow,id='moon'})=><g transform={'translate('+x+' '+y+')'} data-object={id} data-phase={phase} data-blocked={blocked}>
 <circle r={r} fill={dark}/>
 <path d={illuminatedPath(r,phase)} fill={ink}/>
 <defs><clipPath id={'disk-'+id+'-'+x+'-'+y}><circle r={r}/></clipPath></defs>
 {blocked>0&&<g clipPath={'url(#disk-'+id+'-'+x+'-'+y+')'}>
  <circle cx={shadow?.dx||0} cy={shadow?.dy||0} r={shadow?.radius||r} fill="#472E28" opacity={.94}/>
 </g>}
 <path d={roughCircle(0,0,r)} fill="none" stroke={ink} strokeWidth={1.4}/>
 <path d={roughCircle(.4,-.3,r+.6)} fill="none" stroke={ink} strokeWidth={.6} opacity={.5}/>
</g>;

const Sun:React.FC<{x:number;y:number;r?:number}>=({x,y,r=35})=><g data-object="source">
 <circle cx={x} cy={y} r={r} fill={gold} opacity={.9}/>
 {Array.from({length:16},(_,i)=>{const a=i/16*6.283;return <line key={i} x1={x+Math.cos(a)*(r+8)} y1={y+Math.sin(a)*(r+8)} x2={x+Math.cos(a)*(r+17)} y2={y+Math.sin(a)*(r+17)} stroke={gold} strokeWidth={1.4}/>})}
</g>;
const Earth:React.FC<{x:number;y:number;r?:number}>=({x,y,r=35})=><g transform={'translate('+x+' '+y+')'} data-object="occluder">
 <circle r={r} fill="#456F83" stroke="#8FAEB8" strokeWidth={1.5}/>
 <path d={'M '+(-r*.6)+' '+(-r*.7)+' L '+(-r*.05)+' '+(-r*.92)+' L '+(r*.22)+' '+(-r*.3)+' L '+(r*.02)+' '+(r*.01)+' L '+(r*.34)+' '+(r*.75)+' L '+(-r*.24)+' '+(r*.48)+' Z'} fill="#A5B7A4"/>
</g>;

export const Rays:React.FC<{t:number;x0:number;x1:number;cy:number;span:number;opacity?:number}>=({t,x0,x1,cy,span,opacity=1})=><g opacity={opacity} data-object="rays">
 {Array.from({length:9},(_,i)=>{const y=cy+(i-4)*span/8,pos=((t*.22+i*.107)%1+1)%1,x=mix(x0,x1,pos);return <g key={i}>
  <line x1={x0} x2={x1} y1={y} y2={y} stroke={gold} opacity={.3} strokeWidth={1.2}/>
  <path d={'M'+(x-8)+','+(y-4)+' L'+x+','+y+' L'+(x-8)+','+(y+4)} stroke={gold} fill="none" opacity={.8}/>
 </g>})}
</g>;

export const Orbit:React.FC<{p:Props;t:number;tilted?:boolean;mini?:boolean;hideBody?:boolean}>=({p,t,tilted=false,mini=false,hideBody=false})=>{
 const phase=track(p.phaseKeys,t),node=track(p.nodeKeys,t),s=state(p.model,phase,node);
 const cx=555,cy=300,r=205,k=tilted?.29+.09*Math.cos(node):1,rotation=tilted?-.32*Math.sin(node):0;
 const localX=-Math.cos(phase)*r,localY=Math.sin(phase)*r*k;
 const mx=cx+localX*Math.cos(rotation)-localY*Math.sin(rotation),my=cy+localX*Math.sin(rotation)+localY*Math.cos(rotation);
 const entry=t<p.chapters[0].end?smooth((t-.5)/.9):1;
 return <g data-system="orbit">
  <Rays t={t} x0={145} x1={910} cy={cy} span={260} opacity={.7}/>
  <Sun x={90} y={cy}/>
  {tilted&&<ellipse cx={cx} cy={cy} rx={r} ry={r*.29} fill="none" stroke={gold} opacity={.7} strokeWidth={1.6}/>}
  <ellipse cx={cx} cy={cy} rx={r} ry={r*k} transform={tilted?'rotate('+(rotation*180/Math.PI)+' '+cx+' '+cy+')':undefined} fill="none" stroke={ink} strokeWidth={2} pathLength={1} strokeDasharray={entry+' 1'} opacity={.8}/>
  <Earth x={cx} y={cy}/>
  <path d={'M'+cx+','+cy+' L'+mx+','+my} stroke={blue} strokeWidth={2} fill="none"/>
  {!hideBody&&<Moon x={mx} y={my} r={25} phase={3*Math.PI/2} blocked={s.blocked} shadow={{radius:s.shadowRadius/p.model.bodyRadius*25,dx:-s.y/p.model.bodyRadius*25,dy:-s.z/p.model.bodyRadius*25}} id="same-body"/>}
  {tilted&&<line x1={mx} y1={my} x2={mx} y2={cy+(localX)*Math.sin(rotation)} stroke={blue} strokeDasharray="5 7"/>}
  {!mini&&<><Label x={90} y={530} size={28} color={gold}>光源方向固定</Label><Label x={cx} y={565} size={27}>同一个对象 · 连续运动</Label></>}
 </g>;
};

export const Shadow:React.FC<{p:Props;t:number;small?:boolean;comparison?:boolean}>=({p,t,small=false,comparison=false})=>{
 const phase=track(comparison&&p.comparisonPhaseKeys?p.comparisonPhaseKeys:p.phaseKeys,t),node=comparison?0:track(p.nodeKeys,t),s=state(p.model,phase,node);
 const scale=3.5,mx=410+s.x*scale,my=300+s.y*scale+s.z*scale;
 return <g data-system="shadow">
  <Rays t={t} x0={150} x1={940} cy={300} span={250}/>
  <Sun x={95} y={300}/>
  <path d="M410 248 L950 268 L950 332 L410 352Z" fill="#061B18" opacity={.8} stroke={ink} strokeWidth={1.4}/>
  <Earth x={410} y={300} r={52}/>
  <Moon x={mx} y={my} r={15} phase={3*Math.PI/2} blocked={s.blocked} shadow={{radius:s.shadowRadius/p.model.bodyRadius*15,dx:-s.y/p.model.bodyRadius*15,dy:-s.z/p.model.bodyRadius*15}} id="same-body-shadow"/>
  {!small&&<><Label x={740} y={190} size={32}>同一对象进入遮挡区域</Label><Label x={720} y={450} color={gold} size={33}>{'本影遮挡 '+Math.round(s.blocked*100)+'%'}</Label>
  <Label x={510} y={545} color={blue} size={26}>图示位置适度放大 · 遮挡由同一物理模型计算</Label></>}
 </g>;
};

const PhaseResult:React.FC<{p:Props;t:number;x:number;y:number;r:number;eclipse?:boolean;label?:string;comparison?:boolean}>=({p,t,x,y,r,eclipse=false,label,comparison=false})=>{
 const phase=track(comparison&&p.comparisonPhaseKeys?p.comparisonPhaseKeys:p.phaseKeys,t),node=comparison?0:track(p.nodeKeys,t);
 const s=state(p.model,phase,node);
 return <g data-system="observation">
  <Label x={x} y={y-r-46} color={eclipse?gold:blue} size={32}>{label||(eclipse?'光路与遮挡':'观察到的同一个对象')}</Label>
  <Moon x={x} y={y} r={r} phase={eclipse?Math.PI:phase} blocked={eclipse?s.blocked:0} shadow={{radius:s.shadowRadius/p.model.bodyRadius*r,dx:-s.y/p.model.bodyRadius*r,dy:-s.z/p.model.bodyRadius*r}}/>
  <Label x={x} y={y+r+55} color={eclipse?gold:blue} size={34}>{eclipse?'本影遮挡 '+Math.round(s.blocked*100)+'%':'可见亮面 '+Math.round(s.lit*100)+'%'}</Label>
 </g>;
};

export const Surface:React.FC<{p:Props;t:number;c:Chapter}>=({p,t,c})=>{
 const window=p.surfaceWindows?.find(w=>w.chapter_id===c.id);
 const exitStart=Math.max(c.start+4.5,c.end-5.5);
 const enter=window?.enter??[c.start,c.start+2.2],exit=window?.exit??[exitStart,Math.min(c.end-.4,exitStart+1.55)];
 const zoom=smooth((t-enter[0])/(enter[1]-enter[0]))*(1-smooth((t-exit[0])/(exit[1]-exit[0])));
 const phase=track(p.phaseKeys,t),s=state(p.model,phase,track(p.nodeKeys,t));
 const mx=555-Math.cos(phase)*205,my=300+Math.sin(phase)*205;
 const scope=p.captions.filter(v=>v.start>=c.start&&v.end<=c.end);
 const observation=smooth((t-(scope[2]?.start??c.start+12))/.7);
 return <g>
  <g transform={'translate('+(zoom*40)+' '+(zoom*430)+') scale('+(1-.78*zoom)+')'} opacity={1-.2*zoom}><Orbit p={p} t={t} mini hideBody/></g>
  <g opacity={zoom}><Rays t={t} x0={160} x1={660} cy={280} span={340}/><Sun x={88} y={280}/>
  <Label x={565} y={40} size={35}>取出同一对象放大</Label>
  <Label x={400} y={560} color={gold} size={31}>始终只有朝向光源的一半受光</Label>
  <path d="M430 390L840 495M430 180L840 495" stroke={blue} strokeWidth={1.4} opacity={observation*.8}/>
  <Moon x={842} y={495} r={46} phase={phase}/><Label x={845} y={585} color={blue} size={24}>{Math.round(s.lit*100)+'% 可见'}</Label></g>
  <Moon x={mix(mx,570,zoom)} y={mix(my,280,zoom)} r={mix(25,185,zoom)} phase={3*Math.PI/2} id="same-body-enlarged"/>
 </g>;
};

export const BoardScene:React.FC<{p:Props;t:number;c:Chapter}>=({p,t,c})=>{
 const tall=p.height/p.width>1.5,H=tall?1920:1350;
 const local=t-c.start,cap=p.captions.find(v=>t>=v.start&&t<v.end);
 const annotation=annotationIndex(p.captions,c.start,c.end,t);
 const explanation=annotation.index<0?'':c.annotation[Math.min(annotation.index,c.annotation.length-1)]||'';
 const writing=clamp((t-annotation.at)/.7),lineWidth=explanation.length*31,lineX=540-lineWidth/2;
 const comparing=c.kind==='compare'||c.kind==='recap',shadow=c.kind==='shadow';
 const phase=track(p.phaseKeys,t),s=state(p.model,phase,track(p.nodeKeys,t));
 return <svg width="100%" height="100%" viewBox={'0 0 1080 '+H} data-chapter={c.id}>
 <defs><radialGradient id="board"><stop stopColor="#18382E"/><stop offset="1" stopColor="#071A15"/></radialGradient>
 <pattern id="dust" width="71" height="67" patternUnits="userSpaceOnUse"><circle cx="7" cy="4" r=".7" fill="#B5C4AB" opacity=".14"/><path d="M10 49h37M23 16h18" stroke="#A8C3AA" strokeWidth=".6" opacity=".08"/></pattern></defs>
 <rect width="1080" height={H} fill="url(#board)"/><rect width="1080" height={H} fill="url(#dust)"/>
 {Array.from({length:9},(_,i)=><path key={i} d={'M-150 '+(H*.45+i*9)+' Q 500 '+(H*.06+i*13)+' 1200 '+(H*.6+i*4)} stroke="#D5E3CA" strokeWidth="2" fill="none" opacity={.018}/>)}
 <rect x="14" y="14" width="1052" height={H-28} rx="2" fill="none" stroke="#797F6F" strokeWidth="9"/>
 <Label x={72} y={tall?142:125} anchor="start" size={54}>{c.title}</Label>
 <Label x={72} y={tall?197:178} anchor="start" size={25} color={blue}>{p.title}</Label>
 <Label x={1000} y={70} anchor="end" size={23} color="#A2B3A3">{p.brand}</Label>
 <Label x={1000} y={tall?247:228} anchor="end" size={24} color="#A2B3A3">{String(p.chapters.indexOf(c)+1).padStart(2,'0')+' / '+String(p.chapters.length).padStart(2,'0')}</Label>
 <g>
 {comparing?<g>
  <PhaseResult p={p} t={t} x={tall?720:292} y={tall?570:555} r={tall?190:176} label="月相 · 观察角度改变"/>
  <PhaseResult p={p} t={t} x={tall?720:788} y={tall?1270:555} r={tall?190:176} eclipse comparison label="月食 · 光路受到遮挡"/>
  <g transform={tall?'translate(20 420) scale(.5)':'translate(55 825) scale(.46)'}><Orbit p={p} t={t} mini/></g>
  <g transform={tall?'translate(20 1120) scale(.5)':'translate(565 825) scale(.46)'}><Shadow p={p} t={t} small comparison/></g>
  {!tall&&<line x1="540" y1="340" x2="540" y2="1100" stroke={ink} opacity={.4}/>}
 </g>:<g>
  <g transform={'translate(60 '+(tall?340:255)+') scale('+(tall?.96:.86)+')'}>
   {c.kind==='surface'?<Surface p={p} t={t} c={c}/>:shadow?<Shadow p={p} t={t}/>:<Orbit p={p} t={t} tilted={c.kind==='tilt'}/>}
  </g>
  <PhaseResult p={p} t={t} x={tall?540:785} y={tall?1330:995} r={tall?235:137} eclipse={shadow}/>
  {!tall&&<><Label x={280} y={960} size={33} color={gold}>{c.kind==='tilt'?'轨道条件':'同一模型，两个视角'}</Label>
  <Label x={280} y={1012} size={27} color={blue}>{shadow?'亮面未变，光路被挡':c.kind==='tilt'?'满月附近 + 进入本影':c.kind==='surface'?'受光半球一直存在':'对象连续，观察角度改变'}</Label></>}
  {tall&&<Label x={540} y={1715} color={gold} size={34}>{c.kind==='tilt'?'只有同时满足条件，才会发生遮挡':shadow?'变暗来自光路遮挡':'亮面与位置来自同一个模型'}</Label>}
 </g>}
 </g>
 {explanation&&<g data-event="sentence-linked-chalk-note" data-at={annotation.at}>
  <defs><clipPath id="annotation-write"><rect x={lineX-8} y={(tall?302:258)-40} width={lineWidth*writing+16} height="55"/></clipPath></defs>
  <g clipPath="url(#annotation-write)"><Label x={540} y={tall?302:258} color={gold} size={31}>{explanation}</Label></g>
  {writing>0&&writing<1&&<g transform={'translate('+(lineX+lineWidth*writing)+' '+((tall?302:258)-8)+') rotate(35)'}>
   <path d="M0 0L-5-11L-5-50L5-50L5-11Z" fill={ink}/><path d="M-5-11L0 0L5-11Z" fill={gold}/>
  </g>}
 </g>}
 <foreignObject x="70" y={H-(tall?170:163)} width="940" height={tall?130:130}>
  <div xmlns="http://www.w3.org/1999/xhtml" style={{color:ink,fontFamily:'ChalkKai,KaiTi,serif',fontSize:tall?40:35,lineHeight:1.4,textAlign:'center',textShadow:'0 2px 2px #071A15',whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>
   {cap?.text||''}
  </div>
 </foreignObject>
 <rect x="19" y={H-31} width="1042" height="12" fill="#666C5A"/>
 <path d={'M75 '+(H-35)+'h70M170 '+(H-35)+'h34M230 '+(H-35)+'h40'} stroke={ink} strokeWidth="7"/>
 <Label x={1010} y={H-52} anchor="end" size={17} color="#9BA99A">{p.note}</Label>
 </svg>;
};
