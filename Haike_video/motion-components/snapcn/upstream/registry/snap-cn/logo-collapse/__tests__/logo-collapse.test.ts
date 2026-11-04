import { describe, expect, it } from "vitest";
import {
  DOT_AT,
  DOT_IN,
  DOT_OUT,
  DOTS,
  LAND,
  MARK,
  STEP_AT,
  TILE_FRAMES,
  WORD_AT,
} from "../index";

/**
 * The scene is a schedule, and a schedule can be wrong without looking wrong.
 *
 * Two beats out of order is the whole difference between a stack resolving into
 * a logo and a logo appearing next to a card that has not left yet — and in
 * review both are just numbers in a list.
 */
describe("logo-collapse", () => {
  it("lands the mark before it steps aside, and steps before the word", () => {
    expect(TILE_FRAMES).toBeLessThan(STEP_AT);
    expect(STEP_AT).toBeLessThan(WORD_AT);
    expect(WORD_AT).toBeLessThan(DOT_AT[0] ?? 0);
    expect(DOT_AT[0]).toBeLessThan(DOT_AT[1] ?? 0);
  });

  it("overshoots on the way in and settles, never the other way", () => {
    expect(LAND[0]).toBeGreaterThan(MARK);
    for (let i = 1; i < LAND.length; i++) {
      expect(LAND[i]).toBeLessThanOrEqual(LAND[i - 1] ?? 0);
    }
    expect(LAND[LAND.length - 1]).toBeGreaterThanOrEqual(MARK);
  });

  it("pings each bracket in and settles it smaller", () => {
    expect(DOT_OUT).toBeLessThan(DOT_IN);
    expect(DOTS).toHaveLength(DOT_AT.length);
    // They bracket the lockup: one above its centre line, one below.
    const [a, b] = DOTS;
    expect(a?.[1]).toBeLessThan(b?.[1] ?? 0);
  });
});
