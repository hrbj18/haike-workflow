// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {AbsoluteFill, Audio, Composition, OffthreadVideo, registerRoot, Sequence, staticFile, useVideoConfig} from 'remotion';
import {SnapCnUIProvider} from '../../../motion-components/snapcn/upstream/registry/snap-cn-ui/core';
import {WordCaptions} from '../../../motion-components/snapcn/upstream/registry/snap-cn/word-captions';
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

      </SnapCnUIProvider>
    </Sequence></div>

  </AbsoluteFill></FontGate>;
}
