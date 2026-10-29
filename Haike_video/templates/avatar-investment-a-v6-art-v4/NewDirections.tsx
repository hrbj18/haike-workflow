import React from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import type {SceneProps} from './types';
import {CaptionTrack, MaterialWindow, PresenterWindow} from './shared';

const SANS = '"Microsoft YaHei","PingFang SC",sans-serif';
const SONG = '"SimSun","Songti SC","Microsoft YaHei",serif';
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const RED = {paper: '#FFF6E8', ink: '#171411', red: '#D82127', deep: '#8E171C', muted: '#B8AFA2'};
const SILVER = {paper: '#F3F6F8', metal: '#CCD4DB', ink: '#17242D', cyan: '#147B94', muted: '#536672'};
const DOC = {paper: '#EFECE3', ink: '#1A1B19', muted: '#A7ACA5', accent: '#81967C', secondary: '#D7D7CF'};

function localFrame({frame, chapter, fps}: SceneProps) {
  return Math.max(0, frame - Math.round(chapter.start * fps));
}

function reveal(props: SceneProps, frames: number) {
  // The first video frame is a complete, useful poster. Later chapters reveal.
  if (props.chapterIndex === 0) return 1;
  const t = interpolate(localFrame(props), [0, frames], [0, 1], clamp);
  return 1 - Math.pow(1 - t, 3);
}

function fittedSize(lines: string[], maximum: number, width: number) {
  const units = Math.max(1, ...lines.map(line => [...line].reduce((sum, ch) => sum + (/^[\x00-\x7F]$/.test(ch) ? .58 : 1), 0)));
  return Math.min(maximum, Math.floor(width / units));
}

const MaskedHeading: React.FC<{
  lines: string[]; width: number; size: number; color: string;
  progress: number; align?: 'left' | 'center'; font?: string;
  letterSpacing?: number; lineHeight?: number;
}> = ({lines, width, size, color, progress, align = 'left', font = SANS, letterSpacing = -3, lineHeight = 1.08}) => (
  <div style={{width, color, fontFamily: font, fontSize: fittedSize(lines, size, width), fontWeight: 900,
    letterSpacing, lineHeight, textAlign: align}}>
    {lines.slice(0, 2).map((line, index) => <div key={`${index}-${line}`} style={{overflow: 'hidden', paddingBottom: 7}}>
      <div style={{translate: `0 ${(1 - progress) * 37}px`, clipPath: `inset(${(1 - progress) * 100}% 0 0 0)`}}>{line}</div>
    </div>)}
  </div>
);

function activeScene(props: SceneProps) {
  const seconds = props.frame / props.fps;
  return props.p.art.scenes?.find(scene => seconds >= scene.start && seconds < scene.end);
}

const PointRail: React.FC<{points: string[]; x: number; y: number; width: number; color: string; rule: string}> =
  ({points, x, y, width, color, rule}) => <div style={{position: 'absolute', left: x, top: y, width}}>
    {points.slice(0, 3).map((point, index) => <div key={point} style={{position: 'relative', marginTop: index ? 48 : 0,
      paddingTop: 18, borderTop: `3px solid ${rule}`, color, fontFamily: SANS, fontWeight: 800,
      fontSize: fittedSize([point], 38, width), lineHeight: 1.35, overflowWrap: 'anywhere'}}>{point}</div>)}
  </div>;

