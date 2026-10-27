import React from 'react';
import {AbsoluteFill, Audio, Composition, Folder, registerRoot, staticFile} from 'remotion';
import type {LabProps} from './types';
import {Style03,Style04,Style05,Style06} from './styles03to06';
import {Style07,Style08,Style09,Style10} from './styles07to10';
import {SANS} from './shared';
import {activePalette} from './palettes';
import layout from './layout.json';

const defaults:LabProps={templateNumber:3,ratio:'9x16',width:1080,height:1920,fps:30,durationInFrames:360,
  avatarSrc:'source.mp4',audioSrc:'mixed-master.wav',cues:[],brand:'海客AI社区服务站',
  headline:'流量来了',cta:'',beatTitles:['流量来了','生意留下了吗？','找选题 · 拍素材','做带货，佣金和规则']};
const styles:Record<number,React.FC<LabProps>>={3:Style03,4:Style04,5:Style05,6:Style06,7:Style07,8:Style08,9:Style09,10:Style10};
export const LabVideo:React.FC<LabProps>=p=>{
  activePalette(p);
  const Style=styles[p.templateNumber];
  if(!Style)throw new Error('Unknown investment template number');
  return <AbsoluteFill style={{fontFamily:SANS,overflow:'hidden'}}>
    <Style {...p}/>
    {p.audioSrc&&<Audio src={staticFile(p.audioSrc)} volume={1}/>}
  </AbsoluteFill>;
};
const metadata=({props}:{props:LabProps})=>({width:props.width,height:props.height,fps:props.fps,durationInFrames:props.durationInFrames});
const common={component:LabVideo,width:1080,height:1920,fps:layout.fps,durationInFrames:layout.durationInFrames,calculateMetadata:metadata};
const paletteDefaults:LabProps={...defaults,ratio:'4x5',width:1440,height:1800};
const Root=()=> <>
  <Composition id="HaikeInvestmentStyleLab" {...common} defaultProps={defaults}/>
  <Folder name="招商视频模板3至10">
    <Composition id="InvestmentTemplate03" {...common} defaultProps={{...defaults,templateNumber:3}}/>
    <Composition id="InvestmentTemplate04" {...common} defaultProps={{...defaults,templateNumber:4}}/>
    <Composition id="InvestmentTemplate05" {...common} defaultProps={{...defaults,templateNumber:5}}/>
    <Composition id="InvestmentTemplate06" {...common} defaultProps={{...defaults,templateNumber:6}}/>
    <Composition id="InvestmentTemplate07" {...common} defaultProps={{...defaults,templateNumber:7}}/>
    <Composition id="InvestmentTemplate08" {...common} defaultProps={{...defaults,templateNumber:8}}/>
    <Composition id="InvestmentTemplate09" {...common} defaultProps={{...defaults,templateNumber:9}}/>
    <Composition id="InvestmentTemplate10" {...common} defaultProps={{...defaults,templateNumber:10}}/>
  </Folder>
  <Folder name="招商配色测试4比5">
    <Composition id="Investment07BlueBeige" {...common} width={1440} height={1800} defaultProps={{...paletteDefaults,templateNumber:7,paletteVariant:'blue-beige'}}/>
    <Composition id="Investment08CyanCharcoal" {...common} width={1440} height={1800} defaultProps={{...paletteDefaults,templateNumber:8,paletteVariant:'cyan-charcoal'}}/>
    <Composition id="Investment09BlackPink" {...common} width={1440} height={1800} defaultProps={{...paletteDefaults,templateNumber:9,paletteVariant:'black-pink'}}/>
  </Folder>
</>;
registerRoot(Root);
