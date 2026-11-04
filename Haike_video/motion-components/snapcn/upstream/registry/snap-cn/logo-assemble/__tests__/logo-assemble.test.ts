/**
 * Unit tests for the pure timeline helpers in logo-assemble/index.tsx.
 *
 * Run: pnpm vitest run registry/snap-cn/logo-assemble
 */

import { describe, expect, it } from "vitest";

import {
  CONTRACT_END,
  CONTRACT_START,
  cardOpacity,
  cardScale,
  contractProgress,
  LOGO_IN,
  LOGO_SHIFT_END,
  LOGO_SHIFT_START,
  logoPose,
  logoShift,
  MIDDLE_OUT,
  middleTextOpacity,
  NAME_IN,
  namePose,
  orbitAngle,
  ringScale,
} from "../index";

describe("contractProgress", () => {
  it("drains 0 → 1 across the contract window", () => {
    expect(contractProgress(CONTRACT_START)).toBe(0);
    expect(contractProgress(CONTRACT_END)).toBe(1);
    expect(contractProgress(0)).toBe(0);
    expect(contractProgress(90)).toBe(1);
  });
});

describe("orbitAngle", () => {
  it("rotates steadily, then spins faster as it drains in", () => {
    expect(orbitAngle(0)).toBe(0);
    // Before the drain, motion is purely the steady orbit.
    const a10 = orbitAngle(10);
    const a20 = orbitAngle(20);
    expect(a20 - a10).toBeCloseTo(a10 - orbitAngle(0), 5);
    // The drain adds extra spin on top of the steady rate.
    expect(orbitAngle(CONTRACT_END)).toBeGreaterThan(
      orbitAngle(CONTRACT_START) + (CONTRACT_END - CONTRACT_START) * 0.1,
    );
  });
});

describe("ring collapse", () => {
  it("ringScale shrinks the radius to 0 as it drains", () => {
    expect(ringScale(CONTRACT_START)).toBe(1);
    expect(ringScale(CONTRACT_END)).toBe(0);
  });

  it("cards shrink but stay on-screen, then vanish at the very end", () => {
    expect(cardScale(CONTRACT_START)).toBe(1);
    expect(cardScale(CONTRACT_END)).toBeCloseTo(0.34, 5);
    expect(cardOpacity(CONTRACT_START)).toBe(1);
    expect(cardOpacity(CONTRACT_END)).toBe(0);
  });
});

describe("logoPose", () => {
  it("is hidden before the birth, solid and unit-scale after settling", () => {
    expect(logoPose(LOGO_IN - 1).opacity).toBe(0);
    const settled = logoPose(LOGO_IN + 20);
    expect(settled.opacity).toBe(1);
    expect(settled.scale).toBeCloseTo(1, 5);
  });

  it("is born small (below 1) at the start", () => {
    expect(logoPose(LOGO_IN).scale).toBeLessThan(1);
  });
});

describe("middleTextOpacity", () => {
  it("holds the center text through the orbit, then clears for the collapse", () => {
    expect(middleTextOpacity(0)).toBe(0);
    expect(middleTextOpacity(20)).toBe(1);
    expect(middleTextOpacity(MIDDLE_OUT)).toBe(0);
  });
});

describe("logoShift", () => {
  it("slides the logo from centre (0) to its left rest (1) after it lands", () => {
    expect(logoShift(LOGO_SHIFT_START)).toBe(0);
    expect(logoShift(LOGO_SHIFT_END)).toBe(1);
    expect(logoShift(LOGO_IN)).toBe(0); // still centred at birth
  });
});

describe("namePose", () => {
  it("reveals the brand name in step with the slide (simultaneously)", () => {
    expect(namePose(NAME_IN - 1).opacity).toBe(0);
    // The name starts exactly when the logo starts moving — not after it lands.
    expect(NAME_IN).toBe(LOGO_SHIFT_START);
    expect(NAME_IN).toBeLessThan(LOGO_SHIFT_END);
    const settled = namePose(NAME_IN + 14);
    expect(settled.opacity).toBe(1);
    expect(settled.dx).toBeCloseTo(0, 5);
  });
});
