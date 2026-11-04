import { describe, expect, it } from "vitest";
import {
  EXIT_EASING,
  enterOffset,
  exitOffset,
  normalizeEffects,
  resolveEasing,
  resolveTextRevealSettings,
  scheduleExit,
  splitText,
  springEase,
  TEXT_REVEAL_DEFAULTS,
  TEXT_REVEAL_PRESETS,
} from "../index";

describe("splitText", () => {
  it("splits characters including spaces", () => {
    expect(splitText("ab c", "character")).toEqual(["a", "b", " ", "c"]);
  });

  it("splits words and drops empty segments", () => {
    expect(splitText("Meet  Acme Billing", "word")).toEqual([
      "Meet",
      "Acme",
      "Billing",
    ]);
  });

  it("splits lines on newlines", () => {
    expect(splitText("one\ntwo", "line")).toEqual(["one", "two"]);
  });

  it("keeps block as a single unit", () => {
    expect(splitText("a b\nc", "block")).toEqual(["a b\nc"]);
  });
});

describe("normalizeEffects", () => {
  it("parses comma-separated strings", () => {
    expect(normalizeEffects("fade, slide,blur")).toEqual([
      "fade",
      "slide",
      "blur",
    ]);
  });

  it("passes arrays through and drops invalid entries", () => {
    expect(normalizeEffects(["fade", "wiggle", "mask"] as never)).toEqual([
      "fade",
      "mask",
    ]);
  });

  it("falls back to the default bundle when empty or undefined", () => {
    expect(normalizeEffects(undefined)).toEqual(["fade", "slide"]);
    expect(normalizeEffects("")).toEqual(["fade", "slide"]);
  });
});

describe("offsets", () => {
  it("enters against the travel direction", () => {
    expect(enterOffset("up", 24)).toEqual({ x: 0, y: 24 });
    expect(enterOffset("down", 24)).toEqual({ x: 0, y: -24 });
    expect(enterOffset("left", 24)).toEqual({ x: 24, y: 0 });
    expect(enterOffset("right", 24)).toEqual({ x: -24, y: 0 });
  });

  it("exits by continuing in the travel direction", () => {
    expect(exitOffset("up", 14)).toEqual({ x: 0, y: -14 });
    expect(exitOffset("right", 14)).toEqual({ x: 14, y: 0 });
  });
});

describe("scheduleExit", () => {
  it("starts the exit so the last unit finishes at the end", () => {
    const { enterEnd, exitStart } = scheduleExit({
      unitCount: 3,
      enterDuration: 18,
      stagger: 2,
      exitDuration: 14,
      exitStagger: 1,
      totalFrames: 90,
    });
    expect(enterEnd).toBe(18 + 2 * 2);
    // 90 - 14 - 2*1 = 74; last unit exits over [74+2, 90]
    expect(exitStart).toBe(74);
  });

  it("never starts before the enter tail on short compositions", () => {
    const { enterEnd, exitStart } = scheduleExit({
      unitCount: 10,
      enterDuration: 18,
      stagger: 4,
      exitDuration: 14,
      exitStagger: 1,
      totalFrames: 40,
    });
    expect(exitStart).toBe(enterEnd);
  });
});

describe("easing", () => {
  it("maps named curves to functions anchored at 0 and 1", () => {
    for (const name of [
      "smooth",
      "snappy",
      "overshoot",
      "linear",
      "spring",
    ] as const) {
      const fn = resolveEasing(name);
      expect(fn(0)).toBeCloseTo(0, 2);
      expect(fn(1)).toBeCloseTo(1, 2);
    }
  });

  it("supports custom cubic-bezier tuples", () => {
    const fn = resolveEasing([0.22, 1, 0.36, 1]);
    expect(fn(0)).toBeCloseTo(0, 5);
    expect(fn(1)).toBeCloseTo(1, 5);
    expect(fn(0.5)).toBeGreaterThan(0.5); // strong ease-out
  });

  it("springEase overshoots slightly and settles high-damped", () => {
    const peak = Math.max(
      ...Array.from({ length: 101 }, (_, i) => springEase(i / 100)),
    );
    expect(peak).toBeGreaterThan(1);
    expect(peak).toBeLessThan(1.05); // no chrome bounce
  });

  it("exit easing accelerates (ease-in)", () => {
    expect(EXIT_EASING(0.5)).toBeLessThan(0.5);
  });
});

describe("presets", () => {
  it("ships all 14 legacy looks", () => {
    expect(Object.keys(TEXT_REVEAL_PRESETS).sort()).toEqual(
      [
        "blur-out-up",
        "bottom-up-letters",
        "focus-blur-resolve",
        "line-by-line-slide",
        "mask-reveal-up",
        "micro-scale-fade",
        "per-character-rise",
        "scale-down-fade",
        "short-slide-right",
        "soft-blur-in",
        "spring-scale-in",
        "staggered-fade-up",
        "top-down-letters",
        "tracking-in",
      ].sort(),
    );
  });

  it("every preset resolves to valid settings", () => {
    for (const name of Object.keys(
      TEXT_REVEAL_PRESETS,
    ) as (keyof typeof TEXT_REVEAL_PRESETS)[]) {
      const s = resolveTextRevealSettings({ text: "x", preset: name });
      expect(s.effects.length).toBeGreaterThan(0);
      expect(s.enterDuration).toBeGreaterThan(0);
      expect(() => resolveEasing(s.easing)).not.toThrow();
    }
  });
});

describe("resolveTextRevealSettings", () => {
  it("uses defaults when nothing is provided", () => {
    const s = resolveTextRevealSettings({ text: "x" });
    expect(s.unit).toBe(TEXT_REVEAL_DEFAULTS.unit);
    expect(s.effects).toEqual(["fade", "slide"]);
    expect(s.exitDirection).toBe("up");
  });

  it("lets props override defaults", () => {
    const s = resolveTextRevealSettings({ text: "x", distance: 60 });
    expect(s.distance).toBe(60);
  });

  it("preset wins over motion props (locked bundle)", () => {
    const s = resolveTextRevealSettings({
      text: "x",
      preset: "soft-blur-in",
      unit: "word",
      blurAmount: 2,
    });
    expect(s.unit).toBe("character");
    expect(s.blurAmount).toBe(12);
  });

  it('"none" preset leaves props in charge', () => {
    const s = resolveTextRevealSettings({
      text: "x",
      preset: "none",
      unit: "line",
    });
    expect(s.unit).toBe("line");
  });

  it("exitDirection inherits direction unless set", () => {
    expect(
      resolveTextRevealSettings({ text: "x", direction: "right" })
        .exitDirection,
    ).toBe("right");
    expect(
      resolveTextRevealSettings({
        text: "x",
        direction: "right",
        exitDirection: "down",
      }).exitDirection,
    ).toBe("down");
  });

  it("parses comma-string effects from the customizer", () => {
    const s = resolveTextRevealSettings({ text: "x", effects: "slide,mask" });
    expect(s.effects).toEqual(["slide", "mask"]);
  });
});
