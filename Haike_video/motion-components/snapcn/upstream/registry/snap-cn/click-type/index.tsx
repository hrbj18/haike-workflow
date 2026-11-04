"use client";

import { loadFont as loadSans } from "@remotion/google-fonts/Inter";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Caret } from "@/components/snap-cn/caret";
import { CursorTrack } from "@/components/snap-cn/cursor-track";
import { inputStyleContext } from "@/components/snap-cn/input";
import {
  mixOklch,
  type SnapCnTheme,
  useSnapCnTheme,
  withAlpha,
} from "@/lib/snap-cn-ui";

const { fontFamily: SANS } = loadSans("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
});

/**
 * Click to type: a prompt composer whose placeholder writes itself while a
 * cursor flies in and clicks the field — then a hard cut into the field, where
 * the real prompt types at the caret and the send button arms.
 *
 * The composer is Prompt Send's: a glass panel over a soft accent wash, a
 * writing surface inside it, a round ink send button. Same paint, so the two
 * cut together.
 *
 * Two shots of one composer. The close-up is the same scene under a constant
 * camera scale, anchored on the text's first letter, so nothing scales while
 * it moves and the type has no pixel grid to climb.
 */
export interface ClickTypeProps {
  /** Muted text that writes itself in the wide shot. */
  placeholder?: string;
  /** What gets typed after the click, in the close-up. */
  prompt?: string;
  /** Small label at the field's bottom-left. */
  hint?: string;
  /** The wash behind the composer. Defaults to the theme's primary. */
  accentColor?: string;
  theme?: Partial<SnapCnTheme>;
  mode?: "light" | "dark";
  /** Time multiplier. */
  speed?: number;
  className?: string;
}

/** Cursor lands and clicks. */
export const CLICK_AT = 30;
/** The cut into the field. */
export const CUT_AT = 34;
const TYPE_AT = CUT_AT + 4;
const HOLD = 36;

/** At 720p. */
const PANEL_W = 920;
const PANEL_H = 260;
/** The glass rim between panel and writing surface. */
const PAD = 7;
const RADIUS = 32;
const PAD_X = 34;
const PAD_Y = 34;
const TEXT = 30;
const SEND = 46;
const ZOOM = 1.9;
/** Where the first letter lands in the close-up, as a fraction of the frame. */
const FOCUS = { x: 0.2, y: 0.4 };

const EASE = Easing.bezier(0.2, 0.6, 0.35, 1);
const CLAMP = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

/** Frame each character of `prompt` lands on, relative to TYPE_AT. A space costs a beat. */
function keystrokes(prompt: string) {
  const at: number[] = [];
  let f = 0;
  for (const ch of prompt) {
    at.push(f);
    f += ch === " " ? 2 : 1;
  }
  return { at, total: f };
}

export const DEFAULT_PROMPT = "Build me a marketing site";

/** Natural length for a given prompt. */
export function clickTypeFrames(prompt: string = DEFAULT_PROMPT): number {
  return TYPE_AT + keystrokes(prompt).total + HOLD;
}

const PLUS = "M12 7v10M7 12h10";
const MIC =
  "M12 4.5a2.5 2.5 0 0 0-2.5 2.5v4.5a2.5 2.5 0 0 0 5 0V7A2.5 2.5 0 0 0 12 4.5zM7 11a5 5 0 0 0 10 0M12 16v3";
const SPARK = "M12 4v4M12 16v4M4 12h4M16 12h4M6.5 6.5l2.5 2.5M15 15l2.5 2.5";
const ARROW = "M12 19V5M5.5 11.5 12 5l6.5 6.5";

