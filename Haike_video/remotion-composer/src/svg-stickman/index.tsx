/**
 * SVG 火柴人动画测试 (2026-09-20)
 * 主题：如何提升专注力
 *
 * 与同目录另两条测试片的区别：
 *   svg-focus        图形动效（描边、散点收敛）—— 没有角色
 *   svg-remake-ref   静图推拉对照 —— 图在动，人不在动
 *   本片             **角色动画** —— 火柴人有骨架、有关节、有走路循环与表演
 *
 * 技术路线：
 *   1. 参数化骨骼 + 正向运动学（FK）。姿势 = 一组关节角度，四肢末端由 FK 算出。
 *   2. 走路循环由相位驱动（大腿正弦摆动 + 膝盖单向弯曲 + 手臂反向摆）。
 *   3. 每帧结束后做「落地吸附」：整体平移骨架，使最低的脚刚好触地
 *      —— 不用 IK 也能保证脚不穿地、该腾空就腾空。
 *   4. 镜头（缩放 + 震动）只作用于世界层；标题与字幕是 HUD 层，不随镜头缩放。
 *   5. 全部由 Remotion 帧号确定，无随机、无 requestAnimationFrame，可逐帧复现。
 *
 * 独立 registerRoot，不注册进 src/Root.tsx，对生产组合零影响。
 */
import React from 'react';
import {
  AbsoluteFill,
  Composition,
  Easing,
  interpolate,
  registerRoot,
  useCurrentFrame,
} from 'remotion';

// ================================================================ 规格
const W = 1080;
const H = 1920;
const FPS = 30;

const A1 = 0;    // 幕一：走进来
const A2 = 140;  // 幕二：被打扰
const A3 = 320;  // 幕三：三个解法
const A4 = 580;  // 幕四：收束
const END = 660;
const DUR = END;

const GROUND_Y = 1450;   // 世界坐标：脚底站线
const CAM_CY = 1120;     // 镜头缩放中心

const FONT = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif';

// ================================================================ 配色
const INK = '#2A211B';
const INK_FAR = '#9A8878';   // 远侧肢体（浅一档，做出纵深）
const BG_TOP = '#FFF7EE';
const BG_BOT = '#F1E2CF';
const GROUND = '#EAD8C2';
const GROUND_LN = '#D2BCA0';
const RED = '#E8453C';
const RED_LT = '#FFD9D5';
const ORANGE = '#FF6B35';
const ORANGE_LT = '#FFE3D4';
const WHITE = '#FFFFFF';

// ================================================================ 骨骼尺寸（单位 = 头半径 R）
const R = 86;
const BONE = {
  neck: 0.50 * R,
  torso: 3.20 * R,
  thigh: 2.00 * R,
  shin: 2.00 * R,
  upperArm: 0.95 * R,
  foreArm: 0.85 * R,
  shoulderHalf: 0.42 * R,
  hipHalf: 0.34 * R,
};

// ================================================================ 向量 / FK
type Vec = {x: number; y: number};

/** 角度用「度」，0° = 指向右（+x），90° = 指向下（+y，SVG 坐标系） */
const dirOf = (deg: number): Vec => {
  const r = (deg * Math.PI) / 180;
  return {x: Math.cos(r), y: Math.sin(r)};
};
const go = (p: Vec, deg: number, len: number): Vec => {
  const d = dirOf(deg);
  return {x: p.x + d.x * len, y: p.y + d.y * len};
};
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const mix = (a: Vec, b: Vec, k: number): Vec => ({x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k)});

/**
 * 姿势 = 髋位置 + 8 组关节角。
 *   torso：躯干朝上方向。−90 = 竖直向上；−74 = 前倾 16°
 *   head ：相对躯干的额外偏移
 *   四肢：世界绝对角 [近端, 远端]（上臂/前臂、大腿/小腿）
 */
