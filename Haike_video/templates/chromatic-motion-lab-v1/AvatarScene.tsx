import React, {useEffect,useMemo} from 'react';
import {AbsoluteFill,Img,Video,Audio,Sequence,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
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
import palettes from './palettes.json';
import recipeBook from './recipes.json';
import {activeIndex,activeAndNext} from './runtime';
export {activeIndex} from './runtime';
export {palettes};
export const FPS=recipeBook.canvas.fps,FRAMES=recipeBook.canvas.frames,WIDTH=recipeBook.canvas.width,HEIGHT=recipeBook.canvas.height;
export const recipes=recipeBook.recipes;
export const recipeRevision=recipeBook.revision;
export type Recipe=typeof recipes[number];
export type Palette=typeof palettes[number];
export type Segment={role?:'intro'|'material'|'outro';composition?:string;labels?:string[];readingHoldFrames?:number;from:number;to:number;chapter:number;chapterFrom:number;chapterTo:number;headline?:string;kicker?:string;conclusion?:string;photos:number[];intent?:string;motions?:Record<string,{mediaEffect:string;headlineEffect:string;conclusionEffect:string}>};
export type Episode={presentation?:'legacy'|'bookends';pilotVariant?:string;presenterWindows?:{from:number;to:number}[];densityProfile?:string;schema:string;previewQuality?:'standard'|'low';mode:'visual-preview'|'narrated-preview';headline?:string;kicker?:string;presenterName:string;presenter?:string;photos:string[];captions:{from:number;to:number;text:string;lines?:string[]}[];durationInFrames?:number;segments?:Segment[];presenterClips?:{from:number;to:number;src:string}[];audio?:string|null;captionSource?:string;conclusionFrom?:number;fontSrc?:string;fontFamily?:string};
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
function Decoration({r,p}:{r:Recipe;p:Palette}){
 const f=useCurrentFrame();
 if(r.decoration==='split')return <div style={{...rect([0,380,720,12]),background:p.accent}}/>;
 if(r.decoration==='stage')return <div style={{...rect([456,0,264,1280]),background:p.paper,zIndex:-1}}/>;
 if(r.decoration==='steps')return <div style={{...rect([440,412,232,90]),display:'flex',gap:8,alignItems:'center'}}>{['看','问','试'].map((t,i)=><span key={t} style={{background:i===2?p.accent:p.paper,color:i===2?p.onAccent:p.ink,fontSize:28,fontWeight:900,padding:'12px 18px',opacity:interpolate(f,[15+i*10,30+i*10],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}>{t}</span>)}</div>;
 if(r.decoration==='focus')return <div style={{...rect([48,395,624,34]),fontSize:17,color:p.accent,letterSpacing:3}}>● 现场观察　/　选择一个瞬间</div>;
 if(r.decoration==='collage')return <><AbsoluteFill style={{zIndex:-1,backgroundImage:`radial-gradient(${p.ink}22 1px,transparent 1px)`,backgroundSize:'18px 18px'}}/><div style={{...rect([43,450,364,528]),background:p.ink,transform:'rotate(-3deg)'}}/><div style={{...rect([462,382,190,65]),background:p.accent,color:p.onAccent,fontSize:24,padding:18,fontWeight:800,transform:'rotate(-7deg)'}}>新鲜发生 ↗</div></>;
 return <div style={{...rect([120,392,480,625]),border:`1px solid ${p.accent}55`,borderRadius:'50%'}}/>;
}
export function ChromaticScene({variant='01',episode,previewMuted=false}:{variant?:string;episode:Episode;previewMuted?:boolean}){
 const f=useCurrentFrame(),baseRecipe=recipes.find(x=>x.id===variant),p=palettes.find(x=>x.id===variant);
 const {durationInFrames,fps}=useVideoConfig();
 const isV2=episode.schema==='haike.chromatic-avatar-episode/2';
 const segments=episode.segments||[],segmentIndex=activeIndex(segments,f),segment=segments[segmentIndex];
 const plannedMotion=isV2?segment?.motions?.[variant]:undefined;
 const r=useMemo(()=>baseRecipe&&plannedMotion?{...baseRecipe,...plannedMotion}:baseRecipe,[baseRecipe,plannedMotion]);
 const mediaEpisode=useMemo(()=>segment?{...episode,photos:segment.photos.map(i=>episode.photos[i])}:episode,[episode,segment]);
 if(!r||!p)throw Error('未知模板配方');
 if(isV2&&!segment)throw Error('当前帧缺少编排段落，请重新准备内容');
 if(isV2&&!plannedMotion)throw Error('缺少多动效计划，请按当前配方重新准备内容');
 const cue=episode.captions[activeIndex(episode.captions,f)];
 const headline=(segment?.headline||episode.headline||r.headline).split('\n');
 const titleFrom=isV2?segment.chapterFrom:0;
 const mediaStart=isV2?Math.min(r.mediaStart,Math.floor((segment.to-segment.from)*.08)):r.mediaStart;
 const availableFrames=isV2?segment.to-segment.from-mediaStart:180;
 const conclusionFrom=segment?.conclusion?segment.chapterTo-Math.min(90,Math.floor((segment.chapterTo-segment.chapterFrom)/2)):isV2?episode.conclusionFrom??durationInFrames-90:r.conclusionStart;
 const mountedClips=activeAndNext(episode.presenterClips||[],f,fps),sceneFont=episode.fontFamily||font;
 return <AbsoluteFill data-recipe={r.id} data-segment={segmentIndex} data-motion-media={r.mediaEffect} data-motion-title={r.headlineEffect} data-motion-conclusion={r.conclusionEffect} style={{fontFamily:sceneFont,overflow:'hidden',background:p.bg,color:p.ink,isolation:'isolate'}}>
 <style>{`@font-face{font-family:'${sceneFont}';src:url('${episode.fontSrc||'/assets/font.ttf'}')}*,*:before,*:after{box-sizing:border-box}`}</style>
 <SnapCnUIProvider theme={theme(p,sceneFont)}>
 <Decoration r={r} p={p}/>
 <div style={{...rect([48,42,624,32]),fontSize:16,display:'flex',justifyContent:'space-between',color:p.ink,opacity:.8}}><span>海客 · 让 AI 进入日常</span><span>{r.id} / 06</span></div>
 <div style={{...rect([48,108,624,32]),fontSize:21,fontWeight:700,color:p.ink}}><span style={{display:'inline-block',width:28,height:5,background:p.accent,marginRight:12,verticalAlign:'middle'}}/>{segment?.kicker||episode.kicker||r.kicker}</div>
 <div data-role="headline" style={{...rect([48,168,624,196]),fontSize:r.headlineSize,fontWeight:900,lineHeight:1.12}}>{headline.map((line,i)=><div key={i+line} style={{position:'relative',height:r.headlineSize*1.15}}><Sequence from={titleFrom+i*8} layout="none"><TextEffect id={r.headlineEffect} text={line} p={p} size={r.headlineSize} fontFamily={sceneFont}/></Sequence></div>)}</div>
 <div data-role="media" style={{...rect(r.mediaBox),overflow:'hidden',isolation:'isolate',zIndex:2}}>{isV2&&r.mediaEffect!=='orbit'&&<Img src={image(mediaEpisode,r.photos[0])} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',opacity:interpolate(f-(segment?.from||0),[mediaStart+18,mediaStart+30],[1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}/>}<Sequence key={segmentIndex} from={(segment?.from||0)+mediaStart} durationInFrames={isV2?availableFrames:undefined} layout="none"><Media r={r} p={p} e={mediaEpisode} frames={availableFrames} selected={isV2?segmentIndex%r.photos.length:0}/></Sequence>{r.decoration==='split'&&f<38&&<AbsoluteFill style={{zIndex:3,opacity:interpolate(f,[18,38],[1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'})}}><MondrianSplit seed={17} splits={5} speed={1.6} redColor={p.accent} yellowColor={p.bg} blueColor={p.ink} fieldColor={p.ink} lineColor={p.ink} lineWeight={7}/></AbsoluteFill>}</div>
 <div data-role="presenter" style={{...rect(r.presenterBox),borderRadius:r.presenterRadius,overflow:'hidden',border:`4px solid ${p.accent}`,background:p.paper,zIndex:10}}>
 {isV2?mountedClips.map(clip=><Sequence key={clip.from} from={clip.from} durationInFrames={clip.to-clip.from} premountFor={fps} layout="none"><Video data-avatar="true" data-clip-from={clip.from} src={clip.src} muted volume={0} pauseWhenBuffering style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/></Sequence>):<Video data-avatar="true" src={episode.presenter!} muted volume={0} pauseWhenBuffering style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 35%'}}/>}
 <div style={{position:'absolute',bottom:0,left:0,right:0,padding:'24px 8px 15px',background:`linear-gradient(transparent,${p.bg})`,color:p.ink,textAlign:'center',fontSize:20,fontWeight:800}}>{episode.presenterName} · AI 数字人</div>
 </div>
 <div data-role="conclusion" style={{...rect([48,1008,624,66]),color:p.ink}}><Sequence key={conclusionFrom} from={conclusionFrom} layout="none"><TextEffect id={r.conclusionEffect} text={segment?.conclusion||r.conclusion} p={p} size={34} fontFamily={sceneFont}/></Sequence></div>
 <div data-role="caption" style={{...rect(isV2?[48,1084,624,90]:[48,1096,624,68]),background:p.ink,color:p.bg,fontSize:isV2?28:29,lineHeight:1.15,whiteSpace:'pre-line',fontWeight:700,display:'flex',alignItems:'center',justifyContent:'center',textAlign:'center',padding:'6px 16px',borderLeft:`8px solid ${p.accent}`,visibility:cue?'visible':'hidden'}}>{cue?.lines?.join('\n')||cue?.text||''}</div>
 <div style={{...rect([48,1200,624,30]),fontSize:16,display:'flex',justifyContent:'space-between',color:p.ink,opacity:.75}}><span>先体验，再理解。</span><span>海客现场 / {isV2?`${String(segmentIndex+1).padStart(2,'0')} / ${segments.length}`:String(Math.floor(f/120)+1).padStart(2,'0')}</span></div>
 {isV2&&episode.audio&&<Audio key={previewMuted?'muted-preview':'original-audio'} src={episode.audio} muted={previewMuted} volume={previewMuted?0:1} pauseWhenBuffering/>}
 </SnapCnUIProvider></AbsoluteFill>;
}
