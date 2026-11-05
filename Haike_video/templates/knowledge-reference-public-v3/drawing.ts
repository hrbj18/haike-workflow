// Original Canvas drawing primitives, authored from visible public references.
export type C=CanvasRenderingContext2D;
import geometry from './geometry.json';
export const F={kai:'KPublicWenKai',brush:'KPublicLongCang',num:'KPublicFraunces',mono:'KPublicJetBrains'};
export const clamp=(n:number,a=0,b=1)=>Math.max(a,Math.min(b,n));
export const ease=(n:number)=>{n=clamp(n);return n*n*(3-2*n)};
export const progress=(f:number,at:number,duration:number)=>clamp((f-at)/Math.max(1,duration));
export const rnd=(n:number)=>{const x=Math.sin(n*127.1+311.7)*43758.5453123;return x-Math.floor(x)};
export const fontValue=(size:number,font=F.kai,weight=font===F.kai?500:400)=>`${weight} ${size}px "${font}"`;
export function text(c:C,s:string,x:number,y:number,size:number,color:string,font=F.kai,align:CanvasTextAlign='left',weight?:number){
 c.save();c.font=fontValue(size,font,weight);c.textAlign=align;c.textBaseline='alphabetic';c.fillStyle=color;c.fillText(s,x,y);c.restore();
}
export function line(c:C,points:number[][],color:string,width=3,p=1,seed=1){
 if(p<=0||points.length<2)return;c.save();c.strokeStyle=color;c.lineWidth=width;c.lineJoin='round';c.lineCap='round';
 const lengths=points.slice(1).map((b,i)=>Math.hypot(b[0]-points[i][0],b[1]-points[i][1]));let left=lengths.reduce((a,b)=>a+b,0)*clamp(p);
 c.beginPath();c.moveTo(...points[0] as [number,number]);
 for(let i=0;i<lengths.length&&left>0;i++){const t=Math.min(1,left/Math.max(lengths[i],.001)),a=points[i],b=points[i+1];c.lineTo(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t);left-=lengths[i]}c.stroke();
 c.globalAlpha=.14;c.lineWidth=width*.55;c.translate(rnd(seed)*1.3-.65,rnd(seed+1)*1.3-.65);c.stroke();c.restore();
}
export function curve(c:C,points:number[][],color:string,width=3,p=1){line(c,points,color,width,p)}
// Independent interpolating curve; retained anchors own the silhouette, not a
// coarse polygon. Subdivision also preserves the existing arc-length reveal.
export function smoothPoints(points:number[][],subdivisions:number):number[][]{
 if(points.length<2)return points.map(p=>[...p]);const output:number[][]=[];
 for(let i=0;i<points.length-1;i++){
  const a=points[Math.max(0,i-1)],b=points[i],d=points[i+1],e=points[Math.min(points.length-1,i+2)];
  for(let j=0;j<subdivisions;j++){const t=j/subdivisions,t2=t*t,t3=t2*t;output.push([0,1].map(k=>.5*((2*b[k])+(-a[k]+d[k])*t+(2*a[k]-5*b[k]+4*d[k]-e[k])*t2+(-a[k]+3*b[k]-3*d[k]+e[k])*t3)))}
 }output.push([...points[points.length-1]]);return output;
}
export function ellipse(c:C,x:number,y:number,rx:number,ry:number,color:string,width=3,p=1,rotation=0){
 const a=Array.from({length:121},(_,i)=>{const t=i/120*Math.PI*2;return [x+Math.cos(t)*rx*Math.cos(rotation)-Math.sin(t)*ry*Math.sin(rotation),y+Math.cos(t)*rx*Math.sin(rotation)+Math.sin(t)*ry*Math.cos(rotation)]});line(c,a,color,width,p);
}
export function arrow(c:C,points:number[][],color:string,width=3,p=1){
 line(c,points,color,width,p);if(p<.94)return;const a=points[points.length-2],b=points[points.length-1],t=Math.atan2(b[1]-a[1],b[0]-a[0]);line(c,[[b[0]-22*Math.cos(t-.48),b[1]-22*Math.sin(t-.48)],b,[b[0]-22*Math.cos(t+.48),b[1]-22*Math.sin(t+.48)]],color,width);
}
export function dashedArrow(c:C,points:number[][],color:string,width=3,p=1){
 c.save();c.setLineDash([24,16]);line(c,points,color,width,p);c.restore();if(p<.94)return;
 const a=points[points.length-2],b=points[points.length-1],t=Math.atan2(b[1]-a[1],b[0]-a[0]);
 line(c,[[b[0]-22*Math.cos(t-.48),b[1]-22*Math.sin(t-.48)],b,[b[0]-22*Math.cos(t+.48),b[1]-22*Math.sin(t+.48)]],color,width);
}
export function marker(c:C,x:number,y:number,w:number,color:string,p=1){
 c.save();c.globalAlpha=.75;c.fillStyle=color;c.beginPath();c.moveTo(x-7,y+12);c.lineTo(x+8,y-23);c.lineTo(x+w*clamp(p)+4,y-19);c.lineTo(x+w*clamp(p)-5,y+13);c.closePath();c.fill();c.globalAlpha=.2;c.fillRect(x,y-14,w*clamp(p),8);c.restore();
}
export function pen(c:C,x:number,y:number,scale=1,chalk=false){
 c.save();c.translate(x,y);c.rotate(.57);c.scale(scale,scale);
 if(chalk){c.fillStyle='#e6e4d2';c.shadowColor='#0008';c.shadowBlur=4;c.fillRect(-4,-65,11,65);c.fillStyle='#fff8';c.fillRect(-3,-65,2,64)}else{
 c.shadowColor='#17213155';c.shadowBlur=12;c.shadowOffsetX=10;c.shadowOffsetY=7;
 const g=c.createLinearGradient(-15,0,20,0);g.addColorStop(0,'#1c293d');g.addColorStop(.4,'#7e91ab');g.addColorStop(.57,'#d8deeb');g.addColorStop(1,'#233147');c.fillStyle=g;c.fillRect(-12,-135,28,78);
 const metal=c.createLinearGradient(-14,0,17,0);metal.addColorStop(0,'#5e6b7c');metal.addColorStop(.35,'#d4dfeb');metal.addColorStop(.8,'#8b9bac');metal.addColorStop(1,'#2c3a4e');c.fillStyle=metal;
 c.beginPath();c.moveTo(-12,-58);c.lineTo(16,-58);c.lineTo(10,-21);c.lineTo(0,0);c.lineTo(-9,-23);c.closePath();c.fill();c.shadowBlur=0;line(c,[[1,-48],[0,-2]],'#354257',1);ellipse(c,1,-40,2,2,'#223044',1);
 }c.restore();
}
export function write(c:C,s:string,x:number,y:number,size:number,color:string,p:number,font=F.kai,tool=false,chalk=false,weight?:number){
 if(p<=0)return;c.save();c.font=fontValue(size,font,weight);c.textBaseline='alphabetic';c.fillStyle=color;
 const chars=[...s],amount=chars.length*clamp(p),whole=Math.floor(amount),part=amount-whole;
 let at=x;for(let i=0;i<chars.length;i++){const w=c.measureText(chars[i]).width;if(i<whole)c.fillText(chars[i],at,y);else if(i===whole&&part>0){c.save();c.beginPath();c.rect(at-2,y-size-3,w*part+3,size*1.3);c.clip();c.fillText(chars[i],at,y);c.restore()}if(i<whole)at+=w}
 if(tool&&p<1)pen(c,at+(whole<chars.length?c.measureText(chars[whole]).width*part:0),y+2,chalk?.45:1.05,chalk);c.restore();
}
export function wrapped(c:C,s:string,x:number,y:number,width:number,size:number,color:string,font=F.kai,lineHeight=1.4){
 c.save();c.font=`${size}px "${font}"`;const lines:string[]=[];let value='';for(const letter of s){if(letter==='\n'||c.measureText(value+letter).width>width){lines.push(value);value=letter==='\n'?'':letter}else value+=letter}if(value)lines.push(value);lines.forEach((v,i)=>text(c,v,x,y+i*size*lineHeight,size,color,font));c.restore();return lines.length;
}
export function tape(c:C,x:number,y:number,w=170){
 c.save();c.translate(x,y);c.rotate(-.055);c.fillStyle='#9edbc5aa';c.fillRect(-w/2,-16,w,36);c.beginPath();c.rect(-w/2,-16,w,36);c.clip();c.strokeStyle='#d7f2e5aa';c.lineWidth=6;for(let i=-w;i<w;i+=17){c.beginPath();c.moveTo(i,28);c.lineTo(i+32,-24);c.stroke()}c.restore();
}
export function sticky(c:C,lines:string[],x:number,y:number,w:number,color:string,p=1){
 if(p<=0)return;c.save();c.translate(x,y+(1-ease(p))*20);c.rotate(-.025);c.globalAlpha=clamp(p*2);c.shadowColor='#14213433';c.shadowBlur=22;c.shadowOffsetY=13;
 const fill=c.createLinearGradient(0,0,w,geometry.paper.stickyHeight);fill.addColorStop(0,color);fill.addColorStop(.6,color);fill.addColorStop(1,'#fff0bb');c.fillStyle=fill;c.beginPath();c.roundRect(0,0,w,geometry.paper.stickyHeight,[0,0,55,0]);c.fill();
 // The paper casts a shadow; its tape and glyphs must not inherit an offset
 // zero-blur shadow, which produces a second displaced copy of their ink.
 c.shadowBlur=0;c.shadowOffsetX=0;c.shadowOffsetY=0;c.shadowColor='transparent';tape(c,w/2,0,260);lines.forEach((s,i)=>text(c,s,w/2,130+i*62,geometry.paper.stickyFont,'#1F2A44',F.kai,'center'));c.restore();
}
export function icon(c:C,id:string,x:number,y:number,size:number,ink:string,fill:string,p=1){
 c.save();c.translate(x,y);c.scale(size/240,size/240);c.lineWidth=5;c.lineCap='round';c.lineJoin='round';
 const path=(ps:number[][],q=p)=>line(c,ps,ink,5,q);
 if(['concept','bulb','brain'].includes(id)){
  c.fillStyle=fill;c.globalAlpha=.72*clamp((p-.9)/.1);c.beginPath();
  for(let i=0;i<=72;i++){const a=i/72*Math.PI*2,x=16+Math.cos(a)*(62+Math.sin(a*5)*2),y=-23+Math.sin(a)*(78+Math.cos(a*3)*2);if(i===0)c.moveTo(x,y);else c.lineTo(x,y)}c.fill();c.globalAlpha=1;
  const bulb=(points:number[][])=>line(c,points,ink,geometry.paper.bulbStrokeWidth,p);
  bulb(smoothPoints(geometry.paper.bulbOutline,geometry.paper.bulbCurveSubdivisions));bulb([[-37,81],[37,81]]);bulb([[-33,96],[32,96]]);
  bulb(Array.from({length:25},(_,i)=>{const a=i/24*Math.PI;return [-16+32*i/24,106+Math.sin(a)*9]}));bulb([[-17,68],[-16,4],[-7,-10],[0,4],[8,-10],[18,4],[18,68]]);
  const rays=geometry.paper.bulbRays;for(let i=0;i<rays.count;i++){const a=rays.minAngle+i/(rays.count-1)*(rays.maxAngle-rays.minAngle);bulb([[Math.sin(a)*103,-25-Math.cos(a)*118],[Math.sin(a)*129,-25-Math.cos(a)*145]])}
 }else if(['explain','chat','users'].includes(id)){
  path([[-105,-95],[64,-95],[88,-91],[98,-74],[99,6],[90,26],[65,34],[-32,34],[-83,77],[-66,33],[-96,24],[-104,7],[-105,-95]]);path([[-77,-62],[69,-60]]);path([[-77,-34],[53,-35]]);path([[-77,-8],[7,-8]]);
  c.fillStyle=fill;c.globalAlpha=clamp(p*2);c.beginPath();c.arc(124,94,38,0,Math.PI*2);c.fill();c.globalAlpha=1;ellipse(c,126,95,42,43,ink,5,p);path([[150,128],[172,154],[165,111]]);text(c,'?',126,112,49,ink,F.num,'center');
 }else if(['book','evidence','read'].includes(id)){
  c.fillStyle=fill;c.beginPath();c.moveTo(-104,-43);c.lineTo(0,-22);c.lineTo(105,-43);c.lineTo(105,59);c.lineTo(0,81);c.lineTo(-104,59);c.closePath();c.globalAlpha=clamp(p*2);c.fill();c.globalAlpha=1;path([[-104,-43],[0,-22],[105,-43],[105,59],[0,81],[-104,59],[-104,-43]]);path([[0,-22],[0,81]]);path([[-87,-14],[-22,0]]);path([[-87,17],[-22,31]]);path([[20,0],[86,-15]]);path([[20,31],[86,16]]);
 }else if(['simplify','spark','edit'].includes(id)){
  path(Array.from({length:161},(_,i)=>{const t=i/160,a=t*Math.PI*8;return [-110+t*116+Math.sin(a)*14,15+Math.cos(a)*28]}));arrow(c,[[16,15],[100,15]],ink,5,p);path([[70,6],[84,-5],[85,-24],[96,-10],[114,-11],[102,4],[106,22],[88,14],[70,19],[70,6]]);marker(c,53,56,86,fill,p);
 }else if(id==='building'){
  path([[-76,82],[-76,-100],[61,-100],[61,82],[-76,82]]);path([[-100,82],[99,82]]);for(let row=0;row<3;row++)for(let col=0;col<3;col++)path([[-52+col*38,-72+row*42],[-34+col*38,-72+row*42],[-34+col*38,-56+row*42]]);
 }else{ellipse(c,0,0,83,80,ink,5,p);path([[-39,0],[-3,35],[48,-37]])}c.restore();
}
