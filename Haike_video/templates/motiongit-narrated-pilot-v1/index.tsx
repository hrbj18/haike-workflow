import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill, Audio, Composition, Easing, Img, OffthreadVideo, Sequence,
  cancelRender, continueRender, delayRender, interpolate, registerRoot,
  staticFile, useCurrentFrame,
} from 'remotion';
import geometryJson from './layout.json';
import type {Box, NarratedPilotProps, PilotGeometry, PilotMedia, PilotScene} from './types';
import {HumContent, HumScene} from './hum';

export type {NarratedPilotProps, PilotMedia, PilotScene} from './types';

const g = geometryJson as PilotGeometry;
const DISPLAY = 'HaikeNarratedDisplay';
const BODY = 'HaikeNarratedBody';
const loads = new Map<string, Promise<void>>();
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const curve = Easing.bezier(.18, .8, .16, 1);
const step = (f: number, start: number, end: number) => interpolate(f, [start, end], [0, 1], clamp);
const ease = (f: number, start: number, end: number) => interpolate(f, [start, end], [0, 1], {...clamp, easing: curve});
const boxStyle = (box: Box): React.CSSProperties => ({position: 'absolute', left: box[0], top: box[1], width: box[2], height: box[3], boxSizing: 'border-box'});
const mix = (a: Box, b: Box, amount: number): Box => a.map((v, i) => v + (b[i] - v) * amount) as Box;
const displayFont = (p: NarratedPilotProps) => p.fontAssets ? DISPLAY : 'SimHei, Microsoft YaHei, sans-serif';
const bodyFont = (p: NarratedPilotProps) => p.fontAssets ? BODY : 'Microsoft YaHei, sans-serif';

export function pilotSceneAt(p: NarratedPilotProps, frame: number) {
  return p.scenes.find(s => frame >= s.from && frame < s.from + s.frames) || null;
}

/** A single global presenter window and one mode clock; no scene can restart it. */
export function pilotPresenterAt(p: NarratedPilotProps, frame: number) {
  const source = p.presenter;
  if (!source || frame < source.from || frame >= source.from + source.frames) return null;
  const modes = p.presenterModes || [];
  const index = modes.findIndex(m => frame >= m.from && frame < m.from + m.frames);
  if (index < 0) return null;
  const mode = modes[index];
  const previous = index > 0 && modes[index - 1].from + modes[index - 1].frames === mode.from ? modes[index - 1] : mode;
  const oldFactor = previous.mode === 'large' ? 1 : 0;
  const newFactor = mode.mode === 'large' ? 1 : 0;
  const amount = ease(frame, mode.from, mode.from + g.presenter.transitionFrames);
  const large = oldFactor + (newFactor - oldFactor) * amount;
  return {mode: mode.mode, large, box: mix(g.presenter.small, g.presenter.large, large),
    sourceSeconds: source.offset + (frame - source.from) / g.fps};
}

export function pilotSelectionAt(scene: PilotScene, age: number, orientation?: PilotMedia['orientation']) {
  const timing = scene.selection || {cursorFrom: 24, selectFrom: 42, expandFrom: 50, holdFrom: 68};
  const expanded = ease(age, timing.expandFrom, timing.holdFrom);
  const target = orientation === 'portrait' ? g.select.portraitExpanded : g.select.expanded;
  return {timing, expanded, box: mix(g.select.primary, target, expanded),
    selected: age >= timing.selectFrom, playing: age >= timing.expandFrom};
}

const Fonts: React.FC<{assets: NonNullable<NarratedPilotProps['fontAssets']>; children: React.ReactNode}> = ({assets, children}) => {
  const [hold] = useState(() => delayRender('Loading narrated-pilot fonts', {timeoutInMilliseconds: 120000}));
  const key = `${assets.display}|${assets.body}`;
  useEffect(() => {
    if (!loads.has(key)) loads.set(key, (async () => {
      const display = new FontFace(DISPLAY, `url("${staticFile(assets.display)}")`, {weight: '700'});
      const body = new FontFace(BODY, `url("${staticFile(assets.body)}")`, {weight: '400'});
      document.fonts.add(await display.load());
      document.fonts.add(await body.load());
      await Promise.all([document.fonts.load(`700 132px ${DISPLAY}`, '海客AI社区服务站'), document.fonts.load(`400 60px ${BODY}`, '近距离看看')]);
      if (!document.fonts.check(`700 132px ${DISPLAY}`) || !document.fonts.check(`400 60px ${BODY}`)) throw new Error('Narrated-pilot font did not finish loading');
    })());
    loads.get(key)!.then(() => continueRender(hold)).catch(cancelRender);
    return () => continueRender(hold);
  }, [assets.display, assets.body, hold, key]);
  return <>{children}</>;
};

