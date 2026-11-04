import React from 'react';
import {useCurrentFrame} from 'remotion';
import {RecipeStage} from '../chromatic-motion-lab-v1/RecipeStage';
import {resolve,actionFrame} from './action-bindings.cjs';
import type {ReplayProps} from './FieldNotes';
export function MotionReplayFieldNotes(props:ReplayProps){
 resolve(props.templateId,props.version,props.actionIds);
 if(props.templateId!=='field-notes-v1'||props.episode.mode!=='visual-preview'||props.episode.previewQuality!=='low'||props.episode.durationInFrames!==720||props.episode.fps!==30)throw Error('Expected frozen template4 preview');
 return <RecipeStage episode={props.episode}/>;
}
export function MotionReplayFieldNotesAction(props:ReplayProps&{actionId:string}){
 const frame=useCurrentFrame(),binding=resolve(props.templateId,props.version,props.actionIds);
 const stage=binding.stages.find(s=>s[0]===props.actionId);
 if(!stage||frame<stage[1]||frame>=stage[2])throw Error('Host frame outside requested original action');
 return <MotionReplayFieldNotes {...props}/>;
}
