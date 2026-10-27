import React, { useEffect, useState } from 'react';
import { AbsoluteFill, Audio, Composition, Easing, Img, OffthreadVideo, Sequence, cancelRender, continueRender, delayRender, interpolate, registerRoot, spring, staticFile, useCurrentFrame } from 'remotion';
import type { Box, Media, Props, Scene } from './types';
const C = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const smooth = Easing.bezier(.25, .46, .45, .94), gentle = Easing.bezier(.45, 0, .55, 1);
const ramp = (f: number, a: number, b: number, e = smooth) => interpolate(f, [a, b], [0, 1], { ...C, easing: e });
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const mix = (a: Box, b: Box, t: number) => a.map((x, i) => lerp(x, b[i], t)) as Box;
const box = (b: Box): React.CSSProperties => ({ position: 'absolute', left: b[0], top: b[1], width: b[2], height: b[3], boxSizing: 'border-box' });
const HUM = { paper: '#F7F5EA', stock: '#FFFCF1', ink: '#17212B', muted: '#626976', accent: '#EACD38', blue: '#3176BB', coral: '#F16D6D', mint: '#A9D9B7', desk: '#E9E2CF', dark: '#17222E' };
const CORAL = { paper: '#F4F0ED', stock: '#FEFCF8', ink: '#302A27', muted: '#7B716B', accent: '#BA634F', blue: '#C7BDB6', coral: '#BA634F', mint: '#D9D1C8', desk: '#E9E3DD', dark: '#302B28' };
const palette = (p: Props) => p.visualStyle === 'coral' ? CORAL : HUM;
const titleFont = 'HaikeProductionDisplay', bodyFont = 'HaikeProductionBody';
const loads = new Map<string, Promise<void>>();
const Fonts: React.FC<{
    p: Props;
    children: React.ReactNode;
}> = ({ p, children }) => {
    const [handle] = useState(() => delayRender('Production CJK fonts', { timeoutInMilliseconds: 120000 }));
    useEffect(() => { const key = JSON.stringify(p.fontAssets); if (!loads.has(key))
        loads.set(key, (async () => { if (p.fontAssets) {
            const fonts = [new FontFace(titleFont, `url("${staticFile(p.fontAssets.display)}")`, { weight: '700' }), new FontFace(bodyFont, `url("${staticFile(p.fontAssets.body)}")`)];
            for (const font of fonts) {
                await font.load();
                document.fonts.add(font);
            }
            await document.fonts.ready;
        } })()); loads.get(key)!.then(() => continueRender(handle)).catch(cancelRender); }, [handle, p.fontAssets]);
    return <>{children}</>;
};
// Handmade-2D: stable, material-shaped edges; texture is one cached SVG tile.
const tile = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><filter id="g"><feTurbulence type="fractalNoise" baseFrequency=".7" numOctaves="2" seed="13" stitchTiles="stitch"/></filter><rect width="240" height="240" opacity=".16" filter="url(#g)"/></svg>')}`;
const rough = (seed: number) => `polygon(${['0% 0.8%', ...Array.from({ length: 20 }, (_, i) => `${(i + 1) * 5}% ${.5 + Math.abs(Math.sin(i * 2.19 + seed)) * .9}%`), '100% 99%', ...Array.from({ length: 21 }, (_, i) => `${100 - i * 5}% ${99.5 - Math.abs(Math.sin(i * 1.93 + seed)) * .8}%`)].join(',')})`;
const Grain = () => <AbsoluteFill style={{ backgroundImage: `url("${tile}")`, opacity: .23, mixBlendMode: 'multiply', pointerEvents: 'none' }}/>;
const Stock: React.FC<{
    p: Props;
    seed?: number;
    children?: React.ReactNode;
    style?: React.CSSProperties;
}> = ({ p, seed = 3, children, style }) => {
    const t = palette(p), coral = p.visualStyle === 'coral';
    return <div style={{ position: 'absolute', inset: 0, backgroundColor: t.stock, borderRadius: coral ? 9 : 24, clipPath: coral ? undefined : rough(seed), boxShadow: coral ? 'inset 1px 1px 1px #FFFFFFDD, inset -1px -1px 1px #715D4829, 12px 14px 28px #5A453222' : '5px 12px 22px #17212B28', ...style }}><Grain />{children}</div>;
};
const Backdrop: React.FC<{
    p: Props;
    dark: boolean;
}> = ({ p, dark }) => { const t = palette(p); return <AbsoluteFill style={{ backgroundColor: dark ? t.dark : t.paper, backgroundImage: dark ? undefined : `radial-gradient(100% 100% at 0% 28%,${t.stock},transparent 74%)` }}><Grain />{p.visualStyle === 'hum' && <><div style={{ position: 'absolute', left: -35, right: -35, top: 1490, height: 380, backgroundColor: t.mint, clipPath: rough(19), transform: 'rotate(-2deg)' }}/><div style={{ position: 'absolute', left: -35, right: -35, top: 1740, height: 130, backgroundColor: '#D8C29C', clipPath: rough(28), transform: 'rotate(1deg)' }}/></>}</AbsoluteFill>; };
const Heading: React.FC<{
    p: Props;
    s: Scene;
    f: number;
}> = ({ p, s, f }) => {
    const t = palette(p);
    return <>
 <div data-element="title" style={{ position: 'absolute', left: 88, top: 178, width: 1264, color: s.theme === 'dark' ? t.paper : t.ink, fontFamily: titleFont, fontSize: s.module === 'statement' ? 104 : 88, fontWeight: 700, lineHeight: 1.14, letterSpacing: -2, whiteSpace: 'pre' }}>{s.title.split('\n').map((x, i) => <div key={i} style={{ overflow: 'hidden', paddingBottom: 6 }}><div style={{ transform: `translateY(${(1 - ramp(f, i * 3, i * 3 + 18)) * 105}%)` }}>{x}</div></div>)}</div>
 {s.subtitle && <div style={{ position: 'absolute', left: 88, top: s.module === 'wall' ? 400 : s.module === 'statement' ? 447 : 410, width: 1264, fontFamily: bodyFont, fontSize: s.module === 'wall' ? 32 : 37, lineHeight: 1.4, color: s.theme === 'dark' ? '#DDD7CD' : t.muted, opacity: ramp(f, 8, 26), whiteSpace: 'pre' }}>{s.subtitle}</div>}
 </>;
};
const Thumb: React.FC<{
    m: Media;
}> = ({ m }) => <Img src={staticFile(m.thumbnail)} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain' }}/>;
const Live: React.FC<{
    m: Media;
    delay?: number;
    frames: number;
}> = ({ m, delay = 0, frames }) => m.kind === 'image' || (!m.kind && /\.(png|jpe?g|webp)$/i.test(m.src)) ? <Thumb m={m}/> : <Sequence layout="none" from={delay} durationInFrames={Math.max(1, frames - delay)}><OffthreadVideo src={staticFile(m.src)} startFrom={Math.round((m.offset || 0) * 30)} muted style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', objectPosition: m.objectPosition || '50% 50%' }}/></Sequence>;
/** Animated-video camera semantics: log zoom, depth-relative translation, then a locked hold.
 * Canvas dimensions are deliberately 1440x1800; no upstream 1080x1920 constants survive. */
