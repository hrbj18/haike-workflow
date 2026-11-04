import React from 'react';
import {Composition,registerRoot,Sequence,staticFile} from 'remotion';
import {ProductionRoot,Caption} from './Common';
import {KineticProduction} from './Kinetic';
import {RecipeStage} from './FieldNotes';
import {NanaTemplate} from './nana/index';
import type {Episode} from './types';
function Film({episode}:{episode:Episode}){
 if(!episode)throw Error('Missing frozen full episode');
 const id=episode.template_id;
 return <ProductionRoot episode={episode}>{id==='kinetic-field-v1'?<><div style={{position:'absolute',left:54,top:0,width:540,height:960,transform:'scale(1.8)',transformOrigin:'0 0'}}><Sequence width={540} height={960}><KineticProduction episode={episode}/></Sequence></div><Caption kinetic/></>:id==='nana-mint-explainer-v1'?<><NanaTemplate episode={episode.nativeNana} episodeFile="episode.json"/><Caption landscape/></>:id==='field-notes-v1'?<><div style={{position:'absolute',left:0,top:0,width:720,height:1280,transform:'scale(1.5)',transformOrigin:'0 0'}}><Sequence width={720} height={1280}><RecipeStage episode={episode.content}/></Sequence></div><Caption/></>:<div>Unsupported exact renderer</div>}</ProductionRoot>;
}
async function metadata(){
 const response=await fetch(staticFile('episode.json'));if(!response.ok)throw Error('Prepared full episode missing');
 const episode:Episode=await response.json();
 if(episode.schema!=='haike.numbered-full-motion-episode/1'||episode.version!=='2.0.0'||!Number.isInteger(episode.durationFrames))throw Error('Wrong exact full episode version');
 const landscape=episode.template_id==='nana-mint-explainer-v1';
 return {width:landscape?1920:1080,height:landscape?1080:1920,fps:episode.fps,durationInFrames:episode.durationFrames,props:{episode}};
}
registerRoot(()=> <Composition id="FullNumberedMotion" component={Film as any} width={1080} height={1920} fps={30} durationInFrames={1800} defaultProps={{episode:null}} calculateMetadata={metadata}/>);
