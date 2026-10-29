/**
 * SVG 动画视频生成方式 — 最小可用验证 (2026-09-20)
 *
 * 目的：验证「纯 SVG 图形动画 → MP4」能否作为本项目的一条独立画面来源。
 * 特征：零外部素材、零付费、零网络；画面全部由 SVG 图元（rect/circle/path/text）构成，
 *       时间轴由 Remotion 帧时钟驱动，因此与配音时钟天然对齐、可逐帧复现。
 *
 * 独立入口：不注册进 src/Root.tsx，渲染时用 --entry-point 指定本文件即可，
 *           对现有生产组合零影响。
 */
import React from 'react';
import {
  AbsoluteFill,
  Composition,
  Easing,
  Sequence,
  interpolate,
  registerRoot,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

// ---------------------------------------------------------------- 设计令牌（最简陋版：一个文件写完）
const BG = '#0B1220';
const INK = '#F2F6FF';
const MUTED = '#8FA3BF';
const ACCENT = '#4DA3FF';
const WARM = '#FFC24D';
const FONT = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif';

const W = 1080;
const H = 1920;

// ---------------------------------------------------------------- 通用小工具
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

const fadeUp = (frame: number, start: number, dur = 16, dist = 26) => {
  const p = interpolate(frame, [start, start + dur], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  return { opacity: p, dy: (1 - p) * dist };
};

// 底：纯色背景 + 一条贯穿全片的时间进度条（一个 rect，够简陋）
const Stage: React.FC<{children: React.ReactNode}> = ({children}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const p = interpolate(frame, [0, durationInFrames], [0, 1], clamp);
  return (
    <AbsoluteFill style={{backgroundColor: BG}}>
      {children}
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${W} ${H}`}
        style={{position: 'absolute', inset: 0}}
      >
        <rect x={0} y={H - 8} width={W * p} height={8} fill={ACCENT} />
      </svg>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 幕 1：环形描边 + 主题
const SceneTitle: React.FC = () => {
  const frame = useCurrentFrame();
  const R = 132;
  const C = 2 * Math.PI * R;
  const draw = interpolate(frame, [0, 34], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const t = fadeUp(frame, 24, 20);
  const s = fadeUp(frame, 46, 18);

  return (
    <AbsoluteFill>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        <g transform={`translate(540 700) rotate(-90)`}>
          <circle r={R} fill="none" stroke="#1B2A44" strokeWidth={16} />
          <circle
            r={R}
            fill="none"
            stroke={ACCENT}
            strokeWidth={16}
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - draw)}
          />
        </g>
        {/* 环心的一个点，示意「焦点」 */}
        <circle cx={540} cy={700} r={interpolate(frame, [18, 40], [0, 14], clamp)} fill={WARM} />

        <text
          x={540}
          y={995 + t.dy}
          textAnchor="middle"
          fill={INK}
          fontFamily={FONT}
          fontSize={92}
          fontWeight={700}
          opacity={t.opacity}
        >
          如何提升专注力
        </text>
        <text
          x={540}
          y={1090 + s.dy}
          textAnchor="middle"
          fill={MUTED}
          fontFamily={FONT}
          fontSize={40}
          opacity={s.opacity}
        >
          不靠意志力，靠环境
        </text>
      </svg>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 幕 2：三条动作，逐条滑入
const BULLETS = [
  {n: '1', main: '通知全部关掉', sub: '手机反扣，放到抽屉里'},
  {n: '2', main: '一次只做一件', sub: '别边写边回消息'},
  {n: '3', main: '25 分钟一轮', sub: '到点就起来走两分钟'},
];

const SceneActions: React.FC = () => {
  const frame = useCurrentFrame();
  const head = fadeUp(frame, 0, 16);

  return (
    <AbsoluteFill>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        <text
          x={120}
          y={620 + head.dy}
          fill={ACCENT}
          fontFamily={FONT}
          fontSize={44}
          fontWeight={700}
          opacity={head.opacity}
        >
          三个立刻能用的动作
        </text>
        <rect x={120} y={660} width={interpolate(frame, [8, 40], [0, 840], clamp)} height={4} fill="#1B2A44" />

        {BULLETS.map((b, i) => {
          const start = 18 + i * 16;
          const p = interpolate(frame, [start, start + 18], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
          const y = 850 + i * 210;
          return (
            <g key={b.n} opacity={p} transform={`translate(${(1 - p) * -40} 0)`}>
              <circle cx={196} cy={y} r={46} fill="none" stroke={ACCENT} strokeWidth={4} />
              <text
                x={196}
                y={y + 17}
                textAnchor="middle"
                fill={ACCENT}
                fontFamily={FONT}
                fontSize={46}
                fontWeight={700}
              >
                {b.n}
              </text>
              <text x={286} y={y - 4} fill={INK} fontFamily={FONT} fontSize={54} fontWeight={700}>
                {b.main}
              </text>
              <text x={286} y={y + 52} fill={MUTED} fontFamily={FONT} fontSize={36}>
                {b.sub}
              </text>
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 幕 3：散点收敛成一列
const DOTS = [
  {x: 150, y: 560}, {x: 900, y: 640}, {x: 300, y: 780},
  {x: 760, y: 880}, {x: 200, y: 1010}, {x: 880, y: 1120},
  {x: 420, y: 1240}, {x: 700, y: 1320}, {x: 140, y: 1420},
  {x: 940, y: 1450}, {x: 520, y: 1520}, {x: 800, y: 1600},
];

const SceneFocus: React.FC = () => {
  const frame = useCurrentFrame();
  const label = fadeUp(frame, 0, 16);
  const cap = fadeUp(frame, 62, 18);

  return (
    <AbsoluteFill>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        <text
          x={120}
          y={470 + label.dy}
          fill={MUTED}
          fontFamily={FONT}
          fontSize={40}
          opacity={label.opacity}
        >
          专心，就是把同时存在的事减到一件
        </text>

        {/* 目标列：一条竖线 + 12 个落位刻度 */}
        <rect x={540} y={640} width={3} height={interpolate(frame, [14, 50], [0, 780], clamp)} fill="#1B2A44" />
        {DOTS.map((d, i) => {
          const ty = 640 + i * (780 / (DOTS.length - 1));
          const start = 20 + i * 2;
          const p = interpolate(frame, [start, start + 34], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
          const x = d.x + (540 - d.x) * p;
          const y = d.y + (ty - d.y) * p;
          const r = 8 + 10 * p;
          return <circle key={i} cx={x} cy={y} r={r} fill={p > 0.98 ? WARM : ACCENT} opacity={0.35 + 0.65 * p} />;
        })}

        <text
          x={540}
          y={1660 + cap.dy}
          textAnchor="middle"
          fill={INK}
          fontFamily={FONT}
          fontSize={56}
          fontWeight={700}
          opacity={cap.opacity}
        >
          同时只留一件事
        </text>
      </svg>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 幕 4：收口
const SceneClose: React.FC = () => {
  const frame = useCurrentFrame();
  const t = fadeUp(frame, 0, 14);
  const line = interpolate(frame, [8, 26], [0, 620], clamp);
  return (
    <AbsoluteFill>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        <rect x={(W - line) / 2} y={850} width={line} height={6} fill={ACCENT} />
        <text
          x={540}
          y={960 + t.dy}
          textAnchor="middle"
          fill={INK}
          fontFamily={FONT}
          fontSize={76}
          fontWeight={700}
          opacity={t.opacity}
        >
          现在，关掉一个通知
        </text>
      </svg>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 组合
export const SvgFocusTest: React.FC = () => {
  return (
    <Stage>
      <Sequence from={0} durationInFrames={72}>
        <SceneTitle />
      </Sequence>
      <Sequence from={72} durationInFrames={156}>
        <SceneActions />
      </Sequence>
      <Sequence from={228} durationInFrames={108}>
        <SceneFocus />
      </Sequence>
      <Sequence from={336} durationInFrames={54}>
        <SceneClose />
      </Sequence>
    </Stage>
  );
};

const RemotionRoot: React.FC = () => (
  <Composition id="SvgFocusTest" component={SvgFocusTest} durationInFrames={390} fps={30} width={W} height={H} />
);

registerRoot(RemotionRoot);
