/**
 * Unit tests for pure helpers in registry/snap-cn/search-typing/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/search-typing
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 * (The clip/measure path is DOM-bound and is verified in the browser instead.)
 */

import { describe, expect, it } from "vitest";

import {
  buildTypingSchedule,
  cameraPan,
  cameraPush,
  cameraRetreat,
  caretOpacity,
  pageTriggerIndex,
  searchTypingDuration,
  type TypingScheduleOptions,
  typedCount,
} from "../index";

const SENTENCE = "How do I make my product demo actually look expensive?";

const base: TypingScheduleOptions = {
  fps: 60,
  charsPerSecond: 14,
  humanize: 0,
  wordPause: 1,
  punctuationPause: 1,
  seed: "search-typing",
};

describe("buildTypingSchedule", () => {
  it("starts at an empty field and has one entry per character", () => {
    const schedule = buildTypingSchedule(SENTENCE, base);
    expect(schedule).toHaveLength(SENTENCE.length + 1);
    expect(schedule[0]).toBe(0);
  });

  it("is strictly monotonic, so a character can never un-appear on a scrub", () => {
    const schedule = buildTypingSchedule(SENTENCE, { ...base, humanize: 1 });
    for (let i = 1; i < schedule.length; i++) {
      expect(schedule[i]).toBeGreaterThan(schedule[i - 1]);
    }
  });

  it("types at the requested rate when nothing is pausing or jittering", () => {
    const schedule = buildTypingSchedule("abcdefghij", base);
    // 14 cps at 60fps = one character every 30/7 frames.
    expect(schedule[10]).toBeCloseTo((10 / 14) * 60, 6);
  });

  it("is deterministic for the same seed and non-deterministic across seeds", () => {
    const opts = { ...base, humanize: 0.8 };
    const a = buildTypingSchedule(SENTENCE, opts);
    const b = buildTypingSchedule(SENTENCE, opts);
    const c = buildTypingSchedule(SENTENCE, { ...opts, seed: "other" });
    expect(a).toEqual(b);
    expect(a).not.toEqual(c);
  });

  it("rests after a word instead of before typing the space", () => {
    // The gap before "b" (index 2) is the one that follows the space.
    const schedule = buildTypingSchedule("a b", { ...base, wordPause: 3 });
    const spaceGap = schedule[2] - schedule[1];
    const afterSpaceGap = schedule[3] - schedule[2];
    expect(spaceGap).toBeCloseTo(60 / 14, 6);
    expect(afterSpaceGap).toBeCloseTo((60 / 14) * 3, 6);
  });

  it("rests longer after punctuation", () => {
    const schedule = buildTypingSchedule("a.b", {
      ...base,
      punctuationPause: 4,
    });
    expect(schedule[3] - schedule[2]).toBeCloseTo((60 / 14) * 4, 6);
  });

  it("keeps humanize centred on the requested rate", () => {
    const plain = buildTypingSchedule(SENTENCE, base);
    const jittered = buildTypingSchedule(SENTENCE, { ...base, humanize: 1 });
    const drift =
      Math.abs(jittered[jittered.length - 1] - plain[plain.length - 1]) /
      plain[plain.length - 1];
    // Jitter is symmetric, so it perturbs individual keystrokes without
    // meaningfully dragging the sentence off its overall speed.
    expect(drift).toBeLessThan(0.1);
  });
});

describe("typedCount", () => {
  const schedule = buildTypingSchedule(SENTENCE, base);

  it("shows an empty field before and at frame 0", () => {
    expect(typedCount(-20, schedule)).toBe(0);
    expect(typedCount(0, schedule)).toBe(0);
  });

  it("reveals exactly one character per scheduled boundary", () => {
    expect(typedCount(schedule[1], schedule)).toBe(1);
    expect(typedCount(schedule[1] - 0.001, schedule)).toBe(0);
    expect(typedCount(schedule[7], schedule)).toBe(7);
  });

  it("never runs past the end of the sentence", () => {
    const last = schedule[schedule.length - 1];
    expect(typedCount(last, schedule)).toBe(SENTENCE.length);
    expect(typedCount(last + 10_000, schedule)).toBe(SENTENCE.length);
  });

  it("is monotonic across every frame of the clip", () => {
    let prev = 0;
    for (let f = 0; f <= 400; f++) {
      const n = typedCount(f, schedule);
      expect(n).toBeGreaterThanOrEqual(prev);
      prev = n;
    }
  });
});

