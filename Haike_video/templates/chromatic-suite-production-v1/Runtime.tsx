import React,{createContext,useContext} from 'react';
import {OffthreadVideo,Sequence,staticFile} from 'remotion';
export type Knot={source:number;target:number;event:string;anchor?:{kind:string;index:number;boundary:string};offsetFrames?:number};
export type Scene={id:string;actionId:string;from:number;to:number;sourceFrom:number;sourceTo:number;title:string;note:string;knots:Knot[]};
export type Clip={src:string;from:number;to:number;sourceFrom:number;objectPosition:string};
export type Props={templateId:string;version:string;durationInFrames:number;fps:number;scenes:Scene[];
 slots:Record<string,Record<string,Clip[]>>;captions:{from:number;to:number;text:string}[];
 presenters:Clip[];font:string;medicalOverlay:string;medicalFrom:number;medicalTo:number};
type State={p:Props;s:Scene;globalFrame:number;motionFrame:number};
export const Context=createContext<State>(null as any);
export const useCurrentFrame=()=>useContext(Context).motionFrame;
export const useGlobalFrame=()=>useContext(Context).globalFrame;
export const useScene=()=>useContext(Context).s;

// Each meaningful internal source state is independently located by a measured
// word/cue. Projection between neighboring events preserves local easing; video
// and presenter sampling never consumes this motion-only coordinate.
export function motionAt(knots:Knot[],frame:number) {
 if(frame<=knots[0].target)return knots[0].source;
 for(let i=1;i<knots.length;i++)if(frame<=knots[i].target){const a=knots[i-1],b=knots[i];return a.source+(b.source-a.source)*(frame-a.target)/(b.target-a.target);}
 return knots[knots.length-1].source;
}
export function Media({id,style={}}:{id:string;style?:React.CSSProperties}) {
 const {p,s}=useContext(Context),clips=p.slots[s.id]?.[id];
 if(!clips)throw Error('Missing real video slot '+s.id+'/'+id);
 return <>{clips.map((c,i)=><Sequence key={s.id+id+i} from={c.from} durationInFrames={c.to-c.from} layout="none">
  <OffthreadVideo data-slot={id} data-global-from={c.from} data-source-from={c.sourceFrom} src={staticFile(c.src)}
   startFrom={c.sourceFrom} endAt={c.sourceFrom+c.to-c.from} muted volume={0} playbackRate={1}
   style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:c.objectPosition,...style}}/>
 </Sequence>)}</>;
}
