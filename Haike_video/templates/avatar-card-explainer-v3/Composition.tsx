import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type SampleCue = {
  start: number;
  end: number;
  text: string;
  emphasis: string[];
};

export type AvatarTemplate3Props = {
  avatar: string;
  broll: string | null;
  audio: string;
  cues: SampleCue[];
};

const FONT = '"Microsoft YaHei", "PingFang SC", sans-serif';
const INK = '#1D2330';
const MUTED = '#7C818D';
const BLUE = '#316DD6';
const CLAMP = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const CHAPTERS = [
  {start: 0, end: 3.6, number: '01', pill: '观察视角', title: '电商平台', accent: '连接用户', note: '从旧口播出发，观察购买路径的变化', summary: '平台连接用户', detail: ['需求与商品', '曾在同一个入口相遇'], progress: '连接'},
  {start: 3.6, end: 8.68, number: '02', pill: '路径对比', title: '购物习惯', accent: '正在改变', note: '同样是购物，寻找商品的路径正在变化', summary: '购物入口在变化', detail: ['从打开平台', '到先表达自己的需求'], progress: '变化'},
  {start: 8.68, end: 15, number: '03', pill: '流程示意', title: '先问 AI', accent: '再选货下单', note: '把口播里的想法，整理成一条清楚的路径', summary: '先问，再选择', detail: ['提出需求 · 智能选品', '最后回到购买决策'], progress: '新入口'},
];

const reveal = (seconds: number, delay: number) => interpolate(seconds, [delay, delay + 0.4], [0, 1], {...CLAMP, easing: Easing.out(Easing.cubic)});