describe("caretOpacity", () => {
  const opts = { fps: 60, blinksPerSecond: 1 };

  it("is fully on at the top of the cycle and fully off at the half", () => {
    expect(caretOpacity(0, opts)).toBe(1);
    expect(caretOpacity(35, opts)).toBe(0);
  });

  it("repeats every period", () => {
    for (let f = 0; f < 60; f++) {
      expect(caretOpacity(f, opts)).toBeCloseTo(caretOpacity(f + 60, opts), 9);
    }
  });

  it("stays within [0, 1] everywhere", () => {
    for (let f = 0; f < 240; f++) {
      const o = caretOpacity(f, opts);
      expect(o).toBeGreaterThanOrEqual(0);
      expect(o).toBeLessThanOrEqual(1);
    }
  });

  it("eases the edges instead of snapping between on and off", () => {
    // Somewhere on the falling edge the caret must be genuinely mid-fade,
    // otherwise it is a square wave wearing a soft-blink costume.
    const samples = Array.from({ length: 60 }, (_, f) => caretOpacity(f, opts));
    expect(samples.some((o) => o > 0.05 && o < 0.95)).toBe(true);
  });

  it("degenerates to a hard square wave at softness 0", () => {
    expect(caretOpacity(29, { ...opts, softness: 0 })).toBe(1);
    expect(caretOpacity(30, { ...opts, softness: 0 })).toBe(0);
  });

  it("holds solid when blinking is switched off", () => {
    expect(caretOpacity(17, { fps: 60, blinksPerSecond: 0 })).toBe(1);
  });
});

describe("cameraPush / cameraRetreat", () => {
  // 60fps: lead-in 0.5s, the field comes forward over 0.8s while typing runs to
  // f250, then a hold, then it retreats.
  const marks = {
    typingStart: 30,
    dollyEnd: 78,
    panStart: 140,
    panEnd: 170,
    holdEnd: 304,
    recedeEnd: 370,
  };

  it("is parked back for the whole lead-in", () => {
    expect(cameraPush(0, marks)).toBe(0);
    expect(cameraPush(29, marks)).toBe(0);
  });

  it("reaches the front on the dolly and then HOLDS there", () => {
    expect(cameraPush(marks.dollyEnd, marks)).toBeCloseTo(1, 6);
    expect(cameraPush(200, marks)).toBeCloseTo(1, 6);
    // The push must not come back down — the retreat is a separate move to a
    // separate depth, and folding them together is what stopped the field ever
    // pulling back far enough to be seen whole.
    expect(cameraPush(marks.recedeEnd, marks)).toBeCloseTo(1, 6);
  });

  it("pushes forward monotonically", () => {
    let prev = -1;
    for (let f = marks.typingStart; f <= marks.dollyEnd; f++) {
      const d = cameraPush(f, marks);
      expect(d).toBeGreaterThanOrEqual(prev - 1e-9);
      prev = d;
    }
  });

  it("does not retreat until the hold is over", () => {
    expect(cameraRetreat(0, marks)).toBe(0);
    expect(cameraRetreat(marks.holdEnd, marks)).toBeCloseTo(0, 6);
  });

  it("retreats all the way, and stays there", () => {
    expect(cameraRetreat(marks.recedeEnd, marks)).toBeCloseTo(1, 6);
    expect(cameraRetreat(marks.recedeEnd + 60, marks)).toBeCloseTo(1, 6);
  });

  it("retreats monotonically", () => {
    let prev = -1;
    for (let f = marks.holdEnd; f <= marks.recedeEnd; f++) {
      const d = cameraRetreat(f, marks);
      expect(d).toBeGreaterThanOrEqual(prev - 1e-9);
      prev = d;
    }
  });

  it("both stay inside [0, 1] across the whole clip", () => {
    for (let f = -30; f < 430; f++) {
      for (const v of [cameraPush(f, marks), cameraRetreat(f, marks)]) {
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(1);
      }
    }
  });

  it("never retreats when the retreat is switched off", () => {
    const noRecede = { ...marks, recedeEnd: marks.holdEnd };
    for (let f = 0; f < 400; f += 10) {
      expect(cameraRetreat(f, noRecede)).toBe(0);
    }
  });

  it("lands the WHOLE field in frame at the end", () => {
    // The end depth is defined as "the field is exactly as wide as the page", so
    // at full retreat the field must fit — that is the payoff shot.
    const pageWidth = 1200;
    const fieldWidth = 2650;
    const frontScale = 0.81;
    const restScale = frontScale / 1.25;
    const endScale = pageWidth / fieldWidth;

    const scaleAt = (f: number) => {
      const forward =
        restScale + (frontScale - restScale) * cameraPush(f, marks);
      return forward + (endScale - forward) * cameraRetreat(f, marks);
    };

    const onScreen = (f: number) => fieldWidth * scaleAt(f);
    expect(onScreen(marks.holdEnd)).toBeGreaterThan(pageWidth); // wider than the shot
    expect(onScreen(marks.recedeEnd)).toBeCloseTo(pageWidth, 6); // exactly fits
  });
});

