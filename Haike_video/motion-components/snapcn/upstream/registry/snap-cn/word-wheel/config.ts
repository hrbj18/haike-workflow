import {
  type ComponentConfig,
  FONT_FAMILY_CONTROL,
  FPS,
  H,
  W,
} from "@/lib/customizer-config";

/**
 * The reel, in order, starting on the word it comes to rest on.
 *
 * Index 0 is what sits in the slot before the roll and after it: left at the
 * list's own length, `spin` carries the column exactly one turn, so the scene
 * shows its answer, spins it away and brings it back. Everything between is
 * what flashes past, and it is worth writing that list as the audiences you
 * actually want reading the sentence.
 */
const REEL =
  "Launches, Founders, Indie hackers, Agencies, Designers, Startups, Dev tools, Solo builders, Changelogs";

export const wordWheelConfig: ComponentConfig = {
  componentName: "WordWheel",
  importPath: "@/components/snap-cn/word-wheel",
  controls: {
    headline: { type: "text", default: "snapcn for", label: "Lead-in" },
    words: { type: "text", default: REEL, label: "Reel (comma separated)" },
    spin: {
      type: "number",
      default: 9,
      min: 1,
      max: 40,
      step: 1,
      label: "Rows travelled",
    },
    mode: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
    fontFamily: FONT_FAMILY_CONTROL,
  },
  // The roll runs out at 1.842s; the rest is the sentence sitting there being
  // read. 66 frames at 30 leaves it up for eleven.
  durationInFrames: 66,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
};
