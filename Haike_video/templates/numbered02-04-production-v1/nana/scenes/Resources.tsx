// Generated additive adaptation; see build_sources.py and derivation.json.
import React from 'react';
import {Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {CaptureReveal} from '../CaptureReveal';
import {TextBuild} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-build';
import {TextHighlight} from '../../../../motion-components/snapcn/upstream/registry/snap-cn/text-highlight';
import {Arrow, file, FONT, MediaWindow, Presenter, Title, Viewport} from '../shared';
import type {Episode, Scene} from '../types';

export function Resources({scene, episode}: {scene: Scene; episode: Episode}) {
  const {fps} = useVideoConfig(); const f = useCurrentFrame(); const p = episode.palette;
  if (scene.id === 'course') return <>
    <Presenter media={scene.presenter} x={65} y={110} w={430} h={495}/>
    <div style={{position: 'absolute', left: 555, top: 160, fontSize: 15, color: '#8b80b6'}}>在店里，自己看</div>
    <Viewport x={535} y={196} w={680} h={90}><TextBuild text={scene.title} fontSize={48} fontWeight={850} fontFamily={FONT} color={p.ink}/></Viewport>
    <Viewport x={535} y={280} w={680} h={75}><TextHighlight highlight="按需要选" preset="color" fontFamily={FONT} fontSize={46} fontWeight={800} baseColor={p.ink} accentColor={p.accent}/></Viewport>
    {(scene.labels || []).map((label, i) => <Sequence key={i} from={Math.round((.65 + i * .36) * fps)} premountFor={fps}><div style={{position: 'absolute', left: 555 + 225 * i, top: 392, width: 183, height: 150, borderRadius: 13, padding: '20px 17px', background: '#f7fffa'}}><div style={{fontSize: 13, color: '#7d8d88'}}>0{i + 1}</div><div style={{fontSize: 32, fontWeight: 800, marginTop: 25, color: [p.accent, '#6852a5', '#a56536'][i]}}>{label}</div>{i < 2 && <Arrow x={190} y={65} w={27} color={p.accent}/>}</div></Sequence>)}
  </>;
  if (scene.id === 'examples') return <>
    <Title text={scene.title} x={58} y={68} w={1040} size={33}/>
    <Viewport x={60} y={158} w={830} h={451}><CaptureReveal headline="看现场 | 看报告 | 自己判断" capturing="了解现场" copied="给您个参考" src={file(scene.media!.file)} fontFamily={FONT} theme={{background: p.paper, foreground: p.ink, primary: p.accent, card: p.sheet}}/></Viewport>
    {(!scene.overlay || f < (scene.cues?.presenterOff ?? 2.3) * fps) && <Presenter media={scene.presenter} x={950} y={157} w={280} h={452}/>}
    {scene.overlay && <Sequence from={Math.round((scene.cues?.overlay ?? 2.4) * fps)} premountFor={fps}><MediaWindow media={scene.overlay} x={105} y={160} w={1070} h={450}/></Sequence>}
  </>;
  if (scene.id === 'logic') return <>
    <Title text={scene.title} x={58} y={77} w={1100} size={38}/>
    {(scene.labels || []).map((label, i) => <Sequence key={i} from={Math.round(i * .4 * fps)} premountFor={fps}><div style={{position: 'absolute', left: 70 + i * 405, top: 300, width: 365, height: 220, background: '#fafff9', borderRadius: 12, padding: '30px 26px', boxShadow: '0 8px 20px #30554e0d'}}><div style={{fontSize: 14, color: '#81958e'}}>0{i + 1} / {i === 2 ? 'OUTPUT' : 'PROCESS'}</div><Viewport x={14} y={82} w={337} h={90}><TextBuild text={label} fontSize={37} fontWeight={800} fontFamily={FONT} color={[p.accent, '#6852a5', '#a56536'][i]}/></Viewport>{i < 2 && <Arrow x={372} y={95} w={28} color={p.accent}/>}</div></Sequence>)}
    {scene.media && f < Math.round((scene.cues?.overlayEnd ?? 2.1) * fps) && <MediaWindow media={scene.media} x={105} y={160} w={1070} h={438}/>} 
  </>;
  return <>
    <Presenter media={scene.presenter} x={345} y={68} w={590} h={565}/>
    <Sequence from={Math.round(.3 * fps)} premountFor={fps}><div style={{position: 'absolute', left: 60, top: 200, width: 305, minHeight: 236, borderRadius: 13, padding: 26, background: '#f6fffc', boxShadow: '0 12px 25px #234c4120'}}><div style={{fontSize: 20}}>陈家林路63号</div><Viewport x={5} y={49} w={295} h={105}><TextHighlight highlight={scene.labels?.[0] || '您自己定'} preset="marker" fontFamily={FONT} fontSize={60} fontWeight={850} baseColor={p.accent} accentColor="#c9eee4"/></Viewport><div style={{fontSize: 17, marginTop: 116}}>{scene.labels?.[1] || '未来汇一楼'}</div></div></Sequence>
  </>;
}
