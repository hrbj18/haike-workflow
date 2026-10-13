export const EXAMPLE_TEXT = "海客科技，让创作更简单。一个接口，连接配音、数字人和创作工作流。";
export const TEMPLATES = [
  { id: "avatar-safe-circle-v1", name: "模板1 · 圆框口播", ratio: "9:16", description: "素材卡片", poster: "template1-layout.png", kind: "布局示意" },
  { id: "avatar-full-width-v2", name: "模板2 · 全宽讲解", ratio: "9:16", description: "全宽素材带", poster: "template2-layout.png", kind: "布局示意" },
  { id: "avatar-template3-card-3x4-v001", name: "模板3 · 卡片讲解", ratio: "3:4", description: "白卡与章节", poster: "template3-poster.png", kind: "真实样片", sample: "template3-sample.mp4" },
];
export function validateInputs(input, availableVoices) {
  if (!TEMPLATES.some(t => t.id === input.templateId)) return { field: "template", message: "请选择一个可用模板。" };
  if (!input.text.trim()) return { field: "text", message: "请上传文案，或在文案框中粘贴内容。" };
  if ([...input.text].length > 5000) return { field: "text", message: "口播文案最多5,000字，请精简后再试。" };
  if (input.soundMode === "audio" && !input.audio) return { field: "audio", message: "请选择或上传一份口播音频。" };
  if (input.soundMode === "voice" && !availableVoices.some(v => v.id === input.voiceId)) return { field: "voice", message: "请在API设置连接海客Key，再选择可用配音模型。" };
  if (!["audio", "voice"].includes(input.soundMode)) return { field: "audio", message: "请选择声音来源。" };
  if (!input.portrait) return { field: "portrait", message: "请上传人物正面图片。" };
  return null;
}
