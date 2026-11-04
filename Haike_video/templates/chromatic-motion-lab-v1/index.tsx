import React from 'react';
import {AbsoluteFill,Composition,registerRoot,staticFile,type CalculateMetadataFunction} from 'remotion';
import {type Episode,FPS,WIDTH,HEIGHT} from './AvatarScene';
import {ChromaticScene} from './Scene';
import {durationOf} from './runtime';

type Props={variant:string;episode:Episode|null};
const calculateMetadata:CalculateMetadataFunction<Props>=async({props,abortSignal})=>{
 const episode=props.episode||await fetch(staticFile('episode.json'),{signal:abortSignal}).then(r=>{if(!r.ok)throw Error('请先准备episode.json并设置public-dir');return r.json()});
 const asset=(value:string)=>value.startsWith('/assets/')?staticFile(value.slice(1)):value;
 const bound:Episode={...episode,photos:episode.photos.map(asset),fontSrc:staticFile('assets/font.ttf'),fontFamily:'Haike Prepared'};
 if(episode.presenter)bound.presenter=asset(episode.presenter);
 if(episode.presenterClips)bound.presenterClips=episode.presenterClips.map(c=>({...c,src:asset(c.src)}));
 if(episode.audio)bound.audio=asset(episode.audio);
 return {durationInFrames:durationOf(bound),fps:FPS,width:WIDTH,height:HEIGHT,props:{...props,variant:episode.pilotVariant||props.variant,episode:bound}};
};
const PreparedScene=({variant,episode}:Props)=>episode?<ChromaticScene variant={variant} episode={episode}/>:<AbsoluteFill>请先准备本期内容</AbsoluteFill>;
const Root=()=> <Composition id="ChromaticAvatar" component={PreparedScene} width={WIDTH} height={HEIGHT} fps={FPS} durationInFrames={360} defaultProps={{variant:'01',episode:null}} calculateMetadata={calculateMetadata}/>;
registerRoot(Root);
