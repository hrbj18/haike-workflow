// Generated additive adaptation; see build_sources.py and derivation.json.
import React, {useEffect,useMemo} from 'react';
import {AbsoluteFill,Video,Audio,Sequence,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import {TextReveal} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-reveal';
import {TextSwell} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-swell';
import {TextHighlight} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-highlight';
import {TextSwap} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-swap';
import {TextBuild} from '../../motion-components/snapcn/upstream/registry/snap-cn/text-build';
import {OrbitGallery} from '../../motion-components/snapcn/upstream/registry/snap-cn/orbit-gallery';
import {SnapCnUIProvider} from '../../motion-components/snapcn/upstream/registry/snap-cn-ui/core';
import {MondrianSplit} from '../hum-production-v1/vendor/remocn/mondrian-split';
import {ParallaxDepth} from '../hum-production-v1/vendor/remocn/parallax-depth';
import {buildMotion,type Action} from '../hum-production-v1/dynamic/motion';
import palettes from '../chromatic-motion-lab-v1/palettes.json';
import recipeBook from '../chromatic-motion-lab-v1/recipes.json';
import {VideoImage as Img} from './Common';

type Recipe=any;type Palette=any;type Episode=any;
const font='Haike Preview';
const rect=([x,y,width,height]:number[]):React.CSSProperties=>({position:'absolute',left:x,top:y,width,height});
const theme=(p:Palette,fontFamily=font)=>({background:p.bg,foreground:p.ink,primary:p.accent,fontFamily});
const image=(e:Episode,n:number)=>e.photos[(n-1)%e.photos.length];
export function TextEffect({id,text,p,size,fontFamily=font}:{id:string;text:string;p:Palette;size:number;fontFamily?:string}){
 const common={fontSize:size,fontFamily,fontWeight:900,color:p.ink};
 if(id==='swell')return <TextSwell {...common} text={text} frontScale={1.2} wordDelay={12} wordStagger={8}/>;
 if(id==='highlight')return <TextHighlight highlight={text} preset="underline" fontSize={size} fontWeight={800} baseColor={p.ink} accentColor={p.accent} fontFamily={fontFamily} startAt={3} drawDuration={18}/>;
 if(id==='swap')return <TextSwap {...common} fromText="看见新技术" toText={text} transition="shared-axis-z" speed={.8}/>;
 if(id==='build')return <TextBuild {...common} text={text}/>;
 return <TextReveal {...common} text={text} initialScale={1.2} speed={.8}/>;
}
function Cards({r,p,e,frames=180,selected=0}:{r:Recipe;p:Palette;e:Episode;frames?:number;selected?:number}){
 const f=useCurrentFrame(),{fps}=useVideoConfig();
 const items=useMemo(()=>(r.mediaEffect==='waterfall'?[...r.photos,...r.photos,...r.photos]:r.photos).map((n,i)=>({id:String(i),img:image(e,n),width:720,height:1280})),[r,e]);
 const motionFrames=['waterfall','spatial-gallery'].includes(r.mediaEffect)?frames:180;
 const picked=selected%items.length;
 const motion=useMemo(()=>buildMotion(r.mediaEffect as Action,items,picked,motionFrames,true),[r,items,motionFrames,picked]);
 useEffect(()=>()=>{motion.timeline.kill()},[motion]);
 motion.timeline.seek(Math.min(motionFrames-1,f*motionFrames/Math.min(frames,motionFrames))/fps,false);
 const sx=r.mediaBox[2]/1300,sy=r.mediaBox[3]/1000;
 return <div style={{position:'absolute',inset:0,overflow:'hidden'}}><div style={{position:'absolute',inset:0,transform:`translate(${motion.camera.x*sx}px,${motion.camera.y*sy}px) scale(${motion.camera.zoom})`,transformOrigin:'top left'}}>
 {motion.states.map((v,i)=><div key={i} style={{...rect([v.x*sx,v.y*sy,v.w*sx,v.h*sy]),zIndex:i===picked?5:1,opacity:v.opacity,transform:`rotate(${v.rotation}deg) scale(${v.scale})`,background:p.paper,padding:3,border:`2px solid ${p.ink}`}}><Img src={items[i].img} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 60%'}}/></div>)}
 {r.mediaEffect==='click-open'&&<svg width="28" height="34" viewBox="0 0 40 48" style={{position:'absolute',left:motion.cursor.x*sx,top:motion.cursor.y*sy,opacity:motion.cursor.opacity}}><path d="M4 3 L34 26 L22 29 L17 43 Z" fill={p.accent} stroke={p.ink} strokeWidth="3"/></svg>}
 </div></div>;
}
export function Media({r,p,e,frames=180,selected=0}:{r:Recipe;p:Palette;e:Episode;frames?:number;selected?:number}){
 const f=useCurrentFrame();
 if(r.mediaEffect==='orbit')return <OrbitGallery images={r.photos.map(n=>image(e,n))} title="" subtitle="" buttonLabel="" footerLeft="" footerCenter="" footerRight="" background={p.bg} textColor={p.ink} theme={theme(p,e.fontFamily)} fontFamily={e.fontFamily||font} turns={1.4} spacing={12} spread={5} imageSize={210} sizeAttenuation={.8} cardAspect={.7} orbitSeconds={18} cornerRadius={0}/>;
 if(r.mediaEffect==='parallax')return <ParallaxDepth skyColor={p.paper} distance={.02} push={.025} speed={.12} layers={[{depth:5,content:<div style={{position:'absolute',inset:12,background:p.accent,transform:'rotate(3deg)'}}/>},{depth:2,content:<Img src={image(e,r.photos[0])} style={{position:'absolute',inset:14,width:'92%',height:'94%',objectFit:'cover',clipPath:`inset(${interpolate(f,[0,32],[100,0],{extrapolateRight:'clamp'})}% 0 0 0)`}}/>}]}/>;
 return <Cards r={r} p={p} e={e} frames={frames} selected={selected}/>;
}
