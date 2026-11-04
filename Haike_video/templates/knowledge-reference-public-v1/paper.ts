import type {Scene} from './types';
import {C,F,arrow,clamp,ease,ellipse,icon,line,marker,pen,progress,sticky,tape,text,write} from './drawing';
import {paper} from './backgrounds';
const ink='#1F2A44',mint='#8ED5BB',yellow='#F5CF66';
export function drawPaper(c:C,s:Scene,frame:number){
 const event=(kind:string,target?:string)=>s.events.find(e=>e.kind===kind&&(target===undefined||e.target===target));
 const value=(kind:string,target?:string)=>{const e=event(kind,target);return e?progress(frame,e.at,e.duration):0};
 c.save();c.fillStyle='#343d4e';c.fillRect(64,245,952,1328);c.beginPath();c.rect(64,245,952,1328);c.clip();
 const pageWidth=Math.max(1520,s.items.length*750+20),fit=952/pageWidth;let scale=1,tx=120,ty=720;
 for(const e of s.events.filter(v=>v.kind==='camera'||v.kind==='camera-return').sort((a,b)=>a.at-b.at)){
  const i=s.items.findIndex(v=>v.id===e.target);if(frame<e.at)continue;const p=ease(progress(frame,e.at,e.duration));const nx=540-(400+i*750)*1.35;
  scale=scale+(1.35-scale)*p;tx=tx+(nx-tx)*p;ty=ty+(94-ty)*p;
 }
 const full=value('overview');if(full>0){const p=ease(full);scale=scale+(fit-scale)*p;tx=tx+(64-tx)*p;ty=ty+(245+(1328-1100*fit)/2-ty)*p}
 c.translate(tx,ty);c.scale(scale,scale);paper(c,0,0,pageWidth,1100,true);tape(c,205,18,200);
 const firstCamera=event('camera',s.items[0].id);if(firstCamera&&frame>=s.from+9&&frame<firstCamera.at+12)pen(c,100,55,.65);
 if(full>0)write(c,s.title,85,100,75,ink,Math.min(1,full*1.5),F.brush);
 const intro=clamp(value('camera',s.items[0].id)*1.4);line(c,[[80,130],[435,128],[790,133],[pageWidth-70,129]],ink,5,intro);
 for(let i=0;i<s.items.length;i++){
  const item=s.items[i],x=400+i*750,at=value('write',item.id),hl=value('highlight',item.id),draw=value('draw',item.id),note=value('annotation',item.id);
  const labelStart=x-215;ellipse(c,x-286,294,41,43,ink,5,at);
  if(at>0)write(c,String(i+1),x-304,314,65,ink,clamp(at*2),F.num);
  if(hl>0){c.save();c.font=`67px "${F.kai}"`;const chars=[...item.label],[a,b]=item.highlight||[0,Math.min(2,chars.length)],offset=c.measureText(chars.slice(0,a).join('')).width,w=c.measureText(chars.slice(a,b).join('')).width;marker(c,labelStart+offset,310,w,i%2?yellow:mint,hl);c.restore()}
  write(c,item.label,labelStart,318,67,ink,at,F.kai,at>0&&at<1);
  if(draw>0){icon(c,item.icon||'concept',x,633,340,ink,i%2?yellow:mint,draw);if(draw<1)pen(c,x+Math.sin(draw*6.2)*120,633-Math.cos(draw*6.2)*128,.85)}
  (item.notes||[]).forEach((v,j)=>{c.save();c.font=`43px "${F.kai}"`;write(c,v,x-c.measureText(v).width/2,862+j*61,43,'#5D6681',clamp(note*1.3-j*.22),F.kai,note>0&&note<1);c.restore()});
 }
 for(let i=1;i<s.items.length;i++){const a=value('connection',s.items[i].id);arrow(c,[[705+(i-1)*750,471],[750+(i-1)*750,454],[800+(i-1)*750,455],[846+(i-1)*750,473]],ink,4,a)}
 if(s.family==='sketchnote.sticky-revision'&&s.revision){
  const p=value('revision');if(p>0){const i=s.items.findIndex(n=>n.id===s.revision!.targetId),x=400+i*750;line(c,[[x-178,289],[x+135,313]],ink,3,p);sticky(c,s.revision.lines,x-205,414,430,'#b9e6d4',p)}
 }
 if(s.family==='sketchnote.return-loop'&&s.return){
  const p=value('return'),a=400+s.items.findIndex(n=>n.id===s.return!.fromId)*750,b=400+s.items.findIndex(n=>n.id===s.return!.toId)*750,mid=(a+b)/2;const points=Array.from({length:81},(_,i)=>{const t=i/80*Math.PI;return [mid+Math.cos(t)*(a-b)/2,825+Math.sin(t)*120]});arrow(c,points,ink,4,p);
  if(p>.4)text(c,s.return.label,mid,1000,27,'#5D6681',F.kai,'center');
 }
 if(s.conclusion?.length)sticky(c,s.conclusion,pageWidth-590,900,500,'#F9E5A0',value('conclusion'));
 c.restore();
}
