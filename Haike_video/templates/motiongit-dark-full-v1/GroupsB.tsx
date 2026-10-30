import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import type {Context} from './types';
import {body, clamp, cue, mainMedia, Material, mediaAt, mix, NativeWindow, phase, rect, strings, StoryGround, storyPresenterLarge, Study, text, value} from './shared';

/**
 * Complete reference groups B. Source cues are absolute reference seconds; cue()
 * maps their STARTS, while phase() durations below remain fixed local seconds.
 * Inner demonstrations are editable Study artwork, not a reconstruction of an
 * existing product UI. All real moving footage is delegated to SceneClock's
 * declared videoWindows through Material; window changes never restart media.
 */
type Box = [number, number, number, number];
type World = {bg: string; ink: string; muted: string; accent: string; line: string; panel: string};
const box = (b: Box): React.CSSProperties => rect(...b);
const between = (a: Box, b: Box, n: number): Box => a.map((v, i) => mix(v, b[i], n)) as Box;
const at = (c: Context, id: string, source: number) => cue(c, id, source);
const go = (c: Context, id: string, source: number, duration = .65) => phase(c.seconds, at(c, id, source), duration);
const num = (c: Context, key: string, fallback: number) => typeof c.s.content[key] === 'number' && Number.isFinite(c.s.content[key]) ? c.s.content[key] as number : fallback;
const list = (c: Context, key: string, fallback: string[]) => {
  const items = strings(c, key, fallback);
  return fallback.map((f, i) => items[i] || f);
};
const world = (c: Context, mode: 'dark' | 'paper' | 'accent' = 'dark'): World => {
  const ref = c.p.variant === 'reference', blue = c.p.variant === 'cobalt';
  if (mode === 'paper') return {bg: ref ? '#F5F5F2' : c.t.paper, ink: ref ? '#080B0E' : c.t.bg === '#F1F4F8' ? c.t.ink : c.t.bg, muted: '#747A79', accent: c.t.accent, line: '#13232917', panel: ref ? '#FFFFFF' : blue ? '#FFFFFF' : '#FFFEF5'};
  if (mode === 'accent') return {bg: ref ? '#1453E6' : blue ? c.t.accent : '#456D47', ink: '#FFFFFF', muted: '#FFFFFFA3', accent: ref ? '#FFFFFF' : c.t.accent, line: '#FFFFFF20', panel: '#00000020'};
  return {bg: ref ? '#030303' : blue ? '#10213C' : c.t.bg, ink: ref || blue ? '#F7F9FB' : c.t.ink, muted: ref ? '#868B91' : blue ? '#BAC9DF' : c.t.muted, accent: ref ? '#5C84FF' : blue ? '#73B8FF' : c.t.accent, line: ref ? '#FFFFFF0C' : '#FFFFFF12', panel: ref ? '#080E13' : blue ? '#172F4D' : c.t.panel};
};
const Ground: React.FC<{c: Context; w: World; grid?: boolean; children?: React.ReactNode}> = ({c, w, grid = true, children}) => <AbsoluteFill style={{background: w.bg, overflow: 'hidden'}}>
  {grid && <AbsoluteFill style={{pointerEvents: 'none', backgroundImage: `linear-gradient(${w.line} 1px,transparent 1px),linear-gradient(90deg,${w.line} 1px,transparent 1px)`, backgroundSize: c.portrait ? '240px 240px' : '240px 240px'}}/>}{children}
