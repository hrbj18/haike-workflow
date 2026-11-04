// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {TextBuild} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-build';
import {TextReveal} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-reveal';
import {PromptSend} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/prompt-send';
import {Arrow, FONT, Label, MediaWindow, Note, Presenter, Title, Viewport} from '../shared';
import type {Episode, Scene} from '../types';

export function Introduction({scene, episode}: {scene: Scene; episode: Episode}) {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig(); const accent = episode.palette.accent;
  if (scene.id === 'integration') return <>
    <Viewport x={40} y={67} w={400} h={100}><TextBuild text={episode.brand} fontSize={65} fontWeight={800} color="#080c0b" fontFamily={FONT}/></Viewport>
    <Sequence from={Math.round((scene.cues?.partner ?? 2.3) * fps)} premountFor={fps}><Viewport x={415} y={90} w={300} h={68}><TextReveal text={`× ${episode.partner}`} fontSize={38} fontWeight={750} fontFamily={FONT} color={accent} initialScale={1.05} introDuration={3} holdDuration={1} recedeDuration={4} assembleDuration={14}/></Viewport></Sequence>
    <Arrow x={705} y={111} w={130} at={Math.round((scene.cues?.arrow ?? 3.4) * fps)} color={accent}/>
    <MediaWindow media={scene.media} x={50} y={180} w={790} h={430}/>
    <Presenter media={scene.presenter} x={892} y={163} w={340} h={450}/>
    <Note text={scene.note || ''}/>
  </>;
  if (scene.id === 'terms') return <>
    {(scene.labels || []).map((label, i) => <Label key={label} x={55 + i * 125} y={76} active={Math.min(2, Math.floor(frame / (1.75 * fps))) === i} episode={episode}>{label}</Label>)}
    <MediaWindow media={scene.media} x={56} y={174} w={850} h={425} camera={[{at: Math.round(2.5 * fps), duration: 13, zoom: 1.13, x: .53, y: .65}]}/>
    <Presenter media={scene.presenter} x={944} y={165} w={286} h={440}/><Note text={scene.note || ''}/>
  </>;
  if (scene.id === 'brief') return <>
    <Title text={scene.title} x={56} y={72} w={720}/>
    <MediaWindow media={scene.media} x={56} y={155} w={800} h={450}/>
    <Sequence from={Math.round((scene.cues?.presenter ?? 2.1) * fps)} premountFor={fps}><Presenter media={scene.presenter} x={938} y={155} w={292} h={450}/></Sequence>
    {(scene.labels || []).map((label, i) => <Sequence key={i} from={Math.round(((scene.cues?.labelStart ?? .25) + i * (scene.cues?.labelStagger ?? .82)) * fps)} premountFor={fps}><Label x={100 + i * 276} y={558} episode={episode}>{label}</Label></Sequence>)}
  </>;
  return <>
    <Title text={scene.title} y={74}/>
    <MediaWindow media={scene.media} x={55} y={170} w={790} h={425}/>
    <MediaWindow media={scene.overlay} x={954} y={170} w={245} h={425}/>
    <Note text={scene.note || ''}/>
  </>;
}
