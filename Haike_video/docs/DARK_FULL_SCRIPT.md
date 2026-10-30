# 完整动效模板：脚本与素材 CLI

入口 `scripts/dark_full_script.py`，业务模块 `backlot/studio_dark_full_script.py`。使用本项目 `.venv`。本入口只准备输入；合成仍由现有 `dark_full.py` 和统一队列执行，不生成数字人、不发布。

## 输入合同

可用 `--script-file` 传 UTF-8 文稿或含 `text` 的原稿 JSON，配合 `--recipe` 传完整模板素材配方。也可用 `--request` 传一个 JSON：

```json
{
  "title": "到店体验",
  "script": "完整原文……",
  "recipe": {"title": "作品名", "props": {}, "sources": {}, "audio": {}, "provenance": {}, "shotPlan": []},
  "voice_performance": {
    "performance_intent": "平稳说明现场，末句温和邀请",
    "pacing_profile": "沿用已选音色倍率",
    "energy_curve": "位置清楚，内容具体，邀请轻强调",
    "pause_policy": "保留原标点，不向不支持的供应商注入SSML"
  },
  "motion_events": [
    {"sceneId": "scene-1", "cueId": "category_1", "src": "tick.wav", "gainDb": -24, "transientOffsetSeconds": 0}
  ]
}
```

`recipe` 使用 `studio_dark_full.preflight` 同一合同，必须有真实素材、封面、字体、取段看帧证据和完整动作 `shotPlan`。`motion_events` 根据本次规划后的场景起点和局部 cue 重算全局音效时钟；新口播不能直接继承旧片音效入点。

首次检查先调用 `registry.provider_menu_summary()`，再读当前账号实际音色偏好和字幕配置。缺少配置时返回中文 `needs_voice`，不选择新供应商。报价使用当前音色条目公开的 model/voice/rate，随后由现有 AudioCenter 冻结真实供应商快照。

## 分阶段操作

在 `Haike_video` 目录运行，项目目录和预算路径使用明确的绝对本地路径：

```powershell
.venv/Scripts/python.exe scripts/dark_full_script.py check --directory C:/work/sample --script-file C:/work/script.txt --recipe C:/work/recipe.json --voice-performance C:/work/delivery.json --events C:/work/events.json
.venv/Scripts/python.exe scripts/dark_full_script.py quote --directory C:/work/sample --stage tts
.venv/Scripts/python.exe scripts/dark_full_script.py confirm --directory C:/work/sample --stage tts --max-charge-micros 500000 --project-max-micros 1000000 --budget C:/work/budget.json --confirmed
.venv/Scripts/python.exe scripts/dark_full_script.py quote --directory C:/work/sample --stage asr
.venv/Scripts/python.exe scripts/dark_full_script.py confirm --directory C:/work/sample --stage asr --max-charge-micros 100000 --project-max-micros 1000000 --budget C:/work/budget.json --confirmed
.venv/Scripts/python.exe scripts/dark_full_script.py resume --directory C:/work/sample --stage asr
.venv/Scripts/python.exe scripts/dark_full_script.py export --directory C:/work/sample
```

`quote` 不提交生成；`confirm --confirmed` 是付费边界，先保存 facade 意图和预算，再委托现有 AudioCenter/SDK 的持久操作。`resume` 使用保存的同一 operation/intent，不重新报价，不换服务。结果不明时保留预留费用；供应商直连的 `charged_micros=null` 不当作免费。共同预算文件里的其他任务和原 ASR 预留不会被清空。

状态依次为 `needs_voice → needs_alignment → needs_review → ready`；没有真实音轨或时间戳时不能导出。ASR 逐词边界与脚本全文必须匹配；不按字数分摊句子时间。新音轨只转码为完整 PCM，不加速、截断、补语音或按数字人帧率取整。新口播不会继承旧数字人。

获得实际口播后，允许修订镜头与合法尾部留白，而不改文稿或生成另一次配音：

```powershell
.venv/Scripts/python.exe scripts/dark_full_script.py plan --directory C:/work/sample --recipe C:/work/revised-recipe.json
.venv/Scripts/python.exe scripts/dark_full_script.py export --directory C:/work/sample
```

修订配方写入独立带 SHA 的历史文件。原文稿、语音报价和操作编号仍不可变。配方超出素材已看区间或动作最低时长时，由同一 adapter 拒绝导出；不能冻结、循环或拉伸素材补长。

## 零新增调用复用

可在请求中加入 `reuse`，或通过 `--reuse` 传以下 JSON；路径都须明确指向原始记录：

```json
{
  "script": "C:/work/original/script.json",
  "voice_info": "C:/work/original/voice-info.json",
  "captions": "C:/work/original/captions.json"
}
```

复用同时核验原脚本、当前账号原 AudioCenter 成功操作中的真实 `request.text`、供应商 preview 与原 WAV 的完整 PCM/样本时钟，以及原字幕文件 SHA 和全文。只有声明一个相同 SHA 不够。支持既有 `provider-word-timestamps` 字幕容器及标准 caption 数组；只转换真实秒/毫秒，不生成新时间。验证后再次 `quote tts` 返回 `cached`，不新建收费报价。

## 测试

`tests/backlot/test_studio_dark_full_script.py` 使用假供应商和真实 PCM/持久文件，覆盖未配置、查询不收费、上限、账号变化、未知提交恢复、陈旧进程状态、文稿变更、PCM篡改、真实词边界、原任务缓存证据、配方修订和共同预算保留。Windows 测试应使用独立 C 盘 `--basetemp` 和 `-p no:cacheprovider`，避免系统 Temp 的清理权限问题。

单元测试通过不代表连续听音、最终编码或口型通过；这些仍在成片验收阶段完成。
