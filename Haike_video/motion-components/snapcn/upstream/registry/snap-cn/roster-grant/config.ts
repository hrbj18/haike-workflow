import {
  type ComponentConfig,
  FONT_FAMILY_CONTROL,
  FPS,
  H,
  W,
} from "@/lib/customizer-config";

export const rosterGrantConfig: ComponentConfig = {
  componentName: "RosterGrant",
  importPath: "@/components/snap-cn/roster-grant",
  controls: {
    label: { type: "text", default: "Install all", label: "Button" },
    accentColor: {
      type: "color",
      default: "#3072db",
      label: "Accent",
      brand: "accent",
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
  // `rows` is an array of arrays → not a control; the preview uses SNAPCN_ROSTER.
  durationInFrames: 120,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
  // The scene paints its own page; the stage only has to not fight it.
  previewBackdrop: { type: "color", value: "#faf9f6" },
};