const Title: React.FC<{p: NarratedPilotProps; text: string; box: Box; size: number; color: string; age: number; align?: 'left' | 'center'}> = ({p, text, box, size, color, age, align = 'left'}) => (
  <div data-element="scene-title" style={{...boxStyle(box), color, fontFamily: displayFont(p), fontSize: size,
    fontWeight: 700, lineHeight: 1.16, letterSpacing: -2, textAlign: align, whiteSpace: 'pre', overflow: 'hidden'}}>
    {text.split('\n').map((line, i) => <div key={i} style={{overflow: 'hidden', paddingBottom: 3}}>
      <div style={{transform: `translateY(${(1 - ease(age - i * 2, 0, 10)) * 105}%)`}}>{line}</div>
    </div>)}
  </div>
);

const SceneHeader: React.FC<{p: NarratedPilotProps; scene: PilotScene; age: number}> = ({p, scene, age}) => {
  const ink = scene.theme === 'dark' ? p.palette.light : p.palette.ink;
  return <>
    <Title p={p} text={scene.title} box={g.sceneHeader.title} size={g.sceneHeader.titleSize} color={ink} age={age} />
    {scene.subtitle && <div data-element="scene-subtitle" style={{...boxStyle(g.sceneHeader.subtitle), color: scene.theme === 'dark' ? p.palette.line : p.palette.muted,
      fontFamily: bodyFont(p), fontSize: 44, lineHeight: 1.3, opacity: ease(age, 7, 18)}}>{scene.subtitle}</div>}
  </>;
};

const StillCard: React.FC<{p: NarratedPilotProps; media: PilotMedia; box: Box; opacity?: number}> = ({p, media, box, opacity = 1}) => (
  <div data-element="secondary-card" data-media-id={media.id} style={{...boxStyle(box), borderRadius: g.select.radius,
    overflow: 'hidden', backgroundColor: '#FFFFFF', opacity, boxShadow: '0 12px 38px rgba(15,22,32,.09)'}}>
    <Img src={staticFile(media.thumbnail)} style={{position: 'absolute', inset: `0 0 ${g.select.footerHeight}px 0`, width: '100%',
      height: box[3] - g.select.footerHeight, objectFit: 'contain', backgroundColor: p.palette.line}} />
    <div style={{position: 'absolute', left: 22, right: 22, bottom: 0, height: g.select.footerHeight,
      display: 'flex', alignItems: 'center', color: p.palette.ink, fontFamily: bodyFont(p), fontSize: 36, whiteSpace: 'nowrap'}}>{media.label || p.brand}</div>
  </div>
);

