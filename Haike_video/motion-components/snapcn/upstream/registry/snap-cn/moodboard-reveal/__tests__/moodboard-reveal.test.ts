/**
 * Unit tests for the pure timeline helpers in moodboard-reveal/index.tsx.
 *
 * Run: pnpm vitest run registry/snap-cn/moodboard-reveal
 */

import { describe, expect, it } from "vitest";

import {
  BG_END,
  BG_START,
  bgProgress,
  COLLAGE_START,
  DROP_FRAMES,
  DROP_SCALE,
  FLICKER_HOLD,
  flickerImage,
  INLINE_HOLD,
  INLINE_START,
  inlineImage,
  MERGE_END,
  MERGE_START,
  MERGE_W,
  mergeBlur,
  mergeProgress,
  ORBIT_DEG,
  ORBIT_END,
  orbitAngle,
  SLOTS,
  slotPose,
} from "../index";

describe("bgProgress", () => {
  it("stays dark before the transition and light after", () => {
    expect(bgProgress(0)).toBe(0);
    expect(bgProgress(BG_START)).toBe(0);
    expect(bgProgress(BG_END)).toBe(1);
    expect(bgProgress(150)).toBe(1);
  });
});

describe("orbitAngle", () => {
  it("sweeps the cluster from 0 to ORBIT_DEG, monotonically", () => {
    expect(orbitAngle(COLLAGE_START)).toBe(0);
    expect(orbitAngle(ORBIT_END)).toBeCloseTo(ORBIT_DEG, 5);
    const mid = orbitAngle((COLLAGE_START + ORBIT_END) / 2);
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(ORBIT_DEG);
    expect(orbitAngle(500)).toBeCloseTo(ORBIT_DEG, 5); // clamps after
  });
});

describe("flickerImage", () => {
  it("changes the image over time (a shuffle, not a hold)", () => {
    const a = flickerImage(COLLAGE_START, 0, 8);
    const b = flickerImage(COLLAGE_START + FLICKER_HOLD, 0, 8);
    expect(a).not.toBe(b);
  });

  it("shows different images across positions at the same frame", () => {
    const f = COLLAGE_START + 10;
    expect(flickerImage(f, 0, 8)).not.toBe(flickerImage(f, 1, 8));
  });

  it("freezes at the merge so the convergence is not a strobe", () => {
    expect(flickerImage(MERGE_START, 3, 8)).toBe(
      flickerImage(MERGE_START + 40, 3, 8),
    );
  });

  it("only ever returns a valid image index", () => {
    for (let f = COLLAGE_START; f < MERGE_START; f++) {
      for (let s = 0; s < SLOTS.length; s++) {
        const idx = flickerImage(f, s, 8);
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(idx).toBeLessThan(8);
      }
    }
  });
});

describe("mergeProgress / mergeBlur", () => {
  it("progresses 0 → 1 across the merge window", () => {
    expect(mergeProgress(MERGE_START)).toBe(0);
    expect(mergeProgress(MERGE_END)).toBe(1);
    expect(mergeProgress(150)).toBe(1);
  });

  it("blurs only during the merge, peaking in the middle", () => {
    expect(mergeBlur(MERGE_START)).toBe(0);
    expect(mergeBlur(MERGE_END)).toBe(0);
    expect(mergeBlur((MERGE_START + MERGE_END) / 2)).toBeGreaterThan(0);
    expect(mergeBlur(0)).toBe(0);
  });
});

describe("slotPose", () => {
  const slot = SLOTS[0];

  it("is hidden before its staggered appearance", () => {
    expect(slotPose(COLLAGE_START - 1, slot, 0).opacity).toBe(0);
  });

  it("is fully visible at its scattered offset after appearing", () => {
    const pose = slotPose(COLLAGE_START + 14, slot, 0);
    expect(pose.opacity).toBeCloseTo(1, 5);
    // Not yet merging, so it sits out at (roughly) its own offset.
    expect(Math.abs(pose.x) + Math.abs(pose.y)).toBeGreaterThan(50);
  });

  it("converges to the centre and a common footprint — but never fades", () => {
    const pose = slotPose(MERGE_END, slot, 0);
    expect(pose.x).toBeCloseTo(0, 5);
    expect(pose.y).toBeCloseTo(0, 5);
    // Every slot lands at the same width (MERGE_W), so they stack exactly.
    expect(pose.scale * slot.w).toBeCloseTo(MERGE_W, 4);
    // The key fix: it stays fully opaque — hidden by overlap, not vanished.
    expect(pose.opacity).toBe(1);
  });

  it("lands every slot at the same footprint (they overlap exactly)", () => {
    for (let i = 0; i < SLOTS.length; i++) {
      const p = slotPose(MERGE_END, SLOTS[i], i);
      expect(p.scale * SLOTS[i].w).toBeCloseTo(MERGE_W, 4);
      expect(p.opacity).toBe(1);
    }
  });
});

describe("inlineImage (drop swap)", () => {
  it("advances through the swap images over time and clamps to the last", () => {
    expect(inlineImage(0, 5).index).toBe(0);
    expect(inlineImage(INLINE_START, 5).index).toBe(0);
    expect(inlineImage(INLINE_START + INLINE_HOLD, 5).index).toBe(1);
    expect(inlineImage(1000, 5).index).toBe(4);
  });

  it("drops each new image from a zoom that settles to normal", () => {
    const swap = INLINE_START + INLINE_HOLD; // image 1 becomes active
    expect(inlineImage(swap, 5).scale).toBeCloseTo(DROP_SCALE, 5);
    expect(inlineImage(swap, 5).opacity).toBe(0);
    const settled = swap + DROP_FRAMES + 1; // still within this image's hold
    expect(settled).toBeLessThan(swap + INLINE_HOLD);
    expect(inlineImage(settled, 5).scale).toBeCloseTo(1, 5);
    expect(inlineImage(settled, 5).opacity).toBe(1);
  });

  it("never overshoots below normal scale (a settle, not a bounce)", () => {
    for (let f = 0; f < 50; f++) {
      expect(inlineImage(f, 5).scale).toBeGreaterThanOrEqual(1 - 1e-9);
      expect(inlineImage(f, 5).scale).toBeLessThanOrEqual(DROP_SCALE + 1e-9);
    }
  });
});