const BrandMark: React.FC<{size?: number}> = ({size = 39}) => (
  <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
    <rect width="40" height="40" rx="12" fill="#EBF3FF" />
    <path d="M8 26 14 13 13 27 23 12 20 27 30 15 27 27" stroke="#3178D9" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const Arrow: React.FC<{blue?: boolean}> = ({blue = false}) => (
  <svg width="44" height="24" viewBox="0 0 44 24" fill="none" aria-hidden="true">
    <path d="M3 12H37M29 4L37 12 29 20" stroke={blue ? '#79A0E7' : '#B8BDCA'} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const MiniIcon: React.FC<{kind: 'person' | 'spark' | 'bag'; color?: string}> = ({kind, color = BLUE}) => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
    {kind === 'person' ? <><circle cx="20" cy="13" r="6" stroke={color} strokeWidth="2.5" /><path d="M8 33c0-7 5-11 12-11s12 4 12 11" stroke={color} strokeWidth="2.5" strokeLinecap="round" /></> : null}
    {kind === 'spark' ? <><path d="m20 5 4.4 10.6L35 20l-10.6 4.4L20 35l-4.4-10.6L5 20l10.6-4.4L20 5Z" stroke={color} strokeWidth="2.3" strokeLinejoin="round" /><path d="m31 5 1.5 3.5L36 10l-3.5 1.5L31 15l-1.5-3.5L26 10l3.5-1.5L31 5Z" fill={color} /></> : null}
    {kind === 'bag' ? <><path d="M10 14h20l3 21H7l3-21Z" stroke={color} strokeWidth="2.5" strokeLinejoin="round" /><path d="M14 15V11a6 6 0 0 1 12 0v4" stroke={color} strokeWidth="2.5" strokeLinecap="round" /></> : null}
  </svg>
);

const ChapterHeading: React.FC<{index: number}> = ({index}) => {
  const chapter = CHAPTERS[index];
  return <>
    <div style={{position: 'absolute', left: 32, top: 28, display: 'flex', alignItems: 'center', gap: 10, height: 38, padding: '0 14px', background: 'rgba(255,255,255,0.94)', borderRadius: 19, boxShadow: '0 3px 14px rgba(62,77,123,0.05)', color: '#777E8B', fontSize: 23, fontWeight: 600}}>
      <span style={{color: '#7F9DD0', fontFamily: 'Consolas, monospace', fontSize: 20}}>{chapter.number}</span>{chapter.pill}
    </div>
    <div style={{position: 'absolute', top: 92, left: 32, right: 24, fontSize: 60, fontWeight: 800, letterSpacing: '-2.3px', lineHeight: 1.2, whiteSpace: 'nowrap'}}>
      {chapter.title}<span style={{color: BLUE, marginLeft: 22}}>{chapter.accent}</span>
    </div>
    <div style={{position: 'absolute', top: 179, left: 34, right: 30, fontSize: 24, color: '#858995', letterSpacing: 0.25}}>{chapter.note}</div>
  </>;
};

const BrollPanel: React.FC<{broll: string | null}> = ({broll}) => (
  <div style={{position: 'absolute', left: 32, top: 234, width: 788, height: 441, borderRadius: 22, overflow: 'hidden', background: '#E7EDF6', boxShadow: '0 9px 25px rgba(74,79,101,0.09)'}}>
    {broll ? <OffthreadVideo src={staticFile(broll)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} /> : <div style={{width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 34, background: 'linear-gradient(130deg,#E8F0FC,#FAF4E9)'}}>
      {[{kind: 'person' as const, label: '用户'}, {kind: 'bag' as const, label: '商品'}].map((item, index) => <React.Fragment key={item.label}>
        {index > 0 ? <Arrow blue /> : null}
        <div style={{width: 213, height: 230, background: 'rgba(255,255,255,0.87)', border: '2px solid white', borderRadius: 24, boxShadow: '0 15px 40px #637A9E13', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 23}}>
          <div style={{width: 82, height: 82, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#EEF4FD', borderRadius: 24}}><MiniIcon kind={item.kind} /></div>
          <div style={{fontSize: 34, fontWeight: 700}}>{item.label}</div>
        </div>
      </React.Fragment>)}
    </div>}
    <div style={{position: 'absolute', left: 17, top: 17, padding: '9px 15px', display: 'flex', alignItems: 'center', gap: 9, background: 'rgba(255,255,255,0.94)', borderRadius: 14, color: '#424B5B', fontSize: 20, fontWeight: 600}}><BrandMark size={25} />旧素材 · 版式预览</div>
  </div>
);

const PathNode: React.FC<{text: string; active?: boolean; opacity: number; width?: number}> = ({text, active = false, opacity, width = 184}) => (
  <div style={{width, height: 81, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 18, background: active ? '#EAF2FF' : '#F2F4F7', color: active ? BLUE : '#5D6674', border: active ? '2px solid #D5E4FE' : '2px solid #E8EBF1', fontSize: 34, fontWeight: 700, opacity, translate: `0 ${12 * (1 - opacity)}px`}}>{text}</div>
);

const ComparisonPanel: React.FC<{seconds: number}> = ({seconds}) => (
  <>
    <div style={{position: 'absolute', left: 33, top: 235, width: 786, height: 189, borderRadius: 23, background: '#FFFFFF', border: '1.5px solid #E9ECF2', padding: '21px 29px', boxSizing: 'border-box'}}>
      <div style={{fontSize: 23, color: MUTED, marginBottom: 23}}>过去的路径<span style={{float: 'right', color: '#9EA4AE', fontSize: 19}}>打开平台，寻找商品</span></div>
      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
        <PathNode text="用户" opacity={reveal(seconds, 0.1)} />
        <div style={{opacity: reveal(seconds, 0.3)}}><Arrow /></div>
        <PathNode text="平台" opacity={reveal(seconds, 0.5)} />
        <div style={{opacity: reveal(seconds, 0.7)}}><Arrow /></div>
        <PathNode text="商品" opacity={reveal(seconds, 0.9)} />
      </div>
    </div>
    <div style={{position: 'absolute', left: 33, top: 449, width: 786, height: 195, borderRadius: 23, background: 'linear-gradient(110deg,#FFFFFF,#F1F6FF)', border: '2px solid #D8E6FD', padding: '21px 29px', boxSizing: 'border-box', opacity: reveal(seconds, 1.1), translate: `0 ${14 * (1 - reveal(seconds, 1.1))}px`}}>
      <div style={{fontSize: 23, color: BLUE, marginBottom: 25, fontWeight: 700}}>新的入口<span style={{float: 'right', color: '#8A9FBE', fontSize: 19, fontWeight: 400}}>先说需求，再看选择</span></div>
      <div style={{display: 'flex', alignItems: 'center', gap: 39, paddingLeft: 8}}>
        <PathNode text="用户" active opacity={reveal(seconds, 1.4)} width={222} />
        <div style={{opacity: reveal(seconds, 1.7)}}><Arrow blue /></div>
        <div style={{width: 306, height: 81, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, background: BLUE, color: 'white', borderRadius: 18, boxShadow: '0 8px 19px #316DD629', opacity: reveal(seconds, 1.95), translate: `0 ${12 * (1 - reveal(seconds, 1.95))}px`}}><MiniIcon kind="spark" color="#FFFFFF" /><span style={{fontSize: 37, fontWeight: 800}}>AI</span></div>
      </div>
    </div>
  </>
);

const StepsPanel: React.FC<{seconds: number}> = ({seconds}) => {
  const steps = [
    {title: '提出需求', detail: '说清目标与偏好', kind: 'person' as const},
    {title: '智能选品', detail: '按需求整理候选', kind: 'spark' as const},
    {title: '下单', detail: '比较之后，再作决定', kind: 'bag' as const},
  ];
  return <>{steps.map((step, index) => {
    const opacity = reveal(seconds, 0.13 + index * 0.8);
    return <div key={step.title} style={{position: 'absolute', left: 33, top: 235 + index * 143, width: 786, height: 123, background: index === 1 ? 'linear-gradient(110deg,#F2F7FF,#FFFFFF)' : '#FFFFFF', border: `1.5px solid ${index === 1 ? '#D8E6FD' : '#E9ECF2'}`, borderRadius: 23, display: 'flex', alignItems: 'center', padding: '0 27px', boxSizing: 'border-box', opacity, translate: `0 ${18 * (1 - opacity)}px`}}>
      <div style={{width: 65, height: 65, borderRadius: 19, display: 'flex', alignItems: 'center', justifyContent: 'center', background: index === 1 ? '#E4EEFE' : '#F1F4F9', color: index === 1 ? BLUE : '#8793A8', fontFamily: 'Consolas, monospace', fontSize: 28, fontWeight: 700}}>0{index + 1}</div>
      <div style={{marginLeft: 25}}><div style={{fontSize: 35, color: index === 1 ? BLUE : INK, fontWeight: 800, lineHeight: 1.25}}>{step.title}</div><div style={{fontSize: 22, color: '#8A8F99', marginTop: 5}}>{step.detail}</div></div>
      <div style={{marginLeft: 'auto', marginRight: 8}}><MiniIcon kind={step.kind} color={index === 1 ? BLUE : '#96A4B9'} /></div>
    </div>;
  })}</>;
};

const Summary: React.FC<{seconds: number}> = ({seconds}) => {
  const index = seconds < 3.6 ? 0 : seconds < 8.68 ? 1 : 2;
  const chapter = CHAPTERS[index];
  const progress = interpolate(seconds, [chapter.start, index === 2 ? 12.445 : chapter.end], [0, 1], CLAMP);
  return <div style={{position: 'absolute', left: 535, top: 962, width: 401, height: 300}}>
    <div style={{fontSize: 22, color: '#8A8E98', letterSpacing: 1}}>AI 购物观察<span style={{float: 'right', fontSize: 20, fontFamily: 'Consolas, monospace', letterSpacing: 0}}>{chapter.number} / 03</span></div>
    <div style={{display: 'flex', alignItems: 'center', gap: 13, marginTop: 27}}><BrandMark size={36} /><div style={{fontSize: 40, fontWeight: 800, whiteSpace: 'nowrap', letterSpacing: '-1.2px'}}>{chapter.summary}</div></div>
    <div style={{fontSize: 27, color: '#7D828D', lineHeight: 1.62, marginTop: 18, letterSpacing: 0.3}}>{chapter.detail[0]}<br />{chapter.detail[1]}</div>
    <div style={{display: 'flex', gap: 15, marginTop: 26}}>{CHAPTERS.map((item, chapterIndex) => <div key={item.number} style={{width: 115}}>
      <div style={{height: 7, borderRadius: 4, background: '#E8EBF1', overflow: 'hidden'}}><div style={{height: '100%', width: `${chapterIndex < index ? 100 : chapterIndex === index ? progress * 100 : 0}%`, background: BLUE, borderRadius: 4}} /></div>
      <div style={{fontSize: 19, color: chapterIndex === index ? BLUE : '#A6ACB7', marginTop: 12, fontWeight: chapterIndex === index ? 600 : 400}}>{item.progress}</div>
    </div>)}</div>
  </div>;
};

const measureText = (text: string, size: number): number => {
  if (typeof document === 'undefined') return Array.from(text).reduce((sum, letter) => sum + (/^[\x00-\x7F]$/.test(letter) ? size * 0.58 : size), 0);
  const context = document.createElement('canvas').getContext('2d');
  if (!context) return text.length * size;
  context.font = `700 ${size}px ${FONT}`;
  return context.measureText(text).width;
};

const EmphasizedText: React.FC<{text: string; emphasis: string[]}> = ({text, emphasis}) => {
  const words = emphasis.filter(Boolean).sort((a, b) => b.length - a.length);
  const pieces: React.ReactNode[] = [];
  for (let index = 0; index < text.length;) {
    const match = words.find((word) => text.startsWith(word, index));
    if (match) {
      pieces.push(<span key={index} style={{color: BLUE}}>{match}</span>);
      index += match.length;
    } else {
      pieces.push(<React.Fragment key={index}>{text[index]}</React.Fragment>);
      index += 1;
    }
  }
  return <>{pieces}</>;
};

const Captions: React.FC<{cues: SampleCue[]; seconds: number}> = ({cues, seconds}) => {
  const prepared = useMemo(() => cues.map((cue) => {
    const fontSize = Math.max(36, Math.min(44, Math.floor(44 * 880 / Math.max(1, measureText(cue.text, 44)))));
    const textWidth = measureText(cue.text, fontSize);
    if (textWidth > 880) throw new Error(`字幕在36px仍超出880px，请拆句：${cue.text}`);
    return {...cue, fontSize};
  }), [cues]);
  const cue = prepared.find((item) => seconds >= item.start && seconds < item.end);
  if (!cue) return null;
  return <div style={{position: 'absolute', left: 100, top: 1302, width: 880, height: 60, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#686F7E', fontSize: cue.fontSize, fontWeight: 700, lineHeight: 1.25, whiteSpace: 'nowrap'}}><span><EmphasizedText text={cue.text} emphasis={cue.emphasis ?? []} /></span></div>;
};

export const AvatarTemplate3Sample: React.FC<AvatarTemplate3Props> = ({avatar, broll, audio, cues}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frame / fps;
  return <AbsoluteFill style={{fontFamily: FONT, color: INK, background: 'radial-gradient(ellipse at 8% 6%,#C6DEFF 0%,transparent 45%), radial-gradient(ellipse at 100% 4%,#FFECC9 0%,transparent 48%), radial-gradient(ellipse at 100% 80%,#FFDDD8 0%,transparent 53%), radial-gradient(ellipse at 18% 100%,#BFA6E7 0%,transparent 54%), #EAE7F3'}}>
    <div style={{position: 'absolute', left: 63, top: 72, width: 954, height: 1296, borderRadius: 40, background: 'linear-gradient(155deg,#FFFFFF 8%,#FFFEFC 83%,#FDFCFB)', boxShadow: '0 24px 58px rgba(60,56,99,0.16), 0 3px 7px rgba(76,84,123,0.09)', border: '1.5px solid rgba(255,255,255,0.93)', boxSizing: 'border-box'}} />
    <div style={{position: 'absolute', left: 111, top: 111, right: 117, height: 45, display: 'flex', alignItems: 'center'}}>
      <BrandMark /><span style={{marginLeft: 14, fontSize: 32, fontWeight: 800, letterSpacing: -0.7}}>海客</span><span style={{marginLeft: 19, fontSize: 25, color: '#6D7582'}}>AI观察</span>
      <span style={{marginLeft: 'auto', fontSize: 23, color: '#717985', letterSpacing: 0.8}}>消费 · 入口 · 变化</span><span style={{width: 16, height: 16, borderRadius: '50%', background: '#F16A78', marginLeft: 29, boxShadow: '0 0 0 4px #F16A780A'}} />
    </div>
    <div style={{position: 'absolute', left: 112, top: 174, width: 854, height: 1, background: '#EDEEF2'}} />
    <div style={{position: 'absolute', left: 114, top: 186, width: 852, height: 708, borderRadius: 29, background: 'linear-gradient(155deg,#F6F8FD,#F8F7F5)', border: '1.5px solid #F0F1F5', boxSizing: 'border-box', overflow: 'hidden'}}>
      {CHAPTERS.map((chapter, index) => {
        const enter = index === 0 ? 1 : interpolate(seconds, [chapter.start, chapter.start + 0.25], [0, 1], CLAMP);
        const exit = index === CHAPTERS.length - 1 ? 1 : interpolate(seconds, [chapter.end, chapter.end + 0.25], [1, 0], CLAMP);
        const opacity = enter * exit;
        if (opacity <= 0) return null;
        return <AbsoluteFill key={chapter.number} style={{opacity}}>
          <ChapterHeading index={index} />
          {index === 0 ? <BrollPanel broll={broll} /> : null}
          {index === 1 ? <ComparisonPanel seconds={seconds - chapter.start} /> : null}
          {index === 2 ? <StepsPanel seconds={seconds - chapter.start} /> : null}
        </AbsoluteFill>;
      })}
    </div>
    <div style={{position: 'absolute', left: 123, top: 927, width: 360, height: 360, boxSizing: 'border-box', borderRadius: '50%', padding: 6, background: 'linear-gradient(145deg,#C8CCD0,#E8E9E8 52%,#BDC1C5)', boxShadow: '0 5px 17px rgba(37,45,60,0.05)'}}>
      <div style={{width: '100%', height: '100%', borderRadius: '50%', overflow: 'hidden', background: '#E8EAED'}}><OffthreadVideo src={staticFile(avatar)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} /></div>
    </div>
    <Summary seconds={seconds} />
    <Captions cues={cues} seconds={seconds} />
    <Audio src={staticFile(audio)} />
  </AbsoluteFill>;
};
