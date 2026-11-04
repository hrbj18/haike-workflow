import {C,rnd} from './drawing';
import geometry from './geometry.json';
const cache=new Map<string,HTMLCanvasElement>();
export function paper(c:C,x:number,y:number,w:number,h:number,local=false){
 c.save();c.fillStyle='#F7F2E7';c.fillRect(x,y,w,h);c.beginPath();c.rect(x,y,w,h);c.clip();
 const step=local?geometry.paper.pageDotStep:geometry.paper.backgroundDotStep;c.fillStyle='#B8AC94';c.globalAlpha=local?.72:.55;
 for(let j=-1;j<h/step+1;j++)for(let i=-1;i<w/step+1;i++){c.beginPath();c.arc(x+15+i*step+(rnd(i+j*81)-.5)*.5,y+13+j*step,local?1.65:1.1,0,Math.PI*2);c.fill()}
 c.globalAlpha=.07;for(let i=0;i<w*h/230;i++){const a=rnd(i*7+1),b=rnd(i*11+4);c.fillStyle=i%3?'#927f58':'#fff';c.fillRect(x+a*w,y+b*h,1+rnd(i)*2,1)}c.restore();
}
export function blackboard(c:C,w:number,h:number){
 const key=`${w}:${h}`;let image=cache.get(key);if(!image){image=document.createElement('canvas');image.width=w;image.height=h;const d=image.getContext('2d')!;
  d.fillStyle='#0e1a16';d.fillRect(0,0,w,h);const shade=d.createRadialGradient(w*.3,h*.4,0,w*.6,h*.4,w*.9);shade.addColorStop(0,'#17221c');shade.addColorStop(.65,'#0e1815');shade.addColorStop(1,'#0b1411');d.fillStyle=shade;d.fillRect(0,0,w,h);
  // Independently authored erased bands: distributed short wipes, no dominant S.
  d.strokeStyle='#abb0a0';for(let band=0;band<10;band++){
   const cx=(.08+rnd(band+32)*.78)*w,cy=(.08+rnd(band+90)*.7)*h,len=260+rnd(band+74)*700;
   for(let stripe=0;stripe<17;stripe++){
    d.globalAlpha=.0025+rnd(band*31+stripe)*.006;d.lineWidth=5+rnd(stripe+17)*9;d.beginPath();
    for(let n=0;n<=48;n++){const t=n/48,x=cx+(stripe-8)*4+Math.sin(t*3.4+band)*18,y=cy+t*len;if(n===0)d.moveTo(x,y);else d.lineTo(x,y)}d.stroke();
   }
  }
  for(let wipe=0;wipe<7;wipe++){
   const cx=(.12+rnd(wipe+5)*.68)*w,cy=(.1+rnd(wipe+57)*.68)*h,r=120+rnd(wipe+24)*155;
   for(let stripe=0;stripe<18;stripe++){d.globalAlpha=.004+rnd(stripe+wipe*17)*.007;d.lineWidth=2+rnd(stripe+41)*6;d.beginPath();d.ellipse(cx,cy,r+stripe*3,r*.72+stripe*2,-.12,Math.PI*.9,Math.PI*1.94);d.stroke()}
  }
  for(let i=0;i<95;i++){d.globalAlpha=.006+rnd(i+77)*.012;d.lineWidth=2+rnd(i+9)*5;d.beginPath();const x=(rnd(i+44)-.15)*w,y=rnd(i+23)*h;d.moveTo(x,y);d.bezierCurveTo(x+w*.1,y-5,x+w*.28,y+8,x+w*.42,y+4);d.stroke()}
  for(let i=0;i<w*h/40;i++){d.globalAlpha=rnd(i+9)*.035;d.fillStyle=i%5?'#e5e3cd':'#000';d.fillRect(rnd(i*3)*w,rnd(i*3+1)*h,.5+rnd(i)*1.3,.5)}d.globalAlpha=1;
  const frame=d.createLinearGradient(0,0,15,0);frame.addColorStop(0,'#879083');frame.addColorStop(.2,'#303e34');frame.addColorStop(.7,'#3b4b3f');frame.addColorStop(1,'#101912');d.fillStyle=frame;d.fillRect(0,0,10,h);d.fillRect(w-10,0,10,h);
  const top=d.createLinearGradient(0,0,0,24);top.addColorStop(0,'#747d73');top.addColorStop(.65,'#515e52');top.addColorStop(1,'#1c2a22');d.fillStyle=top;d.fillRect(0,0,w,24);
  const tray=d.createLinearGradient(0,h-65,0,h);tray.addColorStop(0,'#233329');tray.addColorStop(.12,'#808d7d');tray.addColorStop(.55,'#697466');tray.addColorStop(1,'#303e34');d.fillStyle=tray;d.fillRect(0,h-65,w,65);
  for(let i=0;i<6500;i++){d.globalAlpha=rnd(i)*.22;d.fillStyle='#eee9d5';d.fillRect(rnd(i+5)*w,h-54+rnd(i+8)*43,1+rnd(i+1)*2,1)}d.globalAlpha=1;
  ['#e9e6d0','#e1c967','#65a3ba','#eee9d5'].forEach((v,i)=>{d.save();d.translate(i===3?w*.61:w*.15+i*38,h-30);d.rotate(-.08+i*.06);d.shadowBlur=4;d.shadowColor='#0008';d.fillStyle=v;d.fillRect(-14,-7,i===3?13:30,17);d.restore()});cache.set(key,image);
 }c.drawImage(image,0,0);
}
