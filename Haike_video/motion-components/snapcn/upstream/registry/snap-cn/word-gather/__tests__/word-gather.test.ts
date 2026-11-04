import { describe, expect, it } from "vitest";
import {
  BEAT,
  BEATS,
  CAP,
  CENTRE_Y,
  DROP,
  END,
  FIRST_AT,
  LEAD_X,
  LEAD_Y,
  LINE_CX,
  LINE_H,
  measureWords,
  ORDER,
  orderAt,
  SCALE,
  SCATTER,
  SETTLE,
  STAGGER,
  solve,
  TRAVEL,
  track,
} from "../index";

/**
 * Two things here can be wrong without looking wrong in review: the clock, and
 * the order. A table keyed in frames where the rest are keyed in beats slides a
 * word a third of a second out of step with the one beside it; an order that
 * repeats an index drops a word off the stage entirely and leaves a gap in the
 * sentence nobody can explain. So most of these are checks that the two agree
 * with each other, plus the layout arithmetic, which is the only real
 * computation in the file.
 */

const frames = (a: number, b: number) =>
  Array.from({ length: b - a + 1 }, (_, i) => a + i);

describe("the recording's clock", () => {
  it("runs from the first frame to the last beat, and never backwards", () => {
    expect(BEAT[0]).toEqual([0, 0]);
    expect(BEAT[BEAT.length - 1]).toEqual([END - 1, BEATS]);
    let last = -1;
    for (const [frame, beat] of BEAT) {
      expect(beat).toBeGreaterThan(last);
      expect(frame).toBeGreaterThanOrEqual(beat);
      last = beat;
    }
  });

  /** 39 beats over 48 frames is 24 to the second against 30 — that is the ratio. */
  it("is slower than the composition, by about a quarter", () => {
    expect(BEATS / (END - 1)).toBeGreaterThan(0.78);
    expect(BEATS / (END - 1)).toBeLessThan(0.83);
  });

  it("is monotone read through `track` as well as read raw", () => {
    let last = -1;
    for (const f of frames(0, END)) {
      const b = track(BEAT, f);
      expect(b).toBeGreaterThanOrEqual(last - 1e-9);
      last = b;
    }
    expect(track(BEAT, END + 20)).toBe(BEATS);
  });
});

describe("the order the words drop in", () => {
  it("is a permutation — every word after the lead, exactly once", () => {
    const seen = new Set<number>();
    for (let k = 0; k < ORDER.length; k++) seen.add(orderAt(k, ORDER.length));
    expect([...seen].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5]);
  });

  it("stays a permutation for a sentence shorter or longer than the reference's", () => {
    for (const n of [1, 2, 3, 4, 5, 6, 7, 9, 12]) {
      const seen = new Set<number>();
      for (let k = 0; k < n; k++) seen.add(orderAt(k, n));
      expect(seen.size).toBe(n);
      for (const i of seen) {
        expect(i).toBeGreaterThanOrEqual(1);
        expect(i).toBeLessThanOrEqual(n);
      }
    }
  });

  /** The lead word is never one of them; it is already on the card. */
  it("never drops the lead word in twice", () => {
    for (let k = 0; k < 12; k++) expect(orderAt(k, 5)).not.toBe(0);
  });

  it("never reads the sentence out in order", () => {
    expect(ORDER[0]).not.toBe(1);
  });
});

describe("the clock the words drop on", () => {
  it("gets every word down before the recording ends", () => {
    const lastAt = FIRST_AT + STAGGER * (ORDER.length - 1);
    expect(lastAt + SETTLE).toBeLessThan(BEATS);
  });

  it("leaves the lead word alone on the card until then", () => {
    expect(FIRST_AT).toBeGreaterThan(LEAD_Y[LEAD_Y.length - 1]?.[0] ?? 0);
  });

  it("has each word still travelling while it is still in the accent", () => {
    expect(track(TRAVEL, SETTLE)).toBeLessThan(1);
    expect(track(TRAVEL, SETTLE)).toBeGreaterThan(0.6);
  });
});

describe("the travel", () => {
  it("starts where it dropped and gets all the way home", () => {
    expect(track(TRAVEL, 0)).toBe(0);
    expect(track(TRAVEL, -5)).toBe(0);
    expect(track(TRAVEL, 14)).toBe(1);
    expect(track(TRAVEL, 500)).toBe(1);
  });

  /** An exponential settle: never faster later than it was earlier. */
  it("only ever slows down", () => {
    let prev = Number.POSITIVE_INFINITY;
    for (const b of frames(0, 13)) {
      const step = track(TRAVEL, b + 1) - track(TRAVEL, b);
      expect(step).toBeGreaterThanOrEqual(-1e-9);
      expect(step).toBeLessThanOrEqual(prev + 1e-9);
      prev = step;
    }
  });

  it("is more than a third of the way home on its first beat", () => {
    expect(track(TRAVEL, 1)).toBeGreaterThan(0.35);
  });
});