export type Pose = {
  hip: Vec;
  torso: number;
  head: number;
  armN: [number, number];
  armF: [number, number];
  legN: [number, number];
  legF: [number, number];
};

type Bones = {
  hip: Vec;
  shoulder: Vec;
  headC: Vec;
  elbowN: Vec;
  handN: Vec;
  elbowF: Vec;
  handF: Vec;
  kneeN: Vec;
  footN: Vec;
  kneeF: Vec;
  footF: Vec;
};

/** 正向运动学：姿势 → 全部关节点世界坐标 */
const solve = (p: Pose): Bones => {
  const shoulder = go(p.hip, p.torso, BONE.torso);
  const headAxis = p.torso + p.head;
  const headBase = go(shoulder, headAxis, BONE.neck);
  const headC = go(headBase, headAxis, R);

  const perp = p.torso + 90;
  const shN = go(shoulder, perp, BONE.shoulderHalf);
  const shF = go(shoulder, perp + 180, BONE.shoulderHalf);
  const hipN = go(p.hip, perp, BONE.hipHalf);
  const hipF = go(p.hip, perp + 180, BONE.hipHalf);

  const elbowN = go(shN, p.armN[0], BONE.upperArm);
  const handN = go(elbowN, p.armN[1], BONE.foreArm);
  const elbowF = go(shF, p.armF[0], BONE.upperArm);
  const handF = go(elbowF, p.armF[1], BONE.foreArm);

  const kneeN = go(hipN, p.legN[0], BONE.thigh);
  const footN = go(kneeN, p.legN[1], BONE.shin);
  const kneeF = go(hipF, p.legF[0], BONE.thigh);
  const footF = go(kneeF, p.legF[1], BONE.shin);

  return {hip: p.hip, shoulder, headC, elbowN, handN, elbowF, handF, kneeN, footN, kneeF, footF};
};

/** 落地吸附：整体平移骨架，让最低的脚踩在 groundY 上 */
const groundAt = (p: Pose, groundY: number): Pose => {
  const b = solve(p);
  const low = Math.max(b.footN.y, b.footF.y);
  return {...p, hip: {x: p.hip.x, y: p.hip.y + (groundY - low)}};
};

// ================================================================ 姿势插值（表演用）
const lerpPose = (a: Pose, b: Pose, k: number): Pose => ({
  hip: mix(a.hip, b.hip, k),
  torso: lerp(a.torso, b.torso, k),
  head: lerp(a.head, b.head, k),
  armN: [lerp(a.armN[0], b.armN[0], k), lerp(a.armN[1], b.armN[1], k)],
  armF: [lerp(a.armF[0], b.armF[0], k), lerp(a.armF[1], b.armF[1], k)],
  legN: [lerp(a.legN[0], b.legN[0], k), lerp(a.legN[1], b.legN[1], k)],
  legF: [lerp(a.legF[0], b.legF[0], k), lerp(a.legF[1], b.legF[1], k)],
});

// ================================================================ 姿势库
const P = (
  x: number,
  torso: number,
  head: number,
  armN: [number, number],
  armF: [number, number],
  legN: [number, number],
  legF: [number, number],
): Pose => ({hip: {x, y: 0}, torso, head, armN, armF, legN, legF});

const easeOut = Easing.out(Easing.cubic);
const easeInOut = Easing.inOut(Easing.cubic);

/** 站立：两臂微微前后错开，避免与躯干糊成一条 */
const STAND = (x: number): Pose =>
  P(x, -88, 2, [80, 92], [100, 112], [93, 89], [87, 93]);

