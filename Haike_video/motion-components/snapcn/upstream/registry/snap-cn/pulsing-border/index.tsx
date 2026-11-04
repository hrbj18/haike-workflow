"use client";

import {
  PulsingBorder as PaperPulsingBorder,
  type PulsingBorderProps as PaperPulsingBorderProps,
} from "@paper-design/shaders-react";
import { useCallback, useState } from "react";
import {
  continueRender,
  delayRender,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  mixOklch,
  parseColor,
  type SnapCnTheme,
  toCss,
  useSnapCnTheme,
} from "@/lib/snap-cn-ui";

export interface PulsingBorderProps
  extends Omit<PaperPulsingBorderProps, "frame" | "ref"> {
  /** First glow color. Defaults to the design system's `primary`. */
  glowColorA?: string;
  /** Second glow color. Defaults to `primary` lifted toward the page. */
  glowColorB?: string;
  /** Design-system token overrides. */
  theme?: Partial<SnapCnTheme>;
  mode?: "light" | "dark";
}

/**
 * "AI is working" frame — a soft glowing border that pulses around the
 * edges of the scene while a response streams. Transparent by default so
 * it layers over any content (e.g. a chat UI mid-response).
 *
 * Deterministic: the shader's clock is driven from `useCurrentFrame()`
 * via the `frame` prop, so renders are frame-exact.
 */
export function PulsingBorder({
  speed = 0.6,
  colorBack = "#00000000",
  colors,
  glowColorA,
  glowColorB,
  roundness = 0.08,
  thickness = 0.06,
  intensity = 0.15,
  bloom = 0.2,
  className,
  theme,
  mode,
  ...rest
}: PulsingBorderProps) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = useSnapCnTheme(theme, mode);

  // The shader parses colors in WebGL, not in CSS — it has no `oklch()`. Tokens
  // are handed over as concrete rgb, which `toCss`/`mixOklch` already emit.
  const glowA = glowColorA ?? toCss(parseColor(t.primary));
  const glowB = glowColorB ?? mixOklch(t.primary, t.background, 0.35);

  const [handle] = useState(() => delayRender("pulsing-border"));
  const gate = useCallback(
    (element: HTMLDivElement | null) => {
      if (!element) return;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => continueRender(handle)),
      );
    },
    [handle],
  );

  return (
    <div
      ref={gate}
      className={className}
      style={{ position: "absolute", inset: 0 }}
    >
      <PaperPulsingBorder
        speed={0}
        frame={(frame / fps) * speed * 1000}
        colorBack={colorBack}
        colors={colors ?? [glowA, glowB]}
        roundness={roundness}
        thickness={thickness}
        intensity={intensity}
        bloom={bloom}
        fit="cover"
        width={width}
        height={height}
        {...rest}
      />
    </div>
  );
}
