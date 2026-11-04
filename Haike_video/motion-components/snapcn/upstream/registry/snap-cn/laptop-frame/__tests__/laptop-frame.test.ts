/**
 * Unit tests for pure helpers in registry/snap-cn/laptop-frame/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/laptop-frame
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 */

import { describe, expect, it } from "vitest";

import {
  BEZEL_WIDTH,
  cameraPose,
  ENTRANCE_FRAMES,
  entrancePose,
  FLOAT_PERIOD_SECONDS,
  floatOffset,
  LID_HEIGHT,
  LID_WIDTH,
  lidTilt,
  NOTCH_DONE_WIDTH,
  NOTCH_IDLE_WIDTH,
  NOTCH_LOADING_WIDTH,
  NOTCH_TIMING,
  notchState,
  PUSH_END,
  PUSH_START,
  REST_TILT,
} from "../index";

describe("entrancePose", () => {
  const entrances = ["rise", "open", "none"] as const;

  it("starts rise and open transparent; none is visible immediately", () => {
    expect(entrancePose(0, "rise").opacity).toBe(0);
    expect(entrancePose(0, "open").opacity).toBe(0);
    expect(entrancePose(0, "none").opacity).toBe(1);
  });

  it("settles every entrance to the identity pose by ENTRANCE_FRAMES", () => {
    for (const entrance of entrances) {
      const pose = entrancePose(ENTRANCE_FRAMES, entrance);
      expect(pose.opacity).toBe(1);
      expect(pose.translateY).toBe(0);
      expect(pose.scale).toBe(1);
    }
  });

  it("rise starts below its resting position and moves up", () => {
    expect(entrancePose(0, "rise").translateY).toBe(70);
    const mid = entrancePose(13, "rise").translateY;
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(70);
  });

  it("clamps past the entrance so late frames stay settled", () => {
    for (const entrance of entrances) {
      const pose = entrancePose(500, entrance);
      expect(pose.opacity).toBe(1);
      expect(pose.translateY).toBe(0);
      expect(pose.scale).toBe(1);
    }
  });
});

describe("lidTilt", () => {
  it("holds the rest tilt for non-open entrances", () => {
    for (const f of [0, 15, 30, 200]) {
      expect(lidTilt(f, "rise")).toBe(REST_TILT);
      expect(lidTilt(f, "none")).toBe(REST_TILT);
    }
  });

  it("open swings the lid from closed-ish down to the rest tilt", () => {
    expect(lidTilt(0, "open")).toBe(82);
    const mid = lidTilt(15, "open");
    expect(mid).toBeLessThan(82);
    expect(mid).toBeGreaterThan(REST_TILT);
    expect(lidTilt(ENTRANCE_FRAMES, "open")).toBe(REST_TILT);
    expect(lidTilt(500, "open")).toBe(REST_TILT);
  });

  it("respects a custom rest tilt", () => {
    expect(lidTilt(0, "rise", "none", 30)).toBe(30);
    expect(lidTilt(ENTRANCE_FRAMES, "open", "none", 30)).toBe(30);
  });

  it("zoom-to-screen flattens the lid to 0 over the push", () => {
    // Before the push it holds the rest tilt; after, it un-tilts to flat.
    expect(lidTilt(PUSH_START - 1, "open", "zoom-to-screen")).toBe(REST_TILT);
    expect(lidTilt(PUSH_START, "open", "zoom-to-screen")).toBe(REST_TILT);
    const mid = lidTilt(
      Math.round((PUSH_START + PUSH_END) / 2),
      "open",
      "zoom-to-screen",
    );
    expect(mid).toBeLessThan(REST_TILT);
    expect(mid).toBeGreaterThan(0);
    expect(lidTilt(PUSH_END, "open", "zoom-to-screen")).toBe(0);
    expect(lidTilt(500, "open", "zoom-to-screen")).toBe(0);
  });
});

describe("cameraPose", () => {
  const W = 1280;
  const H = 720;
  const S = 0.85;

  it("is identity when there is no zoom finale", () => {
    for (const f of [0, 140, 200]) {
      expect(cameraPose(f, "none", S, W, H)).toEqual({
        scale: 1,
        translateY: 0,
      });
    }
  });

  it("holds identity until the push starts", () => {
    expect(cameraPose(PUSH_START, "zoom-to-screen", S, W, H).scale).toBe(1);
    expect(cameraPose(0, "zoom-to-screen", S, W, H).translateY).toBe(0);
  });

  it("ends with the screen inner exactly covering the frame", () => {
    const { scale } = cameraPose(PUSH_END, "zoom-to-screen", S, W, H);
    const innerW = (LID_WIDTH - 2 * BEZEL_WIDTH) * S * scale;
    const innerH = (LID_HEIGHT - 2 * BEZEL_WIDTH) * S * scale;
    // cover: at least one axis fills exactly, neither leaves a gap.
    expect(Math.min(innerW / W, innerH / H)).toBeCloseTo(1, 5);
    expect(innerW).toBeGreaterThanOrEqual(W - 1e-6);
    expect(innerH).toBeGreaterThanOrEqual(H - 1e-6);
  });

  it("scales up monotonically across the push", () => {
    const a = cameraPose(PUSH_START, "zoom-to-screen", S, W, H).scale;
    const b = cameraPose(160, "zoom-to-screen", S, W, H).scale;
    const c = cameraPose(PUSH_END, "zoom-to-screen", S, W, H).scale;
    expect(b).toBeGreaterThan(a);
    expect(c).toBeGreaterThan(b);
  });
});

describe("floatOffset", () => {
  const fps = 30;

  it("is zero at the start frame so it blends out of the entrance", () => {
    expect(floatOffset(ENTRANCE_FRAMES, fps, 4, ENTRANCE_FRAMES)).toBe(0);
  });

  it("holds at zero before the start frame", () => {
    expect(floatOffset(10, fps, 4, ENTRANCE_FRAMES)).toBe(0);
  });

  it("peaks at the amplitude a quarter period in", () => {
    const quarter = (fps * FLOAT_PERIOD_SECONDS) / 4;
    expect(floatOffset(quarter, fps, 4)).toBeCloseTo(-4, 5);
  });

  it("is silent at zero amplitude", () => {
    expect(floatOffset(37, fps, 0)).toBe(0);
  });
});

describe("notchState", () => {
  const { loadingStart, doneStart } = NOTCH_TIMING;

  it("moves idle → loading → done at the timing boundaries", () => {
    expect(notchState(0).phase).toBe("idle");
    expect(notchState(loadingStart).phase).toBe("loading");
    expect(notchState(doneStart).phase).toBe("done");
    expect(notchState(500).phase).toBe("done");
  });

  it("holds the idle width before loading, and the done width after", () => {
    expect(notchState(0).width).toBe(NOTCH_IDLE_WIDTH);
    expect(notchState(500).width).toBe(NOTCH_DONE_WIDTH);
  });

  it("passes through the loading width between the two morphs", () => {
    const mid = Math.round((loadingStart + doneStart) / 2);
    expect(notchState(mid).width).toBeCloseTo(NOTCH_LOADING_WIDTH, 5);
  });

  it("cross-fades exactly one layer at each settled state", () => {
    const idle = notchState(0);
    expect(idle.idle).toBe(1);
    expect(idle.loading).toBe(0);
    expect(idle.done).toBe(0);

    const done = notchState(500);
    expect(done.idle).toBe(0);
    expect(done.loading).toBe(0);
    expect(done.done).toBe(1);
  });
});
