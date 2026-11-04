import type {Scene} from './types';
import {C,F,arrow,clamp,ellipse,icon,line,progress,text,write} from './drawing';
const white='#e5e3d1',blue='#83b8cf',yellow='#d8c56f',green='#82b2a1';
export const phaseState=(phase:number,inclination:number)=>{const a=phase*Math.PI/180,k=inclination*Math.PI/180;const moon=[Math.cos(a),Math.sin(a)*Math.cos(k),Math.sin(a)*Math.sin(k)];return {moon,lit:(1+moon[0])/2,height:moon[2]}};
export function circleOverlap(r:number,R:number,d:number){if(d>=r+R)return 0;if(d<=Math.abs(r-R))return Math.PI*Math.min(r,R)**2;return r*r*Math.acos((d*d+r*r-R*R)/(2*d*r))+R*R*Math.acos((d*d+R*R-r*r)/(2*d*R))-.5*Math.sqrt((-d+r+R)*(d+r-R)*(d-r+R)*(d+r+R))}
function disk(c:C,x:number,y:number,r:number,lit:number,p=1){
 c.save();c.globalAlpha=clamp(p*2);c.fillStyle='#14291f';c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();const k=2*clamp(lit)-1;
 c.fillStyle=white;c.beginPath();c.moveTo(x,y-r);c.arc(x,y,r,-Math.PI/2,Math.PI/2,false);c.ellipse(x,y,Math.abs(k)*r,r,0,Math.PI/2,-Math.PI/2,k<0);c.closePath();c.fill();c.globalAlpha=1;
 ellipse(c,x,y,r,r,'#d9dfcf',2,p);for(let n=0;n<2;n++)ellipse(c,x+.8*n,y-.7*n,r+1.4*n,r-.7*n,'#cdd6c25f',.7,p);c.restore();
}
function model(c:C,s:Scene,f:number){
 const m=s.model!;const time=(f-s.from)/60;const state=phaseState(m.phase+time*18,m.inclination),p=state.moon;const cx=600,cy=660,rx=m.orbitRadius*100,ry=rx*Math.cos(m.inclination*Math.PI/180),mx=cx+p[0]*rx,my=cy-p[1]*rx;
 const start=s.events.find(e=>e.kind==='diagram');const q=start?progress(f,start.at,start.duration):1;
 const light=(x:number,y:number,color:string,r:number)=>{c.fillStyle=color;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();ellipse(c,x,y,r,r,color,1,q)};
 const family=s.family.split('.').pop();
 if(family==='ray-topology'){
  const bodies=[{x:465,y:640,r:m.bodyRadius*192},{x:675,y:738,r:m.occluderRadius*132}];let reachable=0;
  for(let i=0;i<7;i++){const y=540+i*44;const hits=bodies.filter(b=>Math.abs(y-b.y)<b.r).map(b=>b.x-Math.sqrt(b.r**2-(y-b.y)**2));const stop=Math.min(890,...hits);if(stop===890)reachable++;arrow(c,[[190,y],[stop,y]],yellow,1.1,q)}
  bodies.forEach((b,i)=>{light(b.x,b.y,'#385e54',b.r);text(c,String(i+1),b.x,b.y+8,24,white,F.kai,'center')});
  text(c,`可达光路 ${reachable} / 7`,635,1390,28,blue,F.kai,'center');return;
 }
 text(c,family==='projection-compare'?'俯视投影':'同一对象的连续状态',600,440,24,white,F.kai,'center');
 light(340,cy,yellow,m.sunRadius*100);light(cx,cy,'#46829a',31);ellipse(c,cx,cy,rx,ry,white,1,q);disk(c,mx,my,m.bodyRadius*100,.5,q);line(c,[[cx,cy],[mx,my]],blue,1,q);
 text(c,'光源',340,895,22,yellow,F.kai,'center');text(c,s.items[0].label,600,895,22,blue,F.kai,'center');
 if(family==='surface-view'){
  disk(c,760,620,115,state.lit,q);for(let i=0;i<7;i++)arrow(c,[[250,530+i*24],[640,530+i*24]],yellow,1,q);
 }else if(family==='projection-compare'){
  text(c,'侧视投影',600,990,25,blue,F.kai,'center');ellipse(c,600,1200,170,20+Math.abs(state.height)*60,white,1,q);light(600,1200,'#46829a',31);light(600+p[0]*170,1200+state.height*80,white,25);return;
 }else if(family==='shadow-overlap'){
  const d=Math.abs(p[1])*110,r=m.bodyRadius*512,R=m.occluderRadius*128;disk(c,600,1180,r,1,q);c.save();c.beginPath();c.arc(600,1180,r,0,Math.PI*2);c.clip();c.globalAlpha=.8;c.fillStyle='#765044';c.beginPath();c.arc(600+d,1180,R,0,Math.PI*2);c.fill();c.restore();
  const overlap=circleOverlap(r,R,d)/(Math.PI*r*r);text(c,`遮挡圆面 ${(overlap*100).toFixed(1)} %`,600,1380,32,blue,F.kai,'center');return;
 }else if(family==='causal-compare'){
  const r=m.bodyRadius*424,R=m.occluderRadius*188;disk(c,600,1100,r,state.lit,q);disk(c,600,1430,r,1,q);c.save();c.beginPath();c.arc(600,1430,r,0,Math.PI*2);c.clip();c.globalAlpha=.7;c.fillStyle='#73514a';c.beginPath();c.arc(655,1430,R,0,Math.PI*2);c.fill();c.restore();text(c,'受光朝向 / 圆面遮挡',600,930,26,blue,F.kai,'center');return;
 }else if(family==='condition-proof'){
  const r=m.bodyRadius*100,R=m.occluderRadius*100,d=Math.hypot(p[1],p[2])*rx;
  const conditions=[p[0]>.9,Math.abs(state.height)*rx<r+R,circleOverlap(r,R,d)>0];
  ['处于光源对侧','垂向投影接近','发生圆面重叠'].forEach((v,i)=>{const ok=conditions[i];text(c,v,600,1130+i*120,27,white,F.kai,'center');text(c,ok?'成立':'未成立',600,1180+i*120,25,ok?blue:yellow,F.kai,'center')});return;
 }
 text(c,'同一对象的可见亮面',600,1010,25,blue,F.kai,'center');disk(c,600,1190,126,state.lit,q);text(c,'可见亮面比例',600,1390,24,yellow,F.kai,'center');text(c,`${(state.lit*100).toFixed(1)} %`,600,1440,36,yellow,F.kai,'center');
}
export function drawChalk(c:C,s:Scene,f:number){
 const event=(kind:string,target?:string)=>s.events.find(e=>e.kind===kind&&(target===undefined||e.target===target));
 const val=(kind:string,target?:string)=>{const e=event(kind,target);return e?progress(f,e.at,e.duration):0};
 write(c,s.title,89,301,35,white,val('heading'),F.brush,true,true);line(c,[[89,318],[1010,318]],white,.8,val('heading'));
 if(s.model){model(c,s,f);return}
 if(s.family==='compare'){
  text(c,'前态',330,341,19,'#b7c6b4');text(c,'后态',700,341,19,'#b7c6b4');
  s.items.forEach((v,i)=>{const y=565+i*590,p=val('item',v.id);write(c,v.label,90,y,29,white,p,F.brush,true,true);write(c,v.before||'',330,y,26,white,p);write(c,v.after||'',700,y,26,blue,val('answer',v.id),F.kai,true,true);line(c,[[330,y+20],[560,y+20]],white,.9,p)});
 }else if(s.family==='process'){
  const points=[[330,690],[875,690],[600,1210]];line(c,[points[0],points[1]],blue,1.3,val('connection'));line(c,[[600,690],points[2]],blue,1.3,val('connection'));
  s.items.forEach((v,i)=>{const [x,y]=points[i],p=val('item',v.id);if(p>0){c.fillStyle=white;c.beginPath();c.arc(x,y,9,0,Math.PI*2);c.fill();icon(c,v.icon||'concept',x-130,y+40,27,white,green,p)}write(c,v.label,x,y+55,27,white,p,F.brush,true,true);write(c,v.text||'',x,y+89,19,white,p);});
 }else{
  s.items.forEach((v,i)=>{const head=val('tab',v.id),p=val('item',v.id);if(head>0){text(c,`${String(i+1).padStart(2,'0')} ${v.label}`,90+i*490,354,18,white);line(c,[[90+i*490,369],[535+i*490,369]],blue,1,head)}
   const active=s.events.filter(e=>e.kind==='item'&&e.at<=f).pop()?.target===v.id;if(active){write(c,v.label,90,465,29,white,p,F.brush,true,true);write(c,v.text||'',90,510,27,white,p,F.kai,true,true);}
  });
  if(s.note)write(c,s.note,90,1515,18,'#9bad9c',val('note'));
 }
}
