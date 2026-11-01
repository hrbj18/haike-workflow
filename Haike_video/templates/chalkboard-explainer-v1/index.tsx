import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Audio,Composition,continueRender,delayRender,registerRoot,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import {BoardScene} from './Board';
import type {Props} from './types';
export const Chalkboard:React.FC<Props>=p=>{
 const frame=useCurrentFrame(),{fps}=useVideoConfig(),t=frame/fps;
 const chapter=p.chapters.find(c=>t>=c.start&&t<c.end)||p.chapters[p.chapters.length-1];
 const [handle]=useState(()=>delayRender('绑定粉笔字体'));
 useEffect(()=>{if(!p.font){continueRender(handle);return}
  const font=new FontFace('ChalkKai','url('+staticFile(p.font)+')');
  font.load().then(f=>{document.fonts.add(f);continueRender(handle)}).catch(e=>{throw e});
 },[p.font,handle]);
 return <AbsoluteFill><BoardScene p={p} t={t} c={chapter}/>{p.audio&&<Audio src={staticFile(p.audio)}/>}</AbsoluteFill>;
};
const Root=()=> <Composition id="Chalkboard" component={Chalkboard} width={1440} height={1800} fps={60} durationInFrames={600}
 defaultProps={{width:1440,height:1800,fps:60,durationFrames:600,title:'连续对象与观察角度',brand:'海客',note:'独立适配 · 示意模型',
 chapters:[{id:'demo',start:0,end:10,title:'同一对象，观察角度改变',kind:'orbit',annotation:['先看整体，再看观察结果']}],
 captions:[],phaseKeys:[[0,.1],[10,6.28]],nodeKeys:[[0,1.57],[10,1.57]],
 model:{orbitRadius:60.3,bodyRadius:.273,occluderRadius:1,sourceRadius:109.2,sourceDistance:23455,inclinationDegrees:5.1,displayInclinationDegrees:20}}}
 calculateMetadata={({props})=>({width:props.width,height:props.height,fps:props.fps,durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
