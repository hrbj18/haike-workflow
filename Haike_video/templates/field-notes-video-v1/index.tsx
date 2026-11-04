import React from 'react';
import {Composition,registerRoot,staticFile} from 'remotion';
import {FieldNotesVideo,type Episode} from './Scene';
type Props={episodeFile:string;episode?:Episode};
async function resolve({props}:{props:Props}){
 if(props.episodeFile!=='episode.json')throw Error('Only the prepared episode file is accepted');
 const response=await fetch(staticFile(props.episodeFile));if(!response.ok)throw Error('Prepared episode missing');
 const episode=await response.json();
 if(episode.template_id!=='field-notes-v2'||episode.version!=='2.1.0'||episode.fps!==30||!Number.isInteger(episode.durationFrames))throw Error('Exact narrated-video contract does not match');
 return {durationInFrames:episode.durationFrames,props:{...props,episode}};
}
registerRoot(()=> <Composition id="FieldNotesVideo" component={FieldNotesVideo as any} durationInFrames={1800} fps={30} width={1080} height={1920} defaultProps={{episodeFile:'episode.json'}} calculateMetadata={resolve}/>);
