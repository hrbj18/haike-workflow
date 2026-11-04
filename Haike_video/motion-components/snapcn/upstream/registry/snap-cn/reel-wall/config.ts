import { type ComponentConfig, H, W } from "@/lib/customizer-config";

export const reelWallConfig: ComponentConfig = {
  componentName: "ReelWall",
  importPath: "@/components/snap-cn/reel-wall",
  controls: {
    background: { type: "color", default: "#0e0e0e", label: "Page" },
    cardColor: { type: "color", default: "#1a1a1a", label: "Card" },
  },
  // The reference is 24fps and its wall moves on twos — kept at 24 so every
  // frame here is a frame of the reference. 9s: the fitted ease-in, then cruise.
  durationInFrames: 216,
  fps: 24,
  compositionWidth: W,
  compositionHeight: H,
  previewBackdrop: { type: "color", value: "#0e0e0e" },
};
