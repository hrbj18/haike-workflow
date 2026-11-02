import type {Scene} from '../types';

export const ease=(frame:number,start:number,end:number)=>{
  const t=Math.max(0,Math.min(1,(frame-start)/Math.max(1,end-start)));
  return t*t*(3-2*t);
};

// Positions are indexed by the original item ID, never by its current rank.
export function rankPositions(count:number,events:{at:number;order:number[]}[],frame:number){
  let order=Array.from({length:count},(_,i)=>i),positions=[...order];
  for(const e of events){
    if(frame<e.at)break;
    const t=ease(frame,e.at,e.at+18);
    positions=positions.map((_,id)=>order.indexOf(id)+(e.order.indexOf(id)-order.indexOf(id))*t);
    if(t<1)break;
    order=e.order;
  }
  return positions;
}

export function pathAt(scenes:Scene[],index:number,frame:number){
  const current=scenes[index].quest!.path!;
  let first=index;
  while(first>0&&!scenes[first].quest!.path!.reset&&scenes[first-1].quest?.kind==='path'
      &&scenes[first-1].quest!.path!.id===current.id)first--;
  let position=scenes[first].quest!.path!.initial||0,from=position,to=position,progress=1;
  const visited=new Set([position]),legs:{from:number;to:number;progress:number}[]=[];
  for(let i=first;i<=index;i++){
    const s=scenes[i],q=s.quest!,p=q.path!;
    for(let j=0;j<q.cues.length;j++){
      const at=s.from+q.cues[j];
      if(frame<at)return {position,from,to,progress,visited:[...visited],legs};
      from=position;to=p.stops[j];progress=ease(frame,at,at+(p.travelFrames||24));
      legs.push({from,to,progress});position=from+(to-from)*progress;
      if(progress<1)return {position,from,to,progress,visited:[...visited],legs};
      visited.add(to);
    }
  }
  return {position,from,to,progress,visited:[...visited],legs};
}
