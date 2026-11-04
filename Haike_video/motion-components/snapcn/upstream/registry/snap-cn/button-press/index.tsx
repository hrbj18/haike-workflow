"use client";

import { loadFont as loadSans } from "@remotion/google-fonts/Inter";
import type { ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CursorTrack } from "@/components/snap-cn/cursor-track";
import {
  mixOklch,
  type SnapCnTheme,
  useSnapCnTheme,
  withAlpha,
} from "@/lib/snap-cn-ui";

const { fontFamily: SANS } = loadSans("normal", {
  weights: ["500"],
  subsets: ["latin"],
});

/**
 * The click every launch video has: a cursor walks onto a split action button
 * (label, divider, chevron), it darkens on hover, gives on press, spins while
 * it works and lands on a tick. Three labels, one fixed width — the button
 * never reflows, so the cursor resting on it never has to chase it.
 */
export interface ButtonPressProps {
  /** Idle label. */
  label?: string;
  /** While it works. */
  pending?: string;
  /** When it is done. */
  done?: string;
  /** Button width at 720p. Size it for the longest label. */
  width?: number;
  theme?: Partial<SnapCnTheme>;
  mode?: "light" | "dark";
  /** Time multiplier. */
  speed?: number;
  className?: string;
}

/** Cursor lands and clicks. */
export const CLICK_AT = 36;
/** Frames spent pending before the tick. */
export const PENDING_FRAMES = 40;
export const BUTTON_PRESS_FRAMES = 126;

const H = 76;
const EASE = Easing.bezier(0.2, 0.6, 0.35, 1);
const CLAMP = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

/** A label sliding in from below and out above, 8 frames each way. No `to`: it stays. */
function phase(frame: number, from: number, to?: number) {
  const inP = interpolate(frame, [from, from + 8], [0, 1], {
    ...CLAMP,
    easing: EASE,
  });
  const outP =
    to === undefined
      ? 0
      : interpolate(frame, [to, to + 8], [0, 1], { ...CLAMP, easing: EASE });
  return { opacity: inP * (1 - outP), y: (1 - inP) * 14 - outP * 14 };
}

/** The chevron segment's width, as a multiple of the button height. */
const CHEVRON_W = 0.86;

/**
 * A primary split button: the action, a hairline divider, a chevron. Takes its
 * paint from the theme; the label area is whatever you pass as children. Only
 * the surface presses (`press`, 1 at rest) — the label never scales, so it has
 * no glyph snapping to fight.
 */