export function ClickType({
  placeholder = "Describe what you want to build...",
  prompt = DEFAULT_PROMPT,
  hint = "New suggestion",
  accentColor,
  theme,
  mode,
  speed = 1,
  className,
}: ClickTypeProps) {
  const frame = useCurrentFrame() * speed;
  const { width, height } = useVideoConfig();
  const t = useSnapCnTheme(theme, mode);
  const ui = inputStyleContext(t);
  const s = height / 720;
  const accent = accentColor ?? t.primary;

  // Prompt Send's paint, token for token.
  const glassy = withAlpha(t.card, 0.52);
  const surface = withAlpha(t.card, 0.94);
  const hairline = mixOklch(ui.idleBorder, t.background, 0.1);
  const sendIdle = mixOklch(t.foreground, t.card, 0.55);

  const close = frame >= CUT_AT;
  const panelX = (width - PANEL_W * s) / 2;
  const panelY = (height - PANEL_H * s) / 2;
  const fieldX = panelX + PAD * s;
  const fieldY = panelY + PAD * s;
  const fieldW = (PANEL_W - PAD * 2) * s;
  const fieldH = (PANEL_H - PAD * 2) * s;
  const textX = fieldX + PAD_X * s;
  const textY = fieldY + PAD_Y * s;

  // Placeholder writes itself at ~1.5 chars a frame from frame 4.
  const shown = Math.max(0, Math.floor((frame - 4) * 1.5));
  const typed = keystrokes(prompt).at.filter(
    (a) => frame >= TYPE_AT + a,
  ).length;
  const armed = close && typed > 0;
  const enter = interpolate(frame, [0, 12], [0, 1], { ...CLAMP, easing: EASE });

  const path = [
    { at: 6, x: -0.04, y: 0.62, duration: 4 },
    {
      at: 10,
      x: (textX + 8 * s) / width,
      y: (textY + TEXT * 0.9 * s) / height,
      duration: CLICK_AT - 10,
      click: true,
    },
  ];

  // The close-up: one constant camera, the first letter pinned to FOCUS.
  const camera = close
    ? `translate(${FOCUS.x * width - textX * ZOOM}px, ${FOCUS.y * height - textY * ZOOM}px) scale(${ZOOM})`
    : "none";

  const glyph = (d: string, color: string, size: number, stroke = 1.8) => (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      style={{ display: "block" }}
    >
      <title>Icon</title>
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
  const iconButton = (d: string) => (
    <div
      style={{
        width: SEND * s,
        height: SEND * s,
        boxSizing: "border-box",
        borderRadius: 999,
        border: `1px solid ${hairline}`,
        background: t.card,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {glyph(d, ui.mutedForeground, 22 * s)}
    </div>
  );

  const scene = (
    <AbsoluteFill
      className={className}
      style={{
        background: t.background,
        fontFamily: SANS,
        textRendering: "geometricPrecision",
        overflow: "hidden",
      }}
    >
      <AbsoluteFill style={{ transformOrigin: "0 0", transform: camera }}>
        {/* Prompt Send's wash: a cool field falling from the top right, a
            bright patch left of centre, a pale corner under it — alpha over
            the page, never a hue mix through green. Oversized so the close-up
            never finds its edge. */}
        <div
          style={{
            position: "absolute",
            left: -0.2 * width,
            top: -0.2 * height,
            width: 1.4 * width,
            height: 1.4 * height,
            background: t.background,
            backgroundImage: [
              `radial-gradient(${0.96 * width}px ${0.8 * height}px at ${0.26 * width}px ${1.18 * height}px, ${withAlpha(t.background, 0.9)} 0%, transparent 62%)`,
              `radial-gradient(${0.74 * width}px ${0.62 * height}px at ${0.3 * width}px ${0.66 * height}px, ${withAlpha(t.card, 0.42)} 0%, transparent 66%)`,
              `linear-gradient(215deg, ${withAlpha(accent, 0.5)} 0%, ${withAlpha(accent, 0.28)} 52%, ${withAlpha(accent, 0.14)} 100%)`,
            ].join(","),
          }}
        />
        <AbsoluteFill
          style={{
            opacity: close ? 1 : enter,
            transform: close
              ? undefined
              : `translateY(${(1 - enter) * 14 * s}px)`,
          }}
        >
          {/* The glass panel. Hairline as an inset shadow, not a border. */}
          <div
            style={{
              position: "absolute",
              left: panelX,
              top: panelY,
              width: PANEL_W * s,
              height: PANEL_H * s,
              borderRadius: RADIUS * s,
              background: glassy,
              boxShadow: `inset 0 0 0 1px ${withAlpha(t.card, 0.6)}, 0 ${12 * s}px ${32 * s}px ${withAlpha(t.foreground, 0.05)}`,
            }}
          />
          {/* The writing surface. */}
          <div
            style={{
              position: "absolute",
              left: fieldX,
              top: fieldY,
              width: fieldW,
              height: fieldH,
              borderRadius: (RADIUS - 2) * s,
              background: surface,
              boxShadow: `0 ${6 * s}px ${18 * s}px ${withAlpha(t.foreground, 0.05)}`,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: textX,
              top: textY,
              right: width - (fieldX + fieldW) + PAD_X * s,
              fontSize: TEXT * s,
              lineHeight: 1.2,
              fontWeight: 400,
              letterSpacing: "-0.01em",
              whiteSpace: "nowrap",
              display: "flex",
              alignItems: "center",
            }}
          >
            {close ? (
              <>
                <span style={{ color: t.foreground }}>
                  {prompt.slice(0, typed)}
                </span>
                <Caret
                  color={t.foreground}
                  width={Math.max(1.5, 2.4 * s)}
                  height={TEXT * 1.15 * s}
                  // Solid while it types, blinking once it waits.
                  blink={typed === 0 || typed === prompt.length}
                  blinkPerSecond={1.6}
                  marginLeft={2 * s}
                />
              </>
            ) : (
              <span style={{ color: ui.mutedForeground }}>
                {placeholder.slice(0, shown)}
              </span>
            )}
          </div>
          <div
            style={{
              position: "absolute",
              left: textX,
              right: width - (fieldX + fieldW) + 18 * s,
              top: fieldY + fieldH - (SEND + 18) * s,
              height: SEND * s,
              display: "flex",
              alignItems: "center",
              gap: 10 * s,
              fontSize: 19 * s,
              fontWeight: 500,
              color: ui.mutedForeground,
            }}
          >
            {glyph(SPARK, ui.mutedForeground, 18 * s, 2)}
            <span style={{ flex: 1 }}>{hint}</span>
            {iconButton(PLUS)}
            {iconButton(MIC)}
            <div
              style={{
                width: SEND * s,
                height: SEND * s,
                borderRadius: 999,
                background: armed ? t.foreground : sendIdle,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {glyph(ARROW, t.card, SEND * 0.52 * s, 2.2)}
            </div>
          </div>
        </AbsoluteFill>
      </AbsoluteFill>
    </AbsoluteFill>
  );

  // The cursor belongs to the wide shot; the cut leaves it behind.
  return close ? (
    scene
  ) : (
    <CursorTrack path={path} theme={theme} mode={mode} speed={speed}>
      {scene}
    </CursorTrack>
  );
}
