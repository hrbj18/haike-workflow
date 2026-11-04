export type Scene={id:string;recipe:'orange'|'wall'|'detail'|'quote'|'notice'|'brand';start:number;end:number;title:string;subtitle:string;labels:string[];cues:number[];windows?:{mediaId:string;start:number;end:number;offset:number}[]};
export type Media={id:string;src:string;thumbnail:string;kind:'image'|'video';label:string;sourceDuration?:number};
export type Props={width:number;height:number;fps:number;durationFrames:number;title:string;brand:string;font:string;audio?:string;scenes:Scene[];media:Media[];captions:{s:number;e:number;text:string}[]};
