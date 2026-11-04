import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {AbsoluteFill,Audio,Composition,cancelRender,continueRender,delayRender,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import type {Episode} from './types';
import {F,text,wrapped} from './drawing';import {blackboard,paper} from './backgrounds';import {drawPaper} from './paper';import {drawChalk} from './chalk';
const faces=[{name:F.kai,file:'LXGWWenKai-Medium.ttf',weight:'500'},{name:F.brush,file:'LongCang.ttf',weight:'400'},{name:F.num,file:'Fraunces.ttf',weight:'100 900'},{name:F.mono,file:'JetBrainsMono.ttf',weight:'100 800'}];
export function KnowledgeFilm({episode}:{episode:Episode|null}){
 if(episode===null)throw Error('Frozen episode metadata must load before rendering');
 const frame=useCurrentFrame(),canvas=useRef<HTMLCanvasElement>(null),[handle]=useState(()=>delayRender('Knowledge public exact fonts and Canvas frame')),[loaded,setLoaded]=useState(false);
 useEffect(()=>{Promise.all(faces.map(async a=>{const face=await new FontFace(a.name,`url(${staticFile('fonts/'+a.file)})`,{weight:a.weight}).load();document.fonts.add(face)})).then(()=>setLoaded(true)).catch(cancelRender)},[]);
 useLayoutEffect(()=>{if(!loaded||!canvas.current)return;const c=canvas.current.getContext('2d')!,isPaper=episode.template_id==='knowledge-explainer-sketchnote';c.clearRect(0,0,1080,1920);if(isPaper)paper(c,0,0,1080,1920);else blackboard(c,1080,1920);
  const scene=episode.scenes.find(s=>s.from<=frame&&frame<s.to);if(!scene)throw Error('Missing full narrative frame');
  const ink=isPaper?'#1F2A44':'#e5e3d1';text(c,episode.title,67,117,42,ink,F.kai,'left',700);c.strokeStyle=isPaper?'#8b8c8d':'#c7cdb9';c.lineWidth=1.4;c.beginPath();c.moveTo(70,213);c.lineTo(1010,213);c.stroke();text(c,`${String(episode.scenes.indexOf(scene)+1).padStart(2,'0')} / ${String(episode.scenes.length).padStart(2,'0')}`,1007,198,25,isPaper?'#b4ab98':'#c9d0bf',F.num,'right');
  if(isPaper)drawPaper(c,scene,frame);else drawChalk(c,scene,frame);
  if(episode.sourceLabel)text(c,episode.sourceLabel,69,1590,22,isPaper?'#b3aa98':'#aab8a8');
  const cue=episode.captions.find(v=>v.startMs<=frame/episode.fps*1000&&frame/episode.fps*1000<v.endMs);
  if(cue){if(!isPaper){c.save();c.font=`500 39px "${F.kai}"`;let width=0,lines=1;for(const letter of cue.text){const size=c.measureText(letter).width;if(width+size>930){lines++;width=0}width+=size}c.restore();c.fillStyle='#23362ed9';c.fillRect(48,1646,984,lines>1?125:74)}wrapped(c,cue.text,73,1697,930,39,ink,F.kai,1.35)}
  // Full boundary clauses are retained in measured final diagram note/conclusion.
  continueRender(handle);
 },[episode,frame,loaded,handle]);
 return <AbsoluteFill><canvas ref={canvas} width={1080} height={1920} style={{width:'100%',height:'100%'}}/>{episode.narration&&<Audio src={staticFile(episode.narration)}/>} {episode.music&&<Audio src={staticFile(episode.music)} volume={10**(episode.musicGainDb/20)}/>}</AbsoluteFill>;
}
async function metadata(){const response=await fetch(staticFile('episode.json'));if(!response.ok)throw Error('Missing frozen public knowledge input');const episode:Episode=await response.json();if(episode.implementation!=='knowledge-reference-public-v3')throw Error('Wrong implementation');return {width:1080,height:1920,fps:episode.fps,durationInFrames:episode.durationFrames,props:{episode}}}
registerRoot(()=> <Composition id="KnowledgeReferencePublic" component={KnowledgeFilm} width={1080} height={1920} fps={60} durationInFrames={3600} defaultProps={{episode:null}} calculateMetadata={metadata}/>);