</AbsoluteFill>;
const Avatar: React.FC<{c: Context; size: number; color?: string}> = ({c, size, color}) => <div style={{width: size, height: size, borderRadius: '50%', overflow: 'hidden', border: `2px solid ${color || c.t.accent}`, background: c.t.panel, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
  {c.p.referencePortrait ? <Img src={staticFile(c.p.referencePortrait)} style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 30%'}}/> : <span style={{...text(size * .33, color || c.t.accent), lineHeight: 1}}>{value(c, 'identityInitial', 'M')}</span>}
</div>;
const Eyebrow: React.FC<{c: Context; children: React.ReactNode; w: World; style?: React.CSSProperties}> = ({c, children, w, style}) => <div style={{...body(c.portrait ? 25 : 21, w.muted), letterSpacing: 1, ...style}}>{children}</div>;
const Tag: React.FC<{c: Context; children: React.ReactNode; bg: string; color: string; style?: React.CSSProperties}> = ({c, children, bg, color, style}) => <div style={{display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: c.portrait ? '13px 24px' : '9px 22px', borderRadius: 999, background: bg, ...body(c.portrait ? 25 : 24, color), fontWeight: 700, ...style}}>{children}</div>;
const Art: React.FC<{c: Context; index?: number; kind?: number; main?: boolean; live?: boolean; phone?: boolean}> = ({c, index = 0, kind = index, main = false, live = true, phone = false}) => {
  const m = main ? mainMedia(c) : mediaAt(c, index);
  return m ? <Material m={m} live={live}/> : <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#071217'}}><div style={phone ? {position: 'absolute', left: '-100%', width: '300%', height: '100%'} : {position: 'absolute', inset: 0}}><Study kind={kind} seconds={c.seconds} variant={c.p.variant}/></div></div>;
};
const SceneTitle: React.FC<{c: Context; w: World; children: React.ReactNode; style?: React.CSSProperties}> = ({c, w, children, style}) => <div style={{...rect(c.portrait ? 88 : 140, c.portrait ? 220 : 155, c.portrait ? 1264 : 1530, c.portrait ? 200 : 170), ...text(c.portrait ? 88 : 84, w.ink), ...style}}>{children}</div>;

/** s05 content: reactionTop/Bottom, identityContext/Name, softwareHeading/Name,
 * featureLabels/Descriptions[2], playbackLabel, pathLabels[3], pathHeading,
 * pathConclusion. Social variants deliberately have no comparative numbers. */
const S05: React.FC<{c: Context}> = ({c}) => {
  const w = world(c), ref = c.p.variant === 'reference', p = c.portrait;
  const crack = go(c, 'crack', 54.87, .26), identity = go(c, 'identity', 55.4, .55), software = go(c, 'software_window', 57.9, .75), detail = go(c, 'software_detail', 61.3, .52), competition = go(c, 'competition', 66.37, .65), result = go(c, 'lane_result', 68.3, .7);
  const titleIn = phase(c.seconds, at(c, 'crack', 54.87) - .75, .5), crackAge = c.seconds - at(c, 'crack', 54.87);
  const featureLabels = list(c, 'featureLabels', ref ? ['素材接入', '动画组件'] : ['活动现场', '亲手体验']);
  const featureDescriptions = list(c, 'featureDescriptions', ref ? ['镜头素材在自己的时钟中播放', '将内容转折变成完整的动作'] : ['保留真实的到店与互动记录', '从近距离观察，到亲手尝试']);
  const pathLabels = list(c, 'pathLabels', ref ? ['路径 A', '路径 B', '路径 C'] : ['走近现场', '看看新鲜', '亲手尝试']);
  const swBox: Box = p ? [88, 465, 1264, 710] : [180, 333, 880, 600];
  const artifactBox: Box = p ? [172, 495, 1096, 640] : [455, 250, 1010, 570];
  return <Ground c={c} w={w}>
    <div style={{opacity: (1 - identity) * (1 - software), ...rect(p ? 88 : 140, p ? 230 : 350, p ? 1264 : 1150, 430)}}>
      <div style={{...text(p ? 88 : 114, w.muted), opacity: titleIn, transform: `translateY(${mix(32, 0, titleIn)}px)`}}>{value(c, 'reactionTop', ref ? '从展开' : '从看见')}</div>
      <div style={{position: 'relative', ...text(p ? 124 : 185, w.ink), opacity: crack, transform: `scale(${mix(1.16, 1, crack)})`, transformOrigin: '0 50%'}}>{value(c, 'reactionBottom', ref ? '到聚合' : '到亲手体验')}
        {crackAge >= 0 && crackAge < .5 && <svg viewBox="0 0 800 180" style={{position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 1 - clamp(crackAge / .5)}}><path d="M440 0 L405 42 L445 61 L388 94 L433 110 L402 180 M420 52 L505 34 M413 111 L338 128" fill="none" stroke="#E35261" strokeWidth="4"/></svg>}
      </div>
    </div>
    <div style={{...rect(p ? 100 : 150, p ? 660 : 480, p ? 1200 : 1060, 170), display: 'flex', alignItems: 'center', gap: p ? 30 : 24, opacity: identity * (1 - software), transform: `translateY(${mix(30, 0, identity)}px)`}}>
      <Avatar c={c} size={p ? 130 : 112}/><div><Eyebrow c={c} w={w}>{value(c, 'identityContext', ref ? '示例人物 · AI主讲' : '海客AI · 社区服务')}</Eyebrow><div style={{...text(p ? 92 : 96, w.ink), marginTop: 12}}>{value(c, 'identityName', ref ? '创作者' : '来现场，看看新鲜')}</div></div>
    </div>
    {software > 0 && <div style={{opacity: software * (1 - competition), transform: `translateY(${mix(55, 0, software)}px)`}}>
      <SceneTitle c={c} w={w} style={{fontSize: p ? 76 : 66}}>{value(c, 'softwareHeading', ref ? '让画面动起来' : '把体验留在画面里')}</SceneTitle>
      <div style={box(swBox)}><NativeWindow c={c} title={value(c, 'softwareName', ref ? '演示工作台 · 自制界面' : '海客AI · 活动实拍')}>
        {detail < 1 && <div style={{position: 'absolute', inset: 0, opacity: 1 - detail}}><Art c={c} kind={1}/></div>}
        {detail > 0 && <div style={{position: 'absolute', inset: 0, opacity: detail}}><Art c={c} index={1} kind={2}/></div>}
      </NativeWindow></div>
      <div style={{...rect(p ? 88 : 1240, p ? 1210 : 365, p ? 1264 : 500, p ? 160 : 400), display: 'flex', flexDirection: p ? 'row' : 'column', gap: p ? 30 : 62}}>
        {featureLabels.map((label, i) => {const progress = phase(c.seconds, at(c, i ? 'software_detail' : 'software_window', i ? 61.3 : 57.9) + .25, .5); return <div key={i} style={{flex: p ? 1 : undefined, opacity: progress, transform: `translateX(${mix(28, 0, progress)}px)`}}><div style={text(p ? 35 : 34, w.ink)}>{label}</div><div style={{...body(p ? 25 : 22, w.muted), marginTop: 13}}>{featureDescriptions[i]}</div>{i === 1 && <div style={{...body(p ? 20 : 19, w.accent), marginTop: 15}}>{value(c, 'playbackLabel', ref ? '动作示意 · 原素材时钟不变' : '真实素材 · 原速记录')}</div>}</div>;})}
      </div>
    </div>}
    {competition > 0 && <div style={{opacity: competition * (1 - result)}}>
      <div style={{...box(artifactBox), transform: `translateY(${mix(60, 0, competition)}px) scale(${mix(.94, 1, competition)})`, border: `2px solid ${c.t.accent}`, boxShadow: `0 0 48px ${c.t.accent}33`, borderRadius: 10, overflow: 'hidden'}}><Art c={c} main kind={1}/></div>
      <Tag c={c} bg={c.t.accent} color={c.t.onAccent} style={{position: 'absolute', left: p ? 450 : 755, top: p ? 420 : 180}}>{value(c, 'competitionLabel', '三种路径 · 结构示意')}</Tag>
    </div>}
    {result > 0 && <div style={{opacity: result}}>
      <SceneTitle c={c} w={w} style={{top: p ? 230 : 255}}>{value(c, 'pathHeading', '不同路径')}<span style={{color: w.accent}}>{result > .7 ? value(c, 'pathConclusion', '汇聚') : ''}</span></SceneTitle>
      <div style={rect(p ? 88 : 140, p ? 650 : 490, p ? 1264 : 1640, p ? 520 : 330)}>{pathLabels.map((label, i) => {const grow = phase(c.seconds, at(c, 'lane_result', 68.3) + i * .12, .85); return <div key={i} style={{...rect(0, i * (p ? 146 : 94), p ? 1264 : 1640, p ? 106 : 74), background: '#FFFFFF04', borderBottom: `1px solid ${w.line}`}}><div style={{position: 'absolute', inset: 0, right: 'auto', width: `${mix(0, [100, 56, 30][i], grow)}%`, borderRadius: 8, background: i === 0 ? c.t.accent : '#FFFFFF20'}}/><div style={{position: 'absolute', left: 24, top: p ? 29 : 20, ...body(p ? 36 : 27, i === 0 ? c.t.onAccent : w.ink)}}>{label}</div>{ref && <span style={{position: 'absolute', right: 18, top: p ? 32 : 22, ...body(p ? 23 : 20, w.muted)}}>P{i + 1}</span>}</div>;})}</div>
      <Eyebrow c={c} w={w} style={{position: 'absolute', left: p ? 88 : 140, top: p ? 1235 : 815}}>{value(c, 'pathNote', ref ? '示意路径 · 不表示真实效率或性能' : '不同的现场视角，连接同一次真实体验')}</Eyebrow>
    </div>}
  </Ground>;
};

/** s06: timelineHeading/Start/End, processLabels[3], timelineConclusion,
 * accountName/Context/Description, accountLabels/Values[4]. Demo numbers appear
 * only in reference; social variants default to unquantified activity facts. */
const S06: React.FC<{c: Context}> = ({c}) => {
  const w = world(c, 'accent'), p = c.portrait, ref = c.p.variant === 'reference';
  const timeline = go(c, 'timeline', 70.2, .7), fast = go(c, 'fast_lane', 73.4, .75), account = go(c, 'account', 75.85, .65), commit = go(c, 'account_commit', 77.05, .8);
  const processLabels = list(c, 'processLabels', ref ? ['初稿', '调整', '确认'] : ['走近', '观察', '体验']);
  const values = list(c, 'accountValues', ref ? ['第4天', '8小时', '120', '单位240'] : ['门店实拍', '社区互动', '到店看看', '完整记录']);
  const labels = list(c, 'accountLabels', ref ? ['示意起点', '示意时长', '示意数量', '示意单位'] : ['画面来源', '现场内容', '到店邀请', '记录方式']);
  const accountBox: Box = p ? [125, 735, 1190, 570] : [335, 340, 1250, 440];
  return <Ground c={c} w={w}>
    <div style={{opacity: 1 - account * .86, filter: `blur(${account * 2}px)`}}>
      <SceneTitle c={c} w={w} style={{fontSize: p ? 83 : 88}}>{value(c, 'timelineHeading', ref ? '制作过程逐步迭代' : '从走近，到一次体验')}</SceneTitle>
      <div style={{...rect(p ? 88 : 140, p ? 530 : 325, p ? 1264 : 1640, 80), opacity: timeline, transform: `scaleX(${timeline})`, transformOrigin: 'left'}}><div style={{position: 'absolute', top: 17, width: '100%', height: 2, background: '#FFFFFF6B'}}/>{Array.from({length: 23}, (_, i) => {const x = (1 - Math.pow(1 - i / 22, 2.15)) * 100; return <i key={i} style={{position: 'absolute', left: `${x}%`, top: i % 4 ? 4 : -4, width: 2, height: i % 4 ? 27 : 44, background: '#FFFFFFC0'}}/>;})}<span style={{position: 'absolute', top: 48, left: 0, ...body(p ? 20 : 17, w.muted)}}>{value(c, 'timelineStart', ref ? 'DRAFT' : '走近现场')}</span><span style={{position: 'absolute', top: 48, right: 0, ...body(p ? 20 : 17, w.muted)}}>{value(c, 'timelineEnd', ref ? 'FINAL' : '亲身感受')}</span></div>
      <div style={{...rect(p ? 88 : 140, p ? 665 : 430, p ? 1264 : 1640, p ? 365 : 330), borderRadius: 18, background: '#07163B3A', overflow: 'hidden', opacity: timeline}}>
        <svg viewBox="0 0 1640 330" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>{Array.from({length: 35}, (_, i) => {const t = phase(c.seconds, at(c, 'fast_lane', 73.4) + i * .012, .9); const x = mix((i * 137) % 1640, ((i * 137) % 1640) + 180, t); return <line key={i} x1={x} x2={x + 50 + i % 5 * 32} y1={20 + i * 9} y2={20 + i * 9} stroke="#FFFFFF" strokeOpacity={.05 + fast * .08} strokeWidth="1"/>;})}</svg>
        {processLabels.map((label, i) => {const v = phase(c.seconds, at(c, 'competitors', 71) + i * .45, .6); return <Tag key={i} c={c} bg={i === 0 ? '#FFFFFF' : '#FFFFFF2A'} color={i === 0 ? '#2551A8' : '#FFFFFF'} style={{position: 'absolute', left: `${mix(6 + i * 6, 58 - i * 13, v)}%`, top: 35 + i * (p ? 91 : 80), opacity: v}}>▸ {label}</Tag>;})}
      </div>
      <div style={{...rect(p ? 88 : 140, p ? 1110 : 812, p ? 1264 : 1640, 160), ...text(p ? 70 : 82, '#FFFFFF'), opacity: fast, transform: `translateY(${mix(30, 0, fast)}px)`}}>{value(c, 'timelineConclusion', ref ? '沿时间线推进逐步清楚' : '让好奇心，在现场找到回应')}</div>
    </div>
    <div style={{...box(accountBox), background: '#FFFFFF', borderRadius: p ? 32 : 36, color: '#060A0D', opacity: account, boxShadow: '0 32px 70px #10204442', transform: `translateY(${mix(140, 0, account)}px) scale(${mix(.9, 1, account)})`}}>
      <div style={{position: 'absolute', left: p ? 40 : 45, top: p ? 46 : 40}}><Avatar c={c} size={p ? 160 : 200} color={c.t.accent}/></div>
      <div style={rect(p ? 235 : 265, p ? 50 : 48, p ? 800 : 775, 210)}><div style={body(p ? 25 : 23, '#7C817D')}>{value(c, 'accountContext', ref ? '演示数据 · 不代表真实产能' : '活动信息 · 真实素材记录')}</div><div style={{...text(p ? 68 : 88, '#070909'), marginTop: 15}}>{value(c, 'accountName', ref ? 'MotionGit' : c.p.brand)}</div><div style={{...body(p ? 27 : 31, '#202521'), marginTop: 14}}>{value(c, 'accountDescription', ref ? '示意卡片 · 非真实账户' : '陈家林路63号 · 未来汇一楼')}</div></div>
      <div style={{position: 'absolute', right: p ? 42 : 50, top: p ? 250 : 90, width: p ? 115 : 137, height: p ? 62 : 78, borderRadius: 50, background: commit > .5 ? c.t.accent : '#E4E5E1'}}><div style={{position: 'absolute', top: 7, left: mix(8, p ? 60 : 68, commit), width: p ? 48 : 64, height: p ? 48 : 64, background: '#FFFFFF', borderRadius: '50%', boxShadow: '0 3px 10px #0002'}}/></div>
      <div style={{position: 'absolute', left: 42, right: 42, bottom: 35, display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12}}>{values.map((v, i) => {const n = phase(c.seconds, at(c, 'account_commit', 77.05) + i * .06, .6); return <div key={i} style={{padding: p ? '15px 10px' : '15px 18px', background: '#F4F5F1', minHeight: p ? 115 : 90, borderRadius: 6, opacity: n, transform: `translateY(${mix(20, 0, n)}px)`}}><div style={body(p ? 19 : 18, '#858A86')}>{labels[i]}</div><div style={{...text(p ? 30 : 35, i === 2 ? c.t.accent : '#0C1412'), marginTop: 10}}>{ref && i === 2 && c.s.content.accountValues === undefined ? Math.round(120 * n) : v}</div></div>;})}</div>
    </div>
  </Ground>;
};

/** s07: beforeHeading, preparationSteps[3], preparationNote, blockLabel,
 * ringContext/Title/Conclusion, outputHeading, outputLabels[2], outputNotes[2].
 * The process bar really compresses into its time/experience block before the
 * circular presentation; neither social palette promises an invented duration. */
const S07: React.FC<{c: Context}> = ({c}) => {
  const w = world(c, 'paper'), p = c.portrait, ref = c.p.variant === 'reference';
  const enter = go(c, 'before', 78.1, .65), process = go(c, 'process', 80.3, .5), compress = go(c, 'time_shift', 82.15, .65), work = go(c, 'work_video', 83.3, .65), output = go(c, 'output', 85.1, .7), code = go(c, 'code_video', 87.4, .7);
  const steps = list(c, 'preparationSteps', ref ? ['文稿', '素材', '编排'] : ['走进门店', '看看新鲜', '尝试互动']);
  const labels = list(c, 'outputLabels', ref ? ['过程视图', '成果视图'] : ['亲眼看看', '亲手体验']);
  const notes = list(c, 'outputNotes', ref ? ['准备与连接', '内容与表达'] : ['近距离接触新的事物', '留下一次真实的尝试']);
  const barBox: Box = p ? [110, 650, 1220, 170] : [140, 330, 1640, 130];
  const phone: Box = p ? [110, 535, 455, 790] : [440, 178, 386, 683];
  const ring: Box = p ? [730, 755, 535, 535] : [1230, 318, 500, 500];
  const ringProgress = phase(c.seconds, at(c, 'work_video', 83.3) + .1, 1.55);
  const outputAsset: Box = p ? [88, 650, 1264, 711] : [960, 330, 900, 510];
  return <Ground c={c} w={{...w, bg: ref ? '#1453E6' : c.t.bg}} grid={false}>
    <AbsoluteFill style={{background: w.bg, transform: `translateX(${mix(c.p.width, 0, enter)}px)`, borderRadius: `${mix(38, 0, enter)}% 0 0 ${mix(38, 0, enter)}%`, overflow: 'hidden'}}>
      <AbsoluteFill style={{backgroundImage: `linear-gradient(${w.line} 1px,transparent 1px),linear-gradient(90deg,${w.line} 1px,transparent 1px)`, backgroundSize: '240px 240px'}}/>
      <SceneTitle c={c} w={w} style={{opacity: 1 - work, fontSize: p ? 83 : 88}}>{value(c, 'beforeHeading', ref ? '制作之前准备内容' : '让一次尝试，循序发生')}</SceneTitle>
      <div data-phase="preparation-to-block" style={{...box(barBox), width: mix(barBox[2], p ? 245 : 195, compress), transform: `translateY(${mix(0, 100, compress)}px)`, background: compress > .6 ? c.t.accent : '#060606', color: '#FFFFFF', borderRadius: 15, opacity: process * (1 - work), overflow: 'hidden', display: 'flex'}}>
        {steps.map((label, i) => {const n = phase(c.seconds, at(c, 'process', 80.3) + i * .29, .42); return <div key={i} style={{position: 'absolute', left: `${i * 100 / 3}%`, width: `${100 / 3}%`, top: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRight: '1px solid #FFFFFF19', ...text(p ? 40 : 40, '#FFFFFF'), opacity: n * (1 - compress), transform: `translateX(${mix(-22, 0, n)}px)`}}>{label}</div>;})}
        <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', ...text(p ? 42 : 42, c.t.onAccent), opacity: compress}}>{value(c, 'blockLabel', ref ? 'TIME' : '体验')}</div>
      </div>
      <div style={{...rect(p ? 780 : 1340, p ? 855 : 495, p ? 480 : 440, 80), ...text(p ? 76 : 105, c.t.accent), opacity: compress * (1 - work), transform: `translateY(${mix(30, 0, compress)}px)`}}>{value(c, 'compressionTitle', ref ? '审阅阶段' : '在现场试试')}</div>
      <Eyebrow c={c} w={w} style={{position: 'absolute', left: barBox[0], top: barBox[1] + barBox[3] + 30, opacity: process * (1 - compress)}}>{value(c, 'preparationNote', ref ? '准备阶段 · 流程示意' : '按自己的节奏，靠近和感受')}</Eyebrow>
      {work > 0 && <div style={{opacity: work}}>
        <div style={{...box(phone), opacity: 1 - output, transform: `translateX(${mix(-80, 0, work)}px)`, borderRadius: 26, background: '#071217', overflow: 'hidden', boxShadow: '0 30px 55px #0003'}}><Art c={c} main kind={0} phone/><div style={{position: 'absolute', top: 20, left: 22, ...body(p ? 20 : 18, '#FFFFFF'), background: '#0008', padding: '7px 12px', borderRadius: 20}}>{value(c, 'processMediaLabel', ref ? '自制界面 · 制作过程示意' : '现场实拍 · 真实互动')}</div></div>
        <div style={{...box(ring), opacity: 1 - code, transform: `scale(${mix(.8, 1, work)})`}}>
          <svg viewBox="0 0 500 500" style={{position: 'absolute', inset: 0, width: '100%', height: '100%', transform: 'rotate(-90deg)'}}><circle cx="250" cy="250" r="220" fill="none" stroke="#E2E3DE" strokeWidth="56"/><circle cx="250" cy="250" r="220" fill="none" stroke={w.ink} strokeWidth="56" pathLength="1" strokeDasharray={`${mix(.02, .985, ringProgress)} 1`}/><circle cx="250" cy="250" r="220" fill="none" stroke={c.t.accent} strokeWidth="56" pathLength="1" strokeDasharray={`${mix(0, .042, ringProgress)} 1`}/></svg>
          <div style={{position: 'absolute', inset: '30%', left: '12%', right: '12%', display: 'flex', flexDirection: 'column', justifyContent: 'center', textAlign: 'center'}}><div style={body(p ? 23 : 22, '#8A8F88')}>{value(c, 'ringContext', ref ? '过程示意 · 非耗时承诺' : '体验过程 · 非效果承诺')}</div><div style={{...text(p ? 49 : 50, w.ink), marginTop: 17}}>{value(c, 'ringTitle', ref ? '制作过程' : '亲手体验')}</div><div style={{...text(p ? 37 : 40, c.t.accent), marginTop: 17}}>{value(c, 'ringConclusion', ref ? '形成自己的表达' : '让好奇心有回应')}</div></div>
        </div>
      </div>}
      {output > 0 && <div style={{opacity: output}}>
        <SceneTitle c={c} w={w} style={{fontSize: p ? 78 : 76}}>{value(c, 'outputHeading', ref ? '把过程连接到成果' : '把看见，变成一次尝试')}</SceneTitle>
        <div style={p ? rect(88, 470, 1264, 150) : rect(140, 485, 720, 330)}>{labels.map((label, i) => {const n = i ? code : phase(c.seconds, at(c, 'output', 85.1) + .24, .55); return <div key={i} style={{...rect(p ? i * 646 : 0, p ? 0 : i * 182, p ? 618 : 720, p ? 142 : 146), background: '#FFFFFF', borderRadius: 8, padding: p ? '18px 25px' : '21px 29px', boxSizing: 'border-box', opacity: n, transform: `translateY(${mix(25, 0, n)}px)`}}><div style={body(p ? 19 : 18, '#979C96')}>// 0{i + 1} · {notes[i]}</div><div style={{...text(p ? 38 : 46, w.ink), marginTop: 12}}>{label}</div></div>;})}</div>
        <div style={{...box(outputAsset), opacity: code, transform: `translateX(${mix(90, 0, code)}px)`, boxShadow: '0 28px 50px #0003', borderRadius: 14, overflow: 'hidden'}}><NativeWindow c={c} title={value(c, 'outputMediaLabel', ref ? '自制界面 · 成果示意' : '海客AI · 活动记录')}><Art c={c} index={1} kind={1}/></NativeWindow></div>
      </div>}
    </AbsoluteFill>
  </Ground>;
};

/** s08: reflectionTop/Bottom/Conclusion, comparisonLabels[2], comparisonAction, comparisonNote,
 * frameNote, actionText, brandTitle/Description, invitationHeading/Note, signoff.
 * capacityFactor defaults to a clearly illustrative ×3 in reference only.
 * Social comparisonMediaIndex/closingMediaIndex select live, source-clock
 * bound footage in the comparison strip and a separate closing proof window. */
const S08: React.FC<{c: Context}> = ({c}) => {
  const w = world(c), paper = world(c, 'paper'), p = c.portrait, ref = c.p.variant === 'reference';
  const era = go(c, 'era', 91.85, .55), warning = go(c, 'warning', 93.6, .55), growth = go(c, 'growth', 95.4, 1.0), frames = go(c, 'frame_work', 96.5, .65), action = go(c, 'call_to_action', 98.6, .65), closing = go(c, 'comments', 100.1, .65);
  const labels = list(c, 'comparisonLabels', ref ? ['路径 A', '路径 B'] : ['从看见', '到体验']);
  const activeFrame = Math.floor(clamp((c.seconds - at(c, 'frame_work', 96.5)) / 1.65) * 5);
  const comparisonMediaIndex = Math.max(0, Math.floor(num(c, 'comparisonMediaIndex', 0))), closingMediaIndex = Math.max(0, Math.floor(num(c, 'closingMediaIndex', 1)));
  return <Ground c={c} w={w}>
    <div style={{opacity: era * (1 - warning), ...rect(p ? 88 : 140, p ? 230 : 395, p ? 1264 : 1130, p ? 300 : 390), transform: `translateY(${mix(40, 0, era)}px)`}}><Eyebrow c={c} w={w}>{value(c, 'reflectionContext', ref ? '把重点，留在画面里' : '一次真实到店，留下一点新鲜')}</Eyebrow><div style={{...text(p ? 84 : 112, w.ink), marginTop: 26}}>{value(c, 'reflectionTop', ref ? '你的内容' : '从知道AI')}</div><div style={{...text(p ? 84 : 112, w.ink), marginTop: 10}}>{value(c, 'reflectionBottom', ref ? '新的表达' : '到亲手体验')}<span style={{color: w.accent}}>{value(c, 'reflectionConclusion', ref ? '逐步清楚' : '一次')}</span></div></div>
    {warning > 0 && <div style={{opacity: warning * (1 - action), ...rect(p ? 88 : 140, p ? 565 : 300, p ? 1264 : 1260, p ? 730 : 430)}}>
      <Eyebrow c={c} w={w}>{value(c, 'comparisonNote', ref ? '结构对比 · 示意' : '体验过程示意 · 不表示效果比较')}</Eyebrow>
      {labels.map((label, i) => <div key={i} style={rect(0, (p ? 125 : 100) + i * (p ? 240 : 190), p ? 1264 : 1260, p ? 160 : 130)}><div style={{position: 'absolute', left: 0, top: 22, ...text(p ? 46 : 42, w.ink)}}>{label}{i === 0 && <span style={{...body(p ? 26 : 25, w.accent), marginLeft: 16}}>{value(c, 'comparisonAction', ref ? '加上动画' : '')}</span>}</div>{i === 0 ? <div style={{...rect(p ? 275 : 310, 10, p ? 940 : 850, p ? 85 : 72), background: '#FFFFFF03', borderRadius: 12, overflow: ref ? 'visible' : 'hidden'}}>{!ref && <div style={{position: 'absolute', inset: 0, display: 'flex', gap: 8}}>{[0,1,2,3].map((n)=><div key={n} style={{position: 'relative', flex: 1, overflow: 'hidden', background: '#071217', borderRadius: 6}}><Art c={c} index={comparisonMediaIndex+n} live={n===0}/></div>)}</div>}<div style={{position: 'relative', opacity: ref ? 1 : .2, width: `${mix(6, 100, growth)}%`, height: '100%', borderRadius: 12, background: c.t.accent}}/>{ref && <span style={{position: 'absolute', left: `calc(${mix(6, 100, growth)}% - 45px)`, top: 18, ...text(p ? 44 : 43, '#FFFFFF')}}>×{Math.max(1, Math.round(mix(1, num(c, 'capacityFactor', 3), growth)))}</span>}</div> : <div style={{...rect(p ? 275 : 310, 5, p ? 940 : 850, p ? 150 : 130), overflow: 'hidden'}}><div style={{display: 'flex', gap: 12, transform: `translateX(${-activeFrame * 5}px)`}}>{Array.from({length: 6}, (_, i) => <div key={i} style={{width: p ? 140 : 131, height: p ? 100 : 83, flexShrink: 0, background: '#FFFFFF08', border: `1px solid ${i === activeFrame ? c.t.accent : '#FFFFFF0C'}`, borderRadius: 8, opacity: mix(.45, 1, frames), position: 'relative', overflow: 'hidden'}}>{!ref && <Art c={c} index={i+1} live={i===activeFrame}/>}</div>)}</div><div style={{...body(p ? 22 : 20, w.muted), marginTop: 16}}>frame {String(activeFrame + 1).padStart(4, '0')} · {value(c, 'frameNote', ref ? '让动作帮你讲清楚' : '真实的素材，按内容接力')}</div></div>}</div>)}
    </div>}
    {action > 0 && <div style={{...rect(p ? 175 : 320, p ? 730 : 490, p ? 1090 : 770, p ? 160 : 150), opacity: action * (1 - closing), transform: `translateY(${mix(35, 0, action)}px) scale(${mix(.95, 1, action)})`, borderRadius: 70, background: c.t.accent, boxShadow: `0 16px 60px ${c.t.accent}44`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 24, ...text(p ? 48 : 56, c.t.onAccent)}}><svg viewBox="0 0 30 36" width="25" height="30"><path d="M2 2 L28 18 L2 34 Z" fill="currentColor"/></svg>{value(c, 'actionText', ref ? '把想法变成清楚表达' : '来现场，亲手体验一次')}</div>}
    {closing > 0 && <AbsoluteFill style={{background: paper.bg, opacity: closing, transform: `translateX(${mix(-c.p.width, 0, closing)}px)`}}>
      <div style={{...rect(p ? 125 : 145, p ? ref ? 585 : 510 : 385, p ? 1160 : 1210, 240), display: 'flex', alignItems: 'center', gap: p ? 30 : 35}}><Avatar c={c} size={p ? 160 : 220} color={c.t.accent}/><div><div style={text(p ? 67 : 116, paper.ink)}>{value(c, 'brandTitle', ref ? 'MotionGit' : c.p.brand)}</div><div style={{...body(p ? 29 : 29, paper.muted), marginTop: 18}}>{value(c, 'brandDescription', ref ? '模板提供风格与动画' : '陈家林路63号 · 未来汇一楼')}</div></div></div>
      <div style={{...rect(p ? 140 : 145, p ? ref ? 925 : 810 : 690, p ? 1080 : 920, p ? 170 : 120), background: '#FFFFFF', borderRadius: 10, boxShadow: '0 15px 30px #0000000B', display: 'flex', alignItems: 'center', gap: 24, padding: '20px 30px', boxSizing: 'border-box'}}><div style={{width: 52, height: 52, borderRadius: '50%', background: '#101414', color: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 35}}>+</div><div><div style={text(p ? 34 : 34, paper.ink)}>{value(c, 'invitationHeading', ref ? '带上自己的口播与素材' : '有空，来坐坐')}</div><div style={{...body(p ? 22 : 20, paper.muted), marginTop: 10}}>{value(c, 'invitationNote', ref ? '内容始终以你为主' : '看看机器人，也和街坊聊聊天')}</div></div></div>
      <div style={{...rect(p ? 140 : 145, p ? ref ? 1195 : 1025 : 855, p ? 1100 : 900, 100), ...text(p ? 69 : 74, paper.ink), opacity: phase(c.seconds, at(c, 'comments', 100.1) + .85, .4)}}>{value(c, 'signoff', ref ? '再见' : '期待在现场见到你')}</div>
      {!ref && <div style={{...rect(p ? 88 : 1140, p ? 1150 : 695, p ? 1264 : 640, p ? 220 : 250), borderRadius: 12, overflow: 'hidden', background: paper.panel, border: `1px solid ${paper.line}`, display: 'flex'}}><div style={{position: 'relative', width: '62%', height: '100%', background: '#0B1517'}}><Art c={c} index={closingMediaIndex}/></div><div style={{flex: 1, padding: p ? '36px 28px' : '36px 20px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 16}}><div style={text(p ? 36 : 27, paper.ink)}>{value(c, 'closingMediaTitle', '门店活动实拍')}</div><div style={body(p ? 27 : 20, paper.muted)}>{value(c, 'closingMediaNote', '欢迎来坐坐')}</div></div></div>}
    </AbsoluteFill>}
  </Ground>;
};

/** Project-authored4:5 arrangement of the S08 grammar, on the input's actual
 * cue clock. The native landscape reference remains a separate engine. */
const S08Story:React.FC<{c:Context}>=({c})=>{
 const era=go(c,'era',91.85,.55),warning=go(c,'warning',93.6,.55),growth=go(c,'growth',95.4,1),frames=go(c,'frame_work',96.5,.65),action=go(c,'call_to_action',98.6,.65),closing=go(c,'comments',100.1,.65),ink='#111719',labels=list(c,'comparisonLabels',['看看','亲手体验']),activeFrame=Math.min(5,Math.floor(clamp((c.seconds-at(c,'frame_work',96.5))/1.65)*5)),factor=Math.max(1,num(c,'capacityFactor',3));
 const column=mix(1264,740,storyPresenterLarge(c));
 return <StoryGround c={c}>
  <div style={{...rect(88,255,760,160),opacity:1-warning,...body(30,c.t.muted)}}>{value(c,'reflectionContext','把好奇心带到现场')}</div>
  <div style={{...rect(88,425,column,640),opacity:era*(1-warning),transform:`translateY(${mix(40,0,era)}px)`}}><div style={text(105,c.t.ink)}>{value(c,'reflectionTop','从知道AI')}</div><div style={{...text(105,c.t.ink),marginTop:42}}>{value(c,'reflectionBottom','到亲手体验')}</div><div style={{...text(122,c.t.accent2),marginTop:56}}>{value(c,'reflectionConclusion','一起来试试')}</div></div>
  <div style={{...rect(88,375,1264,955),opacity:warning*(1-action)}}><div style={body(35,c.t.muted)}>{value(c,'comparisonNote','体验步骤 · 三个动作')}</div><div style={{...rect(0,125,1264,330)}}><div style={text(48,c.t.ink)}>{labels[0]}<span style={{...body(30,c.t.accent2),marginLeft:25}}>{value(c,'comparisonAction','摸摸 · 用用')}</span></div><div style={{...rect(0,104,1264,142),background:'#FFFFFF06',border:'1px solid #FFFFFF14',borderRadius:16}}><div style={{width:`${mix(8,100,growth)}%`,height:'100%',borderRadius:16,background:c.t.accent,boxShadow:`0 14px 45px ${c.t.accent}44`}}/><span style={{position:'absolute',right:32,top:34,...text(66,'#FFF')}}>×{Math.round(mix(1,factor,growth))}</span></div></div><div style={{...rect(0,510,1264,350)}}><div style={text(48,c.t.ink)}>{labels[1]}</div><div style={{...rect(0,105,1264,180),display:'flex',gap:16,overflow:'hidden'}}>{Array.from({length:6},(_,i)=><div key={i} style={{width:196,height:154,flexShrink:0,position:'relative',overflow:'hidden',borderRadius:10,border:`2px solid ${i===activeFrame?c.t.accent2:'#FFFFFF20'}`,opacity:mix(.5,1,frames),transform:`translateX(${-activeFrame*5}px)`}}><Art c={c} index={i} live={false}/><div style={{position:'absolute',left:8,bottom:8,padding:'3px 8px',background:'#060B14AA',borderRadius:4,...body(19,'#FFF')}}>{String(i+1).padStart(2,'0')}</div></div>)}</div><div style={{...rect(0,290,1264,60),...body(29,c.t.muted)}}>{value(c,'frameNote','真实素材 · 体验步骤')}</div></div></div>
  <div style={{...rect(88,900,column,190),opacity:action*(1-closing),transform:`translateY(${mix(35,0,action)}px) scale(${mix(.95,1,action)})`,borderRadius:95,background:c.t.accent,boxShadow:`0 20px 70px ${c.t.accent}55`,display:'flex',alignItems:'center',justifyContent:'center',gap:24,...text(54,'#FFF')}}><svg viewBox="0 0 30 36" width="30" height="36"><path d="M2 2 L28 18 L2 34 Z" fill="currentColor"/></svg>{value(c,'actionText','这个周末，带孩子来体验')}</div>
  <AbsoluteFill style={{background:c.t.paper,opacity:closing,transform:`translateX(${mix(-c.p.width,0,closing)}px)`}}><div style={{...rect(88,285,780,150),display:'flex',gap:24,alignItems:'center'}}><Avatar c={c} size={136}/><div style={{...text(69,ink),width:610}}>{value(c,'brandTitle',c.p.brand)}</div></div><div style={{...rect(88,485,750,180),...body(37,'#69727A'),lineHeight:1.5}}>{value(c,'brandDescription','陈家林路63号 · 未来汇一楼')}</div><div style={{...rect(88,785,746,195),display:'flex',alignItems:'center',gap:22,padding:26,boxSizing:'border-box',borderRadius:20,boxShadow:'0 18px 45px #0000000C',background:'#FFF'}}><span style={{width:64,height:64,background:ink,color:'#FFF',borderRadius:'50%',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0,fontSize:37}}>✦</span><div><div style={text(40,ink)}>{value(c,'invitationHeading','这个周末，来坐坐')}</div><div style={{...body(27,'#69727A'),marginTop:16}}>{value(c,'invitationNote','近距离看看 · 亲手试试')}</div></div></div><div style={{...rect(88,1190,1264,140),...text(93,ink),opacity:phase(c.seconds,at(c,'comments',100.1)+.85,.4)}}>{value(c,'signoff','期待见到你')}<span style={{marginLeft:25,fontSize:80}}>👋</span></div></AbsoluteFill>
 </StoryGround>;
};

/** s09: productionPrefix/Mark/Suffix, toolName, productionNote, promptHeading,
 * promptText, typingSeconds, signatureName/Note. Prompt typing is a fixed local
 * duration, not a duration-scaled motion or a change to the narration clock. */
const S09: React.FC<{c: Context}> = ({c}) => {
  const p = c.portrait, ref = c.p.variant === 'reference', base = world(c), w: World = {...base, bg: ref ? '#191919' : base.bg};
  const production = go(c, 'production', 102.92, .55), tool = go(c, 'tool', 103.45, .4), prompt = go(c, 'prompt', 104.35, .4), signature = go(c, 'signature', 107, .5);
  const words = value(c, 'promptText', ref ? '使用模板03的原生动画，根据我的文稿和素材选择合适的完整场景。保留镜头衔接，检查字幕与声音，再导出横屏和竖屏视频。' : '保留这一次真实活动中的人物、动作和回应。用完整的原始口播连接现场画面，让观众看清体验过程，并留下清楚的到店信息。');
  const typingDuration = Math.max(.5, num(c, 'typingSeconds', 2.45)), typed = Math.floor(Array.from(words).length * clamp((c.seconds - at(c, 'prompt', 104.35)) / typingDuration));
  const promptBox: Box = p ? [88, 650, 1264, 560] : [136, 400, 1648, 310];
  return <Ground c={c} w={w}>
    <SceneTitle c={c} w={w} style={{opacity: production, fontSize: p ? 85 : 102, transform: `translateY(${mix(25, 0, production)}px)`}}>{value(c, 'productionPrefix', '制作方式')}<span style={{color: w.accent}}>{p ? '\n' : ' '}{value(c, 'productionMark', '原生编舞')}</span>{value(c, 'productionSuffix', '结合')}</SceneTitle>
    <div style={{...rect(p ? 88 : 140, p ? 465 : 297, p ? 1264 : 1600, p ? 138 : 76), display: 'flex', alignItems: 'flex-start', flexWrap: 'wrap', gap: 17, opacity: tool}}><Tag c={c} bg={c.t.accent} color={c.t.onAccent}>{value(c, 'toolName', ref ? 'adu-motion-video' : '海客AI · 现场记录')}</Tag><Tag c={c} bg="#FFFFFF08" color={w.ink} style={{border: `1px solid ${w.line}`}}>{value(c, 'productionNote', ref ? '完整动作 · 文案与素材可替换' : '完整口播 · 真实素材')}</Tag></div>
    <div style={{...box(promptBox), opacity: prompt, transform: `translateY(${mix(25, 0, prompt)}px)`, border: `1px solid ${w.line}`, borderRadius: 28, background: ref ? '#060606' : w.panel, boxShadow: '0 22px 50px #0002', overflow: 'hidden'}}>
      <div style={{position: 'absolute', left: p ? 30 : 40, right: 30, top: p ? 28 : 35, display: 'flex', alignItems: 'center', gap: 10}}>{['#EF5B57', '#EFBC3F', '#3CB74F'].map(color => <i key={color} style={{display: 'block', background: color, width: 11, height: 11, borderRadius: '50%'}}/>)}<span style={{...body(p ? 23 : 21, w.muted), marginLeft: 17}}>{value(c, 'promptHeading', '示例提示词 · 按需调整')}</span></div>
      <div style={{position: 'absolute', left: p ? 35 : 42, top: p ? 110 : 92, color: w.accent, fontSize: p ? 55 : 50}}>›</div><div style={{position: 'absolute', left: p ? 85 : 82, right: p ? 45 : 55, top: p ? 110 : 92, ...body(p ? 48 : 43, w.ink), lineHeight: p ? 1.6 : 1.45}}>{Array.from(words).slice(0, typed).join('')}<span style={{color: w.accent, marginLeft: 8, opacity: signature > .8 || Math.floor(c.seconds * 2) % 2 === 0 ? 1 : .15}}>|</span></div>
    </div>
    <div style={{...rect(p ? 90 : 140, p ? 1290 : 845, p ? 1200 : 1300, p ? 88 : 70), display: 'flex', alignItems: 'center', gap: 18, opacity: signature, transform: `translateY(${mix(20, 0, signature)}px)`}}><Avatar c={c} size={p ? 66 : 55}/><div style={text(p ? 35 : 30, w.ink)}>{value(c, 'signatureName', ref ? 'MotionGit' : c.p.brand)}</div><span style={body(p ? 23 : 20, w.muted)}>{value(c, 'signatureNote', ref ? '提供口播、字幕和本期素材' : '本次口播与现场素材')}</span></div>
  </Ground>;
};

/** Independent review source window is 110–124, i.e. +1.6s from the observed
 * full-preview chapter at108.4s. Content: artifactTitle, reviewHeading,
 * reviewChecks[3], reviewConclusion. Criteria are not fabricated pass marks. */
const Review: React.FC<{c: Context}> = ({c}) => {
  const w = world(c), p = c.portrait, ref = c.p.variant === 'reference';
  const enter = go(c, 'entry', 110, .85), reviewing = go(c, 'review', 114, .75), conclusion = go(c, 'conclusion', 118.6, .65);
  const checkLabels = list(c, 'reviewChecks', ['镜头衔接', '内容层次', '素材与文稿一致']);
  const entryBox: Box = p ? [155, 535, 1130, 636] : [140, 235, 1500, 700];
  const settledBox: Box = p ? [88, 465, 1264, 711] : [80, 250, 1240, 700];
  const b = between(entryBox, settledBox, reviewing), scanAge = c.seconds - at(c, 'review', 114) - .2, scan = clamp(scanAge / 3.3);
  return <Ground c={c} w={w}>
    <SceneTitle c={c} w={w} style={{left: p ? 88 : 80, top: p ? 225 : 140, width: p ? 1264 : 1300, fontSize: p ? 78 : conclusion > .1 ? 72 : 96, color: conclusion > .1 ? w.accent : w.ink, opacity: enter}}>{conclusion > .1 ? value(c, 'reviewConclusion', '根据实际检查形成结论') : value(c, 'artifactTitle', ref ? '本期成果' : '本次真实记录')}</SceneTitle>
    <div style={{...box(b), opacity: enter, transform: `translateY(${mix(70, 0, enter)}px) scale(${mix(.93, 1, enter)})`, transformOrigin: '50% 50%'}}>
      {[2, 1].map(i => <div key={i} style={{position: 'absolute', inset: 0, borderRadius: 22, background: ref ? '#12213C' : c.t.panel, border: `1px solid ${w.accent}44`, transform: `translate(${i * 12}px,${i * 15}px) scale(${1 - i * .015})`, opacity: .3 * (1 - reviewing)}}/>)}
      <div style={{position: 'absolute', inset: 0, border: `2px solid ${w.accent}66`, borderRadius: 22, overflow: 'hidden', background: c.t.panel, boxShadow: ref ? '0 20px 75px #1453E625' : '0 22px 50px #0002'}}><Art c={c} main kind={2}/>{scanAge >= 0 && scanAge <= 3.6 && <div style={{position: 'absolute', top: 0, bottom: 0, left: `${scan * 100}%`, width: 2, background: w.accent, boxShadow: `0 0 18px ${w.accent}`, opacity: 1 - phase(scanAge, 3.3, .3)}}/>}</div>
    </div>
    <div style={p ? rect(88, 1215, 1264, 165) : rect(1380, 400, 440, 400)}><div style={{...body(p ? 23 : 28, w.muted), opacity: reviewing, marginBottom: p ? 15 : 30}}>{value(c, 'reviewHeading', '实际检查')}</div><div style={{display: 'flex', flexDirection: p ? 'row' : 'column', gap: p ? 16 : 24}}>{checkLabels.map((label, i) => {const n = phase(c.seconds, at(c, 'review', 114) + .18 + i * .65, .55); return <div key={i} style={{position: 'relative', flex: p ? 1 : undefined, minWidth: 0, background: ref ? '#080E13' : c.p.variant === 'cobalt' ? '#172F4D' : c.t.panel, border: `1px solid ${ref ? '#29313B' : w.line}`, borderRadius: 14, padding: p ? '20px 20px' : '22px 24px', minHeight: p ? 88 : 86, boxSizing: 'border-box', opacity: n, transform: `translateY(${mix(25, 0, n)}px)`}}><span style={{...body(p ? 17 : 18, w.muted), marginRight: 12}}>{String(i + 1).padStart(2, '0')}</span><span style={text(p ? 36 : 34, w.ink)}>{label}</span></div>;})}</div></div>
  </Ground>;
};

export const GroupsB: React.FC<{c: Context}> = ({c}) => {
  if(c.p.variant==='native-story')return c.s.group==='s08'?<S08Story c={c}/>:null;
  switch (c.s.group) {
    case 's05': return <S05 c={c}/>;
    case 's06': return <S06 c={c}/>;
    case 's07': return <S07 c={c}/>;
    case 's08': return <S08 c={c}/>;
    case 's09': return <S09 c={c}/>;
    case 'review': return <Review c={c}/>;
    default: return null;
  }
};
