import type {Props} from './types';

/** Layout changes never alter offset + (globalFrame - clip.from) / fps. */
export const presenterPose=(clip:NonNullable<Props['presenter']>,frame:number,fps:number)=>{
 const modes=clip.modes,index=modes.findIndex(m=>frame>=m.from&&frame<m.from+m.frames),current=modes[index];
 const mode=current?.mode||'hidden';
 const previous=index>0?modes.slice(0,index).reverse().find(m=>m.mode!=='hidden'):undefined;
 const target=mode==='hidden'?(previous?.mode||'small'):mode;
 const prior=previous?.mode||target;
 const raw=current?Math.max(0,Math.min(1,(frame-current.from)/(fps*.6))):1;
 const progress=raw*raw*(3-2*raw);
 const large=(prior==='large'?1:0)*(1-progress)+(target==='large'?1:0)*progress;
 return {mode,large,visible:mode!=='hidden',sourceSeconds:clip.offset+(frame-clip.from)/fps};
};
