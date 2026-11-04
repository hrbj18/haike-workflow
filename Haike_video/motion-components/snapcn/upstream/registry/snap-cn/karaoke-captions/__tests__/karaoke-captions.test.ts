/**
 * Unit tests for pure helpers in registry/snap-cn/karaoke-captions/index.tsx.
 *
 * Run with:
 *   pnpm vitest run registry/snap-cn/karaoke-captions
 *
 * No React DOM or Remotion player needed — only pure JS logic is exercised.
 */

import { describe, expect, it } from "vitest";
import { defaultDarkTheme, defaultLightTheme } from "@/lib/snap-cn-ui";

import {
  activeLineIndex,
  CAPTION_SAFE_AREAS,
  type CaptionLine,
  emphasisIndices,
  fillProgress,
  karaokePalette,
  LINE_FADE_FRAMES,
  linesFromCaptions,
  linesFromText,
  parseSrt,
  splitWords,
  srtTimeToMs,
  wordWindows,
} from "../index";

describe("splitWords", () => {
  it("splits on any whitespace and drops empties", () => {
    expect(splitWords("  Acme  ships\tfast \n")).toEqual([
      "Acme",
      "ships",
      "fast",
    ]);
  });

  it("returns [] for blank input", () => {
    expect(splitWords("   ")).toEqual([]);
  });
});

describe("wordWindows", () => {
  const line: CaptionLine = {
    text: "one two three four",
    startFrame: 20,
    endFrame: 100,
  };

  it("splits the line window evenly when no wordTimings", () => {
    const windows = wordWindows(line);
    expect(windows).toHaveLength(4);
    expect(windows[0]).toEqual({ start: 20, end: 40 });
    expect(windows[3]).toEqual({ start: 80, end: 100 });
    // Contiguous coverage: each word starts where the previous ends.
    for (let i = 1; i < windows.length; i++) {
      expect(windows[i].start).toBeCloseTo(windows[i - 1].end, 9);
    }
  });

  it("uses wordTimings as absolute per-word start frames", () => {
    const timed: CaptionLine = {
      ...line,
      wordTimings: [20, 30, 55, 70],
    };
    const windows = wordWindows(timed);
    expect(windows[0]).toEqual({ start: 20, end: 30 });
    expect(windows[1]).toEqual({ start: 30, end: 55 });
    expect(windows[2]).toEqual({ start: 55, end: 70 });
    // Last word runs to the line's endFrame.
    expect(windows[3]).toEqual({ start: 70, end: 100 });
  });

  it("pads short wordTimings with the last timing", () => {
    const short: CaptionLine = { ...line, wordTimings: [20, 40] };
    const windows = wordWindows(short);
    expect(windows).toHaveLength(4);
    expect(windows[2].start).toBe(40);
    expect(windows[3].end).toBe(100);
  });

  it("returns [] for an empty line", () => {
    expect(wordWindows({ text: "", startFrame: 0, endFrame: 10 })).toEqual([]);
  });
});

describe("fillProgress", () => {
  const window = { start: 10, end: 20 };

  it("is 0 before the window and 1 after", () => {
    expect(fillProgress(0, window)).toBe(0);
    expect(fillProgress(10, window)).toBe(0);
    expect(fillProgress(25, window)).toBe(1);
  });

  it("sweeps linearly inside the window", () => {
    expect(fillProgress(15, window)).toBeCloseTo(0.5, 9);
    expect(fillProgress(12, window)).toBeCloseTo(0.2, 9);
  });

  it("degrades to a step for zero-length windows", () => {
    expect(fillProgress(4, { start: 5, end: 5 })).toBe(0);
    expect(fillProgress(5, { start: 5, end: 5 })).toBe(1);
  });
});

describe("emphasisIndices", () => {
  const text = "Acme reconciles every transaction automatically";

  it("matches words case-insensitively", () => {
    expect(emphasisIndices(text, "AUTOMATICALLY")).toEqual([4]);
  });

  it("matches multiple comma-separated words", () => {
    expect(emphasisIndices(text, "acme, transaction")).toEqual([0, 3]);
  });

  it("ignores surrounding punctuation on words", () => {
    expect(emphasisIndices("Ship it, fast!", "it,fast")).toEqual([1, 2]);
  });

  it("returns [] for empty emphasize", () => {
    expect(emphasisIndices(text, "")).toEqual([]);
    expect(emphasisIndices(text, " , ")).toEqual([]);
  });
});

