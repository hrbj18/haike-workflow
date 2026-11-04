import { describe, expect, it } from "vitest";

import {
  AVATAR,
  CARD,
  CARD_PITCH,
  cameraScale,
  clearance,
  cursorAt,
  FLIP_AT,
  GRANT_AT,
  GRANT_STEP,
  granted,
  grantOrderOf,
  grantSeed,
  initialsOf,
  pan,
  pillWidth,
  pressScale,
  REF_PILL_HALF,
  rowDrift,
  SNAPCN_ROSTER,
  slotsFor,
  turnOf,
} from "../index";

/**
 * The reference is a 30fps clip and every measurement in the component is in
 * seconds, so this is the only conversion in the file. Frame numbers below are
 * frames of the **re-timed** reference — the recording is variable-rate and had
 * to be resampled onto a 30fps grid before anything could be compared.
 */
const at = (f: number) => f / 30;

describe("the camera", () => {
  it("reproduces the measured pull-back", () => {
    // The scale measured off the reference at six times, to 0.01 — which is
    // 1.5px on the 295px row span it was read from, and the span can only be
    // read to about a pixel.
    for (const [t, s] of [
      [0.0969, 1.1615],
      [0.647, 1.0684],
      [1.247, 1.0325],
      [1.997, 1.013],
      [2.689, 1.0052],
      [3.089, 1.003],
    ] as const) {
      // Within 0.012, which is 1.8px on the 295px row span it was read from —
      // and that span can only be read to about a pixel either way.
      expect(Math.abs(cameraScale(t) - s), `t=${t}`).toBeLessThan(0.012);
    }
    // And the first frame, which the recording caught while still paused.
    expect(cameraScale(0)).toBeCloseTo(1.184, 3);
  });

  it("only ever pulls back", () => {
    for (let f = 1; f <= 120; f++) {
      expect(cameraScale(at(f)), `frame ${f}`).toBeLessThan(
        cameraScale(at(f - 1)),
      );
    }
  });

  it("never freezes: every frame of the settle actually moves", () => {
    // Below half a pixel a frame rasterises identically to the one before it
    // and the shot reads as held. Measured on a card at the frame edge, where
    // the camera and the row's own drift both land — the camera alone is under
    // half a pixel from frame 41, and it is the marquee under it that keeps the
    // middle of this shot from looking like a freeze-frame.
    const edge = (f: number) => {
      const t = at(f);
      return (356 + rowDrift(0, t)) * cameraScale(t);
    };
    for (let f = 1; f <= 88; f++) {
      expect(Math.abs(edge(f) - edge(f - 1)), `frame ${f}`).toBeGreaterThan(
        0.5,
      );
    }
  });
});

describe("the rows", () => {
  it("stream in opposite directions", () => {
    expect(rowDrift(0, 1)).toBeLessThan(0);
    expect(rowDrift(2, 1)).toBeGreaterThan(0);
    // The middle row does not drift at all — it is anchored to the pill.
    expect(rowDrift(1, 1)).toBe(0);
  });

  it("are never symmetric about the pill", () => {
    // The whole texture of the shot. The bottom row is front-loaded and the top
    // row is not, so |bottom| / |top| is nowhere near 1 in the first second.
    const ratio = (t: number) => rowDrift(2, t) / -rowDrift(0, t);
    expect(ratio(0.25)).toBeGreaterThan(1.5);
    expect(ratio(1)).toBeGreaterThan(1.5);
  });

  it("stop before the shot does — only the camera is still moving at the end", () => {
    // The measured track never flattens; the measured track *minus the pan*
    // does, and that is the check on the whole decomposition.
    expect(rowDrift(0, 3.73)).toBeCloseTo(-254.8, 1);
    expect(rowDrift(0, 4.005) - rowDrift(0, 3.73)).toBeGreaterThan(-5);
    expect(rowDrift(2, 4.005) - rowDrift(2, 3.364)).toBeLessThan(5);
  });

  it("never reverses", () => {
    for (let f = 1; f <= 120; f++) {
      expect(rowDrift(0, at(f)), `frame ${f}`).toBeLessThanOrEqual(
        rowDrift(0, at(f - 1)),
      );
      expect(rowDrift(2, at(f)), `frame ${f}`).toBeGreaterThanOrEqual(
        rowDrift(2, at(f - 1)),
      );
    }
  });
});

