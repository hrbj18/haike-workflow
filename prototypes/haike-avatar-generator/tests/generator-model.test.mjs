import { test } from "node:test";
import assert from "node:assert/strict";
import { TEMPLATES, validateInputs } from "../src/generator-model.js";
const ready = () => ({ templateId: TEMPLATES[2].id, text: "海客科技", soundMode: "audio", audio: { name: "我的口播.wav", duration: 12 }, portrait: { name: "人物.png" }, voiceId: "voice-a", rate: 1.2, title: "", subtitles: true });
test("已有音频无需配置配音模型", () => { assert.equal(validateInputs(ready(), []), null); });
test("未配置的音色不能通过校验", () => { assert.equal(validateInputs({ ...ready(), soundMode: "voice" }, []).field, "voice"); });
test("缺文案、图片与音频分别定位必填项", () => {
  assert.equal(validateInputs({ ...ready(), text: "  " }, []).field, "text");
  assert.equal(validateInputs({ ...ready(), portrait: null }, []).field, "portrait");
  assert.equal(validateInputs({ ...ready(), audio: null }, []).field, "audio");
});
test("未知模板和超长文案不默默替换或截断", () => {
  assert.equal(validateInputs({ ...ready(), templateId: "unknown" }, []).field, "template");
  assert.equal(validateInputs({ ...ready(), text: "字".repeat(5001) }, []).field, "text");
  assert.equal(validateInputs({ ...ready(), text: "字".repeat(5000) }, []), null);
});
