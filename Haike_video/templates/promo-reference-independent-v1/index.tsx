import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Composition,cancelRender,continueRender,delayRender,registerRoot,staticFile} from 'remotion';
import {PromoReference} from './Board';
import type {Props} from './types';
const Main:React.FC<Props>=p=>{const [hold]=useState(()=>delayRender('Loading licensed CJK font'));useEffect(()=>{const f=new FontFace('PromoReference',`url("${staticFile(p.font)}")`,{weight:'100 900'});f.load().then(x=>{document.fonts.add(x);continueRender(hold)}).catch(cancelRender);return()=>continueRender(hold)},[p.font,hold]);return <AbsoluteFill style={{fontFamily:'PromoReference,sans-serif'}}><PromoReference {...p}/></AbsoluteFill>};
const Root:React.FC=()=> <Composition id="PromoReferenceFull" component={Main} width={1920} height={1080} fps={60} durationInFrames={3600} defaultProps={{width:1920,height:1080,fps:60,durationFrames:3600,title:'',brand:'海客AI社区服务店',font:'body.ttf',scenes:[],media:[],captions:[]}} calculateMetadata={({props})=>({durationInFrames:props.durationFrames})}/>;
registerRoot(Root);
