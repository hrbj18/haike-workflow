import { describe, expect, it } from "vitest";
import { FADE, PITCH, ROLL, read, SPIN } from "../index";

/**
 * Two things here can be wrong without looking wrong in review.
 *
 * The first is `read`'s second direction. It walks one table both ways — travel
 * from a second, and the second a share of the travel is reached — and the
 * inverse is what decides when a row takes the slot. Get it wrong by a frame and
 * every word in the reel swaps a frame early, which reads as the whole scene
 * being mistimed rather than as one function being wrong.
 *
 * The second is the reel's arithmetic. `SPIN` rows at `PITCH` each has to land
 * the strip on a whole row, or the scene stops between two words forever.
 */
describe("word-wheel", () => {
  it("comes to rest on a whole row", () => {
    expect((SPIN * PITCH) % PITCH).toBe(0);
    expect(ROLL[ROLL.length - 1]?.[1]).toBe(1);
    expect(ROLL[0]?.[1]).toBeLessThan(0.001);
  });

  it("rolls forwards only, and arrives", () => {
    for (let i = 1; i < ROLL.length; i++) {
      const prev = ROLL[i - 1];
      const here = ROLL[i];
      if (!prev || !here) throw new Error("table hole");
      expect(here[0]).toBeGreaterThan(prev[0]);
      // Strictly rising: a repeated value is a frozen frame in the middle of a
      // roll, and it is exactly what the capture's duplicate samples would have
      // put here if they had not been dropped.
      expect(here[1]).toBeGreaterThan(prev[1]);
    }
  });

  it("reads the roll both ways, to the same point", () => {
    for (const t of [0.2, 0.5, 0.9, 1.4, 1.8]) {
      const p = read(ROLL, t);
      expect(read(ROLL, p, 1)).toBeCloseTo(t, 4);
    }
  });

  it("holds before the roll and after it", () => {
    expect(read(ROLL, 0)).toBeLessThan(0.001);
    expect(read(ROLL, 5)).toBe(1);
  });

  it("fades away from the slot and never quite to nothing", () => {
    expect(read(FADE, 0)).toBe(1);
    for (let i = 1; i < FADE.length; i++) {
      const prev = FADE[i - 1];
      const here = FADE[i];
      if (!prev || !here) throw new Error("table hole");
      expect(here[1]).toBeLessThan(prev[1]);
    }
    // The column is cut off by the frame, not by the fade. A fade that reached
    // zero inside the frame would leave a blank band above the top row.
    expect(read(FADE, 0.5)).toBeGreaterThan(0.15);
  });
});
