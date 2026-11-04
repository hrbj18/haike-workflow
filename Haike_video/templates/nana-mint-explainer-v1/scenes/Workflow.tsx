import React from 'react';
import {Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {AgentSteps} from '../../../motion-components/snapcn/upstream/registry/snap-cn/agent-steps';
import {PromptSend} from '../../../motion-components/snapcn/upstream/registry/snap-cn/prompt-send';
import {FONT, MediaWindow, NativeViewport, Note} from '../shared';
import type {Episode, Scene} from '../types';

export function Workflow({scene, episode}: {scene: Scene; episode: Episode}) {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig(); const cue = scene.cues || {};
  const promptAt = cue.prompt ?? 2.4, stepsAt = cue.steps ?? 7.7, previewAt = cue.preview ?? 12.6;
  const step = frame < promptAt * fps ? '上传素材' : frame < stepsAt * fps ? '描述需求' : frame < previewAt * fps ? '打开可视窗口' : '查看剪辑结果';
  return <>
    <div style={{position: 'absolute', left: 58, top: 72, fontSize: 22, fontWeight: 750, color: episode.palette.accent}}>{scene.title}　 /　{step}</div>
    <MediaWindow media={scene.media} x={105} y={119} w={1070} h={486} camera={[{at: Math.round(previewAt * fps), duration: 18, zoom: 1.08, x: .72, y: .55}]}/>
    <Sequence from={Math.round(promptAt * fps)} durationInFrames={Math.round((stepsAt - promptAt) * fps)} premountFor={fps}>
      <NativeViewport x={85} y={327} w={1110} h={290} nativeW={890} nativeH={486}><PromptSend text={episode.phrase} placeholder="描述你想做的视频" chips={['时长', '风格', '给谁看']} fontFamily={FONT} fontSize={24} chipFontSize={18} width={755} fieldHeight={110} typeStart={.5} typeDuration={2.4} cutInAt={9} cutOutAt={10} zoomIn={1} zoomOut={1} cursorAt={3.4} clickAt={4.1} accentColor={episode.palette.accent}/></NativeViewport>
    </Sequence>
    <Sequence from={Math.round(stepsAt * fps)} durationInFrames={Math.round((previewAt - stepsAt) * fps)} premountFor={fps}>
      <NativeViewport x={75} y={170} w={470} h={410} nativeW={470} nativeH={1000}><AgentSteps query="开始剪辑" steps={[{running: '读取素材', done: '素材就绪', hold: .75}, {running: '编排镜头', done: '镜头已编排', hold: .85}, {running: '合成字幕与声音', done: '合成完成', hold: .85}]} result="打开预览窗口" queryHold={.5} finalHold={.65} fontFamily={FONT} paperColor="#f6faf6" glowRadius={0} accentColor={episode.palette.accent}/></NativeViewport>
    </Sequence>
    <Note text={scene.note || ''} x={107}/>
  </>;
}
