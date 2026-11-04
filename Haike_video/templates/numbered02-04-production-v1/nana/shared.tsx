// Generated additive adaptation; see build_sources.py and derivation.json.
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, cancelRender, continueRender, delayRender, Easing, Img, interpolate, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ScreenRecording} from '../../../motion-components/snapcn/upstream/registry/snap-cn/screen-recording';
import {TextReveal} from '../../../motion-components/snapcn/upstream/registry/snap-cn/text-reveal';
import type {Episode, Media, Scene} from './types';
import {VideoImage,CurrentEpisode,AbsoluteFrame} from '../Common';

export const FONT = 'Haike Nana Local';
export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
export const ease = Easing.bezier(.16, 1, .3, 1);
export const file = (name: string) => staticFile(name);
export function FontGate({font, children}: {font: string; children: React.ReactNode}) {
  const [handle] = useState(() => delayRender('加载本地中文字体'));
  useEffect(() => {
    new FontFace(FONT, `url("${file(font)}")`, {weight: '100 900'}).load().then(face => {document.fonts.add(face); continueRender(handle);}).catch(cancelRender);
  }, [font, handle]);
  return <>{children}</>;
}
export function Viewport({x, y, w, h, children, style = {}}: {x: number; y: number; w: number; h: number; children: React.ReactNode; style?: React.CSSProperties}) {
  const {fps} = useVideoConfig();
  return <div style={{position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden', ...style}}><Sequence width={w} height={h} premountFor={fps}>{children}</Sequence></div>;
}
export function Title({text, x = 56, y = 89, w = 1050, size = 32, color = '#16313a'}: {text: string; x?: number; y?: number; w?: number; size?: number; color?: string}) {
  return <Viewport x={x} y={y} w={Math.min(w, Math.max(size * 3, text.length * size))} h={70}><TextReveal text={text} fontSize={size} fontWeight={800} fontFamily={FONT} initialScale={1.02} introDuration={3} holdDuration={1} recedeDuration={3} assembleDuration={12} letterSpacing="0" color={color}/></Viewport>;
}
export function NativeViewport({x, y, w, h, nativeW, nativeH, children}: {x: number; y: number; w: number; h: number; nativeW: number; nativeH: number; children: React.ReactNode}) {
  const {fps} = useVideoConfig(); const scale = w / nativeW;
  return <div style={{position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden', borderRadius: 12}}><div style={{position: 'absolute', left: 0, top: (h - nativeH * scale) / 2, width: nativeW, height: nativeH, transform: `scale(${scale})`, transformOrigin: '0 0'}}><Sequence width={nativeW} height={nativeH} premountFor={fps}>{children}</Sequence></div></div>;
}
export function Backdrop({episode, grid = false}: {episode: Episode; grid?: boolean}) {
  return <AbsoluteFill style={{background: grid ? '#ebece6' : episode.palette.paper}}>
    <div style={{position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 87% 40%, ${episode.palette.accent}20, transparent 61%), radial-gradient(ellipse at 7% 95%, #bdd5ed55, transparent 67%)`}}/>
    {grid && <AbsoluteFill style={{opacity: .3, backgroundImage: 'linear-gradient(#bfc9c755 1px,transparent 1px),linear-gradient(90deg,#bfc9c755 1px,transparent 1px)', backgroundSize: '72px 72px'}}/>}
  </AbsoluteFill>;
}
export function Shell({episode}: {episode: Episode}) {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const scene = episode.scenes.find(s => frame >= Math.round(s.start * fps) && frame < Math.round(s.end * fps)) || episode.scenes[0];
  return <>
    <div style={{position: 'absolute', left: 0, top: 0, width: 1280, height: 48, background: '#f7fbfc', borderBottom: '1px solid #c9d9d5', display: 'flex', alignItems: 'center', padding: '0 30px', gap: 30, fontSize: 15, color: '#748285', whiteSpace: 'nowrap'}}>
      <span style={{fontSize: 17, fontWeight: 800, color: episode.palette.accent}}>{episode.brand} × {episode.partner}</span>
      {episode.chapters.map((label, i) => <span key={i} style={{color: scene.chapter === i ? episode.palette.accent : '#748285', fontWeight: scene.chapter === i ? 800 : 400}}>{String(i + 1).padStart(2, '0')} {label}</span>)}
    </div>
    <div style={{position: 'absolute', left: 0, top: 46, height: 2, width: 1280 * (frame + 1) / Math.round(episode.duration * fps), background: episode.palette.accent}}/>
  </>;
}
export function Presenter({media, x, y, w, h, tilt = 0}: {media?: Media; x: number; y: number; w: number; h: number; tilt?: number}) {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const global=React.useContext(AbsoluteFrame),episode=React.useContext(CurrentEpisode);
  if (!media || (media.role==='avatar' && !episode.presenters.some(c=>c.from<=global&&global<c.to))) return null;
  return <div data-element="presenter" style={{position: 'absolute', left: x, top: y, width: w, height: h, borderRadius: 16, overflow: 'hidden', boxShadow: '0 15px 28px -15px #223a4c55', transformOrigin: '50% 50%', transform: `perspective(1400px) rotateY(${tilt}deg)`, opacity: interpolate(f, [0, 10], [.85, 1], clamp)}}>
    <VideoImage src={media.file} style={{width:'100%',height:'100%',objectFit:'cover'}}/>
    <span style={{position:'absolute',bottom:0,left:0,right:0,padding:7,fontSize:14,fontWeight:800,textAlign:'center',background:'#124a49',color:'#fff'}}>{media.role==='avatar'?'侯总 · AI数字人':'门店实拍'}</span>
  </div>;
}
export function MediaWindow({media, x = 56, y = 170, w = 800, h = 438, camera = [], entrance = 'none'}: {media?: Media; x?: number; y?: number; w?: number; h?: number; camera?: {at: number; duration?: number; zoom: number; x?: number; y?: number}[]; entrance?: 'none' | 'fade'}) {
  if (!media) return null;
  return <Viewport x={x} y={y} w={w} h={h} style={{borderRadius: 14, boxShadow: '0 14px 30px -15px #3f737c44'}}><ScreenRecording src={file(media.file)} sourceAspect={media.width / media.height} fit="contain" backdropColor="#f3f8f5" camera={camera} entrance={entrance} audio={false}/></Viewport>;
}
export function Label({children, x, y, active = false, episode}: {children: React.ReactNode; x: number; y: number; active?: boolean; episode: Episode}) {
  const frame = useCurrentFrame();
  return <div style={{position: 'absolute', left: x, top: y, padding: '10px 19px', fontSize: 25, fontWeight: 750, borderRadius: 7, color: active ? '#fff' : episode.palette.accent, background: active ? episode.palette.accent : '#fcfffd', border: `1px solid ${episode.palette.accent}88`, opacity: interpolate(frame, [0, 9], [0, 1], clamp), translate: `0 ${interpolate(frame, [0, 12], [13, 0], {...clamp, easing: ease})}px`}}>{children}</div>;
}
export function Arrow({at = 0, x, y, w, color}: {at?: number; x: number; y: number; w: number; color: string}) {
  const frame = useCurrentFrame(); const p = interpolate(frame, [at, at + 18], [0, 1], {...clamp, easing: ease});
  return <svg style={{position: 'absolute', left: x, top: y, width: w, height: 26, overflow: 'visible'}} viewBox={`0 0 ${w} 26`}><path d={`M0 13H${w - 8}m-8 -10 10 10 -10 10`} fill="none" stroke={color} strokeWidth="2.4" pathLength="1" strokeDasharray="1" strokeDashoffset={1 - p}/></svg>;
}
export function Note({text, x = 60, y = 615}: {text: string; x?: number; y?: number}) {
  return <div style={{position: 'absolute', left: x, top: y, color: '#647674', fontSize: 15}}>{text}</div>;
}
export function Still({src}: {src: string}) {return <Img src={file(src)} style={{width: '100%', height: '100%', objectFit: 'contain'}}/>;}