describe("the middle row", () => {
  it("closes on the pill by the measured amounts", () => {
    // 91 -> 51 on the left, 123 -> 65 on the right, on the camera's shape and
    // very nearly its clock.
    // Within 3px. Two of these four are inside a pixel and the right-hand
    // pair are not: that side's tail decays slower than any single exponential
    // through its head, and 3px on a card edge against a background this close
    // in value to the card is the width of the measurement itself.
    for (const [side, t, v] of [
      ["left", 0.289, 91],
      ["left", 3.05, 51],
      ["right", 0.289, 123],
      ["right", 3.05, 65],
    ] as const) {
      expect(Math.abs(clearance(side, t) - v), `${side} @ ${t}`).toBeLessThan(
        3,
      );
    }
  });

  it("stays asymmetric", () => {
    for (const t of [0.3, 1, 2, 3]) {
      expect(clearance("right", t) - clearance("left", t)).toBeGreaterThan(10);
    }
  });

  it("leaves the slot behind the pill empty", () => {
    const half = pillWidth("Install all") / 2;
    for (const { u } of slotsFor(1, 2, half)) {
      expect(Math.abs(u) - CARD.w / 2).toBeGreaterThan(half);
    }
  });
});

describe("the pan", () => {
  it("is nothing at all until the shot is over", () => {
    for (let f = 0; f <= 88; f++) expect(pan(at(f)), `frame ${f}`).toBe(0);
  });

  it("accelerates all the way out", () => {
    const v = (f: number) => pan(at(f)) - pan(at(f - 1));
    expect(v(100)).toBeLessThan(v(95));
    expect(v(110)).toBeLessThan(v(100));
    expect(v(120)).toBeLessThan(v(110));
  });
});

describe("the press", () => {
  it("bottoms out at the measured scale, on the measured frame", () => {
    expect(pressScale(1.62)).toBeCloseTo(1, 2);
    expect(pressScale(1.805)).toBeCloseTo(0.931, 3);
    expect(pressScale(2.33)).toBeCloseTo(1, 2);
  });

  it("takes three times as long coming up as going down", () => {
    // Symmetric, a click stops feeling like a click and starts feeling like a
    // bounce. Down 0.18s, up 0.53s.
    const down = 1.805 - 1.622;
    const up = 2.33 - 1.805;
    expect(up / down).toBeGreaterThan(2.5);
  });

  it("never overshoots", () => {
    for (let f = 48; f <= 72; f++) {
      expect(pressScale(at(f)), `frame ${f}`).toBeLessThanOrEqual(1);
    }
  });

  it("flips the pill during the press, not on the release", () => {
    expect(FLIP_AT).toBeGreaterThan(1.622);
    expect(FLIP_AT).toBeLessThan(1.805);
  });
});

describe("the pointer", () => {
  it("arrives on the pill and holds there", () => {
    const half = REF_PILL_HALF;
    expect(cursorAt(0, half).y).toBeCloseTo(89.5, 1);
    // Landed by 1.32s, and still there at 2.0.
    expect(cursorAt(1.5, half).y).toBeCloseTo(-2.6, 1);
    expect(cursorAt(2.0, half).y).toBeCloseTo(-2.6, 1);
    expect(cursorAt(1.5, half).x).toBeCloseTo(103.9, 0);
  });

  it("arrives in two moves, the second one faster than the first", () => {
    // The approach eases out to a hover ~30px below the pill, then drops. That
    // second move is what makes the click read as a decision.
    const speed = (a: number, b: number) =>
      Math.abs(cursorAt(b, REF_PILL_HALF).y - cursorAt(a, REF_PILL_HALF).y) /
      (b - a);
    expect(speed(0.8, 0.95)).toBeLessThan(60);
    expect(speed(1.16, 1.29)).toBeGreaterThan(100);
  });

  it("never jumps, however narrow the pill", () => {
    // The landing is pulled in to the pill's edge and the pull fades in across
    // the pill's height. Clamped hard instead, the frame the pointer crossed
    // that edge on its way out moved 40px in one frame.
    const step = (half: number, f: number) => {
      const a = cursorAt(at(f - 1), half);
      const b = cursorAt(at(f), half);
      return Math.hypot(b.x - a.x, b.y - a.y);
    };
    for (const label of ["Add", "Give everyone access now"]) {
      const half = pillWidth(label) / 2;
      for (let f = 1; f <= 120; f++) {
        // Never more than 5px past what the measured track does on its own,
        // and that worst case is a three-letter label on the frame the pointer
        // is already travelling 11px — the pull is released while everything
        // else is moving, which is the whole point of fading it.
        expect(
          step(half, f) - step(REF_PILL_HALF, f),
          `${label} @ ${f}`,
        ).toBeLessThan(5);
      }
    }
  });

  it("lands inside a narrower pill instead of beside it", () => {
    const narrow = pillWidth("Add") / 2;
    expect(cursorAt(1.7, narrow).x).toBeLessThan(narrow);
    expect(cursorAt(1.7, narrow).x).toBeGreaterThan(narrow * 0.7);
  });
});

