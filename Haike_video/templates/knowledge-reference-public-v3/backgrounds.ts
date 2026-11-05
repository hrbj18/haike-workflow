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
  const material=geometry.chalkMaterial;
  d.fillStyle=material.middleColor;d.fillRect(0,0,w,h);const shade=d.createRadialGradient(w*.42,h*.42,0,w*.5,h*.45,w*1.05);shade.addColorStop(0,material.centerColor);shade.addColorStop(.65,material.middleColor);shade.addColorStop(1,material.edgeColor);d.fillStyle=shade;d.fillRect(0,0,w,h);
  // Fine overlapping erase threads, independently authored. No reference raster
  // or prescribed original dust coordinates; broad bands are not the texture.
  d.strokeStyle='#a6b8a4';d.lineCap='round';
  for(let band=0;band<material.wipeBands;band++){
   const cx=(.04+rnd(band+32)*.86)*w,cy=(-.08+rnd(band+90)*.72)*h,len=450+rnd(band+74)*950,drift=(rnd(band+63)-.5)*180;
   for(let stripe=0;stripe<material.wipeThreads;stripe++){
    d.globalAlpha=.012+rnd(band*131+stripe)*.026;d.lineWidth=.6+rnd(stripe+17)*1.25;d.beginPath();
    for(let n=0;n<=96;n++){const t=n/96,x=cx+(stripe-material.wipeThreads/2)*2.3+Math.sin(t*Math.PI)*drift+Math.sin(t*9+stripe*.13)*1.4,y=cy+t*len;if(n===0)d.moveTo(x,y);else d.lineTo(x,y)}d.stroke();
   }
  }
  for(let wipe=0;wipe<material.arcBands;wipe++){
   const cx=(.1+rnd(wipe+5)*.78)*w,cy=(.02+rnd(wipe+57)*.86)*h,r=115+rnd(wipe+24)*220;
   for(let stripe=0;stripe<material.arcThreads;stripe++){d.globalAlpha=.01+rnd(stripe+wipe*117)*.022;d.lineWidth=.65+rnd(stripe+41)*1.25;d.beginPath();d.ellipse(cx,cy,r+stripe*1.8,r*.72+stripe*1.5,-.12,Math.PI*(.8+rnd(wipe)*.25),Math.PI*(1.55+rnd(wipe+1)*.4));d.stroke()}
  }
  for(let i=0;i<material.horizontalThreads;i++){d.globalAlpha=.012+rnd(i+77)*.028;d.lineWidth=.6+rnd(i+9)*1.4;d.beginPath();const x=(rnd(i+44)-.08)*w,y=rnd(i+23)*h,len=110+rnd(i+62)*350;d.moveTo(x,y);d.bezierCurveTo(x+len*.3,y-7,x+len*.7,y+9,x+len,y+3);d.stroke()}
  d.globalAlpha=1;
  // Shared deterministic luminance grain at real pixel scale, rather than
  // sparse subpixel dots that disappear after Canvas antialiasing.
  const pixels=d.getImageData(0,0,w,h);let grain=material.grainSeed;
  for(let i=0;i<pixels.data.length;i+=4){grain^=grain<<13;grain^=grain>>>17;grain^=grain<<5;const noise=((grain>>>0)/4294967295-.5)*material.grainAmplitude*2;for(let channel=0;channel<3;channel++)pixels.data[i+channel]=Math.max(0,Math.min(255,pixels.data[i+channel]+noise))}d.putImageData(pixels,0,0);
  const frame=d.createLinearGradient(0,0,15,0);frame.addColorStop(0,'#879083');frame.addColorStop(.2,'#303e34');frame.addColorStop(.7,'#3b4b3f');frame.addColorStop(1,'#101912');d.fillStyle=frame;d.fillRect(0,0,10,h);d.fillRect(w-10,0,10,h);
  const top=d.createLinearGradient(0,0,0,24);top.addColorStop(0,'#747d73');top.addColorStop(.65,'#515e52');top.addColorStop(1,'#1c2a22');d.fillStyle=top;d.fillRect(0,0,w,24);
  const tray=d.createLinearGradient(0,h-65,0,h);tray.addColorStop(0,'#233329');tray.addColorStop(.12,'#808d7d');tray.addColorStop(.55,'#697466');tray.addColorStop(1,'#303e34');d.fillStyle=tray;d.fillRect(0,h-65,w,65);
  for(let i=0;i<6500;i++){d.globalAlpha=rnd(i)*.22;d.fillStyle='#eee9d5';d.fillRect(rnd(i+5)*w,h-54+rnd(i+8)*43,1+rnd(i+1)*2,1)}d.globalAlpha=1;
  ['#e9e6d0','#e1c967','#65a3ba','#eee9d5'].forEach((v,i)=>{d.save();d.translate(i===3?w*.61:w*.15+i*38,h-30);d.rotate(-.08+i*.06);d.shadowBlur=4;d.shadowColor='#0008';d.fillStyle=v;d.fillRect(-14,-7,i===3?13:30,17);d.restore()});cache.set(key,image);
 }c.drawImage(image,0,0);
}
