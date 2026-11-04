/**
 * Unit tests for the pure helpers in registry/snap-cn/answer-stream/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/answer-stream/__tests__/answer-stream.test.ts
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 * All tests are fully deterministic (no network, no Date.now).
 */

import { describe, expect, it } from "vitest";

import { heat, shotBScale, wordBirth } from "../index";

// The measured defaults, at 30fps.
const PULL_F = 1.933 * 30;
const DUR_F = 1.1 * 30;
const FROM = 1.364;
const UNDER = 0.028;
const RECOVER = 26;
const cam = (f: number) => shotBScale(f, PULL_F, DUR_F, FROM, UNDER, RECOVER);

describe("shotBScale — the pull-back", () => {
  it("holds the cut's framing until the move starts", () => {
    for (let f = 0; f <= PULL_F; f++) expect(cam(f)).toBe(FROM);
  });

  it("lands on 1 — the framing every layout constant was measured at", () => {
    // If this drifts, nothing is where it was measured and the whole shot is
    // silently a few percent off. It has to be exact, not close.
    expect(cam(PULL_F + DUR_F + 3 + RECOVER)).toBeCloseTo(1, 10);
    expect(cam(500)).toBeCloseTo(1, 10);
  });

  it("bottoms out past its mark, then comes back", () => {
    const bottom = cam(PULL_F + DUR_F + 2);
    expect(bottom).toBeCloseTo(1 - UNDER, 6);
    expect(bottom).toBeLessThan(1);
    // …and every later frame is on the way back up, never below the bottom.
    for (let f = PULL_F + DUR_F; f <= 500; f++) {
      expect(cam(f)).toBeGreaterThanOrEqual(bottom - 1e-9);
    }
  });

  it("is bounded — the reason the recovery is not an open-ended creep", () => {
    // The drift on the reference never stops. Modelled that way it would keep
    // scaling up forever and walk the composer off the bottom of the frame in
    // any config longer than the reference. Nothing may ever exceed the settle.
    for (let f = 0; f <= 2000; f++) expect(cam(f)).toBeLessThanOrEqual(FROM);
    expect(cam(2000)).toBeCloseTo(1, 10);
  });

  it("pulls back monotonically, and peaks at the middle of the move", () => {
    const at = (u: number) => cam(PULL_F + u * DUR_F);
    for (let u = 0; u < 1; u += 0.02) {
      expect(at(u + 0.02)).toBeLessThanOrEqual(at(u) + 1e-9);
    }
    // Peak velocity dead centre is the measurement that rules out a spring,
    // which peaks at a third. Sample speed across the move and check the
    // fastest sample is the middle one.
    let fastest = 0;
    let fastestU = -1;
    for (let u = 0.05; u < 0.95; u += 0.05) {
      const v = Math.abs(at(u + 0.01) - at(u));
      if (v > fastest) {
        fastest = v;
        fastestU = u;
      }
    }
    expect(fastestU).toBeGreaterThan(0.4);
    expect(fastestU).toBeLessThan(0.6);
  });

  it("never stalls: no frame of the move is a repeat of the last", () => {
    // A sub-pixel frame rasterises identically and the camera visibly freezes.
    // Across a 498px-tall stage, 1e-4 of scale is well under half a pixel — the
    // check that matters is that the curve is never *flat* mid-move.
    for (let f = PULL_F + 1; f < PULL_F + DUR_F; f++) {
      expect(Math.abs(cam(f) - cam(f - 1))).toBeGreaterThan(1e-5);
    }
  });
});

describe("heat — hot on arrival, cooled on a fixed clock", () => {
  it("is 0 the frame a word lands and 1 once it has cooled", () => {
    expect(heat(100, 100, 7)).toBe(0);
    expect(heat(103.5, 100, 7)).toBeCloseTo(0.5, 6);
    expect(heat(107, 100, 7)).toBe(1);
    expect(heat(400, 100, 7)).toBe(1);
  });

  it("treats a word that has not landed as cold, not as hot", () => {
    // Clamped low, so an unborn word is never painted at full accent behind an
    // opacity of 0 — and a negative index into the colour ramp is impossible.
    expect(heat(90, 100, 7)).toBe(0);
  });

  it("degenerates to fully cooled when the cool-down is switched off", () => {
    expect(heat(100, 100, 0)).toBe(1);
    expect(heat(100, 100, -5)).toBe(1);
  });

  it("keeps a constant-width hot band whatever the stream rate is", () => {
    // words hot = rate × cool. The band is a property of the two clocks, not of
    // the text, which is what makes one `coolSeconds` right for the pill, the
    // paragraph and the cards at once.
    const coolF = 7;
    for (const wpf of [0.3, 0.83, 2]) {
      const now = 200;
      let hotCount = 0;
      for (let i = 0; i < 400; i++) {
        const born = wordBirth(i, 100, wpf);
        if (born <= now && heat(now, born, coolF) < 1) hotCount++;
      }
      // Within one word — where the grid of birth frames happens to fall
      // against `now` decides whether the band's trailing word has just gone
      // cold or not, and that is the only slack there is.
      expect(Math.abs(hotCount - wpf * coolF)).toBeLessThanOrEqual(1);
    }
  });
});

describe("wordBirth", () => {
  it("spaces words evenly from the stream's opening frame", () => {
    expect(wordBirth(0, 40, 0.5)).toBe(40);
    expect(wordBirth(4, 40, 0.5)).toBe(48);
  });

  it("lands every word at once when the rate is zero", () => {
    // A guard, not a feature: 0 words/second must not divide by zero and send
    // every birth frame to Infinity, which would render an empty answer.
    expect(wordBirth(9, 40, 0)).toBe(40);
    expect(Number.isFinite(wordBirth(9, 40, 0))).toBe(true);
  });

  it("is monotonic in the word index", () => {
    for (let i = 1; i < 100; i++) {
      expect(wordBirth(i, 40, 0.83)).toBeGreaterThan(
        wordBirth(i - 1, 40, 0.83),
      );
    }
  });
});