describe("the lead word", () => {
  /**
   * The two moves are the point: the drop onto the line is over in six beats
   * and the slide along it takes twenty-one. Collapse them into one curve and
   * the word arrives at its line and then keeps sinking, which is the one thing
   * the reference never does.
   */
  it("drops onto its line long before it finishes sliding along it", () => {
    const yDone = LEAD_Y[LEAD_Y.length - 1]?.[0] ?? 0;
    const xDone = LEAD_X[LEAD_X.length - 1]?.[0] ?? 0;
    expect(yDone).toBeLessThan(xDone - 10);
    expect(track(LEAD_X, yDone)).toBeLessThan(0.15);
  });

  it("eases in and out of the slide, not out of it", () => {
    const at = (b: number) => track(LEAD_X, b);
    expect(at(12) - at(11)).toBeLessThan(0.02);
    expect(at(19) - at(18)).toBeGreaterThan(0.2);
    expect(at(29) - at(28)).toBeLessThan(0.02);
  });

  it("only ever moves toward its slot", () => {
    for (const table of [LEAD_X, LEAD_Y]) {
      let last = -1;
      for (const b of frames(0, BEATS)) {
        const v = track(table, b);
        expect(v).toBeGreaterThanOrEqual(last - 1e-9);
        last = v;
      }
      expect(track(table, BEATS)).toBe(1);
    }
  });
});

describe("the block's scale", () => {
  it("holds big, then only ever shrinks, and lands on 1", () => {
    expect(track(SCALE, 0)).toBeGreaterThan(1.25);
    expect(track(SCALE, 18)).toBe(track(SCALE, 0));
    let last = Number.POSITIVE_INFINITY;
    for (const b of frames(0, BEATS)) {
      const v = track(SCALE, b);
      expect(v).toBeLessThanOrEqual(last + 1e-9);
      last = v;
    }
    expect(track(SCALE, BEATS)).toBe(1);
  });

  /** It waits for the words. Shrink while they are still arriving and they land in the wrong place. */
  it("does not start shrinking until the first word has dropped", () => {
    expect(track(SCALE, FIRST_AT - 2)).toBe(track(SCALE, 0));
  });
});

describe("the scatter", () => {
  it("has one offset for every word the reference drops", () => {
    expect(SCATTER).toHaveLength(ORDER.length);
  });

  it("throws them far enough to read as scattered, and not off the card", () => {
    for (const [dx, dy] of SCATTER) {
      expect(Math.hypot(dx, dy)).toBeGreaterThan(25);
      expect(Math.abs(dx)).toBeLessThan(200);
      expect(Math.abs(dy)).toBeLessThan(120);
    }
  });

  it("sends some of them sideways and some of them past their line", () => {
    expect(
      SCATTER.filter(([, dy]) => Math.abs(dy) > 20).length,
    ).toBeGreaterThan(1);
    expect(SCATTER.filter(([, dy]) => Math.abs(dy) < 5).length).toBeGreaterThan(
      1,
    );
  });
});

describe("the layout", () => {
  const widths = [88, 89, 113, 85, 104, 73];

  it("wraps greedily and centres every line it makes", () => {
    const slots = solve(widths, 10, 330);
    const line1 = slots.filter((s) => s.baseline === slots[0]?.baseline);
    expect(line1).toHaveLength(3);
    const left = slots[0]?.x ?? 0;
    const right = (slots[2]?.x ?? 0) + 113;
    expect((left + right) / 2).toBeCloseTo(LINE_CX, 6);
  });

  it("puts the lines a line-height apart, in order", () => {
    const slots = solve(widths, 10, 330);
    expect((slots[3]?.baseline ?? 0) - (slots[0]?.baseline ?? 0)).toBeCloseTo(
      LINE_H,
      6,
    );
    for (let i = 1; i < slots.length; i++) {
      expect(slots[i]?.baseline ?? 0).toBeGreaterThanOrEqual(
        slots[i - 1]?.baseline ?? 0,
      );
    }
  });

  it("centres the block on the card, a measured hair low", () => {
    const two = solve(widths, 10, 330);
    const mid = ((two[0]?.baseline ?? 0) + (two[3]?.baseline ?? 0)) / 2;
    expect(mid).toBeCloseTo(CENTRE_Y + CAP / 2 + DROP, 6);
  });

  it("never breaks a line it does not have to", () => {
    const one = solve(widths, 10, 10_000);
    for (const s of one) expect(s.baseline).toBe(one[0]?.baseline);
  });

  it("gives a word wider than the measure a line of its own rather than nothing", () => {
    const slots = solve([500, 40], 10, 100);
    expect(slots).toHaveLength(2);
    expect(slots[1]?.baseline ?? 0).toBeGreaterThan(slots[0]?.baseline ?? 0);
  });
});

describe("measuring", () => {
  /** Without a document there is still a layout; it is just an estimate of one. */
  it("falls back to an estimate that is proportional to the copy", () => {
    const { widths, space } = measureWords(
      ["a", "abcd"],
      40,
      500,
      "sans-serif",
    );
    expect((widths[1] ?? 0) / (widths[0] ?? 1)).toBeCloseTo(4, 6);
    expect(space).toBeGreaterThan(0);
  });
});

describe("track", () => {
  it("clamps at both ends and interpolates between", () => {
    const t = [
      [0, 10],
      [10, 20],
    ] as const;
    expect(track(t, -5)).toBe(10);
    expect(track(t, 5)).toBe(15);
    expect(track(t, 50)).toBe(20);
  });
});
