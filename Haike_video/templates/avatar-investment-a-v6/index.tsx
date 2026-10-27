import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, OffthreadVideo, Sequence, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import layout from './layout.json';

type Cue = {text: string; startMs: number; endMs: number};
type Emphasis = {match: string; text: string; kind: 'sticker' | 'card'; detail: string; footnote: string};
type Event = Emphasis & {id: string; start: number; end: number};
type Scene = {start: number; end: number; src: string; kind: string; generated: boolean; offset?: number};
type Props = {duration: number; avatarSrc: string; audioSrc: string; captions: Cue[]; events: Event[]; scenes?: Scene[];
  investment: {brand: string; headline: string; cta: string; emphasis: Emphasis[]; opening: boolean; closing: boolean}};
const colors = layout.palette;
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const defaults: Props = {duration: 8, avatarSrc: 'avatar.mp4', audioSrc: 'narration.wav', captions: [], events: [],
  investment: {brand: '海客科技', headline: '社区AI新生意\n全国招商', cta: '点击视频下方链接\n加入我们', emphasis: [], opening: true, closing: true}};
const borderText: React.CSSProperties = {paintOrder: 'stroke fill', WebkitTextStroke: '10px #fff', textShadow: '0 11px 0 #1549d8, 4px 15px 0 #1549d8, 0 20px 20px #12072d66'};
const titleLines = (text: string) => text.includes('\n') ? text.split('\n') : [...text].length > 12 ? [[...text].slice(0, Math.ceil([...text].length / 2)).join(''), [...text].slice(Math.ceil([...text].length / 2)).join('')] : [text];
const fittedTitleSize = (text: string, maximum: number, width: number) => Math.min(maximum, width / Math.max(...titleLines(text).map(line => [...line].length)));
// Keep the original caption text and line clock; only numeric runs change colour.
const captionText = (text: string) => text.split(/(\d+(?:[.,]\d+)*(?:[×xX]\d+)*(?:[万亿千百]\d*)?[%％]?)/g).map((part, index) => <span key={index} style={{color: /^\d/.test(part) ? layout.caption.numericColor : layout.caption.color}}>{part}</span>);

const Lightning: React.FC<{left: number; top: number; rotate?: number}> = ({left, top, rotate = 0}) => <svg viewBox="0 0 90 120" style={{position: 'absolute', left, top, width: 72, height: 96, rotate: `${rotate}deg`, filter: 'drop-shadow(0 4px 0 #fff)'}}><path d="M57 4 10 68h31l-9 49 47-72H48Z" fill={colors.gold} stroke={colors.gold} strokeWidth="5"/></svg>;

const NeonGrid = () => <svg viewBox="0 0 1080 1920" style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>
  <defs><linearGradient id="cover-glow"><stop stopColor={colors.cyan}/><stop offset=".55" stopColor={colors.purple}/><stop offset="1" stopColor={colors.magenta}/></linearGradient></defs>
  <g opacity=".3" stroke="url(#cover-glow)" strokeWidth="3">{Array.from({length: 15}, (_, i) => <path key={i} d={`M${-1200 + i * 240} 1920 540 1120 ${120 + i * 120} 1920`} fill="none"/>)}{[1330, 1450, 1610, 1830].map(y => <path key={y} d={`M0 ${y}h1080`}/>)}</g>
  <g transform="translate(540 1390)"><path d="m0-200 325 155L0 115-325-45Z" fill="#1a246c" stroke="url(#cover-glow)" strokeWidth="8"/><path d="M-325-45v85L0 200 325 40v-85L0 115Z" fill="#181545" stroke="url(#cover-glow)" strokeWidth="7"/><path d="m0-140 220 100L0 65-220-40Z" fill="#172768" stroke={colors.cyan} strokeWidth="4"/><text y="0" textAnchor="middle" fill="#fff" fontFamily="Arial,sans-serif" fontSize="120" fontWeight="900" style={{filter: 'drop-shadow(0 0 14px #59f8f4)'}}>AI</text></g>
</svg>;

