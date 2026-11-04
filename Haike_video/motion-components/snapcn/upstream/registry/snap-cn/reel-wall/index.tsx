"use client";

import type { CSSProperties } from "react";
import {
  Easing,
  Freeze,
  getRemotionEnvironment,
  interpolate,
  OffthreadVideo,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/**
 * A "reel wall": a curved wall of vertical clips turns past in the dark. It
 * eases in from rest, then keeps turning at an even speed for as long as the
 * composition runs.
 *
 * Replicated from a 24fps reference, fitted on its own frames. The wall is a
 * CSS 3D ring: every card is a plane `RING_R` in front of the ring's axis,
 * viewed through a `perspective` of `PERSPECTIVE` (median edge error 0.64px
 * against the recording). Lengths are reference pixels (`REF_W` wide) and scale
 * with the frame; the timeline is in 24fps frames.
 *
 * The wall moves "on twos": it holds every picture for two frames, like the
 * reference, which is part of its look. The opening fade runs on every frame.
 *
 * Like `announce-title` it paints a cinematic world rather than a surface — a
 * dark stage under clips — so it takes no `theme`/`mode`; its colours are props.
 */

export interface ReelWallProps {
  /**
   * Clips for the wall, left to right; they repeat around the ring. Video URLs
   * play muted. Absolute URLs or paths under `public/`.
   */
  videos?: string[];
  /** The page behind the wall. */
  background?: string;
  /** A card before its clip has a frame to show. */
  cardColor?: string;
  speed?: number;
  className?: string;
}

/** Creator-style clips, 12s each, compressed. Absolute, because a root-relative
 *  default becomes `staticFile()` in a render and 404s in the project this file
 *  was just copied into. Ceiling: a clip shorter than the composition stops on
 *  its last frame — pass clips at least as long as the scene runs. */
const DEFAULT_VIDEOS = [1, 2, 3, 4, 5, 6].map(
  (n) => `https://media.snapcn.dev/demos/stock/wall-${n}.mp4`,
);

// ─── Geometry, in reference pixels ────────────────────────────────────────────
export const REF_W = 716;
const REF_H = 398;
/** The card, its ring and the lens. */
export const CARD = { w: 201.92, h: 349.09 } as const;
export const RING_R = 1837.36;
export const PERSPECTIVE = 446.54;
/** Angle between neighbouring cards, radians. */
export const PITCH = 0.1328;
/** Perspective origin, from the top-left of the frame. */
export const ORIGIN = { x: 356.76, y: 197.99 } as const;

// ─── Timeline (24fps frames) ──────────────────────────────────────────────────
/** Where the fitted ease hands over to an even turn, in 12fps steps. */
const CRUISE_AT = 52;
/** The ease-in, radians over 12fps steps: a cubic-bezier fitted to 53 measured
 *  steps (0.31px RMS). Valid up to `CRUISE_AT`; past it the bezier overshoots. */
const easeIn = (step: number) =>
  interpolate(step, [0, 67.8], [-0.0497, -0.2656], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.344, 0.0049, 0.7833, 1.3384),
  });
/** Turn per step once cruising: the ease's own speed where it hands over. */
const CRUISE = easeIn(CRUISE_AT) - easeIn(CRUISE_AT - 1);

/** The wall's turn at a 12fps step: the fitted ease-in, then an even turn. */
export const wallTurn = (step: number) =>
  step <= CRUISE_AT
    ? easeIn(step)
    : easeIn(CRUISE_AT) + (step - CRUISE_AT) * CRUISE;

/** The opening fade-in: a black veil that clears in 9 frames. */
export const veil = (f: number) =>
  f >= 9 ? 0 : 0.142 * (1 - Math.max(f, 0) / 9) ** 3.7;

/** Hold every picture for two frames: 0, 1, 1, 3, 3, 5, … */
const onTwos = (f: number) => (f < 1 ? 0 : Math.floor((f - 1) / 2) * 2 + 1);

function resolveSrc(src: string): string {
  const isLocal = src.startsWith("/") && !src.startsWith("//");
  if (!isLocal || getRemotionEnvironment().isPlayer) return src;
  // A value that already came out of staticFile() carries the static base.
  const base = staticFile("_").slice(0, -2);
  if (base && src.startsWith(`${base}/`)) return src;
  try {
    return staticFile(src.replace(/^\/+/, ""));
  } catch {
    return src;
  }
}

const cover: CSSProperties = {
  width: "100%",
  height: "100%",
  // Preflight's `img { max-width: 100% }` collapses a box sized by its parent.
  maxWidth: "none",
  objectFit: "cover",
  display: "block",
};

export function ReelWall({
  videos = DEFAULT_VIDEOS,
  background = "#0e0e0e",
  cardColor = "#1a1a1a",
  speed = 1,
  className,
}: ReelWallProps) {
  const { width, height, fps } = useVideoConfig();
  const frame = useCurrentFrame() * ((speed * 24) / fps);
  const u = width / REF_W;
  // The reference frame is a hair wider than 16:9; centre it vertically.
  const dy = (height - REF_H * u) / 2;

  const held = onTwos(Math.floor(frame));
  const theta = wallTurn((held + 1) / 2);
  // Only the cards within reach of the lens; the rest are behind the frame.
  const first = Math.floor((-theta - 0.6) / PITCH);
  const n = videos.length;

  return (
    <div
      className={className}
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        backgroundColor: background,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: dy,
          width,
          height: REF_H * u,
          perspective: PERSPECTIVE * u,
          perspectiveOrigin: `${ORIGIN.x * u}px ${ORIGIN.y * u}px`,
        }}
      >
        {/* The page: lit from the middle, falling to black at the sides. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse 60% 75% at 50% 50%, rgba(0,0,0,0) 0%, rgba(0,0,0,0.45) 70%, rgba(0,0,0,0.92) 100%)",
          }}
        />
        {Array.from({ length: 10 }, (_, i) => first + i).map((k) => {
          const src = n ? videos[((k % n) + n) % n] : undefined;
          return (
            <div
              key={k}
              style={{
                position: "absolute",
                left: (ORIGIN.x - CARD.w / 2) * u,
                top: (ORIGIN.y - CARD.h / 2) * u,
                width: CARD.w * u,
                height: CARD.h * u,
                overflow: "hidden",
                backgroundColor: cardColor,
                transform: `translateZ(${-RING_R * u}px) rotateY(${theta + k * PITCH}rad) translateZ(${RING_R * u}px)`,
              }}
            >
              {src && (
                // The clips hold on twos with the wall.
                <Freeze frame={held}>
                  <OffthreadVideo src={resolveSrc(src)} muted style={cover} />
                </Freeze>
              )}
            </div>
          );
        })}
      </div>

      {veil(frame) > 0 && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "#000",
            opacity: veil(frame),
          }}
        />
      )}
    </div>
  );
}
