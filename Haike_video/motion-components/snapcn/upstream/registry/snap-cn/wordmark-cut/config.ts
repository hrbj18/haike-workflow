import {
  type ComponentConfig,
  FONT_FAMILY_CONTROL,
  FPS,
  H,
  W,
} from "@/lib/customizer-config";

export const wordmarkCutConfig: ComponentConfig = {
  componentName: "WordmarkCut",
  importPath: "@/components/snap-cn/wordmark-cut",
  controls: {
    word: { type: "text", default: "snapcn.", label: "Wordmark" },
    dotFrom: {
      type: "color",
      default: "#3072db",
      label: "Gradient (deep end)",
      brand: "accent",
    },
    dotTo: {
      type: "color",
      default: "#4fd8f5",
      label: "Gradient (light end)",
      brand: "accent",
    },
    warm: {
      type: "number",
      default: 1,
      min: 0,
      max: 1,
      step: 0.05,
      label: "Light",
    },
    theme: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
    fontFamily: FONT_FAMILY_CONTROL,
  },
  // `speed` is appended from SHARED_CONTROLS in registry/__index__.tsx.
  durationInFrames: 66,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
  // The scene paints its own page; the stage only has to not fight it.
  previewBackdrop: { type: "color", value: "#faf9f6" },
};