export const SelectModule: React.FC<{p: NarratedPilotProps; scene: PilotScene}> = ({p, scene}) => {
  const age = useCurrentFrame();
  const media = p.media.find(m => m.id === scene.mediaId);
  const secondary = p.media.find(m => m.id === scene.secondaryMediaId);
  if (!media) throw new Error('Select module requires reviewed primary media');
  const state = pilotSelectionAt(scene, age, media.orientation);
  const enter = ease(age, 0, 18);
  const secondEnter = ease(age, 5, 23);
  const cardBox = state.box;
  const selected = ease(age, state.timing.selectFrom, state.timing.expandFrom);
  const target: [number, number] = [g.select.primary[0] + g.select.primary[2] * .6, g.select.primary[1] + g.select.primary[3] * .5];
  const cursor = ease(age, state.timing.cursorFrom, state.timing.selectFrom - 2);
  const cursorAlpha = age < state.timing.cursorFrom ? 0 : 1 - step(age, state.timing.expandFrom, state.timing.expandFrom + 8);
  return <>
    <SceneHeader p={p} scene={scene} age={age} />
    {secondary && <StillCard p={p} media={secondary}
      box={[g.select.secondary[0], g.select.secondary[1] + (1 - secondEnter) * 44, g.select.secondary[2], g.select.secondary[3]]}
      opacity={secondEnter * (1 - state.expanded * .92)} />}
    <div data-element="selected-card" data-media-id={media.id} data-phase={state.playing ? state.expanded === 1 ? 'hold' : 'expand' : state.selected ? 'selected' : 'enter'}
      style={{...boxStyle(cardBox), borderRadius: g.select.radius, overflow: 'hidden', backgroundColor: '#FFFFFF',
        opacity: enter, transform: `translateY(${(1 - enter) * 44}px)`, boxShadow: `0 ${12 + selected * 4}px ${38 + selected * 12}px rgba(15,22,32,.1)`}}>
      <Img src={staticFile(media.thumbnail)} style={{position: 'absolute', inset: `0 0 ${g.select.footerHeight}px 0`, width: '100%',
        height: cardBox[3] - g.select.footerHeight, objectFit: 'contain', backgroundColor: p.palette.line}} />
      {scene.frames > state.timing.expandFrom && <Sequence layout="none" from={state.timing.expandFrom} durationInFrames={scene.frames - state.timing.expandFrom}>
        <OffthreadVideo data-element="selected-video" src={staticFile(media.src)} startFrom={Math.round(media.offset * g.fps)} muted
          style={{position: 'absolute', top: 0, left: 0, width: '100%', height: cardBox[3] - g.select.footerHeight,
            objectFit: 'contain', objectPosition: media.objectPosition || '50% 50%', backgroundColor: '#121317'}} />
      </Sequence>}
      <div data-element="card-label" style={{position: 'absolute', bottom: 0, left: 22, right: 22, height: g.select.footerHeight,
        display: 'flex', alignItems: 'center', fontFamily: bodyFont(p), fontSize: 36 + state.expanded * 7,
        color: p.palette.ink, whiteSpace: 'nowrap'}}>{media.label || p.brand}</div>
    </div>
    <div data-element="selection-outline" style={{...boxStyle(cardBox), borderRadius: g.select.radius,
      border: `3px solid ${p.palette.blue}`, opacity: selected, pointerEvents: 'none'}} />
    <div data-element="selection-cursor" style={{position: 'absolute', left: 1240 + (target[0] - 1240) * cursor,
      top: 440 + (target[1] - 440) * cursor, opacity: cursorAlpha, width: 52, height: 62}}>
      <svg viewBox="0 0 52 62" width="52" height="62"><path d="M4 3 L7 48 L19 37 L29 58 L39 53 L29 32 L46 31 Z"
        fill={p.palette.ink} stroke="#FFFFFF" strokeWidth="3" strokeLinejoin="round" /></svg>
    </div>
  </>;
};

export const FocusModule: React.FC<{p: NarratedPilotProps; scene: PilotScene}> = ({p, scene}) => {
  const age = useCurrentFrame();
  const media = p.media.find(m => m.id === scene.mediaId);
  if (!media) throw new Error('Focus module requires reviewed media');
  const portrait = media.orientation === 'portrait';
  const entry = portrait ? g.focus.portraitEntry : g.focus.entry;
  const target = portrait ? g.focus.portraitExpanded : g.focus.expanded;
  const box = mix(entry, target, ease(age, 0, Math.min(18, scene.frames - 1)));
  const label = portrait ? g.focus.portraitLabel : g.focus.label;
  return <>
    <SceneHeader p={p} scene={scene} age={age} />
    <div data-element="focus-window" data-media-id={media.id} style={{...boxStyle(box), borderRadius: g.select.radius,
      overflow: 'hidden', backgroundColor: '#121317', boxShadow: '0 12px 38px rgba(15,22,32,.08)'}}>
      <OffthreadVideo data-element="focus-video" src={staticFile(media.src)} startFrom={Math.round(media.offset * g.fps)} muted
        style={{width: '100%', height: '100%', objectFit: 'contain', objectPosition: media.objectPosition || '50% 50%'}} />
    </div>
    {media.label && <div data-element="focus-label" style={{...boxStyle(label), color: scene.theme === 'dark' ? p.palette.line : p.palette.muted,
      fontFamily: bodyFont(p), fontSize: 40, lineHeight: 1.45, opacity: ease(age, 6, 18)}}>{media.label}</div>}
  </>;
};

