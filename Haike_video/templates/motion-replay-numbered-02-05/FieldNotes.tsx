import React from 'react';
import {useCurrentFrame} from 'remotion';
import {RecipeStage} from '../chromatic-motion-lab-v1/RecipeStage';
import {CandidateScene} from '../field-notes-v2/Scene';
import type {Episode} from '../chromatic-motion-lab-v1/AvatarScene';
import {resolve,actionFrame} from './action-bindings.cjs';

export type ReplayProps={templateId:'field-notes-v1'|'field-notes-v2';version:string;episode:Episode;actionIds?:string[]};

/** Calls the frozen scene itself, which in turn executes its actual stage parts. */
export function MotionReplayFieldNotes({templateId,version,episode,actionIds}:ReplayProps){
 resolve(templateId,version,actionIds);
 if(episode.mode!=='visual-preview'||episode.previewQuality!=='low'||episode.durationInFrames!==720||episode.fps!==30)throw Error('Only the original 24-second low silent clock is supported');
 return templateId==='field-notes-v2'?<CandidateScene episode={episode}/>:<RecipeStage episode={episode}/>;
}

/** Inspection callable: the host must use the action's ORIGINAL absolute clock.
 * Preview resolves actionId/localFrame into Player.initialFrame before mounting.
 * No shifted/frozen context is applied to the continuous presenter video.
 */
export function MotionReplayFieldNotesAction(props:ReplayProps&{actionId:string}){
 const frame=useCurrentFrame(),binding=resolve(props.templateId,props.version,props.actionIds);
 const stage=binding.stages.find(s=>s[0]===props.actionId);
 if(!stage||frame<stage[1]||frame>=stage[2])throw Error('Host frame outside requested original action');
 return <MotionReplayFieldNotes {...props}/>;
}
