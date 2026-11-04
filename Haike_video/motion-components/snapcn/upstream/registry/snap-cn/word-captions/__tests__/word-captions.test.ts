import { describe, expect, it } from "vitest";

import {
  activeGroupIndex,
  buildPages,
  CAPTION_LOOKS,
  captionsToWords,
  clampGroupSize,
  explodeCue,
  groupWords,
  msToFrame,
  parseSrt,
  popScale,
  resolveWordTimings,
  SAFE_AREA_BOTTOM_PCT,
  scheduleWords,
  srtTimeToMs,
} from "../index";

describe("scheduleWords", () => {
  it("paces a plain transcript evenly", () => {
    expect(scheduleWords("Stop losing hours", 14)).toEqual([
      { text: "Stop", startFrame: 0, endFrame: 14 },
      { text: "losing", startFrame: 14, endFrame: 28 },
      { text: "hours", startFrame: 28, endFrame: 42 },
    ]);
  });

  it("offsets the whole schedule by startFrame", () => {
    const words = scheduleWords("to manual invoices", 10, 30);
    expect(words[0]).toEqual({ text: "to", startFrame: 30, endFrame: 40 });
    expect(words[2].endFrame).toBe(60);
  });

  it("collapses repeated whitespace and trims", () => {
    expect(scheduleWords("  Stop   losing ", 14).map((w) => w.text)).toEqual([
      "Stop",
      "losing",
    ]);
  });

  it("returns an empty schedule for an empty string", () => {
    expect(scheduleWords("", 14)).toEqual([]);
  });

  it("enforces a minimum pace of 1 frame per word", () => {
    const words = scheduleWords("a b", 0);
    expect(words[1].startFrame).toBe(1);
  });
});

describe("resolveWordTimings", () => {
  it("ends a word when the next one starts", () => {
    const timed = resolveWordTimings(
      [
        { text: "Stop", startFrame: 0 },
        { text: "losing", startFrame: 12 },
      ],
      14,
    );
    expect(timed[0].endFrame).toBe(12);
  });

  it("holds the last word for the fallback duration", () => {
    const timed = resolveWordTimings(
      [{ text: "invoices", startFrame: 70 }],
      14,
    );
    expect(timed[0].endFrame).toBe(84);
  });

  it("keeps explicit endFrames", () => {
    const timed = resolveWordTimings(
      [
        { text: "Stop", startFrame: 0, endFrame: 9 },
        { text: "losing", startFrame: 12 },
      ],
      14,
    );
    expect(timed[0].endFrame).toBe(9);
  });

  it("guarantees every word lasts at least one frame", () => {
    const timed = resolveWordTimings(
      [{ text: "Stop", startFrame: 10, endFrame: 5 }],
      14,
    );
    expect(timed[0].endFrame).toBe(11);
  });
});

describe("clampGroupSize", () => {
  it("clamps to the 1-3 range and floors fractions", () => {
    expect(clampGroupSize(0)).toBe(1);
    expect(clampGroupSize(2.9)).toBe(2);
    expect(clampGroupSize(7)).toBe(3);
    expect(clampGroupSize(Number.NaN)).toBe(1);
  });
});

describe("groupWords", () => {
  const timed = resolveWordTimings(scheduleWords("a b c d e", 10), 10);

  it("keeps one word per beat at groupSize 1", () => {
    const groups = groupWords(timed, 1);
    expect(groups).toHaveLength(5);
    expect(groups[1]).toMatchObject({ startFrame: 10, endFrame: 20 });
  });

  it("spans a beat from its first word start to its last word end", () => {
    const groups = groupWords(timed, 2);
    expect(groups).toHaveLength(3);
    expect(groups[0]).toMatchObject({ startFrame: 0, endFrame: 20 });
    expect(groups[2].words.map((w) => w.text)).toEqual(["e"]);
  });
});

