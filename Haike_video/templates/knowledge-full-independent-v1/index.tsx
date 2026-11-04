import React,{useEffect,useState} from 'react';
import {Audio,Composition,continueRender,delayRender,registerRoot,staticFile} from 'remotion';
import {Board} from './Board';
import type {Props} from './types';
const Film:React.FC<Props>=p=>{
 const [handle]=useState(()=>delayRender('知识图解字体'));
 useEffect(()=>{new FontFace('KnowledgeFull',`url(${staticFile(p.font)})`).load().then(font=>{document.fonts.add(font);continueRender(handle)}).catch(error=>{throw error})},[p.font,handle]);
 return <><Board {...p}/>{p.audio&&<Audio src={staticFile(p.audio)}/>}</>;
};
const Root=()=> <Composition id="KnowledgeFull" component={Film} width={1080} height={1920} fps={60} durationInFrames={600} defaultProps={{theme:'sketchnote',width:1080,height:1920,fps:60,durationFrames:600,brand:'海客AI社区服务店',title:'亲手体验AI',font:'body.ttf',captions:[],scenes:[{id:'demo',start:0,end:10,title:'从知道到亲手体验',subtitle:'用图解说明一次改变',recipe:'question',labels:['只在屏幕里见过？','亲手用一次真的AI'],cues:[0,3]}]}} calculateMetadata={({props})=>({width:props.width,height:props.height,fps:props.fps,durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
