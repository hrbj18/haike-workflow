// Independent geometry driven by the public source clock, never a scene reset.
export type Key = [number, number];
export type Model = {orbitRadius:number;bodyRadius:number;occluderRadius:number;sourceRadius:number;sourceDistance:number;inclinationDegrees:number;displayInclinationDegrees:number};
export const clamp=(n:number,a=0,b=1)=>Math.max(a,Math.min(b,n));
export const smooth=(n:number)=>{const t=clamp(n);return t*t*(3-2*t)};
export const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
export function annotationIndex(captions:{start:number;end:number}[],start:number,end:number,t:number) {
  const rows=captions.filter(c=>c.start>=start&&c.end<=end);
  let index=-1;
  rows.forEach((c,i)=>{if(c.start<=t)index=i});
  return {index,at:index>=0?rows[index].start:Infinity};
}
export function track(keys:Key[],t:number):number {
  if(t<=keys[0][0])return keys[0][1];
  if(t>=keys[keys.length-1][0])return keys[keys.length-1][1];
  const h=keys.slice(1).map((k,i)=>k[0]-keys[i][0]);
  const d=h.map((v,i)=>(keys[i+1][1]-keys[i][1])/v);
  const m=d.map((v,i)=>i===0?v:(v*d[i-1]<=0?0:(3*(h[i]+h[i-1]))/((2*h[i]+h[i-1])/d[i-1]+(h[i]+2*h[i-1])/v)));
  m.push(d[d.length-1]);
  const i=keys.findIndex((k,j)=>j<keys.length-1&&t<keys[j+1][0]);
  const x=(t-keys[i][0])/h[i],x2=x*x,x3=x2*x;
  return (2*x3-3*x2+1)*keys[i][1]+(x3-2*x2+x)*h[i]*m[i]+(-2*x3+3*x2)*keys[i+1][1]+(x3-x2)*h[i]*m[i+1];
}
export function overlap(r:number,R:number,d:number) {
  if(d>=r+R)return 0;
  if(d<=Math.abs(r-R))return Math.PI*Math.min(r,R)**2;
  return r*r*Math.acos(clamp((d*d+r*r-R*R)/(2*d*r),-1,1))+R*R*Math.acos(clamp((d*d+R*R-r*r)/(2*d*R),-1,1))-.5*Math.sqrt(Math.max(0,(-d+r+R)*(d+r-R)*(d-r+R)*(d+r+R)));
}
export function state(model:Model,phase:number,node:number) {
  const x=-model.orbitRadius*Math.cos(phase);
  const y=model.orbitRadius*Math.sin(phase);
  const z=model.orbitRadius*Math.sin(model.inclinationDegrees*Math.PI/180)*Math.sin(phase-node);
  const shadowRadius=Math.max(0,model.occluderRadius-x*(model.sourceRadius-model.occluderRadius)/model.sourceDistance);
  const blocked=x>0?overlap(model.bodyRadius,shadowRadius,Math.hypot(y,z))/(Math.PI*model.bodyRadius**2):0;
  return {x,y,z,lit:(1-Math.cos(phase))/2,blocked:clamp(blocked),shadowRadius};
}
export function illuminatedPath(radius:number,phase:number) {
  const waxing=Math.sin(phase)>=0,points:string[]=[];
  for(let i=0;i<=80;i++){
    const y=-radius+i/80*2*radius,x=Math.sqrt(Math.max(0,radius*radius-y*y));
    points.push((waxing?x:-x)+','+y);
  }
  for(let i=80;i>=0;i--){
    const y=-radius+i/80*2*radius,x=Math.sqrt(Math.max(0,radius*radius-y*y))*Math.cos(phase);
    points.push((waxing?x:-x)+','+y);
  }
  return 'M'+points.join('L')+'Z';
}