/** The chosen card retains its DOM identity through cascade, click and expansion. */
export const MaterialWallModule: React.FC<{p: NarratedPilotProps; scene: PilotScene}> = ({p, scene}) => {
  const age = useCurrentFrame();
  const ids = scene.wallMediaIds || [];
  const timing = scene.selection || {cursorFrom:24,selectFrom:42,expandFrom:50,holdFrom:68};
  const progress = ease(age,timing.expandFrom,timing.holdFrom);
  const selected = p.media.find(m=>m.id===scene.mediaId);
  if(!selected) throw new Error('Material wall requires selected media');
  const selectedIndex = ids.indexOf(selected.id);
  const origin: Box = [88+(selectedIndex%3)*432,520+Math.floor(selectedIndex/3)*405,400,365];
  const target = selected.orientation==='portrait'?g.select.portraitExpanded:g.select.expanded;
  const cursor = ease(age,timing.cursorFrom,timing.selectFrom-2);
  const cursorAlpha = age<timing.cursorFrom?0:1-step(age,timing.expandFrom,timing.expandFrom+8);
  return <>
    <SceneHeader p={p} scene={scene} age={age}/>
    <div data-element="wall-category" style={{position:'absolute',left:88,top:426,display:'flex',gap:14,fontSize:25,color:p.palette.ink}}>
      {(p.wallCategories||['全部素材','亲子体验','机器人现场','店内日常']).map((label,i)=><span key={label} style={{padding:'9px 23px',borderRadius:28,backgroundColor:i===0?p.palette.blue:'#FFFFFF',color:i===0?'white':p.palette.ink,opacity:1-progress}}>{label}</span>)}
    </div>
    {ids.map((id,i)=>{
      const media=p.media.find(m=>m.id===id);
      if(!media) throw new Error('Material wall references missing media');
      const isSelected=id===scene.mediaId;
      const enter=ease(age,i*3,i*3+18);
      const start:Box=[88+(i%3)*432,520+Math.floor(i/3)*405,400,365];
      const box=isSelected?mix(start,target,progress):start;
      return <div key={id} data-element="wall-card" data-media-id={id} data-selected={isSelected} style={{...boxStyle(box),zIndex:isSelected?5:1,
        opacity:enter*(isSelected?1:1-progress),transform:`translateY(${(1-enter)*64}px) scale(${.97+.03*enter})`,
        borderRadius:24,overflow:'hidden',backgroundColor:'#FFFFFF',boxShadow:'0 12px 38px rgba(15,22,32,.09)',
        outline:isSelected&&age>=timing.selectFrom?`3px solid ${p.palette.blue}`:'none'}}>
        <Img src={staticFile(media.thumbnail)} style={{position:'absolute',inset:0,width:'100%',height:box[3]-64,objectFit:'contain',backgroundColor:p.palette.line}}/>
        {isSelected&&<Sequence layout="none" from={timing.expandFrom} durationInFrames={scene.frames-timing.expandFrom}>
          <OffthreadVideo src={staticFile(media.src)} startFrom={Math.round(media.offset*g.fps)} muted style={{position:'absolute',left:0,top:0,width:'100%',height:box[3]-64,objectFit:'contain',backgroundColor:'#121317'}}/>
        </Sequence>}
        <div style={{position:'absolute',left:20,right:20,bottom:0,height:64,display:'flex',alignItems:'center',fontSize:29+progress*9,color:p.palette.ink,fontFamily:bodyFont(p)}}>{media.label||p.brand}</div>
      </div>;
    })}
    <div data-element="wall-cursor" style={{position:'absolute',zIndex:10,left:1240+(origin[0]+origin[2]*.6-1240)*cursor,top:440+(origin[1]+origin[3]*.5-440)*cursor,opacity:cursorAlpha}}>
      <svg width="52" height="62" viewBox="0 0 52 62"><path d="M4 3 L7 48 L19 37 L29 58 L39 53 L29 32 L46 31 Z" fill={p.palette.ink} stroke="#FFF" strokeWidth="3" strokeLinejoin="round"/></svg>
    </div>
  </>;
};