/** A declaration is one claim at a time: strong type, a visible speaker, a clean hold. */
export const RedManifesto: React.FC<SceneProps> = props => {
  const {p, chapter} = props;
  const progress = reveal(props, 8);
  const offer = chapter.kind === 'offer';
  const headline = chapter.heading.slice(0, 2);
  return <AbsoluteFill style={{background: RED.paper, fontFamily: SANS, color: RED.ink}}>
    <svg width="1080" height="1920" viewBox="0 0 1080 1920" style={{position: 'absolute', inset: 0}} aria-hidden="true">
      <path d="M0 646H1080V1920H0Z" fill={RED.red}/>
      <path d="M0 646H305L218 1578H0Z" fill={RED.deep}/>
      <path d="M1008 0H1080V646H944Z" fill={RED.red}/>
      <path d="M0 1810H1080V1920H0Z" fill={RED.ink}/>
      <path d={`M0 646H${330 * progress}L${250 * progress} 727H0Z`} fill={RED.ink}/>
    </svg>
    <div style={{position: 'absolute', left: 74, top: offer ? 196 : 211, width: 920}}>
      {offer ? <>
        <div style={{overflow: 'hidden', color: RED.red, fontWeight: 900, lineHeight: 1.04,
          fontSize: fittedSize([headline[0] || ''], 238, 910), letterSpacing: -9,
          fontVariantNumeric: 'tabular-nums', translate: `${(1 - progress) * -42}px 0`}}>{headline[0]}</div>
        {headline[1] && <div style={{marginTop: 10, fontSize: fittedSize([headline[1]], 96, 910),
          lineHeight: 1.13, fontWeight: 900, letterSpacing: -3}}>{headline[1]}</div>}
      </> : <MaskedHeading lines={headline} width={920} size={136} color={RED.ink} progress={progress}/>}
    </div>
    <div style={{position: 'absolute', left: 80, top: 578, width: 894, color: RED.ink,
      fontSize: 42, lineHeight: 1.3, fontWeight: 600, opacity: progress}}>{chapter.deck}</div>
    <div style={{position: 'absolute', left: 330, top: 656, width: 682, height: 930,
      background: RED.ink, translate: `${(1 - progress) * 16}px 0`}}/>
    <PresenterWindow p={p} box={{x: 344, y: 670, w: 654, h: 902, radius: 0}} objectPosition="50% 48%"/>
    <PointRail points={chapter.points} x={80} y={771} width={210} color={RED.paper} rule={`${RED.paper}99`}/>
    <CaptionTrack p={p} box={{x: 80, y: 1614, w: 920, h: 180}} skin="red-manifesto"/>
  </AbsoluteFill>;
};

const SilverStage: React.FC<{progress: number}> = ({progress}) => <svg width="1080" height="1920" viewBox="0 0 1080 1920"
  style={{position: 'absolute', inset: 0}} aria-hidden="true">
  <defs>
    <linearGradient id="release-silver-wall" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stopColor="#FFFFFF"/><stop offset=".5" stopColor="#EFF3F5"/><stop offset="1" stopColor="#D9E2E7"/>
    </linearGradient>
    <linearGradient id="release-silver-base" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#FFFFFF"/><stop offset=".25" stopColor="#C5D1D8"/><stop offset=".6" stopColor="#EDF3F6"/><stop offset="1" stopColor="#B0BEC7"/>
    </linearGradient>
  </defs>
  <path d="M0 0H1080V1920H0Z" fill="url(#release-silver-wall)"/>
  <path d="M0 605C290 552 790 552 1080 605" fill="none" stroke="#D3DDE3" strokeWidth="2"/>
  <path d="M0 617C290 564 790 564 1080 617" fill="none" stroke="#FFFFFF" strokeWidth="3"/>
  <ellipse cx="540" cy="1515" rx={465 * progress + 1} ry="88" fill="url(#release-silver-base)"/>
  <ellipse cx="540" cy="1490" rx={465 * progress + 1} ry="68" fill="#FDFEFF" stroke="#DAE4E9" strokeWidth="2"/>
  <path d="M0 1840H1080" fill="none" stroke="#BDCAD2" strokeWidth="1"/>
</svg>;

/** A launch stage uses actual footage as its object, never a fake app or product. */
export const SilverLaunch: React.FC<SceneProps> = props => {
  const {p, chapter} = props;
  const progress = reveal(props, 12);
  const scene = activeScene(props);
  const offer = chapter.kind === 'offer';
  return <AbsoluteFill style={{background: SILVER.paper, color: SILVER.ink, fontFamily: SANS}}>
    <SilverStage progress={progress}/>
    <div style={{position: 'absolute', left: 80, top: 212, width: 920}}>
      <MaskedHeading lines={chapter.heading} width={920} size={offer ? 128 : 112} color={SILVER.ink}
        progress={progress} align="center" letterSpacing={offer ? -4 : -2} lineHeight={1.12}/>
    </div>
    <div style={{position: 'absolute', left: 105, top: 513, width: 870, textAlign: 'center',
      fontSize: 42, fontWeight: 500, lineHeight: 1.38, color: SILVER.muted, opacity: progress}}>{chapter.deck}</div>
    <div style={{position: 'absolute', left: 66, top: 632, width: 948, height: 865,
      background: '#FFFFFF', border: '2px solid #D4DFE5', borderRadius: 58,
      boxShadow: '0 25px 55px #526F7E1A'}}/>
    {scene ? <>
      <MaterialWindow scene={scene} box={{x: 82, y: 648, w: 916, h: 832, radius: 42}}/>
      {scene.sourceLabel && <div style={{position: 'absolute', left: 105, top: 671,
        padding: '9px 14px', background: '#F3F6F8EE', color: SILVER.ink,
        fontSize: 24, fontWeight: 600, lineHeight: 1.4}}>{scene.sourceLabel}</div>}
      <div style={{position: 'absolute', left: 731, top: 1118, width: 275, height: 366,
        background: '#FFFFFF', border: '2px solid #D5E1E7', borderRadius: 20}}/>
      <PresenterWindow p={p} box={{x: 739, y: 1126, w: 259, h: 350, radius: 14}} objectPosition="50% 44%"/>
    </> : <PresenterWindow p={p} box={{x: 82, y: 648, w: 916, h: 832, radius: 42}} objectPosition="50% 46%"/>}
    <div style={{position: 'absolute', left: 80, top: 1516, width: 920, height: 82,
      display: 'flex', background: '#FAFCFD', borderTop: `2px solid ${SILVER.cyan}`,
      borderBottom: '1px solid #BFCED6'}}>
      {chapter.points.slice(0, 3).map((point, index, list) => {
        const t = props.chapterIndex === 0 ? 1 : interpolate(localFrame(props), [index * 3, index * 3 + 10], [0, 1], clamp);
        return <div key={point} style={{width: `${100 / list.length}%`, display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderLeft: index ? '1px solid #C3D2DB' : undefined, color: SILVER.ink,
          fontSize: fittedSize([point], 35, 850 / list.length), lineHeight: 1.2, fontWeight: 700,
          opacity: t, translate: `0 ${(1 - t) * 5}px`}}>{point}</div>;
      })}
    </div>
    <CaptionTrack p={p} box={{x: 80, y: 1620, w: 920, h: 180}} skin="silver-launch"/>
  </AbsoluteFill>;
};

