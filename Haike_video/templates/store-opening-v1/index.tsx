import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Audio, Composition, Easing, OffthreadVideo, Sequence, cancelRender, continueRender,
  delayRender, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import geometry from './layout.json';

export type OpeningShot = {id: string; lane: 'main' | 'detail'; src: string; from: number; frames: number;
  offset: number; fit: 'contain' | 'cover'; objectPosition?: string};
export type OpeningCaption = {text: string; startMs: number; endMs: number; timestampMs?: number | null; confidence?: number | null};
export type OpeningChapter = {from: number; title: string; sub: string; accent?: string};
export type OpeningAvatar = {src: string; from: number; frames: number};
export type OpeningProps = {style: number; durationFrames: number; audio: string; captions: OpeningCaption[];
  contentMode?: 'opening' | 'community-cend';
  shots: OpeningShot[]; avatarSegments?: OpeningAvatar[]; chapters?: OpeningChapter[]; location?: string;
  fontAssets?: {display: string; body: string; latin: string}};
type Box = readonly [number, number, number, number];
type Stage = {main: Box; detail: Box | null; panel: Box; title: Box; titleSize: number;
  fg: 'a' | 'b'; bg: 'a' | 'b'; secondarySize?: number; spine?: boolean};
type Family = {name: string; a: string; b: string; states: Record<string, Stage>};
type Layout = {id: string; from: number; chapterIndex: number; chapter?: OpeningChapter;
  family: Family; stage: Stage; avatar?: OpeningAvatar; main?: OpeningShot; detail?: OpeningShot};
const FAMILIES = geometry.states as unknown as Record<string, Family>;
const FULL: Box = [0, 0, 1440, 1800];
const DISPLAY = 'HaikeDisplay';
const BODY = 'HaikeBody';
const LATIN = 'HaikeLatin';
const fontPromises = new Map<string, Promise<void>>();

// Frozen original OFL files. Smiley's slant is in the original outlines: no
// synthetic bold/skew. Missing files fail rendering instead of using OS fonts.
const PackagedFonts: React.FC<{assets: NonNullable<OpeningProps['fontAssets']>; children: React.ReactNode}> = ({assets, children}) => {
  const [hold] = useState(() => delayRender('Loading frozen OFL typefaces', {timeoutInMilliseconds: 120000}));
  const key = [assets.display, assets.body, assets.latin].join('|');
  useEffect(() => {
    if (!fontPromises.has(key)) {
      fontPromises.set(key, (async () => {
        const definitions: [string, string, FontFaceDescriptors][] = [
          [DISPLAY, assets.display, {weight: '400', style: 'normal'}],
          [BODY, assets.body, {weight: '100 900', style: 'normal'}],
          [LATIN, assets.latin, {weight: '100 900', style: 'italic'}],
        ];
        await Promise.all(definitions.map(async ([family, file, descriptors]) => {
          const face = new FontFace(family, `url("${staticFile(file)}")`, descriptors);
          document.fonts.add(await face.load());
        }));
        await Promise.all([
          document.fonts.load(`400 200px ${DISPLAY}`, '新塘未来汇免费体验'),
          document.fonts.load(`700 64px ${BODY}`, '海客AI社区服务站'),
          document.fonts.load(`italic 800 64px ${LATIN}`, 'HAIKE AI OPEN'),
        ]);
        if (![DISPLAY, BODY, LATIN].every(family => document.fonts.check(`${family === LATIN ? 'italic 800' : family === DISPLAY ? '400' : '700'} 64px ${family}`))) {
          throw new Error('Required packaged font did not finish loading');
        }
      })());
    }
    fontPromises.get(key)!.then(() => continueRender(hold)).catch(cancelRender);
    return () => continueRender(hold);
  }, [hold, key, assets.display, assets.body, assets.latin]);
  return <>{children}</>;
};

