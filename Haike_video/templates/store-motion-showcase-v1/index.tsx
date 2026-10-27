import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill, Audio, Composition, Easing, OffthreadVideo, Sequence,
  cancelRender, continueRender, delayRender, interpolate, registerRoot,
  staticFile, useCurrentFrame,
} from 'remotion';
import geometryJson from './layout.json';
import type {Box, ShowcaseGeometry, ShowcaseProps, ShowcaseShot} from './types';

export type {ShowcaseProps, ShowcaseShot} from './types';

const geometry = geometryJson as ShowcaseGeometry;
const DISPLAY = 'HaikeShowcaseDisplay';
const BODY = 'HaikeShowcaseBody';
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const ease = Easing.bezier(.16, .78, .18, 1);
const fontLoads = new Map<string, Promise<void>>();

const rectangle = (box: Box): React.CSSProperties => ({
  position: 'absolute', left: box[0], top: box[1], width: box[2], height: box[3],
  boxSizing: 'border-box',
});

/** Geometry is an editable project asset; no private template runtime is used. */
const FrozenFonts: React.FC<{assets: NonNullable<ShowcaseProps['fontAssets']>; children: React.ReactNode}> = ({assets, children}) => {
  const [hold] = useState(() => delayRender('Loading showcase fonts', {timeoutInMilliseconds: 120000}));
  const key = `${assets.display}|${assets.body}`;
  useEffect(() => {
    if (!fontLoads.has(key)) {
      fontLoads.set(key, (async () => {
        const display = new FontFace(DISPLAY, `url("${staticFile(assets.display)}")`, {weight: '700'});
        const body = new FontFace(BODY, `url("${staticFile(assets.body)}")`, {weight: '400'});
        document.fonts.add(await display.load());
        document.fonts.add(await body.load());
        await Promise.all([
          document.fonts.load(`700 126px ${DISPLAY}`, '楼下就有AI走进海客'),
          document.fonts.load(`400 43px ${BODY}`, '海客AI社区服务站'),
        ]);
        if (!document.fonts.check(`700 126px ${DISPLAY}`) || !document.fonts.check(`400 43px ${BODY}`)) {
          throw new Error('Showcase font did not finish loading');
        }
      })());
    }
    fontLoads.get(key)!.then(() => continueRender(hold)).catch(cancelRender);
    return () => continueRender(hold);
  }, [assets.display, assets.body, hold, key]);
  return <>{children}</>;
};

export function showcaseLayoutAt(shot: ShowcaseShot) {
  return geometry.layouts[shot.layout];
}

const ShotScene: React.FC<{p: ShowcaseProps; shot: ShowcaseShot}> = ({p, shot}) => {
  const age = useCurrentFrame();
  const g = showcaseLayoutAt(shot);
  if (!g) throw new Error(`Unsupported showcase layout: ${shot.layout}`);
  const motion = {enterFrames: 16, exitFrames: 10, lineFrames: 22, ...p.motion};
  const incoming = interpolate(age, [0, motion.enterFrames], [0, 1], {...clamp, easing: ease});
  const outgoing = interpolate(age, [shot.frames - motion.exitFrames, shot.frames - 1], [0, 1], clamp);
  const line = interpolate(age, [0, motion.lineFrames], [0, 1], {...clamp, easing: ease});
  // Footage keeps its own real source clock and remains visible during the hold.
  // Only the card and reading layers move; no zoom, loop or speech time-stretch.
  const cardY = (1 - incoming) * 34 - outgoing * 5;
  const cardClip = (1 - incoming) * 7;
  const chapter = p.chapters.find(c => c.id === shot.chapter);
  const side = shot.layout !== 'wide' && shot.layout !== 'portrait-center';
  const guideY = side ? g.title[1] - 42 : g.footage[1] + g.footage[3] + 44;
  const guideWidth = side ? 140 : 260;
  const titleLines = shot.title.split('\n');
  const bodyFont = p.fontAssets ? BODY : 'Microsoft YaHei, sans-serif';
  const displayFont = p.fontAssets ? DISPLAY : 'SimHei, Microsoft YaHei, sans-serif';
  return <AbsoluteFill data-shot-id={shot.id} data-layout={shot.layout}>
    <div data-element="chapter-label" style={{...rectangle(geometry.chapter), color: p.palette.muted,
      fontFamily: bodyFont, fontSize: 34, display: 'flex', alignItems: 'center', gap: 18}}>
      <span style={{display: 'inline-block', width: 10, height: 10, backgroundColor: p.palette.orange}} />
      {chapter?.label || shot.chapter}
    </div>
    <div data-element="footage-card" style={{...rectangle(g.footage), overflow: 'hidden',
      borderRadius: geometry.radius, backgroundColor: p.palette.line,
      transform: `translateY(${cardY}px)`, clipPath: `inset(${cardClip}% 0 0 0 round ${geometry.radius}px)`,
      boxShadow: `0 10px 28px rgba(23, 30, 40, ${.05 * incoming})`}}>
      <OffthreadVideo data-element="footage" src={staticFile(shot.src)}
        startFrom={Math.round(shot.offset * geometry.fps)} muted
        style={{width: '100%', height: '100%', objectFit: shot.fit, objectPosition: shot.objectPosition || '50% 50%'}} />
      <div data-element="card-edge" style={{position: 'absolute', inset: 0, borderRadius: geometry.radius,
        border: `2px solid ${p.palette.line}`, pointerEvents: 'none'}} />
    </div>
    <div data-element="guide-line" style={{position: 'absolute', left: g.title[0], top: guideY,
      width: guideWidth * line, height: 6, backgroundColor: p.palette.blue}} />
    <div data-element="chapter-title" style={{...rectangle(g.title), color: p.palette.ink,
      fontFamily: displayFont, fontSize: g.titleSize, fontWeight: 700, lineHeight: side ? 1.23 : 1.08,
      letterSpacing: -3, textAlign: g.align, overflow: 'hidden', paddingRight: 4}}>
      {titleLines.map((text, i) => {
        const reveal = interpolate(age - i * 3, [0, Math.max(8, motion.enterFrames - 3)], [0, 1], {...clamp, easing: ease});
        return <div key={i} style={{overflow: 'hidden', whiteSpace: 'pre', paddingBottom: 4}}>
          <div style={{transform: `translateY(${(1 - reveal) * 110}%)`, opacity: .35 + .65 * reveal}}>{text}</div>
        </div>;
      })}
    </div>
    <div data-element="chapter-subtitle" style={{...rectangle(g.subtitle), color: p.palette.muted,
      fontFamily: bodyFont, fontSize: g.subtitleSize, lineHeight: 1.55,
      whiteSpace: 'pre-wrap', textAlign: g.align, opacity: interpolate(age, [6, motion.enterFrames + 4], [0, 1], clamp),
      transform: `translateY(${(1 - incoming) * 16}px)`}}>{shot.subtitle}</div>
    <div data-element="shot-kicker" style={{...rectangle(g.kicker), color: p.palette.blue,
      fontFamily: bodyFont, fontSize: 28, letterSpacing: 3,
      opacity: interpolate(age, [10, motion.lineFrames], [0, 1], clamp)}}>{shot.kicker}</div>
  </AbsoluteFill>;
};

