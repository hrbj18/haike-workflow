import { describe, expect, it } from "vitest";
import {
  chipAt,
  fitScale,
  settle,
  statusAt,
  toList,
} from "@/registry/snap-cn/status-cycle";

const SCHEDULE = { introFrames: 24, statusHold: 18, count: 4 };

describe("statusAt", () => {
  it("holds the first label through the whole intro", () => {
    for (let frame = 0; frame < 24; frame += 1) {
      expect(statusAt({ frame, ...SCHEDULE }).index).toBe(0);
    }
  });

  it("swaps on the frame the hold expires, not the one after", () => {
    expect(statusAt({ frame: 23, ...SCHEDULE }).index).toBe(0);
    expect(statusAt({ frame: 24, ...SCHEDULE }).index).toBe(1);
    expect(statusAt({ frame: 42, ...SCHEDULE }).index).toBe(2);
    expect(statusAt({ frame: 60, ...SCHEDULE }).index).toBe(3);
  });

  it("stops at the last label instead of running off the end", () => {
    expect(statusAt({ frame: 10_000, ...SCHEDULE }).index).toBe(3);
  });

  it("restarts `since` at each swap, so a settling morph does not compound", () => {
    expect(statusAt({ frame: 24, ...SCHEDULE }).since).toBe(0);
    expect(statusAt({ frame: 41, ...SCHEDULE }).since).toBe(17);
    expect(statusAt({ frame: 42, ...SCHEDULE }).since).toBe(0);
  });

  it("never advances backwards as the frame advances", () => {
    let last = -1;
    for (let frame = -30; frame < 200; frame += 1) {
      const { index } = statusAt({ frame, ...SCHEDULE });
      expect(index).toBeGreaterThanOrEqual(last);
      last = index;
    }
  });

  it("survives an empty status list", () => {
    expect(statusAt({ frame: 99, ...SCHEDULE, count: 0 })).toEqual({
      index: 0,
      since: 0,
    });
  });
});

describe("chipAt", () => {
  const BEAT = { beat: 82, stagger: 8, count: 5 };

  it("has nothing on screen before the beat", () => {
    expect(chipAt({ frame: 81, ...BEAT }).arrived).toBe(0);
  });

  it("brings the first chip in on the beat itself", () => {
    expect(chipAt({ frame: 82, ...BEAT })).toEqual({ arrived: 1, since: 0 });
  });

  it("adds one chip per stagger", () => {
    expect(chipAt({ frame: 90, ...BEAT }).arrived).toBe(2);
    expect(chipAt({ frame: 98, ...BEAT }).arrived).toBe(3);
    expect(chipAt({ frame: 114, ...BEAT }).arrived).toBe(5);
  });

  it("stops stepping once the last chip is in", () => {
    // Without the clamp the field keeps scrolling and the column leaves the top
    // of the frame, which looks like the scene lost its content.
    const late = chipAt({ frame: 10_000, ...BEAT });
    expect(late.arrived).toBe(5);
  });
});

describe("settle", () => {
  const TAU = 1.8;

  it("starts at zero and never moves before its beat", () => {
    expect(settle(0, TAU)).toBe(0);
    expect(settle(-5, TAU)).toBe(0);
  });

  it("never overshoots — the reference's step peaks at exactly 1.000", () => {
    for (let f = 0; f < 200; f += 0.25) {
      expect(settle(f, TAU)).toBeLessThanOrEqual(1);
    }
  });

  it("is monotone, so the field cannot back up mid-step", () => {
    let last = -1;
    for (let f = 0; f < 60; f += 0.5) {
      const v = settle(f, TAU);
      expect(v).toBeGreaterThanOrEqual(last);
      last = v;
    }
  });

  it("reaches 63% of travel at one time constant", () => {
    expect(settle(TAU, TAU)).toBeCloseTo(0.632, 3);
  });

  it("moves more than half a pixel every frame of a 200px step", () => {
    // A frame that moves under half a pixel rasterises identically to the last
    // one, and a run of them is a visible freeze rather than a settle.
    const D = 200;
    for (let f = 0; f < 8; f += 1) {
      const step = D * (settle(f + 1, TAU) - settle(f, TAU));
      expect(step).toBeGreaterThan(0.5);
    }
  });
});

describe("fitScale", () => {
  it("leaves content that already fits alone", () => {
    expect(fitScale(500, 1000)).toBe(1);
    expect(fitScale(1000, 1000)).toBe(1);
  });

  it("shrinks exactly enough to fit, and never enlarges", () => {
    expect(fitScale(2000, 1000)).toBe(0.5);
    expect(fitScale(1200, 1000) * 1200).toBeCloseTo(1000, 6);
  });

  it("is a no-op before the measurement exists", () => {
    expect(fitScale(0, 1000)).toBe(1);
    expect(fitScale(500, 0)).toBe(1);
    expect(fitScale(Number.NaN, 1000)).toBe(1);
  });
});

describe("toList", () => {
  it("takes an array unchanged", () => {
    expect(toList(["a", "b"])).toEqual(["a", "b"]);
  });

  it("splits and trims the comma-separated string the customizer passes", () => {
    expect(toList("a,  b ,c")).toEqual(["a", "b", "c"]);
  });

  it("drops empties rather than rendering a blank pill", () => {
    expect(toList("a,,b, ,")).toEqual(["a", "b"]);
    expect(toList(undefined)).toEqual([]);
    expect(toList("")).toEqual([]);
  });
});