export const StatementModule: React.FC<{p: NarratedPilotProps; scene: PilotScene}> = ({p, scene}) => {
  const age = useCurrentFrame();
  const color = scene.theme === 'dark' ? p.palette.light : p.palette.ink;
  return <>
    <Title p={p} text={scene.title} box={g.statement.title} size={g.statement.titleSize} color={color} age={age} align="center" />
    <div data-element="statement-rule" style={{...boxStyle(g.statement.line), width: g.statement.line[2] * ease(age, 6, 22),
      backgroundColor: p.palette.orange}} />
    {scene.subtitle && <div data-element="scene-subtitle" style={{...boxStyle(g.statement.subtitle), color: scene.theme === 'dark' ? p.palette.line : p.palette.muted,
      fontFamily: bodyFont(p), fontSize: 52, lineHeight: 1.45, textAlign: 'center', opacity: ease(age, 10, 24)}}>{scene.subtitle}</div>}
  </>;
};

const Scene: React.FC<{p: NarratedPilotProps; scene: PilotScene}> = ({p, scene}) => <AbsoluteFill data-element="scene" data-scene-id={scene.id}
  data-module={scene.module} style={{backgroundColor: scene.theme === 'dark' ? p.palette.dark : p.palette.paper}}>
  {scene.module === 'statement' ? <StatementModule p={p} scene={scene} /> : scene.module === 'select' ? <SelectModule p={p} scene={scene} /> : scene.module === 'wall' ? <MaterialWallModule p={p} scene={scene}/> : <FocusModule p={p} scene={scene} />}
</AbsoluteFill>;

const PresenterLayer: React.FC<{p: NarratedPilotProps}> = ({p}) => {
  const frame = useCurrentFrame();
  const state = pilotPresenterAt(p, frame);
  const scene = pilotSceneAt(p, frame);
  if (!p.presenter || !state || !scene) return null;
  const large = state.large;
  const titleBox = mix(g.statement.title, g.presenter.title, large);
  const size = g.statement.titleSize + (g.sceneHeader.titleSize - g.statement.titleSize) * large;
  const theme = scene.theme === 'dark' ? p.palette.dark : p.palette.paper;
  const ink = scene.theme === 'dark' ? p.palette.light : p.palette.ink;
  const underline = mix(g.statement.line, [340, 407, 760, 5], large);
  return <AbsoluteFill data-element="presenter-layer" data-mode={state.mode} style={{backgroundColor: theme, zIndex: 20}}>
    <Title p={p} text={scene.title} box={titleBox} size={size} color={ink} age={frame - scene.from} align="center" />
    <div data-element="presenter-rule" style={{...boxStyle(underline), width: underline[2] * ease(frame - scene.from, 4, 18), backgroundColor: p.palette.orange}} />
    <Sequence layout="none" from={p.presenter.from} durationInFrames={p.presenter.frames}>
      <div data-element="presenter-window" style={{...boxStyle(state.box), borderRadius: 20, overflow: 'hidden',
        opacity: ease(frame, p.presenter.from, p.presenter.from + 6)}}>
        <OffthreadVideo data-element="presenter-video" src={staticFile(p.presenter.src)} startFrom={Math.round(p.presenter.offset * g.fps)} muted
          style={{width: '100%', height: '100%', objectFit: 'contain', objectPosition: p.presenter.objectPosition || '50% 50%'}} />
      </div>
    </Sequence>
    {scene.subtitle && <div data-element="presenter-label" style={{position: 'absolute', left: 88, top: 1415, width: 180, height: 110,
      fontFamily: bodyFont(p), fontSize: 34, lineHeight: 1.4, color: scene.theme === 'dark' ? p.palette.line : p.palette.muted}}>{scene.subtitle}</div>}
  </AbsoluteFill>;
};