/** Real footage is evidence; the presenter is an explanation window over it. */
export const Documentary: React.FC<SceneProps> = props => {
  const {p, chapter} = props;
  const scene = activeScene(props);
  const progress = reveal(props, 8);
  return <AbsoluteFill style={{background: DOC.ink, color: DOC.paper, fontFamily: SANS}}>
    <svg width="1080" height="1920" viewBox="0 0 1080 1920" style={{position: 'absolute', inset: 0}} aria-hidden="true">
      <path d="M0 0H1080V580H0Z" fill="#20211E"/>
      <path d="M80 173H1000M80 1833H1000" fill="none" stroke="#696E64" strokeWidth="1"/>
      <path d="M0 580H1080" fill="none" stroke={DOC.paper} strokeWidth="2"/>
    </svg>
    <div style={{position: 'absolute', left: 80, top: 222, width: 920}}>
      <MaskedHeading lines={chapter.heading} width={920} size={110} color={DOC.paper}
        progress={progress} font={SONG} letterSpacing={0} lineHeight={1.12}/>
    </div>
    <div style={{position: 'absolute', left: 80, top: 505, width: 920, color: DOC.secondary,
      fontSize: 42, lineHeight: 1.35, fontWeight: 400, opacity: progress}}>{chapter.deck}</div>
    <div style={{position: 'absolute', left: 52, top: 600, width: 976, height: 994,
      background: '#080A08', border: '1px solid #5B6058'}}/>
    {scene ? <>
      <MaterialWindow scene={scene} box={{x: 54, y: 602, w: 972, h: 990, radius: 0}}/>
      {scene.sourceLabel && <div style={{position: 'absolute', left: 76, top: 620, maxWidth: 830,
        boxSizing: 'border-box', padding: '9px 14px', color: DOC.paper, background: '#1A1B19E8',
        fontSize: 24, fontWeight: 500, lineHeight: 1.4}}>{scene.sourceLabel}</div>}
      <div style={{position: 'absolute', left: 704, top: 1172, width: 298, height: 404,
        boxSizing: 'border-box', border: `2px solid ${DOC.paper}`, background: DOC.ink}}/>
      <PresenterWindow p={p} box={{x: 710, y: 1178, w: 286, h: 392, radius: 0}} objectPosition="50% 44%"/>
    </> : <PresenterWindow p={p} box={{x: 54, y: 602, w: 972, h: 990, radius: 0}} objectPosition="50% 48%"/>}
    <CaptionTrack p={p} box={{x: 80, y: 1630, w: 920, h: 180}} skin="documentary"/>
  </AbsoluteFill>;
};

export const NewDirections: React.FC<SceneProps> = props => {
  if (props.p.art.direction === 'red-manifesto') return <RedManifesto {...props}/>;
  if (props.p.art.direction === 'silver-launch') return <SilverLaunch {...props}/>;
  if (props.p.art.direction === 'documentary') return <Documentary {...props}/>;
  return null;
};

export default NewDirections;
