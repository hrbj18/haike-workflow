import React from 'react';
import {AbsoluteFill, Audio, Composition, Img, OffthreadVideo, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import layout from './layout.json';

type Cue = {text: string; startMs: number; endMs: number};
type Direction = 'blue-editorial' | 'community-showcase' | 'optical-cinema';
type Chapter = {kind: 'hook' | 'story' | 'ai' | 'offer' | 'cta'; start: number; end: number; heading: string[]; deck: string; points: string[]};
type Props = {duration: number; avatarSrc: string; audioSrc: string; captions: Cue[]; brand: string; art: {direction: Direction; backgroundSrc: string; chapters: Chapter[]; highlights: string[]; portraitFraming: 'close-4x5' | 'medium-9x16'}};
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const defaults: Props = {duration: 8, avatarSrc: 'avatar.mp4', audioSrc: 'narration.wav', captions: [], brand: '海客AI社区服务站', art: {direction: 'blue-editorial', backgroundSrc: 'art-background.png', chapters: [{kind: 'hook', start: 0, end: 8, heading: ['一家店', '一座内容现场'], deck: '让真实体验，成为内容素材', points: ['真实顾客', '体验互动', '内容素材']}], highlights: ['真实体验', '内容素材'], portraitFraming: 'medium-9x16'}};

// Whole-cue motion follows observed ASR boundaries. Keyword chips are static
// emphasis; they do not pretend to be word-by-word timing or karaoke alignment.
const Caption: React.FC<{cue: Cue; direction: Direction; highlights: string[]; outside: boolean}> = ({cue, direction, highlights, outside}) => {
  const frame = useCurrentFrame(), {fps} = useVideoConfig();
  const a = interpolate(frame - cue.startMs / 1000 * fps, [0, layout.motion.captionRevealFrames], [0, 1], clamp);
  const blue = direction === 'blue-editorial', green = direction === 'community-showcase';
  const lines = cue.text.split('\n');
  const longest = Math.max(...lines.map(line => [...line].length));
  const available = outside ? 856 : blue ? 810 : 708;
  const fontSize = Math.min(layout.type.caption, available / Math.max(1, longest));
  let chips = 0;
  const paint = (line: string) => {
    const tokens: {text: string; chip: boolean}[] = [];
    let cursor = 0;
    while (cursor < line.length) {
      const matches = highlights.map(word => ({word, at: line.indexOf(word, cursor)})).filter(m => m.at >= 0).sort((a, b) => a.at - b.at || b.word.length - a.word.length);
      const hit = chips < layout.caption.maxKeywordChips ? matches[0] : undefined;
      if (!hit) { tokens.push({text: line.slice(cursor), chip: false}); break; }
      if (hit.at > cursor) tokens.push({text: line.slice(cursor, hit.at), chip: false});
      tokens.push({text: hit.word, chip: true}); chips++; cursor = hit.at + hit.word.length;
    }
    return tokens.map((t, i) => <span key={i} style={t.chip ? {background: blue ? '#1745d9' : green ? '#f4c857' : '#dcc393', color: blue ? '#fff' : green ? '#173c2c' : '#10171c', borderRadius: green ? 8 : 3, padding: '3px 3px 5px', boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone', fontWeight: 800} : undefined}>{t.text}</span>);
  };
  return <div style={{position: 'absolute', left: outside ? 80 : layout.caption.insideLeft, right: outside ? 80 : layout.caption.insideLeft, ...(outside ? {top: layout.caption.outsideTop} : {bottom: layout.caption.insideBottom}), opacity: a, transform: `translateY(${(1 - a) * layout.motion.captionRisePx}px)`, zIndex: 10}}>
    <div style={{position: 'relative', padding: blue ? '14px 17px 17px 23px' : '12px 16px 17px', background: blue ? '#fbfaf4fa' : green ? '#214b3bf7' : '#091015ed', color: blue ? '#173fc9' : '#fff5de', borderRadius: green ? 24 : blue ? 4 : 8, border: green ? '1px solid #f2e9cb99' : blue ? '1px solid #ffffff' : '1px solid #b699694d', boxShadow: blue ? '0 7px 0 #1745d9,0 10px 24px #11263c25' : '0 8px 22px #00000029', textAlign: 'center', fontSize, lineHeight: layout.caption.lineHeight, fontWeight: 700, letterSpacing: -.4, whiteSpace: 'pre', fontFamily: '"Microsoft YaHei",sans-serif', fontVariantNumeric: 'tabular-nums'}}>
      {blue && <div style={{position: 'absolute', left: 0, top: 14, bottom: 17, width: 6, background: '#df4930'}}/>}
      {lines.map((line, i) => <div key={i}>{paint(line)}</div>)}
      {!blue && !green && <div style={{position: 'absolute', left: 22, right: 22, bottom: 0, height: 2, background: 'linear-gradient(90deg,#d8b47c,transparent)'}}/>}
    </div>
  </div>;
};

const PointIcon: React.FC<{label: string; color: string}> = ({label, color}) => <svg viewBox="0 0 40 40" width="40" height="40" fill="none" stroke={color} strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
  {/素材|内容|视频|拍/.test(label) ? <><rect x="7" y="11" width="26" height="20" rx="4"/><circle cx="20" cy="21" r="5"/><path d="M13 11l3-4h8l3 4"/></> : /设备|产品|货/.test(label) ? <><path d="m8 13 12-6 12 6-12 6-12-6Z"/><path d="M8 13v15l12 6 12-6V13M20 19v15"/></> : /培训|清单|资料|了解/.test(label) ? <><path d="M11 32V10h18v22H11Z"/><path d="M16 16h8M16 21h8M16 26h5"/></> : <><path d="M8 31V15l12-8 12 8v16H8Z"/><path d="M16 31V20h8v11"/></>}
</svg>;

export const InvestmentArt: React.FC<Props> = (p) => {
  const frame = useCurrentFrame(), {fps, durationInFrames} = useVideoConfig();
  const sec = frame / fps, art = p.art, theme = layout[art.direction];
  const blue = art.direction === 'blue-editorial', green = art.direction === 'community-showcase', dark = art.direction === 'optical-cinema';
  const chapter = art.chapters.find(c => sec >= c.start && sec < c.end) ?? art.chapters[art.chapters.length - 1];
  const cue = p.captions.find(c => sec * 1000 >= c.startMs && sec * 1000 < c.endMs);
  const reveal = interpolate(frame - chapter.start * fps, [0, layout.motion.chapterRevealFrames], [0, 1], clamp);
  const headlineSize = Math.min(layout.type.headline, (green ? 928 : 920) / Math.max(...chapter.heading.map(l => [...l].length)));
  const font = green && chapter.kind !== 'offer' ? '"KaiTi","Microsoft YaHei",sans-serif' : dark && chapter.kind !== 'offer' ? '"SimSun","Microsoft YaHei",serif' : '"Microsoft YaHei",sans-serif';
  const close = art.portraitFraming === 'close-4x5';
  const win = theme.portrait;
  return <AbsoluteFill style={{background: theme.base, color: theme.ink, fontFamily: '"Microsoft YaHei",sans-serif', overflow: 'hidden'}}>
    <Img src={staticFile(art.backgroundSrc)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${1 + (layout.motion.backgroundMaxScale - 1) * frame / Math.max(1, durationInFrames - 1)})`}}/>
    <div style={{position: 'absolute', top: 76, left: 80, right: 80, display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 25, borderBottom: green ? 'none' : `1px solid ${dark ? '#b9976666' : '#1745d9'}`, color: dark ? '#ddc8a5' : theme.ink}}>
      <div style={{fontSize: 35, fontWeight: dark ? 500 : 700, letterSpacing: 1}}>{p.brand}</div>
      <div style={{fontSize: 26, fontWeight: 500, color: theme.muted}}>社区AI × 内容创作</div>
    </div>
    <div key={chapter.start} style={{position: 'absolute', left: 76, right: 76, top: 196, zIndex: 3, transform: `translateX(${(1 - reveal) * (dark ? 0 : 16)}px)`, textAlign: dark ? 'center' : 'left'}}>
      <div style={{fontFamily: font, fontSize: headlineSize, fontWeight: 700, lineHeight: dark ? 1.25 : 1.2, letterSpacing: dark ? 2 : -2.5, fontVariantNumeric: 'tabular-nums'}}>{chapter.heading.map((line, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{line}</div>)}</div>
      <div style={{marginTop: 26, color: theme.muted, fontSize: layout.type.deck, lineHeight: 1.45, maxWidth: 920, whiteSpace: 'pre-wrap', textWrap: 'balance'}}>{chapter.deck}</div>
    </div>
    <div style={{position: 'absolute', left: win.left, top: win.top, width: win.width, height: win.height, borderRadius: win.radius, overflow: 'hidden', boxShadow: dark ? '0 0 0 1px #c59e6755,0 16px 60px #0008' : green ? '0 0 0 4px #fff9,0 12px 42px #535a3b24' : '0 12px 35px #1234491f'}}>
      <OffthreadVideo src={staticFile(p.avatarSrc)} muted style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: `50% ${close ? '48%' : win.objectY}`, transform: close ? 'scale(1.02)' : undefined, filter: dark ? 'saturate(.86) contrast(1.02)' : undefined}}/>
      {!green && <div style={{position: 'absolute', inset: 0, background: dark ? 'linear-gradient(transparent 56%,#080c1044 73%,#080c10d9)' : 'linear-gradient(transparent 65%,#152b4933)'}}/>}
      {!green && cue && <Caption cue={cue} direction={art.direction} highlights={art.highlights} outside={false}/>}
      {dark && <div style={{position: 'absolute', left: 20, right: 20, bottom: 12, height: 1, background: '#d1ad7166'}}/>}
    </div>
    {green && cue && <Caption cue={cue} direction={art.direction} highlights={art.highlights} outside/>}
    {green ? <div style={{position: 'absolute', left: 80, top: chapter.kind === 'cta' ? 830 : 770, width: 180, display: 'flex', flexDirection: 'column', gap: 34}}>
      {(chapter.points.length ? chapter.points : ['了解门店', '领取资料']).map((text, i) => <div key={text} style={{border: '1px solid #7c947466', borderRadius: i === 1 ? '18px 70px 18px 70px' : '80px', minHeight: 146, padding: '16px 6px', background: '#fcfaf0ed', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, boxShadow: '0 6px 18px #5e685b10'}}>
        <PointIcon label={text} color={theme.ink}/><div style={{fontSize: Math.min(36, 160 / Math.max(1, [...text].length)), fontWeight: 700, color: theme.ink, textAlign: 'center'}}>{text}</div>
      </div>)}
    </div> : <div style={{position: 'absolute', left: 80, right: 80, top: 1670, padding: '23px 18px', borderTop: `${blue ? 3 : 1}px solid ${dark ? '#bd9b6b88' : '#1745d9'}`, borderBottom: `1px solid ${dark ? '#bd9b6b55' : '#1745d955'}`, background: dark ? '#0b1013ad' : '#fbfaf2f5', display: 'flex', alignItems: 'center', justifyContent: 'space-around', color: dark ? '#e9d8b9' : '#173fc9', fontSize: chapter.kind === 'cta' ? 43 : 37, fontWeight: 700}}>
      {(chapter.points.length ? chapter.points : ['点击下方', '立即咨询']).map((point, i) => <React.Fragment key={point}>{i > 0 && <div style={{width: 5, height: 5, borderRadius: 5, background: theme.accent, opacity: .8}}/>}<div>{point}</div></React.Fragment>)}
    </div>}
    <div style={{position: 'absolute', left: 80, bottom: 64, fontSize: 23, letterSpacing: 2, color: theme.muted}}>数字人演绎</div>
    {!green && <div style={{position: 'absolute', left: 80, right: 80, bottom: 108, height: 2, background: dark ? '#b8976a24' : '#29433b18'}}><div style={{height: '100%', width: `${100 * frame / Math.max(1, durationInFrames - 1)}%`, background: theme.accent, opacity: .8}}/></div>}
    <Audio src={staticFile(p.audioSrc)} volume={1}/>
  </AbsoluteFill>;
};

const Root = () => <Composition id="HaikeInvestmentArtV3" component={InvestmentArt} width={1080} height={1920} fps={30} durationInFrames={240} defaultProps={defaults} calculateMetadata={({props}) => ({durationInFrames: Math.max(1, Math.round(props.duration * 30))})}/>;
registerRoot(Root);
