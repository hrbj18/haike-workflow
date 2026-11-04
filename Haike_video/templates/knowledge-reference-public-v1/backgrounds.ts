import {C,rnd} from './drawing';
const cache=new Map<string,HTMLCanvasElement>();
export function paper(c:C,x:number,y:number,w:number,h:number,local=false){
 c.save();c.fillStyle='#F7F2E7';c.fillRect(x,y,w,h);c.beginPath();c.rect(x,y,w,h);c.clip();
 const step=local?38:41;c.fillStyle='#B8AC94';c.globalAlpha=local?.72:.55;
 for(let j=-1;j<h/step+1;j++)for(let i=-1;i<w/step+1;i++){c.beginPath();c.arc(x+15+i*step+(rnd(i+j*81)-.5)*.5,y+13+j*step,local?1.65:1.1,0,Math.PI*2);c.fill()}
 c.globalAlpha=.07;for(let i=0;i<w*h/230;i++){const a=rnd(i*7+1),b=rnd(i*11+4);c.fillStyle=i%3?'#927f58':'#fff';c.fillRect(x+a*w,y+b*h,1+rnd(i)*2,1)}c.restore();
}
export function blackboard(c:C,w:number,h:number){
 const key=`${w}:${h}`;let image=cache.get(key);if(!image){image=document.createElement('canvas');image.width=w;image.height=h;const d=image.getContext('2d')!;
  d.fillStyle='#10221c';d.fillRect(0,0,w,h);const shade=d.createRadialGradient(w*.3,h*.4,0,w*.6,h*.4,w*.9);shade.addColorStop(0,'#1d3026');shade.addColorStop(.65,'#0e1b17');shade.addColorStop(1,'#08110e');d.fillStyle=shade;d.fillRect(0,0,w,h);
  d.strokeStyle='#b1b6a0';for(let i=0;i<175;i++){d.globalAlpha=.008+rnd(i+50)*.018;d.lineWidth=1+rnd(i+3)*4;d.beginPath();const sx=w*.46+rnd(i)*w*.2,sy=h*.08+rnd(i+8)*h*.25;d.moveTo(sx,sy);d.bezierCurveTo(w*(.05+rnd(i+15)*.4),h*.35,w*(.75+rnd(i+1)*.2),h*.55,w*(.43+rnd(i+7)*.3),h*.91);d.stroke()}
  for(let i=0;i<65;i++){d.globalAlpha=.008+rnd(i+77)*.013;d.beginPath();const x=rnd(i+44)*w,y=rnd(i+23)*h;d.moveTo(x,y);d.bezierCurveTo(x+w*.12,y-20,x+w*.35,y+28,x+w*.5,y+5);d.stroke()}
  for(let i=0;i<w*h/16;i++){d.globalAlpha=rnd(i+9)*.045;d.fillStyle=i%5?'#e5e3cd':'#000';d.fillRect(rnd(i*3)*w,rnd(i*3+1)*h,.5+rnd(i)*1.3,.5)}d.globalAlpha=1;
  const frame=d.createLinearGradient(0,0,15,0);frame.addColorStop(0,'#879083');frame.addColorStop(.2,'#303e34');frame.addColorStop(.7,'#3b4b3f');frame.addColorStop(1,'#101912');d.fillStyle=frame;d.fillRect(0,0,13,h);d.fillRect(w-13,0,13,h);d.fillStyle='#546257';d.fillRect(0,0,w,14);
  const tray=d.createLinearGradient(0,h-65,0,h);tray.addColorStop(0,'#233329');tray.addColorStop(.12,'#808d7d');tray.addColorStop(.55,'#697466');tray.addColorStop(1,'#303e34');d.fillStyle=tray;d.fillRect(0,h-65,w,65);
  for(let i=0;i<6500;i++){d.globalAlpha=rnd(i)*.22;d.fillStyle='#eee9d5';d.fillRect(rnd(i+5)*w,h-54+rnd(i+8)*43,1+rnd(i+1)*2,1)}d.globalAlpha=1;
  ['#e9e6d0','#e1c967','#65a3ba','#eee9d5'].forEach((v,i)=>{d.save();d.translate(i===3?w*.61:w*.15+i*38,h-30);d.rotate(-.08+i*.06);d.shadowBlur=4;d.shadowColor='#0008';d.fillStyle=v;d.fillRect(-14,-7,i===3?13:30,17);d.restore()});cache.set(key,image);
 }c.drawImage(image,0,0);
}
