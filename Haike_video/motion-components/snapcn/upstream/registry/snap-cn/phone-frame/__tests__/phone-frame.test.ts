/**
 * Unit tests for pure helpers in registry/snap-cn/phone-frame/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/phone-frame
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 */

import { describe, expect, it } from "vitest";

import {
  BEZEL_WIDTH,
  DEVICE_RADIUS_RATIO,
  DEVICE_WIDTH,
  deviceRadius,
  ENTRANCE_FRAMES,
  entrancePose,
  FLOAT_PERIOD_SECONDS,
  floatOffset,
  pointAtFraction,
  screenRadiusFor,
  showcasePose,
  smoothClosedPath,
} from "../index";

describe("deviceRadius", () => {
  it("follows the real-device curvature ratio", () => {
    expect(deviceRadius(DEVICE_WIDTH)).toBe(
      Math.round(DEVICE_WIDTH * DEVICE_RADIUS_RATIO),
    );
  });

  it("scales with the device width", () => {
    expect(deviceRadius(400)).toBe(Math.round(400 * DEVICE_RADIUS_RATIO));
  });
});

describe("screenRadiusFor", () => {
  it("keeps corners concentric: inner = outer - bezel", () => {
    expect(screenRadiusFor(53)).toBe(53 - BEZEL_WIDTH);
    expect(screenRadiusFor(53, 10)).toBe(43);
  });

  it("never collapses below the 4px floor", () => {
    expect(screenRadiusFor(6)).toBe(4);
    expect(screenRadiusFor(0)).toBe(4);
  });
});

describe("entrancePose", () => {
  const entrances = ["rise", "rotate-in", "float"] as const;

  it("starts every entrance fully transparent", () => {
    for (const entrance of entrances) {
      expect(entrancePose(0, entrance).opacity).toBe(0);
    }
  });

  it("settles every entrance to the identity pose by ENTRANCE_FRAMES", () => {
    for (const entrance of entrances) {
      const pose = entrancePose(ENTRANCE_FRAMES, entrance);
      expect(pose.opacity).toBe(1);
      expect(pose.translateY).toBe(0);
      expect(pose.rotateDeg).toBe(0);
      expect(pose.scale).toBe(1);
    }
  });

  it("rise starts below its resting position and moves up", () => {
    const start = entrancePose(0, "rise");
    const mid = entrancePose(13, "rise");
    expect(start.translateY).toBe(70);
    expect(mid.translateY).toBeGreaterThan(0);
    expect(mid.translateY).toBeLessThan(start.translateY);
    expect(start.rotateDeg).toBe(0);
  });

  it("rotate-in starts tilted and scaled down", () => {
    const start = entrancePose(0, "rotate-in");
    expect(start.rotateDeg).toBe(-8);
    expect(start.scale).toBeCloseTo(0.94);
    expect(start.translateY).toBe(60);
  });

  it("float never translates — it only fades and grows in", () => {
    for (const frame of [0, 8, 16, 24, 60]) {
      expect(entrancePose(frame, "float").translateY).toBe(0);
    }
    expect(entrancePose(0, "float").scale).toBeCloseTo(0.96);
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

describe("floatOffset", () => {
  const fps = 30;

  it("is zero at the start frame so it blends out of the entrance", () => {
    expect(floatOffset(0, fps, 6)).toBe(0);
    expect(floatOffset(ENTRANCE_FRAMES, fps, 6, ENTRANCE_FRAMES)).toBe(0);
  });

  it("holds at zero before the start frame", () => {
    expect(floatOffset(10, fps, 6, ENTRANCE_FRAMES)).toBe(0);
  });

  it("drifts upward (negative y) right after the start frame", () => {
    expect(floatOffset(5, fps, 6)).toBeLessThan(0);
  });

  it("peaks at the amplitude a quarter period in", () => {
    const quarter = (fps * FLOAT_PERIOD_SECONDS) / 4;
    expect(floatOffset(quarter, fps, 6)).toBeCloseTo(-6, 5);
  });

  it("completes a full cycle back to zero", () => {
    const full = fps * FLOAT_PERIOD_SECONDS;
    expect(floatOffset(full, fps, 6)).toBeCloseTo(0, 5);
  });

  it("is silent at zero amplitude", () => {
    expect(floatOffset(37, fps, 0)).toBe(0);
  });
});

describe("route geometry (ride-summary demo)", () => {
  const square = [
    [0, 0],
    [10, 0],
    [10, 10],
    [0, 10],
  ] as const;

  it("pointAtFraction returns the loop start at f=0 and clamps out of range", () => {
    expect(pointAtFraction(0, square)).toEqual({ x: 0, y: 0 });
    expect(pointAtFraction(-1, square)).toEqual({ x: 0, y: 0 });
    // f=1 closes back onto the start of the loop.
    expect(pointAtFraction(2, square)).toEqual({ x: 0, y: 0 });
  });

  it("pointAtFraction lands mid-edge at a known fraction", () => {
    // Quarter of the perimeter (40) = 10 along the first edge → its far corner.
    expect(pointAtFraction(0.25, square)).toEqual({ x: 10, y: 0 });
  });

  it("smoothClosedPath emits a closed cubic path through every point", () => {
    const d = smoothClosedPath(square);
    expect(d.startsWith("M 0 0")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    // One cubic segment per point.
    expect(d.match(/C/g)).toHaveLength(square.length);
  });
});

describe("showcasePose", () => {
  const D = 240;

  it("starts laid back, camera low on the bottom-left, zoomed in", () => {
    const start = showcasePose(0, D);
    expect(start.rotateX).toBeGreaterThan(40); // tipped away from the camera
    expect(start.rotateY).toBeGreaterThan(10); // left edge toward the camera
    expect(start.zoom).toBeGreaterThan(1.5);
    expect(start.y).toBeLessThan(0); // looking at the bottom of the device
    expect(start.x).toBeGreaterThan(0); // …and at its left side
  });

  it("sweeps up to the top of the screen at peak zoom mid-flight", () => {
    const start = showcasePose(0, D);
    const mid = showcasePose(Math.round(0.42 * D), D);
    expect(mid.y).toBeGreaterThan(0); // camera now above the device center
    expect(mid.zoom).toBeGreaterThan(start.zoom); // zoomed in further
    expect(mid.rotateX).toBeLessThan(start.rotateX); // straightening up
  });

  it("settles to the straight frontal identity pose and holds it", () => {
    for (const frame of [D - 1, D, D + 90]) {
      const pose = showcasePose(frame, D);
      expect(pose.rotateX).toBeCloseTo(0, 5);
      expect(pose.rotateY).toBeCloseTo(0, 5);
      expect(pose.rotateZ).toBeCloseTo(0, 5);
      expect(pose.zoom).toBeCloseTo(1, 5);
      expect(pose.x).toBeCloseTo(0, 5);
      expect(pose.y).toBeCloseTo(0, 5);
    }
  });

  it("normalizes to any composition duration", () => {
    const short = showcasePose(59, 60);
    expect(short.zoom).toBeCloseTo(1, 5);
    expect(short.rotateX).toBeCloseTo(0, 5);
  });
});