const Cover: React.FC<{p: Props; closing: boolean; opacity: number; localFrame: number}> = ({p, closing, opacity, localFrame}) => <AbsoluteFill style={{opacity, background: 'radial-gradient(ellipse at 105% 55%,#d852eeaa,transparent 47%),radial-gradient(ellipse at 7% 15%,#6724d9,transparent 60%),linear-gradient(160deg,#1c0746,#060921 80%)'}}>
  <NeonGrid/>
  <div style={{position: 'absolute', left: 68, top: 155, right: 68, background: 'linear-gradient(90deg,#ffe76c,#ff8e14)', color: '#291035', padding: '18px 24px', fontSize: 48, fontWeight: 950, textAlign: 'center', rotate: '-5deg', boxShadow: '0 5px 0 #d455ff', whiteSpace: 'nowrap'}}>{p.investment.brand}</div>
  <div style={{position: 'absolute', left: 54, top: layout.cover.headlineTop, width: 972, textAlign: 'center', lineHeight: 1.18, fontSize: fittedTitleSize(p.investment.headline, layout.cover.headlineFontSize, 928), fontWeight: 950, letterSpacing: -5, color: '#fff', textShadow: '0 9px 0 #321157', translate: `0 ${interpolate(localFrame, [0, 10], [25, 0], clamp)}px`}}>
    {titleLines(p.investment.headline).map((line, i) => <div key={i} style={{color: i === 0 ? '#fff' : colors.cyan, textShadow: '0 6px 0 #321157'}}>{line}</div>)}
  </div>
  <div style={{position: 'absolute', left: 74, top: 850, width: 932, padding: '38px 30px', boxSizing: 'border-box', border: '3px solid #65efffb0', background: '#24144980', boxShadow: 'inset 0 0 32px #b750f24d,0 0 32px #ce4eff44', textAlign: 'center', color: '#fff'}}>
    <div style={{fontSize: 31, letterSpacing: 8, color: colors.cyan, fontWeight: 800}}>{p.investment.brand}</div>
    <div style={{fontSize: closing ? fittedTitleSize(p.investment.cta, 67, 850) : 53, lineHeight: 1.45, fontWeight: 900, marginTop: 18, color: closing ? colors.gold : '#fff'}}>{closing ? titleLines(p.investment.cta).map((line, i) => <div key={i}>{line}</div>) : '招商合作 · 共创未来'}</div>
  </div>
  <div style={{position: 'absolute', left: 72, right: 72, bottom: 160, textAlign: 'center', fontSize: 25, letterSpacing: 7, color: '#d5c9f7'}}>HAIKE · AI COMMUNITY</div>
</AbsoluteFill>;