export function openingLayoutAt(p: OpeningProps, frame: number): Layout {
  const family = FAMILIES[String(p.style)];
  if (!family) throw new Error('Opening v002 requires style 22–26');
  const chapters = p.chapters || [];
  const chapterIndex = chapters.reduce((index, chapter, i) => chapter.from <= frame ? i : index, 0);
  const chapter = chapters[chapterIndex];
  const from = chapter?.from || 0;
  const age = frame - from;
  const main = p.shots.find(s => s.lane === 'main' && frame >= s.from && frame < s.from + s.frames);
  const detail = p.shots.find(s => s.lane === 'detail' && frame >= s.from && frame < s.from + s.frames);
  const avatar = (p.avatarSegments || []).find(s => frame >= s.from && frame < s.from + s.frames);
  if (avatar) return {id: 'identity', from: avatar.from, chapterIndex, chapter, family, avatar, main, detail,
    stage: {main: geometry.identity.main as Box, detail: null, panel: geometry.identity.panel as Box,
      title: geometry.identity.title as Box, titleSize: geometry.identity.titleSize,
      fg: p.style === 24 ? 'a' : p.style === 23 ? 'b' : 'a', bg: p.style === 24 ? 'b' : p.style === 23 ? 'a' : 'b'}};
  if (main?.fit === 'contain') {
    const paired = Boolean(detail);
    return {id: paired ? 'wide-pair' : 'wide-single', from: main.from, chapterIndex, chapter, family, main, detail,
      stage: {main: geometry.wideMain as Box, detail: paired ? geometry.wideDetail as Box : null,
        panel: paired ? geometry.wideTitle as Box : [0, 810, 1440, 990],
        title: paired ? [68, 751, 1304, 128] : [68, 970, 1304, 420], titleSize: paired ? 126 : 222,
        fg: p.style === 26 ? 'b' : 'a', bg: p.style === 26 ? 'a' : 'b'}};
  }
  const final = chapterIndex === chapters.length - 1;
  let id = 'field';
  if (p.style === 22) id = frame < 78 ? 'impact' : final ? 'closing' : 'field';
  if (p.style === 23) id = frame < 90 ? 'teaser' : ((chapterIndex === 2 || chapterIndex === 3) && age < 66) ? 'benefit' : final ? 'invite' : 'field';
  if (p.style === 24) id = detail ? 'family-duo' : frame < 84 ? 'family-hero' : final ? 'family-close' : 'chase';
  if (p.style === 25) id = frame < 72 ? 'question' : final ? 'follow' : chapterIndex === 3 && age < 36 ? 'edge' : chapterIndex === 4 ? 'full' : 'quote';
  if (p.style === 26) id = frame < 75 ? 'announcement' : chapterIndex === 3 ? 'offer' : final ? 'invite' : 'field';
  let stageFrom = from;
  if (p.style === 22 && id === 'field' && from === 0) stageFrom = 78;
  if (p.style === 23 && id === 'field') stageFrom = (chapterIndex === 2 || chapterIndex === 3) ? from + 66 : from === 0 ? 90 : from;
  if (p.style === 24 && id === 'chase' && from === 0) stageFrom = 84;
  if (p.style === 24 && id === 'family-duo') stageFrom = detail!.from;
  if (p.style === 25 && id === 'quote' && chapterIndex === 3) stageFrom = from + 36;
  if (p.style === 26 && id === 'field' && from === 0) stageFrom = 75;
  return {id, from: stageFrom, chapterIndex, chapter, family, stage: family.states[id], main, detail};
}

const Panel: React.FC<{id: string; box: Box; style?: React.CSSProperties; children?: React.ReactNode}> = ({id, box, style, children}) => (
  <div data-element={id} style={{position: 'absolute', left: box[0], top: box[1], width: box[2], height: box[3], boxSizing: 'border-box', overflow: 'hidden', ...style}}>{children}</div>
);
const Footage: React.FC<{shots: OpeningShot[]; lane: OpeningShot['lane']; box: Box}> = ({shots, lane, box}) => {
  const {fps} = useVideoConfig();
  return <Panel id={lane === 'main' ? 'main_stream' : 'detail_stream'} box={box}>
    {shots.filter(s => s.lane === lane).map(s => <Sequence key={s.id} name={s.id} from={s.from} durationInFrames={s.frames} premountFor={fps}>
      <OffthreadVideo src={staticFile(s.src)} startFrom={Math.round(s.offset * fps)} muted
        style={{width: '100%', height: '100%', objectFit: s.fit, objectPosition: s.objectPosition || '50% 50%'}} />
    </Sequence>)}
  </Panel>;
};

