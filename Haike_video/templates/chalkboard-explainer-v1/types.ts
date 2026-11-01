import type {Key,Model} from './physics';
export type Caption={id:string;start:number;end:number;text:string};
export type Chapter={id:string;start:number;end:number;title:string;kind:'orbit'|'surface'|'shadow'|'tilt'|'compare'|'recap';annotation:string[]};
export type Props={width:number;height:number;fps:number;durationFrames:number;title:string;brand:string;chapters:Chapter[];captions:Caption[];phaseKeys:Key[];nodeKeys:Key[];comparisonPhaseKeys?:Key[];surfaceWindows?:{chapter_id:string;enter:[number,number];exit:[number,number]}[];model:Model;audio?:string;font?:string;note:string};
