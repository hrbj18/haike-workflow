/**
 * Unit tests for pure helpers in registry/snap-cn/follower-rush/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/follower-rush/__tests__/follower-rush.test.ts
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 * All tests are fully deterministic (no network, no Date.now).
 */

import { describe, expect, it } from "vitest";

import { clamp01, followerCount, smoothstep, waveScroll } from "../index";

describe("clamp01", () => {
  it("clamps to [0,1]", () => {
    expect(clamp01(-2)).toBe(0);
    expect(clamp01(0.4)).toBe(0.4);
    expect(clamp01(3)).toBe(1);
  });
});

describe("smoothstep", () => {
  it("is 0 at 0, 1 at 1, and eased in the middle", () => {
    expect(smoothstep(0)).toBe(0);
    expect(smoothstep(1)).toBe(1);
    expect(smoothstep(0.5)).toBeCloseTo(0.5, 6);
    expect(smoothstep(-5)).toBe(0);
    expect(smoothstep(9)).toBe(1);
  });
});

describe("followerCount", () => {
  // start=20, mid=150, end=214, midCount=22, target=5001 (5000 "others").
  const c = (fc: number) => followerCount(fc, 5001, 20, 150, 214, 22);

  it("holds at 1 through the inline intro", () => {
    expect(c(0)).toBe(1);
    expect(c(20)).toBe(1);
  });

  it("grows linearly to the full pile by the mid frame", () => {
    // half-way through the linear phase → about half of (midCount-1)+1
    expect(c(85)).toBe(Math.round(1 + 0.5 * 21)); // 12
    expect(c(150)).toBe(22);
  });

  it("explodes exponentially and lands exactly on the target", () => {
    const mid = c(180);
    expect(mid).toBeGreaterThan(22);
    expect(mid).toBeLessThan(5001);
    expect(c(214)).toBe(5001);
    expect(c(300)).toBe(5001); // clamped past the end
  });

  it("is monotonic across the whole timeline", () => {
    let prev = 0;
    for (let fc = 0; fc <= 220; fc += 2) {
      const v = c(fc);
      expect(v).toBeGreaterThanOrEqual(prev);
      prev = v;
    }
  });
});

describe("waveScroll", () => {
  // grow=150, explode=214 (T=64), v0=0.85, vMax=14 — the horizontal defaults.
  const s = (fc: number) => waveScroll(fc, 150, 214, 0.85, 14);
  /**
   * Central difference, in px/frame. The window has to be small: at ±0.5 it
   * straddles the ramp/hold join, so it reports a blend of two velocities and
   * nothing either side of the join can be asserted.
   */
  const H = 0.01;
  const v = (fc: number) => (s(fc + H) - s(fc - H)) / (2 * H);

  it("does not move before the pile is full", () => {
    expect(s(0)).toBe(0);
    expect(s(150)).toBe(0);
  });

  it("is monotonic across the whole timeline", () => {
    let prev = -1;
    for (let fc = 0; fc <= 300; fc += 2) {
      const d = s(fc);
      expect(d).toBeGreaterThanOrEqual(prev);
      prev = d;
    }
  });

  it("accelerates from v0 to vMax across the explosion, then holds", () => {
    expect(v(150 + H * 2)).toBeCloseTo(0.85, 2);
    expect(v(214 - H * 2)).toBeCloseTo(14, 2);
    expect(v(260)).toBeCloseTo(14, 6); // flat out
    // …and strictly increasing in between, not a step part-way.
    expect(v(170)).toBeGreaterThan(v(160));
    expect(v(200)).toBeGreaterThan(v(170));
  });

  it("has no velocity step at the hand-off", () => {
    // A jolt here is the one failure the eye cannot be talked out of.
    expect(Math.abs(v(214 - H * 2) - v(214 + H * 2))).toBeLessThan(0.01);
  });

  it("carries the crowd far enough to read as a rush", () => {
    // The bug this replaced: 0.85px/frame moved one ~54px slot over the
    // explosion while the counter ran to 5000.
    const waveP = (1280 - 74 * 2) / 21;
    expect((s(214) - s(150)) / waveP).toBeGreaterThan(6);
  });

  it("degenerates safely when the window has no length", () => {
    expect(waveScroll(160, 150, 150, 0.85, 14)).toBeCloseTo(140, 6);
  });
});
