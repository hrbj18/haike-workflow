import type {Scene} from './types';
import {C,F,arrow,dashedArrow,clamp,ease,ellipse,icon,line,marker,pen,progress,sticky,tape,text,write} from './drawing';
import {paper} from './backgrounds';
import geometry from './geometry.json';
const ink='#1F2A44',mint='#8ED5BB',yellow='#F5CF66';
export function drawPaper(c:C,s:Scene,frame:number){
 const event=(kind:string,target?:string)=>s.events.find(e=>e.kind===kind&&(target===undefined||e.target===target));
 const value=(kind:string,target?:string)=>{const e=event(kind,target);return e?progress(frame,e.at,e.duration):0};
 c.save();c.fillStyle='#343d4e';c.fillRect(64,245,952,1328);c.beginPath();c.rect(64,245,952,1328);c.clip();
 const g=geometry.paper,one=s.items.length===1,layout=one?g.single:g.multiple;
 const pageWidth=one?g.single.width:s.items.length*g.multiple.widthPerItem+g.multiple.widthExtra,pageHeight=layout.height;
 const firstX=layout.firstX,fit=Math.min(952/pageWidth,1328/pageHeight);let scale=1,tx=120,ty=720;
 for(const e of s.events.filter(v=>v.kind==='camera'||v.kind==='camera-return').sort((a,b)=>a.at-b.at)){
  const i=s.items.findIndex(v=>v.id===e.target);if(frame<e.at)continue;const p=ease(progress(frame,e.at,e.duration));const nx=540-(firstX+i*g.itemSpacing)*g.focusScale;
  scale=scale+(g.focusScale-scale)*p;tx=tx+(nx-tx)*p;ty=ty+(g.focusY-ty)*p;
 }
 const full=value('overview');if(full>0){const p=ease(full);scale=scale+(fit-scale)*p;tx=tx+(64-tx)*p;ty=ty+(245+(1328-pageHeight*fit)/2-ty)*p}
 c.translate(tx,ty);c.scale(scale,scale);paper(c,0,0,pageWidth,pageHeight,true);tape(c,205,18,200);
 const firstCamera=event('camera',s.items[0].id);if(firstCamera&&frame>=s.from+9&&frame<firstCamera.at+12)pen(c,100,55,.65);
 if(full>0)write(c,s.title,layout.titleX,g.titleY,g.titleFont,ink,Math.min(1,full*1.5),F.brush);
 const intro=clamp(value('camera',s.items[0].id)*1.4);line(c,[[layout.underlineStart,g.underlineY],[layout.underlineEnd,g.underlineY-3]],ink,5,intro);
 c.save();c.translate(0,g.itemYOffset);
 for(let i=0;i<s.items.length;i++){
  const item=s.items[i],x=firstX+i*g.itemSpacing,at=value('write',item.id),hl=value('highlight',item.id),draw=value('draw',item.id),note=value('annotation',item.id);
  const labelStart=x-215;ellipse(c,x-286,294,41,43,ink,5,at);
  if(at>0)write(c,String(i+1),x-304,314,65,ink,clamp(at*2),F.num);
  if(hl>0){c.save();c.font=`67px "${F.kai}"`;const chars=[...item.label],[a,b]=item.highlight||[0,Math.min(2,chars.length)],offset=c.measureText(chars.slice(0,a).join('')).width,w=c.measureText(chars.slice(a,b).join('')).width;marker(c,labelStart+offset,310,w,i%2?yellow:mint,hl);c.restore()}
  write(c,item.label,labelStart,318,67,ink,at,F.kai,at>0&&at<1);
  if(draw>0){icon(c,item.icon||'concept',x,633,340,ink,i%2?yellow:mint,draw);if(draw<1)pen(c,x+Math.sin(draw*6.2)*120,633-Math.cos(draw*6.2)*128,1.1)}
  (item.notes||[]).forEach((v,j)=>{c.save();c.font=`43px "${F.kai}"`;write(c,v,x-c.measureText(v).width/2,862+j*61,43,'#5D6681',clamp(note*1.3-j*.22),F.kai,note>0&&note<1);c.restore()});
 }
 for(let i=1;i<s.items.length;i++){const a=value('connection',s.items[i].id),mid=firstX+(i-.5)*g.itemSpacing;arrow(c,[[mid-100,390],[mid-40,369],[mid+35,371],[mid+100,393]],ink,4,a)}
 if(s.family==='sketchnote.sticky-revision'&&s.revision){
  const p=value('revision');if(p>0){const i=s.items.findIndex(n=>n.id===s.revision!.targetId),x=firstX+i*g.itemSpacing;line(c,[[x-178,289],[x+135,313]],ink,3,p);sticky(c,s.revision.lines,x-275,414,550,'#b9e6d4',p)}
 }
 c.restore();
 if(s.family==='sketchnote.return-loop'&&s.return){
  const p=value('return'),a=firstX+s.items.findIndex(n=>n.id===s.return!.fromId)*g.itemSpacing,b=firstX+s.items.findIndex(n=>n.id===s.return!.toId)*g.itemSpacing,mid=(a+b)/2;
  if(s.items.length<=2)dashedArrow(c,[[a-180,g.returnY],[b-180,g.returnY]],ink,4,p);
  else {const points=Array.from({length:101},(_,i)=>{const t=-Math.PI*.85+i/100*Math.PI*1.7;return [b+Math.cos(t)*210,703+Math.sin(t)*210]});arrow(c,points,ink,4,p)}
  if(p>.4)text(c,s.return.label,mid,g.returnLabelY,43,'#5D6681',F.kai,'center');
 }
 if(s.conclusion?.length)sticky(c,s.conclusion,one?g.single.conclusionX:pageWidth-g.multiple.conclusionRight,layout.conclusionY,g.stickyWidth,'#F9E5A0',value('conclusion'));
 c.restore();
}
