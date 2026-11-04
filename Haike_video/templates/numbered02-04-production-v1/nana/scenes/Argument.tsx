// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {AbsoluteFill, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {TextBuild} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-build';
import {TextHighlight} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-highlight';
import {TextSwap} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-swap';
import {Arrow, clamp, ease, FONT, Note, Presenter, Title, Viewport} from '../shared';
import type {Episode, Scene} from '../types';

export function Argument({scene, episode}: {scene: Scene; episode: Episode}) {
  const f = useCurrentFrame(); const {fps} = useVideoConfig(); const p = episode.palette; const labels = scene.labels || [];
  if (scene.id === 'compare') return <>
    <Presenter media={scene.presenter} x={60} y={115} w={330} h={495}/>
    <div style={{position: 'absolute', left: 446, top: 103, fontSize: 28, fontWeight: 800}}>{scene.title}</div>
    <div style={{position: 'absolute', left: 700, top: 230, fontSize: 15, color: '#748581'}}>想法</div>
    <Viewport x={650} y={260} w={560} h={100}><TextBuild text={labels[0] || ''} fontSize={54} fontWeight={800} fontFamily={FONT} color={p.ink}/></Viewport>
    <Arrow x={590} y={365} w={400} at={Math.round((scene.cues?.arrow ?? 2.1) * fps)} color={p.accent}/>
    <Sequence from={Math.round((scene.cues?.after ?? 3.3) * fps)} premountFor={fps}>
      <div style={{position: 'absolute', left: 700, top: 425, fontSize: 15, color: '#748581'}}>说明白</div>
      <Viewport x={650} y={455} w={560} h={90}><TextHighlight highlight={labels[1] || ''} preset="color" startAt={0} drawDuration={15} fontSize={53} fontWeight={850} fontFamily={FONT} baseColor={p.ink} accentColor={p.accent}/></Viewport>
    </Sequence><Note text={scene.note || ''} x={445}/>
  </>;
  if (scene.id === 'question') return <>
    <Presenter media={scene.presenter} x={65} y={108} w={705} h={500}/>
    <div style={{position: 'absolute', left: 830, top: 158, fontSize: 15, color: '#8e81a3'}}>决定在您</div>
    <Viewport x={800} y={190} w={410} h={95}><TextBuild text={labels[0] || ''} fontSize={45} fontWeight={850} fontFamily={FONT} color={p.ink}/></Viewport>
    <Viewport x={800} y={280} w={410} h={95}><TextSwap fromText="" toText={labels[1] || ''} transition="fade-through" fontSize={43} fontWeight={800} color={p.accent} fontFamily={FONT}/></Viewport>
    <Sequence from={Math.round((scene.cues?.answer ?? 2.5) * fps)} premountFor={fps}><div style={{position: 'absolute', left: 820, top: 405, width: 380, background: p.sheet, borderRadius: 10, padding: '25px', color: p.accent, fontSize: 32, fontWeight: 800}}>{labels[2]}</div></Sequence>
  </>;
  if (scene.id === 'value') return <>
    <Presenter media={scene.presenter} x={360} y={72} w={560} h={550}/>
    <div style={{position: 'absolute', left: 570, top: 70, fontSize: 24, fontWeight: 850, color: '#8b6e17', background: '#fff7b7', padding: '6px 16px'}}>{scene.title}</div>
    {[0, 1].map(i => <div key={i} style={{position: 'absolute', left: i ? 945 : 45, top: i ? 145 : 120, width: 285, height: i ? 340 : 390, background: '#fffef0', borderRadius: 8, boxShadow: '0 8px 25px #163d3f20', padding: 22, opacity: interpolate(f, [i * 6, i * 6 + 10], [0, 1], clamp), translate: `${interpolate(f, [i * 6, i * 6 + 16], [i ? 40 : -40, 0], {...clamp, easing: ease})}px 0`}}>
      <div style={{fontSize: 12, color: '#927626', marginBottom: 35}}>● ● ●　{i ? '日常用品' : '免费参考'}</div>
      <div style={{fontSize: 27, fontWeight: 800, lineHeight: 1.8}}>{labels[i * 2]}</div>
      {i === 1 && <Arrow x={25} y={156} w={225} color={p.accent} at={Math.round(1.2 * fps)}/>}
      <div style={{fontSize: 25, fontWeight: 800, marginTop: i ? 93 : 20, lineHeight: 1.6}}>{labels[i * 2 + 1]}</div>
    </div>)}
  </>;
  return <>
    <AbsoluteFill style={{backgroundImage: 'linear-gradient(#a6b6af14 1px,transparent 1px),linear-gradient(90deg,#a6b6af14 1px,transparent 1px)', backgroundSize: '72px 72px'}}/>
    <Presenter media={scene.presenter} x={65} y={116} w={500} h={496} tilt={-3}/>
    <div style={{position: 'absolute', left: 620, top: 135, fontSize: 14, letterSpacing: 3, color: p.accent}}>买不买，自己定</div>
    <Title text={scene.title} x={595} y={165} w={610} size={49} color="#0b1713"/>
    {labels.map((label, i) => <Sequence key={i} from={Math.round((.35 + i * .65) * fps)} premountFor={fps}><div style={{position: 'absolute', left: 620, top: 292 + 91 * i, width: 590, height: 69, background: '#fff', border: '1px solid #d9e0da', borderRadius: 12, padding: '15px 25px', fontSize: 27, fontWeight: 750}}><span style={{color: p.accent}}>•　</span>{label}</div></Sequence>)}
  </>;
}
