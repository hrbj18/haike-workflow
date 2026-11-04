import { describe, expect, it } from "vitest";

import { centeredPositions, measureWordSizes } from "../index";

describe("measureWordSizes", () => {
  it("uses one fontSize-tall row per word on the y axis", () => {
    expect(
      measureWordSizes(["Ship.", "Test.", "Deploy."], "y", 72, 600),
    ).toEqual([72, 72, 72]);
  });

  it("falls back to length * fontSize * 0.55 on the x axis without a DOM", () => {
    // vitest runs in a node environment, so the SSR fallback path is taken.
    expect(measureWordSizes(["Ship.", "Go"], "x", 72, 600)).toEqual([
      5 * 72 * 0.55,
      2 * 72 * 0.55,
    ]);
  });

  it("scales the fallback with font size", () => {
    const small = measureWordSizes(["Acme"], "x", 36, 600)[0];
    const large = measureWordSizes(["Acme"], "x", 72, 600)[0];
    expect(large).toBeCloseTo(small * 2);
  });
});

describe("centeredPositions", () => {
  it("returns one layout per intermediate word count", () => {
    const layouts = centeredPositions([100, 60, 80], 10);
    expect(layouts).toHaveLength(3);
    expect(layouts[0]).toHaveLength(1);
    expect(layouts[1]).toHaveLength(2);
    expect(layouts[2]).toHaveLength(3);
  });

  it("centers a single word at 0", () => {
    expect(centeredPositions([120], 10)[0][0]).toBe(0);
  });

  it("keeps every layout centered around 0", () => {
    const sizes = [100, 60, 80, 40];
    const gap = 10;
    const layouts = centeredPositions(sizes, gap);
    for (let k = 1; k <= sizes.length; k++) {
      const centers = layouts[k - 1];
      const left = centers[0] - sizes[0] / 2;
      const right = centers[k - 1] + sizes[k - 1] / 2;
      expect(left).toBeCloseTo(-right);
    }
  });

  it("separates adjacent items by exactly the gap", () => {
    const sizes = [100, 60, 80];
    const gap = 12;
    const centers = centeredPositions(sizes, gap)[2];
    for (let j = 1; j < sizes.length; j++) {
      const prevRight = centers[j - 1] + sizes[j - 1] / 2;
      const currLeft = centers[j] - sizes[j] / 2;
      expect(currLeft - prevRight).toBeCloseTo(gap);
    }
  });

  it("matches the legacy y-axis row math for uniform sizes", () => {
    // short-slide-down: start = -total/2 + rowHeight/2; step = rowHeight + gap
    const rowHeight = 72;
    const gap = 12;
    const n = 3;
    const layouts = centeredPositions(
      Array.from({ length: n }, () => rowHeight),
      gap,
    );
    for (let k = 1; k <= n; k++) {
      const total = rowHeight * k + gap * (k - 1);
      const start = -total / 2 + rowHeight / 2;
      for (let j = 0; j < k; j++) {
        expect(layouts[k - 1][j]).toBeCloseTo(start + j * (rowHeight + gap));
      }
    }
  });

  it("only shifts earlier words when a new one lands (monotone push left)", () => {
    const layouts = centeredPositions([100, 60, 80], 10);
    // Each existing word's center moves left (negative) as words are added.
    expect(layouts[1][0]).toBeLessThan(layouts[0][0]);
    expect(layouts[2][0]).toBeLessThan(layouts[1][0]);
    expect(layouts[2][1]).toBeLessThan(layouts[1][1]);
  });
});