function titleFor(p: OpeningProps, l: Layout): string {
  if (p.contentMode === 'community-cend') {
    const title = (l.chapter?.title || '来店坐坐').replace(/\n/g, '');
    if (l.stage.spine) return Array.from(title).join('\n');
    if (l.stage.title[3] < l.stage.titleSize * 1.8 || l.avatar) return title;
    return title.length > 3 ? title.slice(0, 2) + '\n' + title.slice(2) : title;
  }
  if (l.avatar) return p.style === 23 ? '店长邀你' : p.style === 24 ? '店长欢迎' : '我是店长';
  if (p.style === 23 && l.id === 'field') return ['AI\n在身边', '店长\n邀你', '免费\n体验', '不收费\n不办卡', '来店\n坐坐'][l.chapterIndex] || '来店\n坐坐';
  if (p.style === 25 && l.id === 'quote') return `“${l.chapter?.title || '来聊聊'}”`;
  if (p.style === 25 && l.id === 'full') return '现场\n见面';
  if (l.stage.spine) return ({2: '新\n店\n开\n业', 3: '来\n问\n问', 4: '现\n场\n见', 5: '面\n对\n面', 6: '关\n注\n我'} as Record<number, string>)[l.chapterIndex] || '来\n逛\n逛';
  if (l.id === 'impact') return '开业爆了';
  return l.chapter?.title || '新店开业';
}
const DisplayType: React.FC<{p: OpeningProps; layout: Layout; frame: number}> = ({p, layout: l, frame}) => {
  const stage = l.stage;
  const age = Math.max(0, frame - l.from);
  const easing = Easing.bezier(.18, .8, .2, 1);
  const reveal = interpolate(age, [0, 12], [100, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing});
  const move = interpolate(age, [0, 12], [48, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing});
  const lines = titleFor(p, l).split('\n');
  const size = l.id === 'benefit' && lines.length === 1 ? 232 : stage.titleSize;
  return <>
    <Panel id="color_plane" box={stage.panel} style={{backgroundColor: l.family[stage.bg]}} />
    <Panel id="display_type" box={stage.title} style={{color: l.family[stage.fg], fontFamily: DISPLAY, fontWeight: 400,
      fontStyle: 'normal', fontSynthesis: 'none', fontSize: size, lineHeight: l.stage.spine ? 1.09 : 1.035,
      letterSpacing: -2, clipPath: `inset(0 ${reveal}% 0 0)`, paddingLeft: 5, paddingRight: 20}}>
      <div style={{transform: `translateX(${move}px)`, whiteSpace: 'pre', fontWeight: 400}}>
        {lines.map((line, i) => <div key={i} style={{fontSize: i && stage.secondarySize ? stage.secondarySize : size,
          lineHeight: stage.spine ? 1.09 : 1.035}}>{line}</div>)}
      </div>
    </Panel>
  </>;
};
const Brand: React.FC<{family: Family; styleNumber: number; community?: boolean}> = ({family, styleNumber, community}) => (
  <Panel id="brand" box={geometry.brand as Box} style={{backgroundColor: styleNumber === 26 ? family.b : family.a, color: '#000',
    display: 'flex', alignItems: 'center', padding: '0 20px', gap: 15}}>
    <span style={{fontFamily: LATIN, fontWeight: 800, fontStyle: 'italic', fontSize: 55}}>HAIKE AI</span>
    <span style={{fontFamily: BODY, fontWeight: 800, fontSize: 40, whiteSpace: 'nowrap'}}>{community ? '社区' : '开业'}</span>
  </Panel>
);
const Location: React.FC<{family: Family; styleNumber: number; location?: string; community?: boolean}> = ({family, styleNumber, location, community}) => {
  const bg = styleNumber === 26 ? family.b : family.a;
  const fg = styleNumber === 26 ? family.a : '#000';
  return <Panel id="location" box={geometry.location as Box} style={{backgroundColor: bg, color: fg,
    fontFamily: BODY, fontWeight: 800, padding: '0 50px', display: 'flex', alignItems: 'center', gap: 30}}>
    <span style={{fontSize: 64, whiteSpace: 'nowrap'}}>{community ? '未来汇一楼' : '新塘未来汇'}</span>
    <span style={{fontSize: 64, whiteSpace: 'nowrap'}}>{community ? '海客AI社区服务店' : '海客AI社区服务站'}</span>
    <span data-location={location || '新塘未来汇 · 海客AI社区服务站'} style={{display: 'none'}} />
  </Panel>;
};
const Caption: React.FC<{text: string; styleNumber: number; family: Family}> = ({text, styleNumber, family}) => {
  const background = styleNumber === 23 ? family.a : styleNumber === 26 ? family.b : '#000';
  const fg = styleNumber === 23 ? '#000' : styleNumber === 26 ? family.a : styleNumber === 25 ? family.a : '#fff';
  return <div data-element="caption" style={{position: 'absolute', top: 1500, left: 54, width: 1332,
    display: 'flex', justifyContent: 'center', pointerEvents: 'none'}}>
    <div style={{fontFamily: BODY, fontSize: 64, fontWeight: 700, lineHeight: 1.25, textAlign: 'center', color: fg,
      backgroundColor: background, padding: '17px 32px', maxWidth: '100%', minHeight: 114, boxSizing: 'border-box',
      whiteSpace: 'normal', wordBreak: 'normal', lineBreak: 'strict'}}>{text}</div>
  </div>;
};

