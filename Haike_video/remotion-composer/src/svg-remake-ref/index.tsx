/**
 * SVG 复刻对照测试 (2026-09-20)
 *
 * 参照片：抖音 7687039216236472934《头顶一块布，全球我最富》(720x1556 / 51.9s / 24fps)
 * 其画面构成（逐项实测）：
 *   · 上下纯黑板 + 中间白底画面条带（y 0.409~0.661，左右各留 10px）
 *   · 顶部两行白色标题，全片固定不变、紧贴画面条带上沿（字号 40，行距 52）
 *   · 画面内容 = 黑白线描插画（沙色单色块），全片约 30 张，每张约 1.7s
 *   · 每张图唯一的运动 = 整张图缓慢推拉（Ken Burns），无任何元素级动画
 *
 * 本片用同一张 SVG 场景做 A/B 对照：
 *   A 段 0~6s  —— 完全按原片做法：整张图推拉
 *   B 段 6~12s —— SVG 才能做到的：同一张图拆成分层元素各自运动
 * 结论指向：这个「动画效果」本身动画量为零，SVG 复刻没有技术障碍，
 *          真正的工作量在插画本身，不在动画。
 *
 * 独立入口，不注册进 src/Root.tsx，对生产组合零影响。
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

// ---------------------------------------------------------------- 版式常量（按参照片实测值）
const W = 720;
const H = 1556;
const FPS = 24;

const BOARD = '#000000';        // 上下黑板：实测 (0,0,0)
const PAPER = '#FFFFFF';        // 画面区：实测 (255,255,255)
const INK = '#000000';          // 线描：实测 (0,0,0)
const SAND = '#FBC791';         // 沙袋：实测取色 (251,199,145)
const SAND_DK = '#E9A96B';
const ACCENT = '#FF4D2E';       // 本片新加（原片没有）

// 画面条带实测：x 10~708，y 636~1029
const BOX = {x: 10, y: 636, w: 698, h: 393};

const FONT = '"Microsoft YaHei", "PingFang SC", sans-serif';

// ---------------------------------------------------------------- 场景（局部坐标：以条带左上角为原点，698 x 393）
const GY = 206; // 沙丘地平线

// —— 坦克（侧视线描）
const Tank: React.FC<{turret?: number; recoil?: number; muzzle?: number}> = ({
  turret = 0,
  recoil = 0,
  muzzle = 0,
}) => (
  <g transform="translate(150 226) scale(0.9)">
    {/* 炮管 + 制退器（recoil 驱动后座） */}
    <g transform={`translate(${-recoil} 0)`}>
      <rect x={52} y={-8} width={172} height={20} fill={PAPER} stroke={INK} strokeWidth={5} />
      <rect x={200} y={-16} width={30} height={36} fill={PAPER} stroke={INK} strokeWidth={5} />
      {muzzle > 0.02 && (
        <g opacity={muzzle} transform="translate(232 -8)">
          <path
            d="M 0 0 L 40 -32 L 28 -6 L 70 -12 L 30 8 L 46 30 L 10 14 L -6 38 L -8 8 Z"
            fill={ACCENT}
            stroke={INK}
            strokeWidth={4}
            strokeLinejoin="round"
          />
        </g>
      )}
    </g>
    {/* 炮塔（turret 驱动旋转） */}
    <g transform={`rotate(${turret} 18 30)`}>
      <path d="M -46 30 L 52 30 L 40 -24 L -34 -24 Z" fill={PAPER} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
      <circle cx={0} cy={3} r={13} fill={PAPER} stroke={INK} strokeWidth={5} />
      <line x1={-30} y1={-24} x2={-44} y2={-76} stroke={INK} strokeWidth={5} />
    </g>
    {/* 车体 */}
    <path d="M -118 30 L 118 30 L 108 78 L -108 78 Z" fill={PAPER} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    {/* 履带 + 负重轮 */}
    <rect x={-128} y={74} width={256} height={56} rx={28} fill={PAPER} stroke={INK} strokeWidth={5} />
    {[-78, -26, 26, 78].map((cx) => (
      <circle key={cx} cx={cx} cy={102} r={17} fill={PAPER} stroke={INK} strokeWidth={5} />
    ))}
    {/* 前装甲纹路 */}
    <line x1={-96} y1={44} x2={-76} y2={70} stroke={INK} strokeWidth={4} />
    <line x1={-70} y1={44} x2={-50} y2={70} stroke={INK} strokeWidth={4} />
  </g>
);

// —— 沙袋堆（错位堆叠）
const BAGS: {x: number; y: number}[] = [
  {x: 0, y: 0},
  {x: 64, y: 0},
  {x: 128, y: 0},
  {x: 32, y: 30},
  {x: 96, y: 30},
  {x: 0, y: 60},
  {x: 64, y: 60},
];

