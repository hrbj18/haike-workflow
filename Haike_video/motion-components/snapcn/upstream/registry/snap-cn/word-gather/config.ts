import {
  type ComponentConfig,
  FONT_FAMILY_CONTROL,
  FPS,
  H,
  W,
} from "@/lib/customizer-config";

export const wordGatherConfig: ComponentConfig = {
  componentName: "WordGather",
  importPath: "@/components/snap-cn/word-gather",
  controls: {
    text: {
      type: "text",
      default: "Every scene is yours to own.",
      label: "Sentence",
    },
    maxWidth: {
      type: "number",
      default: 330,
      min: 120,
      max: 690,
      step: 5,
      label: "Line width",
    },
    accent: { type: "color", default: "", label: "Travelling colour" },
    mode: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
    fontFamily: FONT_FAMILY_CONTROL,
  },
  durationInFrames: 49,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
};
