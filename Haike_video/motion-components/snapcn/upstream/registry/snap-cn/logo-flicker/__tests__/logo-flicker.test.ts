/**
 * Unit tests for the pure timeline helpers in logo-flicker/index.tsx.
 *
 * Run: pnpm vitest run registry/snap-cn/logo-flicker
 */

import { describe, expect, it } from "vitest";

import {
  FADE_END,
  FADE_START,
  FLIP_INTERVAL,
  flickerImage,
  flickerOpacity,
  revealOpacity,
  revealScale,
} from "../index";

describe("flickerImage", () => {
  it("holds each image for exactly `interval` frames — a constant speed", () => {
    // Same image within an interval, a new one at the next interval boundary.
    expect(flickerImage(0, 8, 2)).toBe(flickerImage(1, 8, 2));
    expect(flickerImage(2, 8, 2)).not.toBe(flickerImage(0, 8, 2));
  });

  it("keeps the SAME flip speed at the very end as at the start", () => {
    // Distinct images two frames apart both early and just before the fade ends.
    expect(flickerImage(0, 8, 2)).not.toBe(flickerImage(2, 8, 2));
    expect(flickerImage(FADE_END - 2, 8, 2)).not.toBe(
      flickerImage(FADE_END, 8, 2),
    );
  });

  it("only ever returns a valid image index", () => {
    for (let f = 0; f <= FADE_END; f++) {
      const idx = flickerImage(f, 8, FLIP_INTERVAL);
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(8);
    }
  });
});

describe("cross-fade (fade + reveal simultaneous)", () => {
  it("the flicker fades OUT and the lockup fades IN on the exact same window", () => {
    expect(flickerOpacity(FADE_START)).toBe(1);
    expect(revealOpacity(FADE_START)).toBe(0);
    expect(flickerOpacity(FADE_END)).toBe(0);
    expect(revealOpacity(FADE_END)).toBe(1);
  });

  it("their opacities are exact complements at every frame — one move, not two", () => {
    for (let f = FADE_START; f <= FADE_END; f++) {
      expect(flickerOpacity(f) + revealOpacity(f)).toBeCloseTo(1, 5);
    }
  });

  it("settles the lockup scale to 1 by the end", () => {
    expect(revealScale(FADE_START)).toBeLessThan(1);
    expect(revealScale(FADE_END)).toBeCloseTo(1, 5);
  });
});
