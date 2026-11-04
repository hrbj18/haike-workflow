import { type ComponentConfig, FPS, H, W } from "@/lib/customizer-config";

export const dotBloomConfig: ComponentConfig = {
  componentName: "DotBloom",
  importPath: "@/components/snap-cn/dot-bloom",
  controls: {
    speed: {
      type: "number",
      default: 1,
      min: 0.5,
      max: 2,
      step: 0.1,
      label: "Speed",
    },
  },
  durationInFrames: 30,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
  // The transition alone, on a black stage.
  previewBackdrop: { type: "color", value: "#000000" },
};