const OpeningContent: React.FC<OpeningProps> = p => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const l = openingLayoutAt(p, frame);
  const {stage, family, avatar} = l;
  const ms = frame / fps * 1000;
  const caption = [...p.captions].reverse().find(c => ms >= c.startMs && ms < c.endMs + 65);
  return <AbsoluteFill data-template-version="v002" data-layout-state={l.id}
    style={{backgroundColor: family.a, fontFamily: BODY, fontSynthesis: 'none'}}>
    {avatar ? <Panel id="avatar_stream" box={FULL}>
      <Sequence from={avatar.from} durationInFrames={avatar.frames} premountFor={fps} name="店长短段·原4比5">
        <OffthreadVideo src={staticFile(avatar.src)} muted style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      </Sequence>
    </Panel> : <>
      <Footage shots={p.shots} lane="main" box={stage.main} />
      {stage.detail && <Footage shots={p.shots} lane="detail" box={stage.detail} />}
    </>}
    <DisplayType p={p} layout={l} frame={frame} />
    <Brand family={family} styleNumber={p.style} community={p.contentMode === 'community-cend'} />
    {avatar && <div data-element="speaker" style={{position: 'absolute', left: 54, top: 1370,
      fontFamily: BODY, fontSize: 54, fontWeight: 800, lineHeight: 1.2, backgroundColor: '#000', color: '#fff', padding: '14px 24px'}}>
      {p.contentMode === 'community-cend' ? '侯总 · 海客AI社区服务店' : '海客AI社区服务站店长'}
    </div>}
    {caption && <Caption text={caption.text} styleNumber={p.style} family={family} />}
    <Location family={family} styleNumber={p.style} location={p.location} community={p.contentMode === 'community-cend'} />
    {p.audio && <Audio src={staticFile(p.audio)} />}
  </AbsoluteFill>;
};
export const StoreOpeningFilm: React.FC<OpeningProps> = p => (
  <PackagedFonts assets={p.fontAssets || {display: 'display.ttf', body: 'body.ttf', latin: 'latin.ttf'}}>
    <OpeningContent {...p} />
  </PackagedFonts>
);
registerRoot(() => <Composition id="HaikeStoreOpening" component={StoreOpeningFilm} width={1440} height={1800} fps={30}
  durationInFrames={180}
  defaultProps={{style: 22, durationFrames: 180, audio: '', shots: [], captions: [], avatarSegments: [], chapters: [],
    fontAssets: {display: 'display.ttf', body: 'body.ttf', latin: 'latin.ttf'}, location: '新塘未来汇 · 海客AI社区服务站'}}
  calculateMetadata={({props}) => ({durationInFrames: props.durationFrames})} />);
