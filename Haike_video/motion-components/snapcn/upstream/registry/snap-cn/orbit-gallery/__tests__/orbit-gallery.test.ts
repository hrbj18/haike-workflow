/**
 * Unit tests for pure helpers in registry/snap-cn/orbit-gallery/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/orbit-gallery
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 */

import { describe, expect, it } from "vitest";

import {
  archimedeanPoint,
  arcToN,
  buildArcTable,
  ringRadius,
  sizeScale,
} from "../index";

describe("archimedeanPoint", () => {
  it("puts n=0 at the outer radius and n=1 at the center", () => {
    const outer = archimedeanPoint(0, 400, 3.5);
    expect(Math.hypot(outer.x, outer.y)).toBeCloseTo(400, 6);
    const center = archimedeanPoint(1, 400, 3.5);
    expect(Math.hypot(center.x, center.y)).toBeCloseTo(0, 6);
  });

  it("keeps EQUAL radial gaps between successive coils (Archimedean)", () => {
    const turns = 3.5;
    const R = 400;
    const radAt = (n: number) => {
      const p = archimedeanPoint(n, R, turns);
      return Math.hypot(p.x, p.y);
    };
    // one full coil is Δn = 1/turns; the radial drop is R/turns everywhere
    const expected = R / turns;
    for (let n = 0; n + 1 / turns <= 1; n += 0.1) {
      const gap = radAt(n) - radAt(n + 1 / turns);
      expect(gap).toBeCloseTo(expected, 4);
    }
  });
});

describe("buildArcTable + arcToN", () => {
  const nForArc = buildArcTable(3.5);

  it("spans the whole path from outer to center", () => {
    expect(arcToN(0, nForArc)).toBeCloseTo(0, 3);
    expect(arcToN(1, nForArc)).toBeCloseTo(1, 3);
  });

  it("is monotonic in arc fraction", () => {
    let prev = -1;
    for (let s = 0; s <= 1; s += 0.02) {
      const n = arcToN(s, nForArc);
      expect(n).toBeGreaterThanOrEqual(prev);
      prev = n;
    }
  });

  it("spaces cards evenly by ARC LENGTH, not by parameter", () => {
    const turns = 3.5;
    const R = 400;
    const arcLen = (nA: number, nB: number) => {
      const STEPS = 600;
      let len = 0;
      let p = archimedeanPoint(nA, R, turns);
      for (let k = 1; k <= STEPS; k++) {
        const q = archimedeanPoint(nA + ((nB - nA) * k) / STEPS, R, turns);
        len += Math.hypot(q.x - p.x, q.y - p.y);
        p = q;
      }
      return len;
    };
    // Ten equal arc steps should have near-equal true arc length.
    const ns = Array.from({ length: 11 }, (_, i) => arcToN(i / 10, nForArc));
    const lens = [];
    for (let i = 0; i < 10; i++) lens.push(arcLen(ns[i], ns[i + 1]));
    const mean = lens.reduce((a, b) => a + b, 0) / lens.length;
    for (const l of lens) expect(Math.abs(l - mean) / mean).toBeLessThan(0.02);
  });
});

describe("ringRadius", () => {
  it("matches the reference formula and grows with spread", () => {
    expect(ringRadius(600, 6)).toBeCloseTo(0.48 * 600 * 1.9, 6);
    expect(ringRadius(600, 1)).toBeCloseTo(0.48 * 600, 6);
    expect(ringRadius(600, 8)).toBeGreaterThan(ringRadius(600, 4));
  });

  it("pushes the outer edge off-frame at the default spread", () => {
    // spread 6 → R ≈ 0.91·min > half the frame, so outer cards overflow
    expect(ringRadius(600, 6)).toBeGreaterThan(0.5 * 600);
  });
});

describe("sizeScale", () => {
  it("is 1 at the outer radius and 0 at the center", () => {
    expect(sizeScale(400, 400, 2)).toBeCloseTo(1, 6);
    expect(sizeScale(0, 400, 2)).toBeCloseTo(0, 6);
  });

  it("shrinks monotonically toward the center", () => {
    let prev = Number.POSITIVE_INFINITY;
    for (let d = 400; d >= 0; d -= 20) {
      const s = sizeScale(d, 400, 2);
      expect(s).toBeLessThanOrEqual(prev);
      prev = s;
    }
  });

  it("is linear in distance at sizeAttenuation=2", () => {
    expect(sizeScale(200, 400, 2)).toBeCloseTo(0.5, 6);
  });

  it("is uniform when sizeAttenuation=0", () => {
    expect(sizeScale(100, 400, 0)).toBe(1);
    expect(sizeScale(400, 400, 0)).toBe(1);
  });
});
