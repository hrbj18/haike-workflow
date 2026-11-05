import {clamp,ease,progress} from './drawing';
import type {OrbitModel,RayModel,Scene} from './types';
import geometry from './geometry.json';
export const phaseState=(phase:number,inclination:number)=>{const a=phase*Math.PI/180,k=inclination*Math.PI/180;const moon=[Math.cos(a),Math.sin(a)*Math.cos(k),Math.sin(a)*Math.sin(k)];return {moon,lit:(1+moon[0])/2,height:moon[2]}};
export function circleOverlap(r:number,R:number,d:number){
 if(d>=r+R)return 0;if(d<=Math.abs(r-R))return Math.PI*Math.min(r,R)**2;
 return r*r*Math.acos(clamp((d*d+r*r-R*R)/(2*d*r),-1,1))+R*R*Math.acos(clamp((d*d+R*R-r*r)/(2*d*R),-1,1))-.5*Math.sqrt(Math.max(0,(-d+r+R)*(d+r-R)*(d-r+R)*(d+r+R)));
}
export function projectedPoint(moon:number[],radius:number,view:'top'|'side',rotation=0):number[]{
 if(view==='top')return [moon[0]*radius,-moon[1]*radius];
 const pitch=82*Math.PI/180,a=rotation*Math.PI/180,x=moon[0]*radius,y=-(moon[1]*Math.cos(pitch)+moon[2]*Math.sin(pitch))*radius;
 return [x*Math.cos(a)-y*Math.sin(a),x*Math.sin(a)+y*Math.cos(a)];
}
export function orbitState(m:OrbitModel,time:number){
 const state=phaseState(m.phase+time*m.phaseSpeed,m.inclination),r=m.bodyRadius,R=m.occluderRadius||0;
 const distance=Math.hypot(state.moon[1]*m.orbitRadius-(m.shadowOffset||0),state.moon[2]*m.orbitRadius);
 const behind=state.moon[0]>0,overlap=R>0&&behind?circleOverlap(r,R,distance)/(Math.PI*r*r):0;
 return {...state,distance,overlap,conditions:[state.moon[0]>.9,Math.abs(state.height*m.orbitRadius)<r+R,behind&&overlap>0]};
}
export function sectionState(body:number,shadow:number,offset:number){return {offset,overlap:circleOverlap(body,shadow,Math.abs(offset))/(Math.PI*body*body)}}
export function raySegments(m:RayModel){
 return Array.from({length:m.count},(_,i)=>{const y=m.firstY+i*m.gap;let end=m.endX,hitId:string|null=null;
  for(const b of m.blockers){const dy=y-b.y;if(Math.abs(dy)>b.radius)continue;const dx=Math.sqrt(Math.max(0,b.radius*b.radius-dy*dy)),near=b.x-dx,far=b.x+dx;if(far<m.startX)continue;const hit=Math.max(m.startX,near);if(hit<=end){end=hit;hitId=b.id}}
  return {start:[m.startX,y],end:[end,y],hitId};
 });
}
export function inspectProgress(s:Scene,f:number){const e=s.events.find(v=>v.kind==='inspect');return e?ease(progress(f,e.at,e.duration)):0}
export function surfaceCamera(moon:number[],radius:number,p:number){const g=geometry.science,target=g.surface;return {x:moon[0]+(target.center[0]-moon[0])*p,y:moon[1]+(target.center[1]-moon[1])*p,radius:radius+(target.radius-radius)*p,miniScale:1+(target.miniScale-1)*p,miniX:(target.miniEarth[0]-g.center[0]*target.miniScale)*p,miniY:(target.miniEarth[1]-g.center[1]*target.miniScale)*p}}
