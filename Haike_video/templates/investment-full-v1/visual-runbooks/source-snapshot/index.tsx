import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {FullVideo} from './Full';

const Root=()=> <Composition id="HaikeInvestmentFull" component={FullVideo} width={1440} height={1800} fps={30} durationInFrames={900}
  defaultProps={{templateNumber:7,paletteVariant:'blue-beige',ratio:'4x5',width:1440,height:1800,fps:30,duration:30,durationInFrames:900,contentEndFrame:900,tailHoldFrames:0,
    avatarSrc:'',audioSrc:'',brand:'海客AI社区服务站',sourceEdits:[],cues:[],
    chapters:[{id:'preview',kind:'graphic',startFrame:0,endFrame:900,heading:['完整招商样片','视觉组件预览'],deck:'正式内容以本期冻结输入为准',points:[]}],shots:[],
    graphics:[{id:'preview-note',chapterId:'preview',kind:'list',heading:'预览不包含实际口播',items:['等待本期资产与字幕'],sourceCueIndices:[]}],soundEvents:[]}}/>;
registerRoot(Root);