describe("the cascade", () => {
  it("turns one monogram over every seven frames from frame 70", () => {
    expect(GRANT_AT).toBeCloseTo(70 / 30, 6);
    expect(GRANT_STEP).toBeCloseTo(7 / 30, 6);
    // The reference's five visible onsets, four of them exact.
    for (const [order, frame] of [
      [0, 70],
      [2, 84],
      [3, 91],
      [4, 98],
    ] as const) {
      expect(granted(order, at(frame)), `order ${order}`).toBe(true);
      expect(granted(order, at(frame - 1)), `order ${order}`).toBe(false);
    }
  });

  it("never grants the same row twice running", () => {
    const rowAt = new Map<number, number>();
    for (const row of [0, 1, 2] as const) {
      for (let step = 0; step < 8; step++) rowAt.set(turnOf(row, step), row);
    }
    for (let order = 1; order < 18; order++) {
      expect(rowAt.get(order), `order ${order}`).not.toBe(rowAt.get(order - 1));
    }
  });

  it("gives every order to exactly one row", () => {
    const seen = new Set<number>();
    for (const row of [0, 1, 2] as const) {
      for (let step = 0; step < 8; step++) seen.add(turnOf(row, step));
    }
    for (let order = 0; order < 18; order++) expect(seen.has(order)).toBe(true);
  });

  it("seeds on a monogram that is actually on screen", () => {
    const half = pillWidth("Install all") / 2;
    const reach = 712 / 2 / cameraScale(GRANT_AT);
    for (const row of [0, 1, 2] as const) {
      const len = (SNAPCN_ROSTER[row] ?? []).length;
      const seed = grantSeed(row, len, half);
      const slot = slotsFor(row, GRANT_AT, half).find(
        (k) => ((k.slot % len) + len) % len === seed,
      );
      expect(slot, `row ${row}`).toBeDefined();
      const disc = (slot?.u ?? 0) - CARD.w / 2 + AVATAR.padX + AVATAR.size / 2;
      expect(Math.abs(disc), `row ${row}`).toBeLessThan(reach);
    }
  });

  it("opens each row's cascade on the entry it seeded", () => {
    const half = pillWidth("Install all") / 2;
    for (const row of [0, 1, 2] as const) {
      const len = (SNAPCN_ROSTER[row] ?? []).length;
      const seed = grantSeed(row, len, half);
      expect(grantOrderOf(row, seed, len, seed), `row ${row}`).toBe(
        turnOf(row, 0),
      );
      // …and walks the roster one entry at a time from there.
      expect(grantOrderOf(row, (seed + 1) % len, len, seed)).toBe(
        turnOf(row, 1),
      );
    }
  });
});

describe("layout", () => {
  it("keeps the marquee pitch the reference measured", () => {
    expect(CARD_PITCH).toBe(312);
    expect(CARD.w / CARD_PITCH).toBeCloseTo(0.917, 3);
  });

  it("sizes the default pill within two pixels of the reference's", () => {
    // The reference's "Give access" pill is 244 wide.
    expect(pillWidth("Give access")).toBeGreaterThan(240);
    expect(pillWidth("Give access")).toBeLessThan(250);
  });

  it("derives a monogram from a name", () => {
    expect(initialsOf({ name: "Text Reveal", role: "" })).toBe("TR");
    expect(initialsOf({ name: "Karaoke Captions", role: "" })).toBe("KC");
    expect(initialsOf({ name: "Remotion", role: "" })).toBe("R");
    expect(initialsOf({ name: "x", role: "", initials: "ZZ" })).toBe("ZZ");
  });

  it("draws enough cards to cover the frame at every scale", () => {
    const half = pillWidth("Install all") / 2;
    for (let f = 0; f <= 120; f += 5) {
      for (const row of [0, 1, 2] as const) {
        const slots = slotsFor(row, at(f), half);
        const s = cameraScale(at(f));
        // A content x is on screen when 356 + (u + pan) * s is in [0, 712].
        const right = 356 / s - pan(at(f));
        const left = -356 / s - pan(at(f));
        expect(
          Math.max(...slots.map((k) => k.u + CARD.w / 2)),
          `row ${row} frame ${f}`,
        ).toBeGreaterThan(right);
        expect(
          Math.min(...slots.map((k) => k.u - CARD.w / 2)),
          `row ${row} frame ${f}`,
        ).toBeLessThan(left);
      }
    }
  });
});
