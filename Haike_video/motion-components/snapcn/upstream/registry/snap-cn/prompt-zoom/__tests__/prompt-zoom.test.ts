/**
 * Unit tests for the pure helpers in registry/snap-cn/prompt-zoom/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/prompt-zoom/__tests__/prompt-zoom.test.ts
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 * All tests are fully deterministic (no network, no Date.now).
 */

import { describe, expect, it } from "vitest";

import { caretOn, isZoomed, typedCount } from "../index";

describe("isZoomed — the cut", () => {
  const cutF = 1.0 * 30; // 30 frames

  it("is a step, never a ramp", () => {
    // Measured on the reference: the wide view is whole on one frame and fully
    // pushed in on the next, 803ms → 824ms, nothing between. There must be no
    // frame at which this is partially true.
    for (let f = 0; f <= 60; f++) {
      expect(typeof isZoomed(f, cutF)).toBe("boolean");
    }
    expect(isZoomed(29, cutF)).toBe(false);
    expect(isZoomed(30, cutF)).toBe(true);
  });

  it("never goes back", () => {
    let seen = false;
    for (let f = 0; f <= 90; f++) {
      const z = isZoomed(f, cutF);
      if (seen) expect(z).toBe(true);
      if (z) seen = true;
    }
  });
});

describe("typedCount", () => {
  const perFrame = 18 / 30; // 18 chars/sec at 30fps
  const total = 26;
  const c = (fc: number) => typedCount(fc, 27, perFrame, total);

  it("types nothing before its cue", () => {
    expect(c(0)).toBe(0);
    expect(c(27)).toBe(0);
  });

  it("advances at the measured rate", () => {
    // ~0.6 chars per frame, so the first character lands within two frames.
    expect(c(29)).toBe(1);
    expect(c(27 + 10 / perFrame)).toBe(10);
  });

  it("clamps at the end of the string and is monotonic", () => {
    let prev = -1;
    for (let f = 0; f <= 200; f++) {
      const v = c(f);
      expect(v).toBeGreaterThanOrEqual(prev);
      expect(v).toBeLessThanOrEqual(total);
      prev = v;
    }
    expect(c(400)).toBe(total);
  });

  it("shows everything at once when the rate is zero", () => {
    expect(typedCount(28, 27, 0, total)).toBe(total);
  });
});

describe("caretOn", () => {
  it("is solid whenever a character is landing", () => {
    for (let f = 0; f < 60; f++) expect(caretOn(f, 30, true)).toBe(true);
  });

  it("blinks on a ~1.06s cycle when idle", () => {
    const half = 0.53 * 30; // 15.9 frames
    expect(caretOn(0, 30, false)).toBe(true);
    expect(caretOn(half + 1, 30, false)).toBe(false);
    expect(caretOn(2 * half + 1, 30, false)).toBe(true);
  });
});

describe("the cut lands mid-sentence", () => {
  // The order is the point: typing starts, runs, and the cut fires while it is
  // still going. One continuous action across the cut is what stops it reading
  // as a scene change.
  const fps = 30;
  const typeStartF = 0.35 * fps;
  const cutF = 1.0 * fps;
  const perFrame = 18 / fps;
  const total = "Get me a plan for tomorrow".length;

  it("has typing already running when the cut fires", () => {
    const atCut = typedCount(cutF, typeStartF, perFrame, total);
    expect(atCut).toBeGreaterThan(0);
    expect(atCut).toBeLessThan(total);
  });

  it("keeps typing after the cut", () => {
    const atCut = typedCount(cutF, typeStartF, perFrame, total);
    const later = typedCount(cutF + 10, typeStartF, perFrame, total);
    expect(later).toBeGreaterThan(atCut);
  });

  it("starts typing before it cuts", () => {
    expect(typeStartF).toBeLessThan(cutF);
    expect(typedCount(cutF - 1, typeStartF, perFrame, total)).toBeGreaterThan(
      0,
    );
  });
});
