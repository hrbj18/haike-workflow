import { describe, expect, it } from "vitest";
import {
  defaultThickness,
  inkReach,
  perspectiveScale,
  strikethroughPhases,
  swingGain,
  swingWorldX,
} from "../index";

describe("defaultThickness", () => {
  it("derives thickness as round(fontSize * 0.08)", () => {
    expect(defaultThickness(56)).toBe(4);
    expect(defaultThickness(100)).toBe(8);
  });

  it("never goes below 2px", () => {
    expect(defaultThickness(12)).toBe(2);
  });
});

describe("swingWorldX", () => {
  const S = 42;
  const W = 1280;
  // The projected offset is the world path times the apparent scale — that multiply is
  // the whole effect, so the tests have to look at it, not at the world path alone.
  const gain = swingGain(S);
  const drift = (0.55 * W) / S;
  const bow = (0.25 * W) / gain;
  const projected = (t: number) =>
    swingWorldX(t, drift, bow) * perspectiveScale(t, S);

  it("bows out to the left on the way and crosses to the right at the end", () => {
    expect(projected(0)).toBeCloseTo(0, 6);
    expect(projected(0.5)).toBeLessThan(0); // out on the arc
    expect(projected(1)).toBeCloseTo(0.55 * W, -1); // and away, on the far side
  });

  it("turns exactly once — a curve, not a change of mind", () => {
    // A swing has one extreme. Two would mean it wandered back and forth, which is the
    // thing that reads as two animations fighting rather than one arc.
    let turns = 0;
    let prev = projected(0.001) - projected(0);
    for (let i = 2; i <= 400; i++) {
      const step = projected(i / 400) - projected((i - 1) / 400);
      if (step !== 0 && prev !== 0 && Math.sign(step) !== Math.sign(prev))
        turns++;
      if (step !== 0) prev = step;
    }
    expect(turns).toBe(1);
  });

  it("opens the arc up as the mark nears the lens, which is what makes it an arc", () => {
    // The bow is symmetric in world space, but the projection magnifies the near half.
    // So the widest point on screen must fall in the *second* half of the approach — if
    // it landed at the midpoint, the mark would be sliding on glass, not swinging at you.
    let widestAt = 0;
    let widest = 0;
    for (let i = 1; i < 200; i++) {
      const t = i / 200;
      if (-projected(t) > widest) {
        widest = -projected(t);
        widestAt = t;
      }
    }
    expect(widestAt).toBeGreaterThan(0.6);
    // Roughly as wide as asked for, and never wider: the rightward crossing is already
    // pulling against the bow by the time it peaks, so it eats a fifth of it. That is why
    // `swingOut` is documented as about this wide rather than exactly this wide.
    expect(widest).toBeLessThanOrEqual(0.25 * W);
    expect(widest).toBeGreaterThan(0.75 * 0.25 * W);
  });

  it("is a straight crossing with no bow", () => {
    expect(swingWorldX(0.5, drift, 0)).toBeCloseTo(drift * 0.5, 6);
  });
});

describe("swingGain", () => {
  it("is the factor the projection applies to the bow at its widest", () => {
    // Quoting swingOut as a fraction of the frame only works if this divides back out.
    const gain = swingGain(42);
    expect(gain).toBeGreaterThan(2);
    let peak = 0;
    for (let i = 1; i < 500; i++) {
      const t = i / 500;
      peak = Math.max(peak, Math.sin(Math.PI * t) * perspectiveScale(t, 42));
    }
    expect(gain).toBeCloseTo(peak, 1);
  });

  it("never divides by less than one, however small the rush", () => {
    expect(swingGain(1)).toBe(1);
  });
});

describe("inkReach", () => {
  const W = 1280;
  const H = 720;
  const CORNERS = [
    [0, 0],
    [W, 0],
    [0, H],
    [W, H],
  ];

  /**
   * The mark rests at the left end of a centred lockup, so its centre is somewhere in
   * [0, W/2] for any string — the left edge for a wordmark that fills the frame, the
   * centre for an empty one — and nothing measures which. The ink has to close the frame
   * from every one of them, swung either way.
   */
  it("closes every corner from anywhere the rush can leave the mark", () => {
    for (const driftFraction of [-0.8, -0.45, 0, 0.45, 0.8]) {
      const driftPx = driftFraction * W;
      const reach = inkReach(W, H, driftPx);
      for (const rest of [0, W / 4, W / 2]) {
        const cx = rest + driftPx;
        const cy = H / 2;
        for (const [x, y] of CORNERS) {
          expect(Math.hypot(cx - x, cy - y)).toBeLessThanOrEqual(reach);
        }
      }
    }
  });

  it("reaches further than a flat 0.85 × diagonal once the mark swings out", () => {
    // The bug this replaces: 0.85 * diagonal is only enough while the mark stays near the
    // middle of the frame. Swing it out to one side and the far corner is further away
    // than that, so the ink stops short and a wedge of backdrop survives in the corner.
    const diagonal = Math.hypot(W, H);
    expect(inkReach(W, H, 0.45 * W)).toBeGreaterThan(0.85 * diagonal);
  });
});

describe("perspectiveScale", () => {
  it("creeps for most of the trip and blows up at the end", () => {
    // The character of a thing coming at your face: halfway through it has spent barely a
    // fiftieth of its growth, and the rest arrives in the last few frames.
    expect(perspectiveScale(0.5, 42)).toBeLessThan(2);
    expect(perspectiveScale(1, 42)).toBeCloseTo(42, 0);
  });

  it("is 1 at rest and never inverts", () => {
    expect(perspectiveScale(0, 42)).toBe(1);
    expect(perspectiveScale(-1, 42)).toBe(1);
    expect(perspectiveScale(0.5, 1)).toBe(1);
  });
});

describe("strikethroughPhases", () => {
  it("draws over drawDuration, then crossfades over half of it", () => {
    const phases = strikethroughPhases(15, 30);
    expect(phases.drawStart).toBe(15);
    expect(phases.drawEnd).toBe(45);
    expect(phases.fadeStart).toBe(45);
    expect(phases.fadeEnd).toBe(60);
  });

  it("keeps the 0-40% draw / 40-60% crossfade ratio of the total window", () => {
    const { drawStart, drawEnd, fadeEnd } = strikethroughPhases(0, 40);
    const total = fadeEnd / 0.6;
    expect((drawEnd - drawStart) / total).toBeCloseTo(0.4);
    expect((fadeEnd - drawEnd) / total).toBeCloseTo(0.2);
  });
});
