// Installation smoke test only; no episode, personal media or template approval.
import React from 'react';
import {AbsoluteFill, Composition, registerRoot, useCurrentFrame} from 'remotion';

const PixelProbe: React.FC = () => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{backgroundColor:'#1658d4'}}>
    <div style={{position:'absolute',left:8+frame*16,top:8,width:8,height:8,backgroundColor:'#ffffff'}}/>
  </AbsoluteFill>;
};

const Root: React.FC = () => <Composition id="HaikeRuntimeCheck" component={PixelProbe}
  durationInFrames={2} fps={30} width={96} height={96}/>;
registerRoot(Root);
