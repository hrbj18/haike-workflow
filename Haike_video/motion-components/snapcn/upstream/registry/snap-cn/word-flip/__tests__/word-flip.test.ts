import { describe, expect, it } from "vitest";

import {
  charStartFrame,
  DEFAULT_MOTION,
  easeInBack,
  easeInBackSpeed,
  fitScales,
  flipStartFrame,
  framesPerChar,
  keystrokeOffset,
  typingEndFrame,
  wordAt,
} from "../index";

const CLOCK = { typeStart: 4, cps: 9, fps: 30, jitter: 0 };

describe("framesPerChar", () => {
  it("converts a characters-per-second rate to frames", () => {
    expect(framesPerChar(10, 30)).toBeCloseTo(3);
    expect(framesPerChar(9, 30)).toBeCloseTo(30 / 9);
  });
});

describe("keystrokeOffset", () => {
  it("is exactly zero when jitter is off, so the clock is a metronome", () => {
    for (let i = 0; i < 40; i++) expect(keystrokeOffset(i, 0)).toBe(0);
  });

  it("stays inside ±jitter of one keystroke", () => {
    for (let i = 0; i < 200; i++) {
      expect(Math.abs(keystrokeOffset(i, 0.2))).toBeLessThanOrEqual(0.2);
    }
  });

  it("is deterministic — a render and the Player must agree frame for frame", () => {
    expect(keystrokeOffset(7, 0.2)).toBe(keystrokeOffset(7, 0.2));
    expect(keystrokeOffset(7, 0.2)).not.toBe(keystrokeOffset(8, 0.2));
  });
});

describe("charStartFrame", () => {
  it("advances one keystroke at a time from typeStart", () => {
    expect(charStartFrame(0, CLOCK)).toBeCloseTo(4);
    expect(charStartFrame(1, CLOCK)).toBeCloseTo(4 + 30 / 9);
    expect(charStartFrame(9, CLOCK)).toBeCloseTo(4 + 9 * (30 / 9));
  });

  it("is monotonic even with jitter — keys never arrive out of order", () => {
    const jittered = { ...CLOCK, jitter: 0.25 };
    for (let i = 1; i < 60; i++) {
      expect(charStartFrame(i, jittered)).toBeGreaterThan(
        charStartFrame(i - 1, jittered),
      );
    }
  });
});

describe("typingEndFrame", () => {
  it("lands one full fade after the last keystroke", () => {
    const end = typingEndFrame({ ...CLOCK, charCount: 22, charFade: 6 });
    expect(end).toBeCloseTo(charStartFrame(21, CLOCK) + 6);
  });

  it("matches the reference: 22 characters at 9cps finish around frame 78", () => {
    const end = typingEndFrame({ ...CLOCK, charCount: 22, charFade: 6 });
    expect(end).toBeGreaterThan(74);
    expect(end).toBeLessThan(82);
  });
});

describe("flipStartFrame", () => {
  it("waits out the pause, then runs on the cycle", () => {
    const opts = { typingEnd: 80, pause: 6, cycle: 35 };
    expect(flipStartFrame(0, opts)).toBe(86);
    expect(flipStartFrame(1, opts)).toBe(121);
    expect(flipStartFrame(2, opts)).toBe(156);
  });
});

describe("wordAt", () => {
  const opts = {
    typingEnd: 80,
    pause: 6,
    cycle: 35,
    wordCount: 3,
    loop: true,
  };

  it("holds the first word before the first flip, with a negative local clock", () => {
    const { index, local } = wordAt(10, opts);
    expect(index).toBe(0);
    expect(local).toBeLessThan(0);
  });

  it("brings in word 0 on the first flip", () => {
    expect(wordAt(86, opts)).toEqual({ index: 0, local: 0 });
  });

  it("advances one word per cycle", () => {
    expect(wordAt(121, opts).index).toBe(1);
    expect(wordAt(156, opts).index).toBe(2);
  });

  it("wraps when looping", () => {
    expect(wordAt(191, opts).index).toBe(0);
    expect(wordAt(226, opts).index).toBe(1);
  });

  it("holds the last word when not looping", () => {
    const once = { ...opts, loop: false };
    expect(wordAt(191, once).index).toBe(2);
    expect(wordAt(400, once).index).toBe(2);
  });

  it("runs local from 0 up to the cycle length", () => {
    expect(wordAt(86 + 12, opts).local).toBe(12);
    expect(wordAt(86 + 34, opts).local).toBe(34);
    expect(wordAt(86 + 35, opts).local).toBe(0);
  });
});

describe("easeInBack", () => {
  it("starts at 0 and ends at 1", () => {
    expect(easeInBack(0)).toBeCloseTo(0);
    expect(easeInBack(1)).toBeCloseTo(1);
  });

  it("dips below zero — that backswing is the anticipation", () => {
    expect(easeInBack(0.2)).toBeLessThan(0);
    expect(easeInBack(0.42)).toBeLessThan(0);
  });

  it("bottoms out at p = -0.100 at t = 0.42, which is what the reference measured", () => {
    let minT = 0;
    let minP = 0;
    for (let i = 0; i <= 1000; i++) {
      const t = i / 1000;
      const p = easeInBack(t);
      if (p < minP) {
        minP = p;
        minT = t;
      }
    }
    expect(minT).toBeCloseTo(0.42, 2);
    expect(minP).toBeCloseTo(-0.1, 2);
  });

  it("gives a ~10px dip at a 72px font, which is the 8-12px the brief asks for", () => {
    const dip = Math.abs(-0.1 * DEFAULT_MOTION.exitY * 72);
    expect(dip).toBeGreaterThan(8);
    expect(dip).toBeLessThan(12);
  });
});

describe("easeInBackSpeed", () => {
  it("is zero at the turnaround — the frame the word has stopped must be sharp", () => {
    expect(easeInBackSpeed(0.42)).toBeLessThan(0.02);
  });

  it("peaks at 1 when the word is flying", () => {
    expect(easeInBackSpeed(1)).toBeCloseTo(1);
  });

  it("never blurs the word while it is standing still", () => {
    expect(easeInBackSpeed(0)).toBeCloseTo(0);
  });

  it("blurs the throw far more than the backswing", () => {
    expect(easeInBackSpeed(0.89)).toBeGreaterThan(5 * easeInBackSpeed(0.2));
  });
});

describe("fitScales", () => {
  it("leaves the widest word alone and scales the rest up to meet it", () => {
    expect(fitScales([100, 50, 80])).toEqual([1, 2, 1.25]);
  });

  it("makes every word render at exactly the same width — the slot cannot reflow", () => {
    const widths = [529, 563, 571];
    const scaled = fitScales(widths).map((s, i) => s * widths[i]);
    for (const w of scaled) expect(w).toBeCloseTo(571);
  });

  it("survives a zero width instead of dividing by it", () => {
    expect(fitScales([0, 40])).toEqual([1, 1]);
  });
});
