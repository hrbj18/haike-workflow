import React from 'react';
import {AbsoluteFill, Audio, Composition, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {NewDirections} from './NewDirections';
import {RefinedDirections} from './RefinedDirections';
import type {VideoProps} from './types';
import layout from './layout.json';

const defaults: VideoProps={duration:8,avatarSrc:'avatar.mp4',audioSrc:'narration.wav',brand:'海客AI社区服务站',captions:[],art:{direction:'red-manifesto',backgroundSrc:null,chapters:[{kind:'hook',fromCue:0,toCue:0,heading:['账号经营','多一条变现路径'],deck:'了解社区AI服务',points:['产品体验','社区服务'],start:0,end:8}],highlights:[],portraitFraming:'medium-9x16',wordCues:[],phraseHighlights:[],scenes:[]}};
export const SixStyleVideo: React.FC<VideoProps>=p=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  const chapterIndex=Math.max(0,p.art.chapters.findIndex(c=>frame/fps>=c.start&&frame/fps<c.end));
  const chapter=p.art.chapters[chapterIndex]??p.art.chapters[p.art.chapters.length-1];
  const theme=layout.palette[p.art.direction];
  const headerInk=p.art.direction==='red-manifesto'?'#171411':theme.ink;
  const headerMuted=p.art.direction==='red-manifesto'?'#65564b':theme.muted;
  const isNew=['red-manifesto','silver-launch','documentary'].includes(p.art.direction);
  const ctx={p,chapter,chapterIndex,frame,fps};
  return <AbsoluteFill style={{fontFamily:'"Microsoft YaHei",sans-serif',background:theme.base,overflow:'hidden'}}>
    {isNew?<NewDirections {...ctx}/>:<RefinedDirections {...ctx}/>}
    <div style={{position:'absolute',left:80,right:80,top:76,zIndex:50,display:'flex',alignItems:'center',justifyContent:'space-between',color:headerInk,paddingBottom:24,borderBottom:p.art.direction==='community-showcase'?'none':`1px solid ${headerInk}55`}}><div style={{fontSize:34,fontWeight:700}}>{p.brand}</div><div style={{fontSize:25,color:headerMuted}}>社区AI × 内容创作</div></div>
    <div style={{position:'absolute',left:80,bottom:64,zIndex:50,color:theme.muted,fontSize:23,letterSpacing:2}}>数字人演绎</div>
    <Audio src={staticFile(p.audioSrc)} volume={1}/>
  </AbsoluteFill>;
};
const Root=()=> <Composition id="HaikeInvestmentArtV4" component={SixStyleVideo} width={1080} height={1920} fps={30} durationInFrames={240} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round(props.duration*30))})}/>;
registerRoot(Root);