const Content: React.FC<NarratedPilotProps> = p => {
  const frame = useCurrentFrame();
  const scene = pilotSceneAt(p, frame);
  const dark = scene?.theme === 'dark';
  const ink = dark ? p.palette.light : p.palette.ink;
  const caption = p.captions.find(c => frame * 1000 / g.fps >= c.startMs && frame * 1000 / g.fps < c.endMs);
  return <AbsoluteFill data-element="canvas" data-template="motiongit-narrated-pilot-v1" style={{backgroundColor: dark ? p.palette.dark : p.palette.paper,
    color: ink, fontFamily: bodyFont(p), fontSynthesis: 'none'}}>
    {p.scenes.map(s => <Sequence key={s.id} from={s.from} durationInFrames={s.frames} name={s.id} premountFor={g.fps}>
      <Scene p={p} scene={s} />
    </Sequence>)}
    <PresenterLayer p={p} />
    <div data-element="brand" style={{...boxStyle(g.brand), color: ink, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      fontFamily: bodyFont(p), fontSize: 29, zIndex: 40}}><span>{p.brand}</span><span style={{fontSize: 24, letterSpacing: 2, opacity: .6}}>HAIKE AI</span></div>
    {caption && <div data-element="caption" style={{...boxStyle(g.captions), zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: ink, fontFamily: bodyFont(p), fontSize: g.captionSize, lineHeight: 1.25, textAlign: 'center', whiteSpace: 'pre',
      borderTop: `1px solid ${dark ? '#41434B' : p.palette.line}`}}>{caption.text}</div>}
    <div data-element="footer" style={{...boxStyle(g.footer), color: dark ? p.palette.line : p.palette.muted,
      fontFamily: bodyFont(p), fontSize: 25, zIndex: 40}}>{p.footer}</div>
    {p.audio && <Audio src={staticFile(p.audio)} />}
  </AbsoluteFill>;
};

export const MotionGitNarratedPilot: React.FC<NarratedPilotProps> = p => p.fontAssets
  ? <Fonts assets={p.fontAssets}>{p.visualStyle === 'hum' ? <HumContent {...p} presenterAt={pilotPresenterAt}/> : <Content {...p} />}</Fonts>
  : p.visualStyle === 'hum' ? <HumContent {...p} presenterAt={pilotPresenterAt}/> : <Content {...p} />;

/** Local visual preview deliberately omits narration, captions and presenter. */
const SilentModulePreview: React.FC<NarratedPilotProps & {module: PilotScene['module']}> = ({module, ...p}) => {
  const scene = p.scenes.find(s => s.module === module);
  const ready = scene && (module === 'statement' || p.media.some(m => m.id === scene.mediaId));
  const content = <AbsoluteFill data-element="module-preview" data-module={module}
    style={{backgroundColor: scene?.theme === 'dark' ? p.palette.dark : p.palette.paper}}>
    {ready && (p.visualStyle === 'hum' ? <HumScene p={p} scene={{...scene, from:0}}/> : <Scene p={p} scene={{...scene, from: 0}} />)}
  </AbsoluteFill>;
  return p.fontAssets ? <Fonts assets={p.fontAssets}>{content}</Fonts> : content;
};

export const NarratedStatementPreview: React.FC<NarratedPilotProps> = p => <SilentModulePreview {...p} module="statement" />;
export const NarratedSelectPreview: React.FC<NarratedPilotProps> = p => <SilentModulePreview {...p} module="select" />;
export const NarratedFocusPreview: React.FC<NarratedPilotProps> = p => <SilentModulePreview {...p} module="focus" />;
export const NarratedWallPreview: React.FC<NarratedPilotProps> = p => <SilentModulePreview {...p} module="wall" />;

const defaults: NarratedPilotProps = {
  durationFrames: 600, audio: '', brand: '海客AI社区服务站', footer: '',
  palette: {paper: '#F6F5EF', ink: '#15171C', muted: '#62646B', blue: '#3245F3', orange: '#F26448', line: '#D8DBDC', dark: '#101116', light: '#FAFAF4'},
  media: [], scenes: [], captions: [], presenterModes: [],
};

const previews = [
  {id: 'MotionGitNarratedStatement', module: 'statement', component: NarratedStatementPreview},
  {id: 'MotionGitNarratedSelect', module: 'select', component: NarratedSelectPreview},
  {id: 'MotionGitNarratedFocus', module: 'focus', component: NarratedFocusPreview},
  {id: 'MotionGitNarratedWall', module: 'wall', component: NarratedWallPreview},
] as const;

const Root: React.FC = () => <>
  <Composition id="MotionGitNarratedPilot" component={MotionGitNarratedPilot}
    width={g.width} height={g.height} fps={g.fps} durationInFrames={600} defaultProps={defaults}
    calculateMetadata={({props}) => ({durationInFrames: props.durationFrames})} />
  {previews.map(preview => <Composition key={preview.id} id={preview.id} component={preview.component}
    width={g.width} height={g.height} fps={g.fps} durationInFrames={1} defaultProps={defaults}
    calculateMetadata={({props}) => ({durationInFrames: Math.max(1, props.scenes.find(s => s.module === preview.module)?.frames || 1)})} />)}
</>;

registerRoot(Root);
