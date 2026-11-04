import { describe, expect, it } from "vitest";

import {
  BASELINE_IN_BOX,
  baselineFor,
  CLOSE,
  CUT,
  closeOffset,
  closeScale,
  DOT,
  drift,
  FOCUS,
  inkRatio,
  rise,
  sizeFor,
  WIDE,
  warmth,
} from "../index";

/** The reference is 30fps and every measurement in the component is in seconds. */
const at = (f: number) => f / 30;

describe("the wide shot", () => {
  it("reproduces the measured rise", () => {
    // Read off the top row of ink: 274 down to 224, and nothing after.
    for (const [t, v] of [
      [0, 50],
      [0.158, 20],
      [0.325, 10],
      [0.625, 2],
      [0.792, 0],
    ] as const) {
      expect(rise(t), `t=${t}`).toBeCloseTo(v, 0);
    }
  });

  it("only ever rises, and stops", () => {
    for (let f = 1; f <= 36; f++) {
      expect(rise(at(f)), `frame ${f}`).toBeLessThanOrEqual(rise(at(f - 1)));
    }
    expect(rise(1)).toBe(0);
  });

  it("holds still before it drifts", () => {
    // The vertical settles at 0.79 and the horizontal does not start until
    // 0.66 — there is a beat where the shot is doing nothing at all, and it is
    // what makes the drift afterwards read as the camera and not as the type.
    expect(drift(0.6)).toBeCloseTo(0, 6);
    expect(rise(0.825)).toBe(0);
  });

  it("is still accelerating left when the cut takes it", () => {
    const v = (t: number) => drift(t) - drift(t - 1 / 30);
    expect(v(CUT)).toBeLessThan(v(CUT - 0.2));
    expect(v(CUT - 0.2)).toBeLessThan(v(CUT - 0.4));
    // 21px by the last frame the recording caught, 27 by the cut.
    expect(drift(1.158)).toBeCloseTo(-21, 0);
  });
});

describe("the cool-down", () => {
  it("holds, then goes to ink linearly", () => {
    expect(warmth(0)).toBeCloseTo(0.455, 3);
    expect(warmth(0.3)).toBeCloseTo(0.455, 2);
    // Straight enough that the midpoint of the fall is the mean of its ends.
    const a = warmth(0.458);
    const b = warmth(1.017);
    expect(warmth((0.458 + 1.017) / 2)).toBeCloseTo((a + b) / 2, 1);
    expect(warmth(1.03)).toBe(0);
  });

  it("never warms back up", () => {
    for (let f = 1; f <= 36; f++) {
      expect(warmth(at(f)), `frame ${f}`).toBeLessThanOrEqual(
        warmth(at(f - 1)),
      );
    }
  });
});

describe("the close shot", () => {
  it("is nothing at all until the cut", () => {
    expect(closeScale(CUT - 0.01)).toBeCloseTo(closeScale(0), 4);
  });

  it("lands, holds, and then pushes", () => {
    // Settled by 1.45, still at 1.63, and 1.30 by the last frame.
    expect(closeScale(1.45)).toBeCloseTo(1, 2);
    expect(closeScale(1.63)).toBeLessThan(1.01);
    expect(closeScale(2.2)).toBeCloseTo(1.297, 2);
  });

  it("is still accelerating on the last frame", () => {
    const v = (t: number) => closeScale(t) - closeScale(t - 1 / 30);
    expect(v(2.2)).toBeGreaterThan(v(2.0));
    expect(v(2.0)).toBeGreaterThan(v(1.8));
  });

  it("overshoots vertically and not horizontally", () => {
    // Two different settles on one object. Averaging them out is what stops a
    // landing reading as a landing.
    const ys: number[] = [];
    for (let f = 36; f <= 50; f++) ys.push(closeOffset(at(f)).y);
    expect(Math.min(...ys)).toBeLessThan(-4);
    expect(closeOffset(1.6).y).toBeGreaterThan(Math.min(...ys) + 3);
    const xs: number[] = [];
    for (let f = 36; f <= 50; f++) xs.push(closeOffset(at(f)).x);
    // The horizontal only ever comes down.
    for (let i = 1; i < xs.length; i++) {
      expect(xs[i] ?? 0).toBeLessThanOrEqual((xs[i - 1] ?? 0) + 0.01);
    }
  });
});

describe("framing", () => {
  it("gives the reference's own word the reference's own numbers", () => {
    expect(inkRatio("Product.")).toBe(0.75);
    expect(sizeFor("wide")).toBe(245);
    expect(sizeFor("close")).toBe(419);
    // 224 + 0.75 × 245, and the dot's centre plus its own radius.
    expect(baselineFor("wide", "Product.")).toBeCloseTo(408, 0);
    expect(baselineFor("close", "Product.")).toBeCloseTo(308, 0);
  });

  it("drops a word with no ascenders to where the ink goes, not the em", () => {
    // "snapcn" reaches 0.556em, "Product" 0.75. At one fixed baseline the first
    // would sit 48px lower in the frame and read like a caption.
    expect(inkRatio("snapcn")).toBe(0.556);
    const lowercase = baselineFor("wide", "snapcn");
    expect(WIDE.inkTop + inkRatio("snapcn") * WIDE.size).toBeCloseTo(
      lowercase,
      3,
    );
    expect(baselineFor("wide", "Product.") - lowercase).toBeGreaterThan(40);
  });

  it("puts the dot on the baseline, wherever the baseline is", () => {
    for (const w of ["snapcn.", "Product.", "Acme."]) {
      const r = (DOT.size * CLOSE.size) / 2;
      expect(baselineFor("close", w) - r).toBeCloseTo(CLOSE.dot.y, 3);
    }
  });

  it("keeps the baseline inside the line box where CSS puts it", () => {
    // Inter's ascent and descent are 0.9688 and 0.2422; half-leading at
    // line-height 1 is −0.1055em, which lands the baseline at 0.8633em.
    expect(BASELINE_IN_BOX).toBeCloseTo(0.9688 - (1.211 - 1) / 2, 3);
  });
});

describe("the lens", () => {
  it("is sharp where the reference is sharp and soft where it is soft", () => {
    // Measured 10–90 edge widths against distance from the middle of the frame:
    // 1px at 92, 3px at 165, 7px at 192, 15px at 205, 16px at 310.
    expect(FOCUS.inner).toBeGreaterThan(165);
    expect(FOCUS.outer).toBeLessThan(215.001);
    expect(FOCUS.outer).toBeGreaterThan(FOCUS.inner);
    // σ 6 is a 10–90 width of about 15px, which is what the far edges measure.
    expect(FOCUS.sigma * 2.56).toBeGreaterThan(14);
    expect(FOCUS.sigma * 2.56).toBeLessThan(17);
  });
});