const ShowcaseContent: React.FC<ShowcaseProps> = p => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, Math.max(1, p.durationFrames - 1)], [0, 1], clamp);
  const bodyFont = p.fontAssets ? BODY : 'Microsoft YaHei, sans-serif';
  const displayFont = p.fontAssets ? DISPLAY : 'SimHei, Microsoft YaHei, sans-serif';
  return <AbsoluteFill data-element="canvas" data-template="store-motion-showcase-v1" style={{backgroundColor: p.palette.paper,
    color: p.palette.ink, fontFamily: bodyFont, fontSynthesis: 'none'}}>
    <div data-element="brand" style={{...rectangle(geometry.brand), display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', fontSize: 36}}>
      <span data-element="brand-mark" style={{fontFamily: displayFont, fontWeight: 700, fontSize: 48, letterSpacing: -1}}>{p.brand}</span>
      <span data-element="brand-context" style={{fontSize: 26, letterSpacing: 4, color: p.palette.muted}}>社区现场</span>
    </div>
    <div data-element="top-rule" style={{...rectangle(geometry.topRule), backgroundColor: p.palette.line}} />
    {p.shots.map(shot => <Sequence key={shot.id} name={shot.id} from={shot.from} durationInFrames={shot.frames} premountFor={geometry.fps}>
      <ShotScene p={p} shot={shot} />
    </Sequence>)}
    <div data-element="progress-track" style={{...rectangle(geometry.progress), backgroundColor: p.palette.line}}>
      <div data-element="progress-fill" style={{height: '100%', width: `${progress * 100}%`, backgroundColor: p.palette.blue}} />
      <div style={{position: 'absolute', right: `${(1 - progress) * 100}%`, top: -4,
        width: 12, height: 12, backgroundColor: p.palette.orange}} />
    </div>
    <div data-element="location" style={{...rectangle(geometry.location), display: 'flex', alignItems: 'center',
      justifyContent: 'space-between', color: p.palette.muted, fontSize: 30}}>
      <span>{p.location}</span><span style={{fontSize: 24, letterSpacing: 3}}>HAIKE AI</span>
    </div>
    {p.audio && <Audio src={staticFile(p.audio)} />}
  </AbsoluteFill>;
};

export const StoreMotionShowcase: React.FC<ShowcaseProps> = p => p.fontAssets
  ? <FrozenFonts assets={p.fontAssets}><ShowcaseContent {...p} /></FrozenFonts>
  : <ShowcaseContent {...p} />;

const defaults: ShowcaseProps = {
  durationFrames: 738, audio: '', brand: '海客AI社区服务站', location: '门店现场 · 走近身边的AI',
  palette: {paper: '#F6F5EF', ink: '#172027', muted: '#58616B', blue: '#3152D9', orange: '#E96835', line: '#D9DDD8'},
  shots: [], chapters: [], motion: {enterFrames: 16, exitFrames: 10, lineFrames: 22},
};

const Root: React.FC = () => <Composition id="StoreMotionShowcase" component={StoreMotionShowcase}
  width={geometry.width} height={geometry.height} fps={geometry.fps} durationInFrames={738}
  defaultProps={defaults} calculateMetadata={({props}) => ({durationInFrames: props.durationFrames})} />;

registerRoot(Root);