export function cameraAt(f: number, depth = 1) { const u = ramp(f, 0, 42, gentle); return { x: lerp(18, 0, u) * depth, y: lerp(26, 0, u) * depth, scale: Math.exp(lerp(Math.log(.97), 0, u) * depth), rot: lerp(-.6, 0, u) * depth }; }
const Focus: React.FC<{
    p: Props;
    s: Scene;
}> = ({ p, s }) => {
    const f = useCurrentFrame(), t = palette(p), m = p.media.find(x => x.id === s.mediaId)!;
    const coral = p.visualStyle === 'coral', portrait = m.orientation === 'portrait';
    const b: Box = portrait ? (coral ? [454, 455, 750, 1060] : [348, 460, 744, 1060]) : [88, 535, 1264, 884];
    const cam = cameraAt(f), reveal = s.motion === 'paper-reveal' ? ramp(f, 0, 36, gentle) : 1;
    return <><Heading p={p} s={s} f={f}/><div style={{ ...box(b), perspective: 1600, transform: `translate(${cam.x}px,${cam.y}px) scale(${cam.scale}) rotate(${cam.rot}deg)` }}><div style={{ position: 'absolute', inset: -14, backgroundColor: coral ? t.desk : t.blue, transform: `rotate(${coral ? -2 : 2}deg)`, borderRadius: coral ? 7 : 22 }}/><Stock p={p}><div style={{ position: 'absolute', inset: 16, overflow: 'hidden', borderRadius: coral ? 4 : 17, backgroundColor: coral ? '#E3DAD2' : t.ink, clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)` }}><Live m={m} frames={s.frames}/></div>{reveal < 1 && <div style={{ position: 'absolute', top: 16, bottom: 16, left: `${Math.max(1, reveal * 100)}%`, width: 30, background: 'linear-gradient(90deg,#89786633,transparent)', transform: 'translateX(-15px)' }}/>}</Stock></div>
 <div style={{ position: 'absolute', left: 88, top: coral && portrait ? 980 : 1453, width: coral && portrait ? 280 : 930, fontFamily: bodyFont, fontSize: coral ? 32 : 36, lineHeight: 1.6, color: t.muted, opacity: ramp(f, 16, 40) }}>{m.label}</div>{coral && portrait && <div style={{ position: 'absolute', left: 88, top: 640, fontSize: 188, fontFamily: titleFont, color: t.accent, opacity: .7 }}>“</div>}</>;
};
// card-stack adapted from shotcraft CardStack.tsx: accelerating arrivals, damping13,
// 6f anticipation, damping20 fan, fixed z ordering, lift102f, hold>=30f.
const fanState = (f: number, i: number, n: number) => {
    const k = i - (n - 1) / 2;
    const startAt = (j:number) => 2 + (1 - Math.pow(1 - j / Math.max(1,n-1),3))*40;
    const start = startAt(i);
    const enterAt = (fr:number) => fr < start ? 0 : spring({frame:fr-start,fps:30,config:{damping:13,stiffness:150}});
    const enter = enterAt(f);
    const fan = f < 68 ? 0 : spring({frame:f-68,fps:30,config:{damping:20,stiffness:95}});
    const dip = Array.from({length:n},(_,j) => Math.sin(Math.min(1,Math.max(0,(f-startAt(j)-6)/9))*Math.PI)*5).reduce((a,b)=>a+b,0);
    const squeeze = 1-.02*Math.sin(Math.min(1,Math.max(0,(f-62)/10))*Math.PI);
    const tilt = (i%2?1:-1)*9*(1-enter);
    return {x:lerp(Math.sin(i*127.1)*11,k*188,fan), y:(1-enter)*820+dip,
        rot:lerp(Math.sin(i*311.7)*3.2+tilt,k*6.5,fan),scale:squeeze,opacity:f>=start?1:0,
        blur:Math.min(10,Math.abs((enterAt(f+.5)-enterAt(f-.5))*820)*.18)};
};
const Wall: React.FC<{
    p: Props;
    s: Scene;
}> = ({ p, s }) => {
    const f = useCurrentFrame(), t = palette(p), ids = s.wallMediaIds!, timing = s.selection!, expand = ramp(f, timing.expandFrom, timing.holdFrom), selected = p.media.find(x => x.id === s.mediaId)!, featured = ids.indexOf(selected.id), stack = s.motion === 'card-stack';
    const target: Box = selected.orientation === 'portrait' ? [348, 440, 744, 1090] : [88, 520, 1264, 900];
    const colors = p.visualStyle==='coral'?[t.desk,t.mint,t.blue,t.desk]:[t.accent,t.blue,t.coral,t.mint];
    const pos = (i: number): Box => stack ? [520, 620, 400, 650] : [88 + (i % 3) * 432, 520 + Math.floor(i / 3) * 405, 400, 365];
    const origin = pos(featured);
    const cursor = ramp(f, timing.cursorFrom, timing.selectFrom - 2);
    const fanCam=lerp(lerp(1,1.06,ramp(f,0,64,gentle)),.88,ramp(f,64,106,gentle))*lerp(1,1.017,ramp(f,122,150,gentle));
    const cam=stack?lerp(fanCam,1,expand):1;
    return <><Heading p={p} s={s} f={f}/>{!stack && <div style={{ position: 'absolute', left: 88, top: 456, display: 'flex', gap: 14, fontSize: 26, color: t.ink, opacity: 1 - expand }}>{(p.wallCategories || ['亲手体验', '机器人现场', '社区日常']).map((x, i) => <span key={x} style={{ backgroundColor: colors[i], padding: '9px 22px', borderRadius: p.visualStyle==='coral'?8:12, transform: `rotate(${i % 2 ? 1 : -1}deg)` }}>{x}</span>)}</div>}
 <AbsoluteFill style={{transform:`scale(${cam})`,transformOrigin:'720px 1040px',perspective:1800}}>
 {stack&&<div style={{position:'absolute',left:720-lerp(220,760,ramp(f,68,106))/2,top:1250,width:lerp(220,760,ramp(f,68,106)),height:70,borderRadius:'50%',background:'radial-gradient(ellipse,#302A2726,transparent 70%)',opacity:1-expand}}/>}
 {ids.map((id, i) => {
            const m = p.media.find(x => x.id === id)!, active = id === selected.id;
            const a = stack ? fanState(f, i, ids.length) : { x: 0, y: (1 - ramp(f, i * 3, i * 3 + 18)) * 64, rot: i % 2 ? 1.2 : -1.1, scale: .97 + .03 * ramp(f, i * 3, i * 3 + 18), opacity: ramp(f, i * 3, i * 3 + 18),blur:0 };
            const b = active ? mix(pos(i), target, expand) : pos(i);
            const lift = stack && active ? -72 * ramp(f, 102, 122) : 0;
            return <div key={id} data-element="wall-card" data-media-id={id} data-selected={active} style={{ ...box(b), zIndex: active && f >= timing.selectFrom ? 20 : i + 1, opacity: a.opacity * (active ? 1 : 1 - expand), transformOrigin: stack ? '50% 130%' : '50% 50%', transform: `translate(${a.x * (active ? 1 - expand : 1)}px,${(a.y + lift) * (active ? 1 - expand : 1)}px) rotate(${a.rot * (active ? 1 - expand : 1)}deg) scale(${lerp(a.scale, 1, active ? expand : 0)})` }}><div style={{ position: 'absolute', inset: -10, backgroundColor: active && f >= timing.selectFrom ? t.accent : colors[i % colors.length], borderRadius: 26, transform: 'rotate(-1.4deg)' }}/><Stock p={p} seed={i + 6}><div style={{ position: 'absolute', inset: '14px 14px 72px', overflow: 'hidden', borderRadius: 15, backgroundColor: t.ink }}><Thumb m={m}/>{active && <Live m={m} delay={timing.expandFrom} frames={s.frames}/>}</div><div style={{ position: 'absolute', left: 22, right: 22, bottom: 20, fontSize: 28 + expand * 8, color: t.ink, overflow: 'hidden', whiteSpace: 'nowrap' }}>{m.label}</div></Stock></div>;
        })}
 <div data-element="selection-cursor" style={{ position: 'absolute', zIndex: 40, left: lerp(1240, origin[0] + origin[2] * .6, cursor), top: lerp(450, origin[1] + origin[3] * .5, cursor), opacity: f < timing.cursorFrom ? 0 : 1 - ramp(f, timing.expandFrom, timing.expandFrom + 8) }}><svg width="52" height="62" viewBox="0 0 52 62"><path d="M4 3 L7 48 L19 37 L29 58 L39 53 L29 32 L46 31 Z" fill={t.ink} stroke={t.stock} strokeWidth="3" strokeLinejoin="round"/></svg></div></AbsoluteFill></>;
};
const Statement: React.FC<{
    p: Props;
    s: Scene;
}> = ({ p, s }) => { const f = useCurrentFrame(), t = palette(p), coral = p.visualStyle === 'coral', large = presenterAt(p, s.from + f)?.mode.mode === 'large'; return <>{large ? <Heading p={p} s={s} f={f}/> : <div style={{ position: 'absolute', left: 88, top: 210, fontSize: 37, color: s.theme === 'dark' ? t.paper : t.muted, opacity: ramp(f, 0, 20), whiteSpace: 'pre' }}>{s.subtitle}</div>}<div style={{ position: 'absolute', left: coral ? 180 : 190, top: coral ? 650 : 620, width: coral ? 1080 : 1060, height: coral ? 660 : 680, transform: `translateY(${(1 - ramp(f, 0, 32)) * 90}px) rotate(${coral ? -2 : 2}deg)`, opacity: large ? 0 : ramp(f, 0, 26) }}><div style={{ position: 'absolute', inset: -24, backgroundColor: coral ? t.desk : t.mint, transform: 'rotate(-3deg)', borderRadius: 12 }}/><Stock p={p}><div style={{ position: 'absolute', left: 58, top: 66, right: 58, color: t.ink, fontSize: coral ? 81 : 92, fontFamily: titleFont, lineHeight: 1.25, whiteSpace: 'pre' }}>{s.title}</div><div style={{ position: 'absolute', left: 58, right: 58, bottom: 130, height: 2, backgroundColor: coral ? '#D6CBC2' : t.blue }}/><div style={{ position: 'absolute', left: 58, bottom: 62, fontSize: 34, color: coral ? t.accent : t.blue }}>{p.brand}</div></Stock></div></>; };
export function presenterAt(p: Props, frame: number) { const index = (p.presenterModes || []).findIndex(m => frame >= m.from && frame < m.from + m.frames); if (index < 0)
    return null; const mode = p.presenterModes![index], clip = p.presenterClips!.find(c => c.id === mode.clipId)!; if (mode.mode === 'hidden')
    return null; const previous = p.presenterModes![index - 1], wasLarge = previous?.clipId === clip.id && previous.from + previous.frames === mode.from && previous.mode === 'large'; const factor = lerp(wasLarge ? 1 : mode.mode === 'large' ? 1 : 0, mode.mode === 'large' ? 1 : 0, ramp(frame, mode.from, mode.from + 18)); return { mode, clip, box: mix([1082, 1205, 270, 338], [300, 460, 840, 1060], factor), sourceSeconds: clip.offset + (frame - clip.from) / 30 }; }
const Presenter: React.FC<{
    p: Props;
}> = ({ p }) => { const frame = useCurrentFrame(), state = presenterAt(p, frame), t = palette(p); if (!state)
    return null; const { clip, box: b, mode } = state; return <div data-element="presenter" data-mode={mode.mode} style={{ ...box(b), zIndex: 45 }}><Stock p={p}><div style={{ position: 'absolute', inset: 10, overflow: 'hidden', borderRadius: p.visualStyle === 'coral' ? 5 : 18, backgroundColor: t.paper }}><Sequence layout="none" from={clip.from} durationInFrames={clip.frames}><OffthreadVideo src={staticFile(clip.src)} startFrom={Math.round(clip.offset * 30)} muted style={{ width: '100%', height: '100%', objectFit: 'contain', objectPosition: clip.objectPosition || '50% 50%' }}/></Sequence></div></Stock><div style={{ position: 'absolute', bottom: 20, left: 22, fontSize: mode.mode === 'large' ? 24 : 18, color: t.ink, backgroundColor: t.stock, padding: '4px 8px' }}>AI数字人演绎</div></div>; };
const Content: React.FC<Props> = p => { const f = useCurrentFrame(), s = p.scenes.find(x => f >= x.from && f < x.from + x.frames), t = palette(p), dark = s?.theme === 'dark', cue = p.captions.find(c => f / 30 * 1000 >= c.startMs && f / 30 * 1000 < c.endMs); return <AbsoluteFill style={{ overflow: 'hidden', fontFamily: bodyFont, backgroundColor: t.paper }}><Backdrop p={p} dark={!!dark}/>{p.scenes.map(scene => <Sequence key={scene.id} from={scene.from} durationInFrames={scene.frames}><AbsoluteFill>{scene.module === 'wall' ? <Wall p={p} s={scene}/> : scene.module === 'focus' ? <Focus p={p} s={scene}/> : <Statement p={p} s={scene}/>}</AbsoluteFill></Sequence>)}<Presenter p={p}/><div style={{ position: 'absolute', left: 88, right: 88, top: 64, zIndex: 50, display: 'flex', justifyContent: 'space-between', fontSize: 29, color: dark ? t.paper : t.ink }}><span>{p.brand}</span><span style={{ letterSpacing: 3, fontSize: 24 }}>HAIKE AI</span></div>{cue && <div data-element="caption" style={{ position: 'absolute', left: 88, top: 1580, width: 1264, height: 116, zIndex: 60, borderTop: `1px solid ${dark ? '#77716C' : '#CEC7BC'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 58, lineHeight: 1.3, textAlign: 'center', whiteSpace: 'pre', color: dark ? t.paper : t.ink }}>{cue.text}</div>}<div style={{ position: 'absolute', left: 88, top: 1730, width: 1264, fontSize: 25, color: dark ? '#DDD7CD' : t.muted, zIndex: 50 }}>{p.footer}</div>{p.audio && <Audio src={staticFile(p.audio)}/>}</AbsoluteFill>; };
export const HumProduction: React.FC<Props> = p => <Fonts p={p}><Content {...p}/></Fonts>;
const defaults: Props = { durationFrames: 600, brand: '海客AI社区服务店', footer: '', visualStyle: 'hum', media: [], scenes: [], captions: [] };
const Root = () => <Composition id="HumProduction" component={HumProduction} width={1440} height={1800} fps={30} durationInFrames={600} defaultProps={defaults} calculateMetadata={({ props }) => ({ durationInFrames: props.durationFrames })}/>;
registerRoot(Root);
