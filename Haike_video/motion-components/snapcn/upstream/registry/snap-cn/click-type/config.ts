import { type ComponentConfig, FPS, H, W } from "@/lib/customizer-config";

export const clickTypeConfig: ComponentConfig = {
  componentName: "ClickType",
  importPath: "@/components/snap-cn/click-type",
  controls: {
    placeholder: {
      type: "text",
      default: "Describe what you want to build...",
      label: "Placeholder",
    },
    prompt: {
      type: "text",
      default: "Build me a marketing site",
      label: "Prompt",
    },
    hint: { type: "text", default: "New suggestion", label: "Hint" },
    accentColor: {
      type: "color",
      default: "#3577e0",
      label: "Wash",
      brand: "accent",
    },
    mode: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
  },
  // `clickTypeFrames()` for the default prompt, evaluated — a config cannot
  // import a .tsx (registry/__tests__/demo-durations.test.ts checks it).
  durationInFrames: 103,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
};