const OverlayGroup: React.FC<{events: Event[]}> = ({events}) => {
  const frame = useCurrentFrame(), {fps} = useVideoConfig();
  const e = layout.emphasis;
  const multi = events.length > 1;
  const cards = events.slice(0, e.maxCards);
  const sticker = !multi && cards[0].kind === 'sticker';
  const progress = interpolate(frame - Math.round(events[0].start * fps), [0, layout.motion.popFrames], [0, 1], clamp);
  return <div style={{position: 'absolute', left: e.left, top: sticker ? e.top : e.cardTop, width: e.width, scale: .82 + progress * .18, opacity: progress}}>
    {!multi && cards[0].kind === 'sticker' ? <div style={{position: 'relative', textAlign: 'center', padding: '8px 40px', rotate: `${layout.motion.stickerTiltDegrees}deg`}}>
      <Lightning left={-8} top={-30} rotate={-20}/><Lightning left={e.width - 70} top={80} rotate={170}/>
      <div style={{...borderText, fontSize: Math.min(e.fontSize, 770 / Math.max(3, cards[0].text.length)), lineHeight: 1.25, fontWeight: 950, color: colors.red, letterSpacing: -2}}>{cards[0].text}</div>
      {cards[0].detail && <div style={{marginTop: 20, fontSize: 36, fontWeight: 850, color: '#fff', textShadow: '0 3px 0 #341071'}}>{cards[0].detail}</div>}
      {cards[0].footnote && <div style={{marginTop: 12, fontSize: 23, color: '#fff', textShadow: '0 2px 3px #000'}}>{cards[0].footnote}</div>}
    </div> : <div style={{display: 'flex', gap: 16, alignItems: 'stretch'}}>{cards.map((event, index) => <div key={event.id} style={{flex: 1, minWidth: 0, minHeight: e.cardHeight, boxSizing: 'border-box', padding: '18px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'center', background: 'linear-gradient(145deg,#2d106beF,#171d50f5)', border: '3px solid #a86cff', borderRadius: 18, boxShadow: '3px 5px 0 #5bf7f3bb,0 8px 25px #18062f88', textAlign: 'center'}}>
      <div style={{fontSize: 20, color: colors.cyan, letterSpacing: 3, fontWeight: 800}}>0{index + 1} · 项目要点</div>
      <div style={{fontSize: multi ? 36 : 60, lineHeight: 1.2, color: colors.gold, fontWeight: 950, marginTop: 10, overflowWrap: 'anywhere'}}>{event.text}</div>
      {event.detail && <div style={{fontSize: multi ? 16 : 28, color: '#fff', lineHeight: 1.35, marginTop: 10, overflowWrap: 'anywhere'}}>{event.detail}</div>}
      {event.footnote && <div style={{fontSize: multi ? 14 : 20, color: '#ddd3ef', lineHeight: 1.35, marginTop: 8, overflowWrap: 'anywhere'}}>{event.footnote}</div>}
    </div>)}</div>}
  </div>;
};

const InvestmentVideo: React.FC<Props> = p => {
  const frame = useCurrentFrame(), {fps, durationInFrames} = useVideoConfig(), seconds = frame / fps;
  const cue = p.captions.find(c => seconds * 1000 >= c.startMs && seconds * 1000 < c.endMs);
  const active = p.events.filter(e => seconds >= e.start && seconds < e.end);
  const scene = p.scenes?.find(s => seconds >= s.start && seconds < s.end);
  const coverFrames = Math.min(Math.round(layout.cover.openingSeconds * fps), Math.floor(durationInFrames / 3));
  const closingFrames = Math.min(Math.round(layout.cover.closingSeconds * fps), Math.floor(durationInFrames / 3));
  const closeStart = durationInFrames - closingFrames;
  const opening = p.investment.opening && frame < coverFrames;
  const closing = p.investment.closing && frame >= closeStart;
  const c = layout.caption, badge = layout.projectBadge, portrait = layout.portrait;
  return <AbsoluteFill style={{background: colors.ink, color: '#fff', fontFamily: '"Microsoft YaHei","PingFang SC",sans-serif'}}>
    <OffthreadVideo muted src={staticFile(p.avatarSrc)} style={{position: 'absolute', inset: -60, width: 1200, height: 2040, objectFit: 'cover', objectPosition: '50% 35%', filter: `blur(${portrait.backgroundBlur}px)`, opacity: .7}}/>
    <OffthreadVideo muted src={staticFile(p.avatarSrc)} style={{position: 'absolute', left: portrait.left, top: portrait.top, width: portrait.width, height: portrait.height, objectFit: 'contain'}}/>
    <AbsoluteFill style={{background: 'linear-gradient(#16052d75,transparent 26%,transparent 62%,#110b2c6b 82%,#110b2c 100%)'}}/>
    <div style={{position: 'absolute', left: 62, top: 102, fontSize: 26, fontWeight: 750, letterSpacing: 3, color: '#f0e4ff', textShadow: '0 2px 5px #11072e'}}>海客科技<br/><span style={{fontSize: 18, letterSpacing: 4, color: colors.cyan}}>AI COMMUNITY</span></div>
    <div style={{position: 'absolute', left: badge.left, top: badge.top, width: badge.width, minHeight: badge.height, boxSizing: 'border-box', borderRadius: 20, padding: '20px 22px', border: '3px solid #f3a6ff', background: 'linear-gradient(130deg,#54239dbc,#131456d9)', boxShadow: 'inset 0 0 22px #d55bfa88,4px 5px 0 #60e9f2,0 0 20px #ae40ef77', fontSize: 39, fontWeight: 900, lineHeight: 1.25, textAlign: 'center', overflowWrap: 'anywhere'}}>{p.investment.brand}</div>
    {scene && <div style={{position: 'absolute', left: 72, top: 896, width: 936, height: 527, background: '#12072d', border: '3px solid #a86cff', boxShadow: '4px 5px 0 #59f8f4', overflow: 'hidden'}}>
      <Sequence from={Math.round(scene.start * fps)} durationInFrames={Math.max(1, Math.round((scene.end - scene.start) * fps))} premountFor={fps}>
        {scene.kind === 'video' ? <OffthreadVideo muted trimBefore={Math.round((scene.offset || 0) * fps)} src={staticFile(scene.src)} style={{width: '100%', height: '100%', objectFit: 'contain'}}/> : <Img src={staticFile(scene.src)} style={{width: '100%', height: '100%', objectFit: 'contain'}}/>}
      </Sequence>
      {scene.generated && <div style={{position: 'absolute', bottom: 12, right: 14, fontSize: 21, background: '#140b2ccc', padding: '5px 10px'}}>AI示意画面</div>}
    </div>}
    {!scene && !!active.length && <OverlayGroup events={active}/>}
    {opening && <Cover p={p} closing={false} localFrame={frame} opacity={interpolate(frame, [coverFrames - layout.motion.coverFadeFrames, coverFrames], [1, 0], clamp)}/>}
    {closing && <Cover p={p} closing={true} localFrame={frame - closeStart} opacity={interpolate(frame, [closeStart, closeStart + layout.motion.coverFadeFrames], [0, 1], clamp)}/>}
    {cue && <div style={{position: 'absolute', left: c.left, top: c.top, width: c.width, minHeight: 96, textAlign: 'center', fontSize: c.fontSize, lineHeight: c.lineHeight, fontWeight: c.fontWeight, color: c.color, paintOrder: 'stroke fill', WebkitTextStroke: `${c.strokeWidth}px ${c.strokeColor}`, textShadow: c.textShadow, overflowWrap: 'anywhere'}}>{Array.from({length: Math.ceil([...cue.text.replace(/\n/g, '')].length / c.maxCharsPerLine)}, (_, i) => <div key={i}>{captionText([...cue.text.replace(/\n/g, '')].slice(i * c.maxCharsPerLine, (i + 1) * c.maxCharsPerLine).join(''))}</div>)}</div>}
    <div style={{position: 'absolute', left: 64, bottom: 99, fontSize: 22, letterSpacing: 3, color: '#eee6ffbd'}}>数字人演绎</div>
    <Audio src={staticFile(p.audioSrc)}/>
  </AbsoluteFill>;
};
const Root = () => <Composition id="HaikeInvestmentA6" component={InvestmentVideo} width={layout.canvas.width} height={layout.canvas.height} fps={layout.canvas.fps} durationInFrames={240} defaultProps={defaults} calculateMetadata={({props}) => ({durationInFrames: Math.max(1, Math.round(props.duration * layout.canvas.fps))})}/>;
registerRoot(Root);