describe("activeGroupIndex", () => {
  const groups = groupWords(
    resolveWordTimings(scheduleWords("a b c d", 10), 10),
    2,
  );

  it("returns -1 before the first word and after the last", () => {
    expect(activeGroupIndex(groups, -1)).toBe(-1);
    expect(activeGroupIndex(groups, 40)).toBe(-1);
  });

  it("switches beats exactly on the boundary frame", () => {
    expect(activeGroupIndex(groups, 0)).toBe(0);
    expect(activeGroupIndex(groups, 19)).toBe(0);
    expect(activeGroupIndex(groups, 20)).toBe(1);
    expect(activeGroupIndex(groups, 39)).toBe(1);
  });
});

describe("SAFE_AREA_BOTTOM_PCT", () => {
  it("lifts 9:16 captions well above the feed chrome", () => {
    expect(SAFE_AREA_BOTTOM_PCT["9:16"]).toBeGreaterThan(
      SAFE_AREA_BOTTOM_PCT["1:1"],
    );
    expect(SAFE_AREA_BOTTOM_PCT["1:1"]).toBeGreaterThan(
      SAFE_AREA_BOTTOM_PCT["16:9"],
    );
  });
});

describe("CAPTION_LOOKS (the premium presets)", () => {
  it("sizes captions at 11–13% of the frame's short side, not 2.8%", () => {
    // The old default was 54px on a 1080-wide frame — 5% of the short side, and a
    // subtitle rather than a caption. Every loud preset now lands in the band that
    // burned-in captions actually occupy.
    for (const key of ["beast", "hormozi", "pop"] as const) {
      expect(CAPTION_LOOKS[key].sizeRatio).toBeGreaterThan(0.1);
      expect(CAPTION_LOOKS[key].sizeRatio).toBeLessThan(0.14);
    }
  });

  it("gives every loud preset a real outline — that is what makes it legible on footage", () => {
    for (const key of ["beast", "hormozi", "pop"] as const) {
      expect(CAPTION_LOOKS[key].strokeRatio).toBeGreaterThan(0.05);
    }
    // `clean` is the quiet one and deliberately carries none.
    expect(CAPTION_LOOKS.clean.strokeRatio).toBe(0);
  });

  it("uses a display weight, not a UI weight", () => {
    for (const key of ["beast", "hormozi", "pop"] as const) {
      expect(CAPTION_LOOKS[key].weight).toBeGreaterThanOrEqual(800);
    }
  });

  it("shouts in caps only where the look calls for it", () => {
    expect(CAPTION_LOOKS.beast.uppercase).toBe(true);
    expect(CAPTION_LOOKS.hormozi.uppercase).toBe(true);
    expect(CAPTION_LOOKS.pop.uppercase).toBe(false);
    expect(CAPTION_LOOKS.clean.uppercase).toBe(false);
  });
});

describe("popScale", () => {
  const fps = 30;

  it("starts at 1 and springs up to the peak", () => {
    expect(popScale(20, 20, fps, 1.14)).toBeCloseTo(1, 3);
    const settled = popScale(20 + 14, 20, fps, 1.14);
    expect(settled).toBeGreaterThan(1.05);
  });

  it("overshoots — a caption that eases politely into place is a lower third", () => {
    const samples = Array.from({ length: 16 }, (_, i) =>
      popScale(20 + i, 20, fps, 1.2),
    );
    expect(Math.max(...samples)).toBeGreaterThan(1.2);
  });

  it("does not move at all before the word is spoken", () => {
    expect(popScale(10, 20, fps, 1.14)).toBeCloseTo(1, 6);
  });
});

