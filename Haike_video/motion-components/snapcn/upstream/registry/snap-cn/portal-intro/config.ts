import {
  type ComponentConfig,
  FONT_FAMILY_CONTROL,
  FPS,
  H,
  W,
} from "@/lib/customizer-config";

export const portalIntroConfig: ComponentConfig = {
  componentName: "PortalIntro",
  importPath: "@/components/snap-cn/portal-intro",
  controls: {
    lead: {
      type: "text",
      default: "your launch video",
      label: "Before the chip",
    },
    trail: { type: "text", default: "in code", label: "After the chip" },
    title: { type: "text", default: "Introducing", label: "Title" },
    brand: { type: "text", default: "snapcn", label: "Name" },
    mode: {
      type: "select",
      default: "light",
      options: ["light", "dark"],
      label: "Theme",
    },
    fontFamily: FONT_FAMILY_CONTROL,
  },
  durationInFrames: 108,
  fps: FPS,
  compositionWidth: W,
  compositionHeight: H,
};
