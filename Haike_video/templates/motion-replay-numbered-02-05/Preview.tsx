import React from 'react';
import {createRoot} from 'react-dom/client';
import {Player} from '@remotion/player';
import {MotionReplayFieldNotes,MotionReplayFieldNotesAction} from './FieldNotes';
import {actionFrame,resolve} from './action-bindings.cjs';

async function boot(){
 const response=await fetch('/motion-replay-props.json');
 if(!response.ok)throw Error('Run motion replay preparation first');
 const props=await response.json();
 const font=new FontFace(props.episode.fontFamily,"url('/assets/font.ttf')");
 await font.load();document.fonts.add(font);await document.fonts.ready;
 const params=new URLSearchParams(location.search),capture=params.has('capture');
 const initialFrame=Math.max(0,Math.min(719,Number(params.get('frame'))||0)),actionId=params.get('action');
 const component=actionId?MotionReplayFieldNotesAction:MotionReplayFieldNotes;
 const inputProps=actionId?{...props,actionId}:props;
 const sourceFrame=actionId?actionFrame(props.templateId,props.version,actionId,Number(params.get('localFrame'))||0):initialFrame;
 const endFrame=actionId?resolve(props.templateId,props.version).stages.find(s=>s[0]===actionId)[2]:720;
 createRoot(document.getElementById('root')!).render(<Player ref={ref=>{(window as any).motionReplayPlayer=ref}} component={component} inputProps={inputProps} durationInFrames={endFrame} fps={30} compositionWidth={720} compositionHeight={1280} initialFrame={sourceFrame} initiallyMuted controls={!capture&&!actionId} style={capture?{width:720,height:1280}:{height:'100vh',aspectRatio:'9/16'}} acknowledgeRemotionLicense/>);
}
boot().catch(e=>document.getElementById('root')!.textContent=e.message);
