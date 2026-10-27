export type Box = [number, number, number, number];
export type Media = {id:string;src:string;thumbnail:string;offset:number;fit?:'contain';orientation:'portrait'|'landscape';label?:string;kind?:'image'|'video';objectPosition?:string};
export type Scene = {id:string;from:number;frames:number;module:'statement'|'wall'|'focus';theme?:'paper'|'dark';title:string;subtitle?:string;mediaId?:string;wallMediaIds?:string[];motion?:'cascade'|'card-stack'|'paper-reveal';selection?:{cursorFrom:number;selectFrom:number;expandFrom:number;holdFrom:number}};
export type Clip = {id:string;src:string;from:number;frames:number;offset:number;fit?:'contain';objectPosition?:string};
export type Mode = {clipId:string;from:number;frames:number;mode:'large'|'small'|'hidden'};
export type Props = {width?:number;height?:number;fps?:number;durationFrames:number;brand:string;footer:string;visualStyle:'hum'|'coral';media:Media[];scenes:Scene[];captions:{text:string;startMs:number;endMs:number}[];presenterClips?:Clip[];presenterModes?:Mode[];fontAssets?:{display:string;body:string};audio?:string;wallCategories?:string[]};