describe("linesFromText", () => {
  it("builds a single line with resolved emphasis indices", () => {
    const lines = linesFromText("Acme ships fast", "fast", 10, 120);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toEqual({
      text: "Acme ships fast",
      startFrame: 10,
      endFrame: 120,
      emphasize: [2],
    });
  });

  it("keeps endFrame after startFrame", () => {
    const lines = linesFromText("hi", "", 30, 5);
    expect(lines[0].endFrame).toBeGreaterThan(lines[0].startFrame);
  });
});

describe("activeLineIndex", () => {
  const lines: CaptionLine[] = [
    { text: "a", startFrame: 0, endFrame: 30 },
    { text: "b", startFrame: 30, endFrame: 60 },
  ];

  it("picks the line whose window contains the frame", () => {
    expect(activeLineIndex(lines, 10, 0)).toBe(0);
    expect(activeLineIndex(lines, 45, 0)).toBe(1);
  });

  it("prefers the newer line when fade-out windows overlap", () => {
    expect(activeLineIndex(lines, 32, LINE_FADE_FRAMES)).toBe(1);
  });

  it("keeps a line active through its fade-out tail", () => {
    expect(activeLineIndex(lines, 65, LINE_FADE_FRAMES)).toBe(1);
    expect(
      activeLineIndex(lines, 60 + LINE_FADE_FRAMES, LINE_FADE_FRAMES),
    ).toBe(-1);
  });

  it("returns -1 outside all lines", () => {
    expect(activeLineIndex(lines, 200, 0)).toBe(-1);
    expect(activeLineIndex([], 0)).toBe(-1);
  });
});

describe("design tokens", () => {
  it("sweeps muted → ink, taking both ends from the theme", () => {
    const light = karaokePalette(defaultLightTheme);
    expect(light.base).toBe(defaultLightTheme.mutedForeground);
    expect(light.fill).toBe(defaultLightTheme.foreground);
  });

  it("follows the dark theme rather than a second hardcoded ramp", () => {
    const dark = karaokePalette(defaultDarkTheme);
    expect(dark.base).toBe(defaultDarkTheme.mutedForeground);
    expect(dark.fill).toBe(defaultDarkTheme.foreground);
    expect(dark.fill).not.toBe(karaokePalette(defaultLightTheme).fill);
  });

  it("carries a user's token override into the pill", () => {
    const themed = karaokePalette({ ...defaultLightTheme, border: "#ABCDEF" });
    expect(themed.pillBorder).toBe("#ABCDEF");
  });

  it("defines safe areas for all aspect presets", () => {
    expect(Object.keys(CAPTION_SAFE_AREAS).sort()).toEqual([
      "landscape",
      "portrait",
      "square",
    ]);
  });
});

describe("real transcripts", () => {
  const SRT = `1
00:00:01,000 --> 00:00:03,000
Acme reconciles every transaction

2
00:00:05,000 --> 00:00:06,500
automatically
`;

  it("parses srt timestamps, commas and dots alike", () => {
    expect(srtTimeToMs("00:00:01,000")).toBe(1000);
    expect(srtTimeToMs("00:00:01.500")).toBe(1500);
    expect(srtTimeToMs("garbage")).toBeNull();
  });

  it("reads an .srt into captions", () => {
    const caps = parseSrt(SRT);
    expect(caps).toHaveLength(2);
    expect(caps[0].text).toBe("Acme reconciles every transaction");
    expect(caps[1].startMs).toBe(5000);
  });

  it("builds caption LINES from ms captions, one timing per word", () => {
    const lines = linesFromCaptions(parseSrt(SRT), 30);
    // The 2s pause splits them into two lines.
    expect(lines).toHaveLength(2);
    expect(lines[0].text).toBe("Acme reconciles every transaction");
    expect(lines[0].wordTimings).toHaveLength(4);
    // 1000ms at 30fps = frame 30
    expect(lines[0].startFrame).toBeCloseTo(30, 5);
    // words spread across their own cue, in order
    const t = lines[0].wordTimings ?? [];
    for (let i = 1; i < t.length; i++) expect(t[i]).toBeGreaterThan(t[i - 1]);
  });

  it("collapses word-level Whisper output into lines instead of one line per word", () => {
    const words = ["Acme", "reconciles", "every"].map((text, i) => ({
      text,
      startMs: i * 400,
      endMs: i * 400 + 380,
    }));
    const lines = linesFromCaptions(words, 30);
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toBe("Acme reconciles every");
    expect(lines[0].wordTimings).toHaveLength(3);
  });

  it("survives an empty transcript", () => {
    expect(linesFromCaptions([], 30)).toEqual([]);
  });
});
