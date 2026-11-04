import { type ComponentConfig, FPS, H, W } from "@/lib/customizer-config";

export const phoneStackConfig: ComponentConfig = {
  componentName: "PhoneStack",
  importPath: "@/components/snap-cn/phone-stack",
  controls: {
    stagger: {
      type: "number",
      default: 14,
      min: 6,
      max: 30,
      step: 1,
      label: "Frames between screens",
    },
    time: { type: "text", default: "9:41", label: "Status bar time" },
    background: { type: "color", default: "#f3f3ee", label: "Page" },
    glowColor: { type: "color", default: "#cdb4e6", label: "Glow" },
    statusColor: { type: "color", default: "#ffffff", label: "Status bar" },
  },
  // Five screens 14 frames apart, the last settled by ~82, then a hold.
  durationInFrames: 120,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
  previewBackdrop: { type: "color", value: "#f3f3ee" },
};