describe("real transcripts (the reason the old API was unusable)", () => {
  const SRT = `1
00:00:01,000 --> 00:00:02,500
You are losing

2
00:00:02,500 --> 00:00:04,000
three hours every week

3
00:00:06,000 --> 00:00:07,200
to manual invoices
`;

  it("parses an .srt, commas and dots alike", () => {
    expect(srtTimeToMs("00:00:01,000")).toBe(1000);
    expect(srtTimeToMs("00:00:01.250")).toBe(1250);
    expect(srtTimeToMs("01:02:03,004")).toBe(3723004);
    expect(srtTimeToMs("nonsense")).toBeNull();
  });

  it("reads a whole .srt into captions", () => {
    const caps = parseSrt(SRT);
    expect(caps).toHaveLength(3);
    expect(caps[0]).toEqual({
      text: "You are losing",
      startMs: 1000,
      endMs: 2500,
    });
    expect(caps[2].startMs).toBe(6000);
  });

  it("explodes a multi-word cue so the active-word highlight has something to track", () => {
    const words = explodeCue({
      text: "three hours every",
      startMs: 0,
      endMs: 3000,
    });
    expect(words.map((w) => w.text)).toEqual(["three", "hours", "every"]);
    expect(words[0].startMs).toBe(0);
    expect(words[1].startMs).toBe(1000);
    expect(words[2].endMs).toBe(3000);
  });

  it("leaves word-level Whisper output alone — it is already one word per cue", () => {
    const one = { text: "three", startMs: 0, endMs: 400 };
    expect(explodeCue(one)).toEqual([one]);
  });

  it("converts milliseconds to frames at the composition's rate", () => {
    expect(msToFrame(1000, 30)).toBe(30);
    expect(msToFrame(500, 60)).toBe(30);
    const words = captionsToWords(parseSrt(SRT), 30);
    expect(words[0].text).toBe("You");
    expect(words[0].startFrame).toBeCloseTo(30, 5); // 1000ms at 30fps
  });
});

describe("buildPages (pages from the speech, not a fixed chop)", () => {
  const w = (text: string, startFrame: number, endFrame: number) => ({
    text,
    startFrame,
    endFrame,
  });

  it("breaks a page where the speaker pauses", () => {
    const pages = buildPages(
      [
        w("You", 0, 5),
        w("are", 5, 10),
        w("losing", 10, 15),
        w("three", 60, 65),
      ],
      { maxWords: 8, maxChars: 80, maxGapFrames: 12 },
    );
    expect(pages).toHaveLength(2);
    expect(pages[0].words.map((x) => x.text)).toEqual(["You", "are", "losing"]);
    expect(pages[1].words.map((x) => x.text)).toEqual(["three"]);
  });

  it("breaks on the character budget — that is what stops a page wrapping into a tower", () => {
    const words = ["alpha", "bravo", "charlie", "delta"].map((t, i) =>
      w(t, i * 5, i * 5 + 5),
    );
    const pages = buildPages(words, {
      maxWords: 10,
      maxChars: 14,
      maxGapFrames: 999,
    });
    expect(pages.length).toBeGreaterThan(1);
    for (const page of pages) {
      const chars = page.words.reduce((n, x) => n + x.text.length + 1, 0);
      expect(chars).toBeLessThanOrEqual(14 + 1);
    }
  });

  it("breaks on the word cap", () => {
    const words = Array.from({ length: 7 }, (_, i) =>
      w("hi", i * 5, i * 5 + 5),
    );
    const pages = buildPages(words, {
      maxWords: 3,
      maxChars: 999,
      maxGapFrames: 999,
    });
    expect(pages.map((p) => p.words.length)).toEqual([3, 3, 1]);
  });

  it("every page is contiguous and in order — a scrub can never show a page twice", () => {
    const words = Array.from({ length: 12 }, (_, i) =>
      w(`w${i}`, i * 6, i * 6 + 6),
    );
    const pages = buildPages(words, {
      maxWords: 4,
      maxChars: 999,
      maxGapFrames: 999,
    });
    for (let i = 1; i < pages.length; i++) {
      expect(pages[i].startFrame).toBeGreaterThanOrEqual(pages[i - 1].endFrame);
    }
    expect(pages.flatMap((p) => p.words)).toHaveLength(12);
  });

  it("survives an empty transcript", () => {
    expect(
      buildPages([], { maxWords: 4, maxChars: 20, maxGapFrames: 10 }),
    ).toEqual([]);
  });
});
