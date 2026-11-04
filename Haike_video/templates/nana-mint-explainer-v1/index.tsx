import React from 'react';
import {AbsoluteFill, Audio, Composition, OffthreadVideo, registerRoot, Sequence, staticFile, useVideoConfig} from 'remotion';
import {SnapCnUIProvider} from '../../motion-components/snapcn/upstream/registry/snap-cn-ui/core';
import {WordCaptions} from '../../motion-components/snapcn/upstream/registry/snap-cn/word-captions';
import {Backdrop, file, FontGate, FONT, Shell} from './shared';
import {Introduction} from './scenes/Introduction';
import {Workflow} from './scenes/Workflow';
import {Argument} from './scenes/Argument';
import {Resources} from './scenes/Resources';
import type {Episode, TemplateProps} from './types';

export const resolveEpisode = async ({props}: {props: TemplateProps}) => {
  if (!/^[a-zA-Z0-9_.-]+\.json$/.test(props.episodeFile)) throw Error('请选择本地本期内容JSON。');
  const response = await fetch(staticFile(props.episodeFile));
  if (!response.ok) throw Error('本期输入未准备；先按README运行prepare。');
  const episode: Episode = await response.json();
  if (episode.version !== 1 || episode.fps !== 30 || !episode.scenes.length) throw Error('模板输入版本或时钟不正确。');
  return {durationInFrames: Math.round(episode.duration * episode.fps), props: {...props, episode}};
};
export function NanaTemplate({episode}: TemplateProps) {
  const {fps, width} = useVideoConfig();
  if (!episode) return null;
  const p = episode.palette;
  return <FontGate font={episode.font}><AbsoluteFill style={{fontFamily: FONT, color: p.ink, background: p.paper, overflow: 'hidden'}}>
    <style>{`*,*:before,*:after{box-sizing:border-box}.nana-captions{padding-bottom:1.7%!important}.nana-captions span{letter-spacing:0!important}`}</style>
    <div style={{position: 'absolute', left: 0, top: 0, width: 1280, height: 720, transform: `scale(${width / 1280})`, transformOrigin: '0 0'}}><Sequence width={1280} height={720} premountFor={fps}>
      <SnapCnUIProvider theme={{background: p.paper, foreground: p.ink, primary: p.accent, card: p.sheet, border: p.line, fontFamily: FONT}}>
        <Backdrop episode={episode}/>
        {/* All instances are intentionally controlled by one authored episode table. */}
        {episode.scenes.map(scene => <Sequence key={scene.id} name={scene.title} from={Math.round(scene.start * fps)} durationInFrames={Math.round(scene.end * fps) - Math.round(scene.start * fps)} premountFor={fps}>
          {['integration', 'terms', 'brief', 'result'].includes(scene.id) ? <Introduction scene={scene} episode={episode}/> : scene.id === 'workflow' ? <Workflow scene={scene} episode={episode}/> : ['compare', 'question', 'value', 'difference'].includes(scene.id) ? <Argument scene={scene} episode={episode}/> : <Resources scene={scene} episode={episode}/>}
        </Sequence>)}
        <Shell episode={episode}/>
        <WordCaptions className="nana-captions" words={episode.captions.map(cue => ({text: cue.text, startFrame: Math.round(cue.startMs * fps / 1000), endFrame: Math.round(cue.endMs * fps / 1000)}))} groupSize={1} activeStyle="color" preset="clean" aspect="16:9" fontFamily={FONT} fontSize={28} fontWeight={750} textColor="#fff" accentColor="#fff" strokeRatio={0} pillColor="#171e1cf5" maxWidth={1160}/>
      </SnapCnUIProvider>
    </Sequence></div>
    <Audio src={file(episode.voice)} premountFor={fps}/>
  </AbsoluteFill></FontGate>;
}
export function NanaReference({episode}: TemplateProps) {
  const {fps} = useVideoConfig();
  return episode?.reference ? <OffthreadVideo src={file(episode.reference)} premountFor={fps} style={{width: '100%', height: '100%'}}/> : <AbsoluteFill/>;
}
export const resolveReferenceEpisode = async (input: {props: TemplateProps}) => {
  const result = await resolveEpisode(input);
  return {...result, durationInFrames: Math.round((result.props.episode.referenceClock?.duration ?? result.props.episode.duration) * result.props.episode.fps)};
};
export function ReferenceOnNewClock({episode}: {episode: Episode}) {
  const {fps} = useVideoConfig();
  if (!episode.reference) return <AbsoluteFill/>;
  const anchors = episode.referenceClock?.anchors;
  if (!anchors) return <OffthreadVideo src={file(episode.reference)} muted premountFor={fps} style={{width: '100%', height: '100%'}}/>;
  // Only the silent visual reference follows the new measured speech clock.
  // The new presenter, new voice and standalone original stay at native speed.
  return <>{anchors.slice(0, -1).map(([sourceStart, newStart], i) => {
    const [sourceEnd, newEnd] = anchors[i + 1];
    const from = Math.round(newStart * fps), end = Math.round(newEnd * fps);
    if (end <= from) return null;
    return <Sequence key={i} name="原片语义对照" from={from} durationInFrames={end - from} premountFor={fps}><OffthreadVideo src={file(episode.reference!)} muted trimBefore={Math.round(sourceStart * fps)} playbackRate={(sourceEnd - sourceStart) / (newEnd - newStart)} premountFor={fps} style={{width: '100%', height: '100%'}}/></Sequence>;
  })}</>;
}
export function NanaComparison(props: TemplateProps) {
  const {fps} = useVideoConfig();
  return <AbsoluteFill style={{background: '#edf5ef'}}>
    <Sequence width={1280} height={720} premountFor={fps}><ReferenceOnNewClock episode={props.episode!}/></Sequence>
    <div style={{position: 'absolute', left: 1280, top: 0, width: 1280, height: 720}}><Sequence width={1280} height={720} premountFor={fps}><NanaTemplate {...props}/></Sequence></div>
  </AbsoluteFill>;
}
registerRoot(() => <>
  <Composition id="NanaTemplate" component={NanaTemplate} width={1920} height={1080} fps={30} durationInFrames={2236} defaultProps={{episodeFile: 'content.json'}} calculateMetadata={resolveEpisode}/>
  <Composition id="NanaReference" component={NanaReference} width={1280} height={720} fps={30} durationInFrames={2236} defaultProps={{episodeFile: 'content.json'}} calculateMetadata={resolveReferenceEpisode}/>
  <Composition id="NanaComparison" component={NanaComparison} width={2560} height={720} fps={30} durationInFrames={2236} defaultProps={{episodeFile: 'content.json'}} calculateMetadata={resolveEpisode}/>
</>);
