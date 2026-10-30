import {gsap} from 'gsap';
import {layoutOf, type Item} from './vendor/layouts';
export type Pose={x:number;y:number;w:number;h:number;scale:number;rotation:number;opacity:number};
export type Action='click-open'|'waterfall'|'spatial-gallery'|'reflow';
export function buildMotion(action:Action,items:Item[],selected:number,frames:number,playroom:boolean){
 const seconds=frames/30,gap=playroom?24:22,base=layoutOf(items,1300,action==='waterfall'?3:3,300,gap);
 const states:Pose[]=base.tiles.map(t=>({x:t.x,y:t.y,w:t.w,h:Math.min(t.h,action==='waterfall'?720:405),scale:1,rotation:0,opacity:1}));
 if(action!=='waterfall')states.forEach((s,i)=>{s.y=items.length<=3?80:Math.floor(i/3)*450;s.h=items.length<=3?760:405});
 const originals=states.map(s=>({...s})),cursor={x:1200,y:900,opacity:0,press:0},camera={x:-5,y:-25,zoom:1};
 const timeline=gsap.timeline({paused:true});
 states.forEach((s,i)=>{timeline.fromTo(s,{y:s.y+75,opacity:0,scale:.94},{y:s.y,opacity:1,scale:1,duration:.52,ease:'power3.out'},Math.min(.38,i*.055))});
 if(action==='waterfall'){
  const travel=Math.max(450,base.height-800);
  states.forEach((s,i)=>timeline.fromTo(s,{y:originals[i].y-travel*.8},{y:originals[i].y+travel*.1,duration:Math.max(.1,seconds-.4),ease:'none'},.35));
 }else if(action==='click-open'){
  const picked=states[selected],origin=originals[selected],arrive=.9,click=1.42,open=1.62,settle=2.2,back=Math.max(2.7,seconds-.62);
  timeline.to(cursor,{opacity:1,duration:.15},arrive).to(cursor,{x:origin.x+origin.w*.64,y:origin.y+origin.h*.55,duration:.48,ease:'power2.inOut'},arrive)
   .to(cursor,{press:1,duration:.1},click).to(cursor,{press:0,duration:.14},click+.1).to(cursor,{opacity:0,duration:.2},open+.2);
  const portrait=(items[selected].height||1)>(items[selected].width||1),target=portrait?{x:310,y:5,w:680,h:930}:{x:35,y:80,w:1230,h:760};
  timeline.to(picked,{...target,rotation:playroom?-1:0,duration:settle-open,ease:'power3.inOut'},open).to(picked,{...origin,duration:.55,ease:'power3.inOut'},back);
  states.forEach((s,i)=>{if(i!==selected){timeline.to(s,{x:originals[i].x+(i%3<selected%3?-110:110),scale:.86,opacity:.18,duration:.56,ease:'power3.inOut'},open).to(s,{...originals[i],duration:.55,ease:'power3.inOut'},back)}});
 }else if(action==='reflow'){
  const sideHeight=Math.min(420,(930-gap*Math.max(0,states.length-2))/Math.max(1,states.length-1));
  const targets=states.map((_,i)=>i===selected?{x:0,y:0,w:790,h:930}:{x:830,y:(i<selected?i:i-1)*(sideHeight+gap),w:470,h:sideHeight});
  states.forEach((s,i)=>timeline.to(s,{...targets[i],rotation:playroom?(i===selected?-1.5:(i%2?2:-2)):0,duration:.9,ease:'power3.inOut'},.8+i*.045));
 }else{
  timeline.to(camera,{y:24,duration:Math.max(1,seconds*.6),ease:'power1.inOut'},.3).to(camera,{zoom:1.12,x:1,duration:Math.max(1,seconds*.3),ease:'power2.inOut'},Math.max(1,seconds*.6));
 }
 timeline.to({}, {duration:.01},seconds);timeline.pause(0);gsap.ticker.sleep();
 return {states,originals,cursor,camera,timeline,selected};
}