const Sandbags: React.FC<{drop?: number[]}> = ({drop}) => (
  <g transform="translate(346 252)">
    {BAGS.map((b, i) => {
      const from = drop ? 1 - drop[i] : 0; // A 段 drop 为空 → 恒定归位
      return (
        <g key={i} transform={`translate(0 ${-from * 240})`} opacity={drop ? 1 - from * 0.85 : 1}>
          <rect x={b.x} y={b.y} width={62} height={30} rx={15} fill={i % 2 ? SAND : SAND_DK} stroke={INK} strokeWidth={4.5} />
          <line x1={b.x + 13} y1={b.y + 15} x2={b.x + 49} y2={b.y + 15} stroke={INK} strokeWidth={3} opacity={0.5} />
        </g>
      );
    })}
  </g>
);

// —— 士兵（线描：头巾 + 长袍 + 步枪）
const Soldier: React.FC<{arm?: number; muzzle?: number}> = ({arm = 0, muzzle = 0}) => (
  <g transform="translate(558 304) scale(1.1)">
    {/* 长袍 */}
    <path d="M -21 -28 C -27 6 -31 30 -38 44 L 38 44 C 31 30 27 6 21 -28 Z" fill={PAPER} stroke={INK} strokeWidth={5} />
    {/* 头 */}
    <circle cx={0} cy={-45} r={18} fill={PAPER} stroke={INK} strokeWidth={5} />
    {/* 头巾（盖顶 + 侧垂） */}
    <path d="M -21 -49 A 21 21 0 0 1 21 -49 L 25 -32 L -25 -32 Z" fill={PAPER} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    <path d="M 24 -50 L 39 -28 L 27 -33 Z" fill={PAPER} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    {/* 手臂 + 步枪（arm 驱动点射） */}
    <g transform={`translate(${-arm * 8} ${-arm * 3})`}>
      <path d="M -6 -18 L 34 -6 L 30 8 L -8 -2 Z" fill={PAPER} stroke={INK} strokeWidth={4.5} />
      <rect x={-16} y={-10} width={78} height={13} rx={4} fill={PAPER} stroke={INK} strokeWidth={4.5} />
      <path d="M 40 3 L 46 26 L 28 26 L 24 3 Z" fill={PAPER} stroke={INK} strokeWidth={4.5} />
      <path d="M -26 3 L -14 3 L -20 32 L -36 32 Z" fill={PAPER} stroke={INK} strokeWidth={4.5} />
      {muzzle > 0.02 && (
        <path
          d="M 62 4 L 94 -16 L 84 4 L 118 0 L 88 12 L 102 30 L 74 16 Z"
          fill={ACCENT}
          stroke={INK}
          strokeWidth={4}
          strokeLinejoin="round"
          opacity={muzzle}
        />
      )}
    </g>
  </g>
);

// —— 背景：沙丘 + 地面草点（原片是平滑曲线 + 小笔触，正好 SVG 原生）
const GRASS = [
  {x: 46, y: 66}, {x: 132, y: 118}, {x: 232, y: 84},
  {x: 320, y: 140}, {x: 452, y: 96}, {x: 560, y: 152}, {x: 648, y: 82},
];

const Backdrop: React.FC<{wave?: number}> = ({wave = 0}) => (
  <g>
    <path
      d={`M 0 ${GY - 84} C 120 ${GY - 118} 250 ${GY - 46} 380 ${GY - 76} C 500 ${GY - 104} 620 ${GY - 58} 698 ${GY - 80} L 698 ${GY} L 0 ${GY} Z`}
      fill="none"
      stroke={INK}
      strokeWidth={4}
      opacity={0.85}
    />
    <path
      d={`M 0 ${GY - 26} C 150 ${GY - 48} 300 ${GY} 440 ${GY - 20} C 560 ${GY - 38} 640 ${GY - 8} 698 ${GY - 22}`}
      fill="none"
      stroke={INK}
      strokeWidth={3.5}
      opacity={0.55}
    />
    {GRASS.map((g, i) => (
      <g key={i} transform={`translate(${g.x} ${g.y})`} opacity={0.65}>
        <line x1={0} y1={0} x2={0} y2={-11} stroke={INK} strokeWidth={3} />
        <line x1={0} y1={0} x2={-7} y2={-7} stroke={INK} strokeWidth={3} />
        <line x1={0} y1={0} x2={7} y2={-7} stroke={INK} strokeWidth={3} />
      </g>
    ))}
    {wave > 0.01 && (
      <circle
        cx={150 + 209}
        cy={GY + 8}
        r={30 + wave * 300}
        fill="none"
        stroke={INK}
        strokeWidth={5}
        opacity={(1 - wave) * 0.45}
      />
    )}
  </g>
);