/** 走路循环。phase 每 +1 = 一个完整步态周期（左一步 + 右一步） */
const walkPose = (
  x: number,
  phase: number,
  opt?: {stride?: number; swing?: number; lean?: number},
): Pose => {
  const stride = opt?.stride ?? 30;
  const swing = opt?.swing ?? 26;
  const lean = opt?.lean ?? 6;

  const a = phase * Math.PI * 2;
  const s = Math.sin(a);
  const c = Math.cos(a);

  const thighN = 90 + s * stride;
  const thighF = 90 - s * stride;
  // 膝盖只能向后弯 → 摆动相（cos<0）才屈，支撑相基本伸直
  const bendN = Math.max(0, -c) * 62;
  const bendF = Math.max(0, c) * 62;
  const armN = 90 - s * swing;
  const armF = 90 + s * swing;

  return P(
    x,
    -90 + lean,
    0,
    [armN, armN + 24],
    [armF, armF + 24],
    [thighN, thighN + bendN],
    [thighF, thighF + bendF],
  );
};

// ================================================================ 火柴人
const Stickman: React.FC<{
  pose: Pose;
  mood?: number;      // −1 沮丧 / 0 平静 / +1 有精神
  shadow?: boolean;
  accent?: string;
  blinkOffset?: number;
}> = ({pose, mood = 0, shadow = true, accent = ORANGE, blinkOffset = 0}) => {
  const frame = useCurrentFrame();
  const b = solve(pose);
  const line = (pts: Vec[]) => pts.map((q) => `${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(' L ');

  // 眨眼：每 ~3.2 秒一次，纯帧号驱动
  const cyc = (frame + blinkOffset) % 96;
  const blink = Math.max(0, 1 - Math.abs(cyc - 3) / 2.4);
  const eyeOpen = 1 - blink;

  const armPath = `M ${line([b.shoulder, b.elbowN, b.handN])}`;
  const legPath = `M ${line([b.hip, b.kneeN, b.footN])}`;
  const eye = {x: b.headC.x + R * 0.34, y: b.headC.y - R * 0.08 + pose.head * 0.5};
  const browY = b.headC.y - R * 0.46;
  const browTilt = -mood * 15;

  return (
    <g>
      {shadow && <ellipse cx={b.hip.x} cy={GROUND_Y + 10} rx={130} ry={22} fill={INK} opacity={0.13} />}
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        {/* 远侧肢体 */}
        <g stroke={INK_FAR} strokeWidth={22} opacity={0.9}>
          <path d={`M ${line([b.shoulder, b.elbowF, b.handF])}`} />
          <path d={`M ${line([b.hip, b.kneeF, b.footF])}`} />
        </g>
        {/* 躯干 */}
        <path d={`M ${line([b.hip, b.shoulder])}`} stroke={INK} strokeWidth={27} />
        {/* 头 */}
        <circle cx={b.headC.x} cy={b.headC.y} r={R} fill={BG_TOP} stroke={INK} strokeWidth={23} />
        {/* 近侧肢体：先描一圈背景色把身体与环境分开，否则侧视下手臂会与躯干糊成一根 */}
        <g stroke={BG_TOP} strokeWidth={29}>
          <path d={armPath} />
        </g>
        <g stroke={INK} strokeWidth={21}>
          <path d={armPath} />
          <path d={legPath} />
        </g>
        {/* 拳头：让肢体末端读得出 */}
        <circle cx={b.handN.x} cy={b.handN.y} r={14} fill={INK} stroke="none" />
        <circle cx={b.handF.x} cy={b.handF.y} r={13} fill={INK_FAR} stroke="none" />
        {/* 表情 */}
        <ellipse cx={eye.x} cy={eye.y} rx={9.5} ry={Math.max(0.6, 9.5 * eyeOpen)} fill={INK} stroke="none" />
        <line
          x1={eye.x - 24}
          y1={browY + browTilt * 0.4}
          x2={eye.x + 20}
          y2={browY - browTilt * 0.4}
          stroke={INK}
          strokeWidth={9}
          strokeLinecap="round"
        />
        {/* 专注光环 */}
        {mood > 0.8 && (
          <circle
            cx={b.headC.x}
            cy={b.headC.y}
            r={R * 1.85}
            fill="none"
            stroke={accent}
            strokeWidth={7}
            opacity={(mood - 0.8) * 2 < 0 ? 0 : Math.min(0.55, (mood - 0.8) * 2.4)}
          />
        )}
      </g>
    </g>
  );
};

// ================================================================ 场景装饰
const RADIAL = [-320, -80, 200, 520, 840, 1160, 1440];

const PerspectiveFloor: React.FC = () => {
  const t = useCurrentFrame() / FPS;
  const off = (t / 0.35) % 1;
  return (
    <g opacity={0.45}>
      {[0, 1, 2, 3, 4, 5, 6].map((i) => {
        const k = (i + off) / 7;
        const y = GROUND_Y + Math.pow(k, 2.2) * (H - GROUND_Y) * 1.05;
        return <line key={i} x1={-240} y1={y} x2={W + 240} y2={y} stroke={GROUND_LN} strokeWidth={6} />;
      })}
      {RADIAL.map((x, i) => (
        <line key={i} x1={x * 0.55 + (W / 2) * 0.45} y1={GROUND_Y} x2={x} y2={H} stroke={GROUND_LN} strokeWidth={6} />
      ))}
    </g>
  );
};

const Backdrop: React.FC<{tint?: number}> = ({tint = 0}) => (
  <g>
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={BG_TOP} />
        <stop offset="100%" stopColor={BG_BOT} />
      </linearGradient>
    </defs>
    <rect x={-400} y={-200} width={W + 800} height={H + 400} fill="url(#sky)" />
    {/* 远处无脸建筑剪影：给「世界」感，不抢主体 */}
    <g opacity={0.2} fill={INK}>
      <rect x={40} y={1010} width={118} height={240} rx={8} />
      <rect x={190} y={1088} width={88} height={162} rx={6} />
      <rect x={306} y={1046} width={132} height={204} rx={8} />
      <rect x={772} y={1062} width={108} height={188} rx={8} />
      <rect x={908} y={1012} width={102} height={238} rx={8} />
    </g>
    <rect x={-400} y={GROUND_Y} width={W + 800} height={H - GROUND_Y + 400} fill={GROUND} />
    <line x1={-400} y1={GROUND_Y} x2={W + 400} y2={GROUND_Y} stroke={GROUND_LN} strokeWidth={7} />
    <PerspectiveFloor />
    {tint !== 0 && (
      <rect x={-400} y={-200} width={W + 800} height={H + 400} fill={tint > 0 ? ORANGE_LT : RED_LT} opacity={Math.abs(tint) * 0.45} />
    )}
  </g>
);

// ================================================================ 干扰气泡
type Bubble = {x: number; y: number; label: string; kind: 'phone' | 'bell' | 'chat' | 'mail' | 'hot'};

/** 只落在两侧空档，避开顶部标题带与中央主体；x 收在镜头推近后的可见区（125~955）内 */
const BUBBLES: Bubble[] = [
  {x: 262, y: 900, label: '抖音', kind: 'phone'},
  {x: 836, y: 880, label: '微信', kind: 'chat'},
  {x: 242, y: 1180, label: '邮件', kind: 'mail'},
  {x: 848 - 10, y: 1160, label: '热搜', kind: 'hot'},
  {x: 288, y: 1420, label: '推送', kind: 'bell'},
  {x: 806, y: 1410, label: '群消息', kind: 'chat'},
];

const Glyph: React.FC<{kind: Bubble['kind']}> = ({kind}) => {
  const s = INK;
  switch (kind) {
    case 'phone':
      return (
        <g stroke={s} strokeWidth={7} fill="none" strokeLinecap="round">
          <rect x={-24} y={-38} width={48} height={76} rx={10} />
          <line x1={-9} y1={30} x2={9} y2={30} />
        </g>
      );
    case 'bell':
      return (
        <g stroke={s} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d="M -26 20 L -20 -6 A 20 20 0 0 1 20 -6 L 26 20 Z" />
          <path d="M -30 20 L 30 20" />
          <path d="M -8 28 A 9 9 0 0 0 8 28" />
        </g>
      );
    case 'chat':
      return (
        <g stroke={s} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d="M -30 -26 L 30 -26 L 30 16 L 4 16 L -12 32 L -12 16 L -30 16 Z" />
        </g>
      );
    case 'mail':
      return (
        <g stroke={s} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <rect x={-32} y={-22} width={64} height={44} rx={8} />
          <path d="M -32 -18 L 0 8 L 32 -18" />
        </g>
      );
    default:
      return (
        <g stroke={s} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d="M 0 30 A 15 15 0 1 0 0 -30 A 15 15 0 1 0 0 30 Z" />
          <path d="M 0 -19 L 0 8 M 0 17 L 0 19" />
        </g>
      );
  }
};

const BubbleCard: React.FC<{b: Bubble; k: number; scatter: number}> = ({b, k, scatter}) => {
  const pop = interpolate(k, [0, 1], [0.4, 1], {easing: Easing.out(Easing.back(1.8)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fly = interpolate(scatter, [0, 1], [0, 1], {easing: Easing.out(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const ang = Math.atan2(b.y - 1100, b.x - 540);
  return (
    <g
      transform={`translate(${b.x + Math.cos(ang) * fly * 1200} ${b.y + Math.sin(ang) * fly * 1200}) scale(${pop}) rotate(${fly * 240})`}
      opacity={k <= 0 ? 0 : 1 - fly}
    >
      <rect x={-110} y={-54} width={220} height={108} rx={28} fill={WHITE} stroke={RED} strokeWidth={9} />
      <g transform="translate(-64 0) scale(0.6)">
        <Glyph kind={b.kind} />
      </g>
      <text x={48} y={4} textAnchor="middle" dominantBaseline="middle" fontFamily={FONT} fontSize={40} fontWeight={700} fill={INK}>
        {b.label}
      </text>
    </g>
  );
};

// ================================================================ 幕一：走进来
const ActOne: React.FC<{f: number; p: number}> = ({f, p}) => {
  const x = -190 + p * 750;
  const phase = (x + 190) / 400;
  const walking = groundAt(walkPose(x, phase, {lean: 7, stride: 31, swing: 27}), GROUND_Y);

  // 末段收步：从走路姿过渡到站姿
  const stop = interpolate(f, [104, 128], [0, 1], {easing: easeOut, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const settle = lerpPose(walking, STAND(560), stop);
  // 收步时必须重做落地吸附：STAND 的 hip.y 是相对值，不吸附会整个人飞出去
  const stood = groundAt(settle, GROUND_Y);
  const bounce = interpolate(f, [104, 114, 124], [0, -18, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pose: Pose = {...stood, hip: {x: stood.hip.x, y: stood.hip.y + bounce}};

  return (
    <g>
      <Stickman pose={pose} mood={0.2} />
      {/* 走路扬尘 */}
      {[0, 1, 2].map((i) => {
        const kk = (f / 14 + i * 0.33) % 1;
        return (
          <circle
            key={i}
            cx={pose.hip.x - 96 - kk * 150}
            cy={GROUND_Y - 6 - kk * 40}
            r={8 + kk * 22}
            fill={GROUND_LN}
            opacity={stop > 0.6 ? 0 : (1 - kk) * 0.5}
          />
        );
      })}
    </g>
  );
};

// ================================================================ 幕二：被打扰
const ActTwo: React.FC<{f: number}> = ({f}) => {
  const jitter = interpolate(f, [56, 96], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const h = Math.sin(f * 0.44) * 26 + Math.sin(f * 0.31 + 1.1) * 18;
  const aN = 80 + Math.sin(f * 0.38) * 46 * jitter;
  const aF = 100 + Math.sin(f * 0.33 + 2.2) * 50 * jitter;

  const base = STAND(560);
  const pose: Pose = {
    ...base,
    head: h * jitter,
    armN: [aN, aN + 32 + Math.sin(f * 0.6) * 20 * jitter],
    armF: [aF, aF + 32 + Math.cos(f * 0.55) * 20 * jitter],
    torso: -88 + Math.sin(f * 0.27) * 5 * jitter,
  };

  // 抖完以后一挥手把气泡赶走（交接给幕三）
  const swipe = interpolate(f, [150, 176], [0, 1], {easing: Easing.inOut(Easing.cubic), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const swiped: Pose = {
    ...pose,
    armN: [-58, -18],
    armF: [26, 60],
    head: -4,
    torso: -92,
  };
  const final = lerpPose(pose, swiped, swipe);
  const scatter = swipe;

  return (
    <g>
      <Stickman pose={groundAt(final, GROUND_Y)} mood={-1 + swipe * 0.4} />
      {BUBBLES.map((b, i) => {
        const start = 30 + i * 12;
        const k = interpolate(f, [start, start + 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const jx = Math.sin(f * 0.5 + i * 1.7) * 12 * jitter;
        const jy = Math.cos(f * 0.42 + i * 2.3) * 10 * jitter;
        return (
          <g key={i} transform={`translate(${jx} ${jy})`}>
            <BubbleCard b={b} k={k} scatter={scatter} />
          </g>
        );
      })}
    </g>
  );
};

// ================================================================ 幕三：三个解法
const TimerRing: React.FC<{k: number}> = ({k}) => {
  const r = 96;
  const circ = Math.PI * 2 * r;
  const remain = Math.max(0, 25 - Math.floor(k * 25));
  return (
    <g>
      <circle cx={0} cy={0} r={r} fill="none" stroke="#E6DACB" strokeWidth={21} />
      <circle
        cx={0}
        cy={0}
        r={r}
        fill="none"
        stroke={ORANGE}
        strokeWidth={21}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ * (1 - k)}
        transform="rotate(-90)"
      />
      <text x={0} y={5} textAnchor="middle" dominantBaseline="middle" fontFamily={FONT} fontSize={58} fontWeight={800} fill={INK}>
        {`${String(remain).padStart(2, '0')}:00`}
      </text>
    </g>
  );
};

/** 三个解法各自的动作：拍下去 / 抓一个 / 静下来 */
const solutionPose = (idx: number, local: number, SEG: number): Pose => {
  const base = STAND(560);
  const k = local / SEG;
  const up = Math.sin(Math.min(1, k * 1.35) * Math.PI); // 0 → 1 → 0
  if (idx === 0) {
    // 抬手过顶，往下一按：手举到肩的正上方，再落回
    return {
      ...base,
      head: -3,
      torso: -92,
      armN: [lerp(80, -62, up), lerp(92, -88, up)],
      armF: [lerp(100, 46, up), lerp(112, 22, up)],
      legN: [94, 90],
      legF: [86, 92],
    };
  }
  if (idx === 1) {
    // 双手往前抓：上臂前平举，前臂略收
    return {
      ...base,
      head: 2,
      torso: -84,
      armN: [lerp(80, -6, up), lerp(92, -12, up)],
      armF: [lerp(100, 4, up), lerp(112, 2, up)],
      legN: [96, 92],
      legF: [84, 90],
    };
  }
  // 静下来：只是呼吸，几乎不动
  const breathe = Math.sin(local * 0.16) * 2;
  return {...base, head: -1 + breathe * 0.4, armN: [82, 90], armF: [98, 108]};
};

const ActThree: React.FC<{f: number}> = ({f}) => {
  const SEG = 86;
  const idx = Math.min(2, Math.floor(f / SEG));
  const local = f - idx * SEG;
  const localK = interpolate(local, [0, SEG], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pose = solutionPose(idx, local, SEG);

  // 图标卡：世界坐标 (540, 430)，尺寸 240，落在头顶上方
  const iconK = interpolate(local, [4, 20], [0, 1], {easing: Easing.out(Easing.back(1.5)), extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <g>
      <Stickman pose={groundAt(pose, GROUND_Y)} mood={0.4 + localK * 0.6} />
      <g transform={`translate(540 430) scale(${iconK})`} opacity={iconK}>
        <rect x={-124} y={-124} width={248} height={248} rx={62} fill={WHITE} stroke={INK} strokeWidth={11} />
        {idx === 0 && (
          <>
            <g transform="scale(1.75)">
              <Glyph kind="bell" />
            </g>
            <line x1={-84} y1={-84} x2={84} y2={84} stroke={RED} strokeWidth={17} strokeLinecap="round" />
          </>
        )}
        {idx === 1 && (
          <>
            <circle cx={0} cy={0} r={88} fill="none" stroke={INK} strokeWidth={11} />
            <text x={0} y={7} textAnchor="middle" dominantBaseline="middle" fontFamily={FONT} fontSize={112} fontWeight={800} fill={ORANGE}>
              1
            </text>
          </>
        )}
        {idx === 2 && (
          <TimerRing k={interpolate(local, [12, SEG - 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})} />
        )}
      </g>
    </g>
  );
};

// ================================================================ 幕四：收束
const ActFour: React.FC<{f: number}> = ({f}) => {
  const halo = interpolate(f, [8, 46], [0, 1], {easing: easeOut, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const breath = 1 + Math.sin(f * 0.13) * 0.012;
  const pose: Pose = {...STAND(560), armN: [84, 94], armF: [96, 106], head: 0};
  const settled = groundAt(pose, GROUND_Y);
  const b = solve(settled);

  return (
    <g>
      {/* 从角色向外扩散的脉冲光环，比静态同心圆更有"活气" */}
      <g opacity={halo}>
        {[0, 1, 2].map((i) => {
          const k = ((f / 42 + i / 3) % 1);
          return (
            <circle
              key={i}
              cx={b.headC.x}
              cy={GROUND_Y - 300}
              r={190 + k * 330}
              fill="none"
              stroke={ORANGE}
              strokeWidth={6}
              opacity={(1 - k) * 0.42}
            />
          );
        })}
      </g>
      <g transform={`translate(${b.hip.x} ${GROUND_Y}) scale(${breath}) translate(${-b.hip.x} ${-GROUND_Y})`}>
        <Stickman pose={settled} mood={1} shadow={false} />
      </g>
    </g>
  );
};

// ================================================================ HUD（不随镜头缩放）
const Title: React.FC<{
  lines: string[];
  y: number;
  size: number;
  color?: string;
  k: number;
}> = ({lines, y, size, color = INK, k}) => {
  const e = interpolate(k, [0, 1], [0, 1], {easing: easeOut, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <g opacity={e} transform={`translate(0 ${(1 - e) * 38})`}>
      {lines.map((ln, i) => (
        <text
          key={i}
          x={W / 2}
          y={y + i * size * 1.22}
          textAnchor="middle"
          fontFamily={FONT}
          fontSize={size}
          fontWeight={800}
          fill={color}
        >
          {ln}
        </text>
      ))}
    </g>
  );
};

/** 底部字幕条，底边 1738 < 1920*0.80*... 远高于安全线 */
const Caption: React.FC<{text: string; k: number}> = ({text, k}) => {
  const e = interpolate(k, [0, 1], [0, 1], {easing: easeOut, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cw = Math.min(W - 100, text.length * 52 + 96);
  return (
    <g opacity={e} transform={`translate(0 ${(1 - e) * 26})`}>
      <rect x={(W - cw) / 2} y={1626} width={cw} height={112} rx={56} fill={INK} opacity={0.93} />
      <text x={W / 2} y={1682} textAnchor="middle" dominantBaseline="middle" fontFamily={FONT} fontSize={50} fontWeight={700} fill={WHITE}>
        {text}
      </text>
    </g>
  );
};

const Dots: React.FC<{idx: number}> = ({idx}) => (
  <g>
    {[0, 1, 2].map((i) => (
      <circle key={i} cx={W / 2 + (i - 1) * 40} cy={1548} r={i === idx ? 13 : 9} fill={i === idx ? ORANGE : '#D8C8B6'} />
    ))}
  </g>
);

// ================================================================ 主组合
export const SvgStickmanFocus: React.FC = () => {
  const frame = useCurrentFrame();

  // 镜头：幕一逐渐推近并保持；幕二后半段轻微震动
  const camScale = interpolate(frame, [0, 112, 200, END], [1.0, 1.26, 1.3, 1.26], {
    easing: easeInOut,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const shake = frame >= A2 + 60 && frame < A3 ? interpolate(frame, [A2 + 60, A2 + 150], [0, 1], {extrapolateRight: 'clamp'}) : 0;
  const sx = Math.sin(frame * 1.7) * 10 * shake;
  const sy = Math.cos(frame * 2.3) * 6 * shake;

  const act = frame < A2 ? 1 : frame < A3 ? 2 : frame < A4 ? 3 : 4;

  return (
    <AbsoluteFill style={{backgroundColor: BG_TOP}}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        <defs>
          <clipPath id="stage">
            <rect x={0} y={0} width={W} height={H} />
          </clipPath>
        </defs>
        <g clipPath="url(#stage)">
          {/* ---------- 世界层：跟随镜头 ---------- */}
          <g transform={`translate(${sx} ${sy}) translate(${W / 2} ${CAM_CY}) scale(${camScale}) translate(${-W / 2} ${-CAM_CY})`}>
            <Backdrop tint={act === 2 && frame > A2 + 46 ? -0.5 : 0} />
            {act === 1 && (
              <ActOne
                f={frame - A1}
                p={interpolate(frame, [0, 112], [0, 1], {easing: easeOut, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
              />
            )}
            {act === 2 && <ActTwo f={frame - A2} />}
            {act === 3 && <ActThree f={frame - A3} />}
            {act === 4 && <ActFour f={frame - A4} />}
          </g>

          {/* ---------- HUD 层：屏幕坐标，不受镜头影响 ---------- */}
          {act === 1 && (
            <Title
              lines={['为什么你', '总是分心？']}
              y={272}
              size={96}
              k={interpolate(frame, [42, 76], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
            />
          )}
          {act === 2 && (
            <Title
              lines={['一条通知', '够毁掉二十分钟']}
              y={236}
              size={80}
              color={RED}
              k={interpolate(frame - A2, [4, 26], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
            />
          )}
          {act === 3 && (
            <>
              <Dots idx={Math.min(2, Math.floor((frame - A3) / 86))} />
              <Caption
                text={['关掉通知，只留电话', '一次只做一件事', '25 分钟一个周期'][Math.min(2, Math.floor((frame - A3) / 86))]}
                k={interpolate((frame - A3) % 86, [8, 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
              />
            </>
          )}
          {act === 4 && (
            <>
              <Title
                lines={['专注不是天赋', '是设置']}
                y={300}
                size={94}
                k={interpolate(frame - A4, [4, 34], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
              />
              <Caption
                text="从今天挑一个开始"
                k={interpolate(frame - A4, [26, 50], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
              />
            </>
          )}
        </g>
      </svg>
    </AbsoluteFill>
  );
};

const RemotionRoot: React.FC = () => (
  <Composition
    id="SvgStickmanFocus"
    component={SvgStickmanFocus}
    durationInFrames={DUR}
    fps={FPS}
    width={W}
    height={H}
  />
);

registerRoot(RemotionRoot);
