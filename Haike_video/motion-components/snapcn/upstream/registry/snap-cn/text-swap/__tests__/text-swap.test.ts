import { describe, expect, it } from "vitest";
import {
  getEnterStart,
  perspectiveScale,
  splitSegments,
  type TextSwapTransition,
  TRANSITION_DEFAULTS,
  TRANSITION_MOTION,
} from "../index";

const TRANSITIONS = Object.keys(TRANSITION_DEFAULTS) as TextSwapTransition[];

describe("splitSegments", () => {
  it("splits into words when unit is 'word'", () => {
    expect(splitSegments("Manual invoicing today", "word")).toEqual([
      "Manual",
      "invoicing",
      "today",
    ]);
  });

  it("keeps the whole line when unit is 'block'", () => {
    expect(splitSegments("Manual invoicing today", "block")).toEqual([
      "Manual invoicing today",
    ]);
  });

  it("returns a single segment for a single word in both units", () => {
    expect(splitSegments("Acme", "word")).toEqual(["Acme"]);
    expect(splitSegments("Acme", "block")).toEqual(["Acme"]);
  });
});

describe("getEnterStart", () => {
  it("uses enterStart = exitTotal - overlap + microDelay for a single block", () => {
    expect(
      getEnterStart({
        exitDuration: 8,
        segmentCount: 1,
        exitStagger: 1,
        overlap: 1,
        microDelay: 2,
      }),
    ).toBe(9);
  });

  it("extends the exit total by the stagger tail for multiple words", () => {
    // exitTotal = 15 + (3 - 1) * 1 = 17 → 17 - 5 + 2 = 14
    expect(
      getEnterStart({
        exitDuration: 15,
        segmentCount: 3,
        exitStagger: 1,
        overlap: 5,
        microDelay: 2,
      }),
    ).toBe(14);
  });

  it("never schedules the enter before frame 0", () => {
    expect(
      getEnterStart({
        exitDuration: 2,
        segmentCount: 1,
        exitStagger: 0,
        overlap: 10,
        microDelay: 0,
      }),
    ).toBe(0);
  });

  it("ignores negative segment counts safely", () => {
    expect(
      getEnterStart({
        exitDuration: 8,
        segmentCount: 0,
        exitStagger: 4,
        overlap: 0,
        microDelay: 0,
      }),
    ).toBe(8);
  });
});

describe("TRANSITION_DEFAULTS", () => {
  it("covers every transition with 8-21 frame durations", () => {
    for (const name of TRANSITIONS) {
      const d = TRANSITION_DEFAULTS[name];
      expect(d.exitDuration).toBeGreaterThanOrEqual(8);
      expect(d.exitDuration).toBeLessThanOrEqual(21);
      expect(d.enterDuration).toBeGreaterThanOrEqual(8);
      expect(d.enterDuration).toBeLessThanOrEqual(21);
    }
  });

  it("defaults crossfade and cut to per-word, the rest to block", () => {
    expect(TRANSITION_DEFAULTS.crossfade.unit).toBe("word");
    expect(TRANSITION_DEFAULTS.cut.unit).toBe("word");
    expect(TRANSITION_DEFAULTS["fade-through"].unit).toBe("block");
    expect(TRANSITION_DEFAULTS["shared-axis-y"].unit).toBe("block");
    expect(TRANSITION_DEFAULTS["shared-axis-z"].unit).toBe("block");
  });
});

describe("TRANSITION_MOTION", () => {
  it("gives shared-axis-y the real ±24px vertical travel", () => {
    expect(TRANSITION_MOTION["shared-axis-y"].exitY).toBe(-24);
    expect(TRANSITION_MOTION["shared-axis-y"].enterY).toBe(24);
  });

  it("keeps cut free of any drift, scale or blur", () => {
    const cut = TRANSITION_MOTION.cut;
    expect(cut.exitY).toBe(0);
    expect(cut.enterY).toBe(0);
    expect(cut.exitScale).toBe(1);
    expect(cut.enterScale).toBe(1);
    expect(cut.exitBlur).toBe(0);
    expect(cut.enterBlur).toBe(0);
  });

  it("moves shared-axis-z on the scale axis only", () => {
    const z = TRANSITION_MOTION["shared-axis-z"];
    expect(z.exitY).toBe(0);
    expect(z.enterY).toBe(0);
    expect(z.exitScale).toBeGreaterThan(1);
    expect(z.enterScale).toBeLessThan(1);
  });
});

describe("perspectiveScale", () => {
  it("is 1 at rest and maxScale at the eye", () => {
    expect(perspectiveScale(0, 12)).toBeCloseTo(1, 5);
    expect(perspectiveScale(1, 12)).toBeCloseTo(12, 1);
  });

  it("creeps early and blows up late — the whole point of it", () => {
    // A plain ramp would be at the halfway size by halfway. Perspective is not:
    // it is still small at half travel and then runs away at the end.
    const half = perspectiveScale(0.5, 12);
    const linearHalf = 1 + (12 - 1) * 0.5;
    expect(half).toBeLessThan(linearHalf / 2);
    expect(perspectiveScale(0.9, 12)).toBeGreaterThan(
      perspectiveScale(0.8, 12) * 1.5,
    );
  });

  it("reproduces the reference's blowup, which a plain ramp cannot", () => {
    // Frame-by-frame off the reference recording: at 95% of the way through the
    // exit the easing has spent ~0.985 of the travel, and the line measured
    // 10.28x its resting size. The model lands on 10.30. A linear ramp at the
    // same point would only be at 1 + 11 * 0.985 = 11.8 — it gets there, but by
    // marching steadily, with none of the late rush that makes it read as
    // something passing your face.
    expect(perspectiveScale(0.985, 12)).toBeGreaterThan(10);
    expect(perspectiveScale(0.985, 12)).toBeLessThan(10.6);
  });

  it("never divides by zero, and degrades to 1 for a no-op maxScale", () => {
    expect(Number.isFinite(perspectiveScale(1, 12))).toBe(true);
    expect(Number.isFinite(perspectiveScale(2, 12))).toBe(true);
    expect(perspectiveScale(0.5, 1)).toBe(1);
  });
});

describe("fly-through", () => {
  it("rushes the camera rather than merely growing", () => {
    const m = TRANSITION_MOTION["fly-through"];
    expect(m.exitPerspective).toBe(true);
    expect(m.exitScale).toBeGreaterThan(5);
    // it holds solid almost the whole way in, then goes
    expect(m.exitFadeStart).toBeGreaterThan(0.5);
    // and it is motion-blurred, or it would strobe at that speed
    expect(m.exitTrail ?? 1).toBeGreaterThan(1);
  });

  it("animates as one block — per-word would be a collision, not a camera move", () => {
    expect(TRANSITION_DEFAULTS["fly-through"].unit).toBe("block");
  });

  it("leaves every other transition on the plain ramp", () => {
    for (const name of TRANSITIONS) {
      if (name === "fly-through") continue;
      expect(TRANSITION_MOTION[name].exitPerspective ?? false).toBe(false);
      expect(TRANSITION_MOTION[name].exitTrail ?? 1).toBe(1);
      expect(TRANSITION_MOTION[name].exitFadeStart ?? 0).toBe(0);
    }
  });
});