export function SplitButton({
  t,
  width,
  height,
  background,
  press = 1,
  children,
}: {
  t: SnapCnTheme;
  /** px */
  width: number;
  /** px */
  height: number;
  /** Fill; defaults to the theme's primary. */
  background?: string;
  press?: number;
  children: ReactNode;
}) {
  const chevron = height * CHEVRON_W;
  return (
    <div
      style={{
        position: "relative",
        width,
        height,
        color: t.primaryForeground,
        whiteSpace: "nowrap",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          // shadcn's button radius, kept in proportion at this height.
          borderRadius: t.radius * (height / 36),
          backgroundColor: background ?? t.primary,
          scale: press,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          right: chevron,
          overflow: "hidden",
        }}
      >
        {children}
      </div>
      <div
        style={{
          position: "absolute",
          right: chevron,
          top: height * 0.24,
          bottom: height * 0.24,
          width: Math.max(1, height / 76),
          backgroundColor: withAlpha(t.primaryForeground, 0.32),
        }}
      />
      <svg
        viewBox="0 0 24 24"
        width={height * 0.34}
        height={height * 0.34}
        style={{
          position: "absolute",
          right: (chevron - height * 0.34) / 2,
          top: height * 0.33,
        }}
      >
        <title>More</title>
        <path
          d="M6 9.5 L12 15.5 L18 9.5"
          fill="none"
          stroke={t.primaryForeground}
          strokeWidth={2.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function ButtonPress({
  label = "Deploy",
  pending = "Deploying…",
  done = "Deployed",
  width: w = 320,
  theme,
  mode,
  speed = 1,
  className,
}: ButtonPressProps) {
  const frame = useCurrentFrame() * speed;
  const { height } = useVideoConfig();
  const t = useSnapCnTheme(theme, mode);
  const s = height / 720;

  const doneAt = CLICK_AT + PENDING_FRAMES;
  const path = [
    { at: 8, x: 0.86, y: 1.08, duration: 6 },
    { at: 14, x: 0.47, y: 0.53, duration: CLICK_AT - 14, click: true },
    { at: doneAt + 14, x: 0.62, y: 0.7, duration: 18 },
  ];

  const enter = interpolate(frame, [0, 14], [0, 1], { ...CLAMP, easing: EASE });
  const hover = interpolate(frame, [CLICK_AT - 6, CLICK_AT], [0, 1], CLAMP);
  // Press returns exactly to 1, and only on the surface: the label never
  // scales, so there is no glyph snapping to fight.
  const pressP = interpolate(frame, [CLICK_AT, CLICK_AT + 10], [0, 1], CLAMP);
  const press = 1 - Math.sin(pressP * Math.PI) * 0.035;

  const idle = phase(frame, -8, CLICK_AT + 2);
  const busy = phase(frame, CLICK_AT + 2, doneAt);
  const ok = phase(frame, doneAt);
  const tick = interpolate(frame, [doneAt + 4, doneAt + 14], [0, 1], {
    ...CLAMP,
    easing: EASE,
  });

  const bg = mixOklch(t.primary, t.foreground, hover * 0.14);
  const icon = 26 * s;
  const row = (y: number, opacity: number, children: ReactNode) => (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 12 * s,
        opacity,
        transform: `translateY(${y * s}px)`,
      }}
    >
      {children}
    </div>
  );

  return (
    <CursorTrack path={path} theme={theme} mode={mode} speed={speed}>
      <AbsoluteFill
        className={className}
        style={{
          backgroundColor: t.background,
          alignItems: "center",
          justifyContent: "center",
          fontFamily: SANS,
          fontWeight: 500,
          textRendering: "geometricPrecision",
        }}
      >
        <div
          style={{
            opacity: enter,
            transform: `translateY(${(1 - enter) * 12 * s}px)`,
            fontSize: 28 * s,
            letterSpacing: "-0.01em",
          }}
        >
          <SplitButton
            t={t}
            width={w * s}
            height={H * s}
            background={bg}
            press={press}
          >
            {row(idle.y, idle.opacity, label)}
            {row(
              busy.y,
              busy.opacity,
              <>
                <svg
                  viewBox="0 0 24 24"
                  width={icon}
                  height={icon}
                  style={{ rotate: `${frame * 12}deg` }}
                >
                  <title>Pending</title>
                  <circle
                    cx={12}
                    cy={12}
                    r={9}
                    fill="none"
                    stroke={t.primaryForeground}
                    strokeOpacity={0.3}
                    strokeWidth={2.6}
                  />
                  <path
                    d="M12 3 A9 9 0 0 1 21 12"
                    fill="none"
                    stroke={t.primaryForeground}
                    strokeWidth={2.6}
                    strokeLinecap="round"
                  />
                </svg>
                {pending}
              </>,
            )}
            {row(
              ok.y,
              ok.opacity,
              <>
                <svg viewBox="0 0 24 24" width={icon} height={icon}>
                  <title>Done</title>
                  <path
                    d="M5 12.5 L10 17 L19 7.5"
                    fill="none"
                    stroke={t.primaryForeground}
                    strokeWidth={2.8}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pathLength={1}
                    strokeDasharray={1}
                    strokeDashoffset={1 - tick}
                  />
                </svg>
                {done}
              </>,
            )}
          </SplitButton>
        </div>
      </AbsoluteFill>
    </CursorTrack>
  );
}
