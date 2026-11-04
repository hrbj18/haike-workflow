import { type ComponentConfig, FPS, H, W } from "@/lib/customizer-config";

export const buttonPressConfig: ComponentConfig = {
  componentName: "ButtonPress",
  importPath: "@/components/snap-cn/button-press",
  controls: {
    label: { type: "text", default: "Deploy", label: "Label" },
    pending: { type: "text", default: "Deploying…", label: "Pending" },
    done: { type: "text", default: "Deployed", label: "Done" },
    width: {
      type: "number",
      default: 320,
      min: 160,
      max: 600,
      step: 10,
      label: "Width",
    },
    mode: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
  },
  // `BUTTON_PRESS_FRAMES`.
  durationInFrames: 126,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
};
