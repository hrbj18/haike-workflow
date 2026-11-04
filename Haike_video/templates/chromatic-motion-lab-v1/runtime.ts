export type Span={from:number;to:number};
export function activeIndex(items:Span[],frame:number){
 let lo=0,hi=items.length-1;
 while(lo<=hi){const mid=(lo+hi)>>1;if(frame<items[mid].from)hi=mid-1;else if(frame>=items[mid].to)lo=mid+1;else return mid}
 return -1;
}
export function activeAndNext<T extends Span>(items:T[],frame:number,premount:number){
 const index=activeIndex(items,frame);
 return index<0?[]:items.slice(index,index+2).filter((item,i)=>i===0||item.from-frame<=premount);
}
export function durationOf(episode:{durationInFrames?:number}){return episode.durationInFrames??360}
export function displayTime(seconds:number){const n=Math.max(0,Math.floor(seconds));return `${String(Math.floor(n/3600)).padStart(2,'0')}:${String(Math.floor(n/60)%60).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
