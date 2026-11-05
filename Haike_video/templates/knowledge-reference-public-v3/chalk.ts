import type {OrbitModel,RayModel,Scene,SectionModel,CausalModel} from './types';
import {C,F,arrow,clamp,ellipse,icon,line,progress,text,write} from './drawing';
import {phaseState,projectedPoint,orbitState,sectionState,raySegments,inspectProgress,surfaceCamera} from './geometry';
import geometry from './geometry.json';
export {phaseState,circleOverlap} from './geometry';
const white='#e5e3d1',blue='#83b8cf',yellow='#d8c56f',green='#82b2a1',shadow='#634539';

function disk(c:C,x:number,y:number,r:number,lit:number,side=1,outline=1){
 c.save();c.translate(x,y);c.scale(side,1);c.fillStyle='#14251f';c.beginPath();c.arc(0,0,r,0,Math.PI*2);c.fill();
 const k=2*clamp(lit)-1;c.fillStyle=white;c.beginPath();c.moveTo(0,-r);c.arc(0,0,r,-Math.PI/2,Math.PI/2,false);c.ellipse(0,0,Math.abs(k)*r,r,0,Math.PI/2,-Math.PI/2,k<0);c.closePath();c.fill();
 ellipse(c,0,0,r,r,'#d9dfcf',1.6,outline);for(let n=0;n<2;n++)ellipse(c,n*.8,-n*.7,r+n*1.4,r-n*.7,'#cdd6c25f',.7,outline);c.restore();
}
function mask(c:C,x:number,y:number,r:number,sx:number,sy:number,R:number){
 c.save();c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.clip();c.fillStyle=shadow;c.globalAlpha=.9;c.beginPath();c.arc(sx,sy,R,0,Math.PI*2);c.fill();c.restore();
}
function dot(c:C,x:number,y:number,r:number,color:string){c.fillStyle=color;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill()}
function eventValue(s:Scene,f:number,kind:string){const e=s.events.find(v=>v.kind===kind);return e?progress(f,e.at,e.duration):0}
function phaseView(c:C,lit:number,blocked?:number,m?:{bodyRadius:number;occluderRadius?:number},offset=0,bodyLabel='模型球'){
 const [x,y]=geometry.science.phase.center,r=geometry.science.phase.radius;
 text(c,'镜头观察同一球面',x,955,25,blue,F.kai,'center');text(c,bodyLabel,x,984,20,white,F.kai,'center');disk(c,x,y,r,lit);
 if(blocked!==undefined&&m&&m.occluderRadius!==undefined)mask(c,x,y,r,x-offset*r/m.bodyRadius,y,m.occluderRadius*r/m.bodyRadius);
 text(c,'可见亮面比例',x,1325,24,yellow,F.kai,'center');text(c,`${(lit*100).toFixed(1)} %`,x,1365,36,yellow,F.kai,'center');
 if(blocked!==undefined){text(c,'光路遮挡比例',x,1410,22,blue,F.kai,'center');text(c,`${(blocked*100).toFixed(1)} %`,x,1448,30,blue,F.kai,'center')}
}
function system(c:C,m:OrbitModel,time:number,q:number,view:'top'|'side',caption=true,bodyLabel='遮光阻片'){
 const [cx,cy]=geometry.science.center,state=orbitState(m,time),r=m.orbitRadius*100;
 c.save();c.globalAlpha=.2;for(let i=0;i<4;i++)arrow(c,[[380,560+i*65],[820,560+i*65]],yellow,.9);c.restore();
 dot(c,340,cy,m.sunRadius*100,yellow);dot(c,cx,cy,31,'#46829a');
 const points=Array.from({length:121},(_,i)=>{const p=projectedPoint(phaseState(i*3,m.inclination).moon,r,view,m.displayInclination);return [cx+p[0],cy+p[1]]});line(c,points,white,1.5,q);
 if(view==='side')ellipse(c,cx,cy,r,40,'#c6b96460',1);
 const p=projectedPoint(state.moon,r,view,m.displayInclination),mx=cx+p[0],my=cy+p[1];disk(c,mx,my,m.bodyRadius*100,.5,-1);line(c,[[cx,cy],[mx,my]],blue,1.2);
 if(state.overlap>0)mask(c,mx,my,m.bodyRadius*100,mx-state.distance*100,my,(m.occluderRadius||0)*100);
 if(caption){text(c,'检验灯',340,895,22,yellow,F.kai,'center');text(c,bodyLabel,600,895,22,blue,F.kai,'center')}
 return {state,moon:[mx,my]};
}
function section(c:C,s:Scene,m:SectionModel,f:number){
 const time=(f-s.from)/60,inspect=inspectProgress(s,f),factor=.4+.6*inspect;
 const state=sectionState(m.bodyRadius,m.occluderRadius,m.offset+time*m.offsetSpeed),scale=geometry.science.section.worldScale*factor,[x,y]=geometry.science.section.center;
 text(c,'同一状态的遮挡截面',540,440,24,white,F.kai,'center');ellipse(c,x,y,m.occluderRadius*scale,m.occluderRadius*scale,white,1.3);
 const bx=x+state.offset*scale,r=m.bodyRadius*scale;disk(c,bx,y,r,1);mask(c,bx,y,r,x,y,m.occluderRadius*scale);
 text(c,'光路遮挡比例',540,810,25,blue,F.kai,'center');text(c,`${(state.overlap*100).toFixed(1)} %`,540,855,34,blue,F.kai,'center');
 phaseView(c,phaseState(m.phase+time*m.phaseSpeed,0).lit,state.overlap,m,state.offset,s.items[0].label);
}
function causal(c:C,s:Scene,m:CausalModel,f:number){
 const time=(f-s.from)/60,[ux,uy]=geometry.science.causal.upper,[lx,ly]=geometry.science.causal.lower,r=geometry.science.causal.radius;
 const actual=phaseState(m.phase+time*m.phaseSpeed,0).lit,counter=phaseState(m.counterPhase+time*m.counterSpeed,0).lit,state=sectionState(m.bodyRadius,m.occluderRadius,m.offset+time*m.offsetSpeed),q=Math.max(.12,eventValue(s,f,'diagram'));
 text(c,'实际模型',ux,435,25,blue,F.kai,'center');text(c,s.items[0].label,ux,470,20,white,F.kai,'center');disk(c,ux,uy,r,actual,1,q);
 text(c,'可见亮面比例',ux,805,24,yellow,F.kai,'center');text(c,`${(actual*100).toFixed(1)} %`,ux,850,36,yellow,F.kai,'center');
 text(c,'另一组明确条件',lx,955,25,blue,F.kai,'center');text(c,s.items[0].label,lx,984,20,white,F.kai,'center');disk(c,lx,ly,r,counter,1,q);
 mask(c,lx,ly,r,lx-state.offset*r/m.bodyRadius,ly,m.occluderRadius*r/m.bodyRadius);
 text(c,'可见亮面比例',lx,1325,24,yellow,F.kai,'center');text(c,`${(counter*100).toFixed(1)} %`,lx,1365,36,yellow,F.kai,'center');text(c,'光路遮挡比例',lx,1410,22,blue,F.kai,'center');text(c,`${(state.overlap*100).toFixed(1)} %`,lx,1448,30,blue,F.kai,'center');
}
function rays(c:C,s:Scene,m:RayModel,f:number){
 const paths=raySegments(m),q=eventValue(s,f,'diagram');for(const ray of paths)arrow(c,[ray.start,ray.end],yellow,1.2,q);
 m.blockers.forEach((b,i)=>{dot(c,b.x,b.y,b.radius,'#38544c');ellipse(c,b.x,b.y,b.radius,b.radius,blue,1.2);text(c,String(i+1),b.x,b.y+10,25,white,F.kai,'center');text(c,`${i+1} ${i===0?'前方':'后方'}遮板`,180,1060+i*65,22,white)});
 text(c,'检验灯',190,980,22,yellow);text(c,s.items[0].label,890,980,22,blue,F.kai,'right');text(c,`可达 ${paths.filter(p=>p.hitId===null).length} / ${m.count}`,540,1415,32,blue,F.kai,'center');
}
function model(c:C,s:Scene,f:number){
 const m=s.model!;if(m.kind==='section'){section(c,s,m,f);return}if(m.kind==='causal'){causal(c,s,m,f);return}if(m.kind==='rays'){rays(c,s,m,f);return}
 const time=(f-s.from)/60,q=eventValue(s,f,'diagram'),family=s.family.split('.').pop(),state=orbitState(m,time);
 if(family==='surface-view'){
  const moon=projectedPoint(state.moon,m.orbitRadius*100,'top'),point=[600+moon[0],660+moon[1]],p=inspectProgress(s,f),camera=surfaceCamera(point,m.bodyRadius*100,p);
  c.save();c.translate(camera.miniX,camera.miniY);c.scale(camera.miniScale,camera.miniScale);system(c,m,time,q,'top',true,s.items[0].label);c.restore();
  if(p>0){disk(c,camera.x,camera.y,camera.radius,.5,-1);c.save();c.globalAlpha=p;for(let i=0;i<7;i++){const y=camera.y-90+i*30,dy=y-camera.y;if(Math.abs(dy)<camera.radius){const end=camera.x-Math.sqrt(camera.radius**2-dy**2);arrow(c,[[260,y],[end,y]],yellow,1.2)}}c.restore()}
  text(c,p>.8?'同一对象取出放大后归位':'球体的连续运动',600,440,24,white,F.kai,'center');phaseView(c,state.lit,undefined,undefined,0,s.items[0].label);return;
 }
 if(family==='projection-compare'){
  text(c,'俯视投影',540,440,25,white,F.kai,'center');system(c,m,time,q,'top',true,s.items[0].label);
  c.save();c.translate(0,515);system(c,m,time,q,'side',true,s.items[0].label);c.restore();text(c,'侧视投影',540,960,25,blue,F.kai,'center');text(c,`高度 ${(state.height*m.orbitRadius).toFixed(3)} 模型单位`,540,1460,27,blue,F.kai,'center');return;
 }
 text(c,'球体的连续运动',600,440,24,white,F.kai,'center');system(c,m,time,q,family==='inclined-orbit'||family==='condition-proof'?'side':'top',true,s.items[0].label);
 if(family==='condition-proof'){
  ['处于对向位置','位于影带范围','发生圆面重叠'].forEach((label,i)=>{const p=eventValue(s,f,['condition-opposition','condition-plane','condition-overlap'][i]);write(c,label,465,1040+i*150,27,white,p);write(c,state.conditions[i]?'成立':'未成立',500,1100+i*150,25,state.conditions[i]?blue:yellow,p)});return;
 }
 phaseView(c,state.lit,family==='inclined-orbit'?state.overlap:undefined,m,state.distance,s.items[0].label);
 if(family==='inclined-orbit')text(c,`实际倾角 ${m.inclination.toFixed(1)}° · 示意 ${m.displayInclination.toFixed(1)}°`,540,1510,20,blue,F.kai,'center');
}
export function drawChalk(c:C,s:Scene,f:number){
 const event=(kind:string,target?:string)=>s.events.find(e=>e.kind===kind&&(target===undefined||e.target===target));
 const val=(kind:string,target?:string)=>{const e=event(kind,target);return e?progress(f,e.at,e.duration):0};
 write(c,s.title,89,300,30,white,val('heading'),F.brush,true,true,700);line(c,[[89,309],[995,309]],white,.8,val('heading'));
 if(s.model){model(c,s,f);return}
 if(s.family==='compare'){
  text(c,'前态',322,341,19,'#b7c6b4');text(c,'后态',666,341,19,'#b7c6b4');
  s.items.forEach((v,i)=>{const y=572+i*590,p=val('item',v.id);write(c,v.label,86,y,23,white,p,F.kai,true,true,700);write(c,v.before||'',322,y,21,white,p);write(c,v.after||'',666,y,21,blue,val('answer',v.id),F.kai,true,true);line(c,[[322,y+11],[497,y+11]],white,.9,p)});
 }else if(s.family==='process'){
  const points=[[330,690],[875,690],[600,1210]];line(c,[points[0],points[1]],blue,1.3,val('connection'));line(c,[[600,690],points[2]],blue,1.3,val('connection'));
  s.items.forEach((v,i)=>{const [x,y]=points[i],p=val('item',v.id);if(p>0){dot(c,x,y,9,white);icon(c,v.icon||'concept',x-130,y+40,27,white,green,p)}write(c,v.label,x,y+55,23,white,p,F.kai,true,true,700);write(c,v.text||'',x,y+89,19,white,p);});
 }else{
  s.items.forEach((v,i)=>{const head=val('tab',v.id),p=val('item',v.id);if(head>0){text(c,`${String(i+1).padStart(2,'0')} ${v.label}`,90+i*490,354,18,white);line(c,[[90+i*490,369],[535+i*490,369]],blue,1,head)}
   const active=s.events.filter(e=>e.kind==='item'&&e.at<=f).pop()?.target===v.id;if(active){write(c,v.label,90,465,23,white,p,F.kai,true,true,700);write(c,v.text||'',90,510,27,white,p,F.kai,true,true);}
  });
  if(s.note)write(c,s.note,90,1515,18,'#9bad9c',val('note'));
 }
}
