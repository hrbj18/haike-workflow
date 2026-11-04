// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {AgentSteps} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/agent-steps';
import {PromptSend} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/prompt-send';
import {FONT, MediaWindow, NativeViewport, Note} from '../shared';
import type {Episode, Scene} from '../types';

export function Workflow({scene, episode}: {scene: Scene; episode: Episode}) {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig(); const cue = scene.cues || {};
  const promptAt = cue.prompt ?? 2.4, stepsAt = cue.steps ?? 7.7, previewAt = cue.preview ?? 12.6;
  const step = frame < promptAt * fps ? '看清现场' : frame < stepsAt * fps ? '测完看报告' : frame < previewAt * fps ? '不看病不卖药' : '自己判断';
  return <>
    <div style={{position: 'absolute', left: 58, top: 72, fontSize: 22, fontWeight: 750, color: episode.palette.accent}}>{scene.title}　 /　{step}</div>
    <MediaWindow media={scene.media} x={105} y={119} w={1070} h={486} camera={[{at: Math.round(previewAt * fps), duration: 18, zoom: 1.08, x: .72, y: .55}]}/>
    <Sequence from={Math.round(promptAt * fps)} durationInFrames={Math.round((stepsAt - promptAt) * fps)} premountFor={fps}>
      <NativeViewport x={85} y={327} w={1110} h={290} nativeW={890} nativeH={486}><PromptSend text={episode.phrase} placeholder="先把话说明白" chips={['报告', '参考', '自己定']} fontFamily={FONT} fontSize={24} chipFontSize={18} width={755} fieldHeight={110} typeStart={.5} typeDuration={1.1} cutInAt={9} cutOutAt={10} zoomIn={1} zoomOut={1} cursorAt={1.8} clickAt={2.1} accentColor={episode.palette.accent}/></NativeViewport>
    </Sequence>
    <Sequence from={Math.round(stepsAt * fps)} durationInFrames={Math.round((previewAt - stepsAt) * fps)} premountFor={fps}>
      <NativeViewport x={75} y={170} w={470} h={410} nativeW={470} nativeH={1000}><AgentSteps query="到店了解" steps={[{running: '查看报告', done: '给您参考', hold: .75}, {running: '了解边界', done: '不看病不卖药', hold: .85}, {running: '自己判断', done: '选择由您', hold: .85}]} result="不是医疗诊断" queryHold={.5} finalHold={.65} fontFamily={FONT} paperColor="#f6faf6" glowRadius={0} accentColor={episode.palette.accent}/></NativeViewport>
    </Sequence>
    <Note text={scene.note || ''} x={107}/>
  </>;
}