describe("cameraPan", () => {
  const marks = {
    typingStart: 30,
    dollyEnd: 78,
    panStart: 140,
    panEnd: 170,
    holdEnd: 304,
    recedeEnd: 358,
  };

  it("shows the left half until the caret runs out of frame", () => {
    expect(cameraPan(0, marks)).toBe(0);
    expect(cameraPan(139, marks)).toBeCloseTo(0, 6);
  });

  it("lands on the right half and stays there", () => {
    expect(cameraPan(marks.panEnd, marks)).toBeCloseTo(1, 6);
    expect(cameraPan(300, marks)).toBeCloseTo(1, 6);
    // It must NOT pan back during the retreat — the field pulls back around its
    // right cap, it does not re-cross to the left half.
    expect(cameraPan(marks.recedeEnd, marks)).toBeCloseTo(1, 6);
  });

  it("moves monotonically, in one direction only", () => {
    let prev = -1;
    for (let f = marks.panStart; f <= marks.panEnd; f++) {
      const p = cameraPan(f, marks);
      expect(p).toBeGreaterThanOrEqual(prev - 1e-9);
      prev = p;
    }
  });

  it("never pans at all when the sentence fits in the first half", () => {
    const noPan = { ...marks, panStart: null };
    for (let f = 0; f < 400; f += 10) expect(cameraPan(f, noPan)).toBe(0);
  });
});

describe("pageTriggerIndex", () => {
  // Field height 240 → text starts 1.024 × 240 = 245.8px into the field.
  const textLeft = 245.8;

  it("fires on the character whose caret would leave the frame", () => {
    // advances every 100px; at scale 1 with a 1200px page, the caret leaves the
    // frame once textLeft + advance > 1200 → advance > 954.2 → the 10th (1000px).
    const advances = Array.from({ length: 21 }, (_, i) => i * 100);
    expect(pageTriggerIndex(advances, textLeft, 1, 1200)).toBe(10);
  });

  it("returns null when the whole sentence fits in the first half", () => {
    const advances = [0, 100, 200, 300];
    expect(pageTriggerIndex(advances, textLeft, 1, 1200)).toBeNull();
  });

  it("fires earlier when the field is scaled up", () => {
    const advances = Array.from({ length: 21 }, (_, i) => i * 100);
    const a = pageTriggerIndex(advances, textLeft, 1, 1200);
    const b = pageTriggerIndex(advances, textLeft, 1.5, 1200);
    expect(b).toBeLessThan(a as number);
  });
});

describe("searchTypingDuration", () => {
  it("covers the lead-in, the typing, the hold and the retreat", () => {
    const duration = searchTypingDuration(SENTENCE, {
      ...base,
      startDelay: 0.5,
      holdAfter: 0.9,
      recedeDuration: 1.2,
    });
    const typing = buildTypingSchedule(SENTENCE, base).at(-1) ?? 0;
    expect(duration).toBe(Math.ceil(0.5 * 60 + typing + 0.9 * 60 + 1.2 * 60));
  });

  it("leaves the configured duration long enough for the default clip", () => {
    const duration = searchTypingDuration(SENTENCE, {
      ...base,
      charsPerSecond: 14,
      humanize: 0.35,
      wordPause: 1.55,
      punctuationPause: 2.2,
      startDelay: 0.5,
      holdAfter: 0.9,
      recedeDuration: 1.2,
    });
    // config.ts ships durationInFrames: 420 — the clip must fit inside it, or
    // the render cuts the field off mid-retreat.
    expect(duration).toBeLessThanOrEqual(420);
  });
});