// ---------------------------------------------------------------- 版式：黑板 + 白框 + 顶部固定标题
const Frame: React.FC<{children: React.ReactNode; tag?: string}> = ({children, tag}) => (
  <AbsoluteFill style={{backgroundColor: BOARD}}>
    <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
      <defs>
        <clipPath id="paperbox">
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} />
        </clipPath>
      </defs>
      <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} fill={PAPER} />
      <g clipPath="url(#paperbox)">
        <g transform={`translate(${BOX.x} ${BOX.y})`}>{children}</g>
      </g>

      {/* 顶部标题：实测字号 40、两行、白字、全片固定、紧贴条带上沿 */}
      <text x={W / 2} y={572} textAnchor="middle" fill="#FFFFFF" fontFamily={FONT} fontSize={40} fontWeight={700}>
        同一张图
      </text>
      <text x={W / 2} y={626} textAnchor="middle" fill="#FFFFFF" fontFamily={FONT} fontSize={40} fontWeight={700}>
        两种动法
      </text>
    </svg>

    {tag && (
      <div
        style={{
          position: 'absolute', left: 0, right: 0, top: 1150,
          textAlign: 'center', color: '#8A8A8A', fontFamily: FONT, fontSize: 30,
        }}
      >
        {tag}
      </div>
    )}
  </AbsoluteFill>
);

// ---------------------------------------------------------------- A 段：原片做法 —— 整张图推拉
const ScenePush: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const p = interpolate(frame, [0, durationInFrames], [0, 1], {extrapolateRight: 'clamp'});

  const scale = 1.0 + p * 0.12;
  const tx = -p * 40;
  const ty = p * 8;
  const cx = BOX.w / 2;
  const cy = BOX.h / 2;

  return (
    <Frame tag="A · 原片做法：整张图缓慢推拉">
      <g transform={`translate(${cx} ${cy}) scale(${scale}) translate(${-cx + tx} ${-cy + ty})`}>
        <Backdrop />
        <Tank />
        <Sandbags />
        <Soldier />
      </g>
    </Frame>
  );
};

// ---------------------------------------------------------------- B 段：SVG 做法 —— 分层元素各自动
const SceneLayer: React.FC = () => {
  const frame = useCurrentFrame();

  // 沙袋逐袋落下
  const drop = BAGS.map((_, i) =>
    interpolate(frame, [4 + i * 5, 18 + i * 5], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.bounce),
    }),
  );

  // 坦克三连发：后座 + 炮口火焰
  const shots = [26, 46, 66];
  const firing = shots.some((s) => frame >= s && frame < s + 7);
  const recoil = shots.reduce((acc, s) => {
    if (frame < s || frame > s + 18) return acc;
    const k = interpolate(frame, [s, s + 4, s + 18], [0, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    return Math.max(acc, k);
  }, 0);

  // 炮塔缓慢转向右前方
  const turret = interpolate(frame, [0, 26], [-14, 4], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic),
  });

  // 冲击波
  const wave = shots.reduce((acc, s) => {
    if (frame < s || frame > s + 30) return acc;
    return Math.max(acc, interpolate(frame, [s, s + 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}));
  }, 0);

  // 炮弹飞出画面
  const shellT = interpolate(frame, [30, 78], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const shellX = 150 + 209 + shellT * 520;
  const shellY = GY + 24 - shellT * 20;

  // 士兵点射应和
  const arm = [46, 66].some((s) => frame >= s && frame < s + 5) ? 1 : 0;

  // 本段刻意不做任何整体位移/缩放 —— 只让元素各自动，与 A 段形成干净对照
  const settle = interpolate(frame, [0, 10], [1.02, 1.0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic),
  });
  const cx = BOX.w / 2;
  const cy = BOX.h / 2;

  return (
    <Frame tag="B · SVG 做法：同一张图，元素各动">
      <g transform={`translate(${cx} ${cy}) scale(${settle}) translate(${-cx} ${-cy})`}>
        <Backdrop wave={wave} />
        <Tank turret={turret} recoil={recoil * 16} muzzle={firing ? 1 : 0} />
        <Sandbags drop={drop} />
        <Soldier arm={arm} muzzle={arm} />
        {frame >= 30 && frame <= 82 && (
          <g>
            <line x1={shellX - 60} y1={shellY} x2={shellX - 16} y2={shellY} stroke={ACCENT} strokeWidth={4} opacity={0.45} />
            <ellipse cx={shellX} cy={shellY} rx={15} ry={7} fill={PAPER} stroke={INK} strokeWidth={4} />
          </g>
        )}
      </g>
    </Frame>
  );
};

// ---------------------------------------------------------------- 组合：A 6s + B 6s
const SEG = 6 * FPS;

export const SvgRemakeRefTest: React.FC = () => (
  <>
    <Sequence from={0} durationInFrames={SEG}>
      <ScenePush />
    </Sequence>
    <Sequence from={SEG} durationInFrames={SEG}>
      <SceneLayer />
    </Sequence>
  </>
);

const RemotionRoot: React.FC = () => (
  <Composition
    id="SvgRemakeRefTest"
    component={SvgRemakeRefTest}
    durationInFrames={SEG * 2}
    fps={FPS}
    width={W}
    height={H}
  />
);

registerRoot(RemotionRoot);
