# 阿里云百炼配音与识别

本机开发能力，入口 `/audio`；内部供应商 ID 为 `bailian`，与旧版 `dashscope` 工具独立。

## 使用

1. 配音中心的「API 管理」默认收起；点击展开后，在「配置服务」下拉框选择阿里云百炼或腾讯云。切换服务和收起面板保留本页未保存的输入，刷新页面会清空草稿。保存百炼 API Key（北京地域）时仅写入忽略提交的 `.env.secrets.local`，接口只返回是否已配置。留空不覆盖已有密钥。
2. 分别点击 TTS、ASR「测试连通」。ASR 测试会先合成短句再转写，因此两种服务都会产生用量；成功状态带测试时间。
3. 云端音色管理选择「阿里云百炼配音」，填写名称和原始音色 ID。支持模型 `qwen-audio-3.1-tts-flash` 与 `cosyvoice-v3.5-flash`；模型随每条音色保存，语速范围 0.5–2.0，默认 1.0。CosyVoice 复刻音色须选择创建时绑定的同名模型，模型错配在云端提交前拒绝。
4. 添加只保存本地记录，试听才验证实际权限。可选择试听、调整语速、设为通用默认、删除记录；开始的旁白/审核预览任务保存音色参数快照。
5. 项目中需要识别素材声音时，在识别引擎选「阿里云百炼」。模型为 `qwen-audio-3.1-asr-flash-filetrans`，复用素材识别流程及缓存，保留句级与词级秒制时间戳。

## 工作台上传创建音色（2026-10-10）

配音中心「音色管理 → 配音服务 → 百炼云端克隆音色」显示专用上传表单，其他服务隐藏此表单。上传参考录音后调用 `voice-enrollment/create_voice`，保存返回 ID 并查询审核；`OK` 后登记为配音音色，保留原默认。默认模型 `cosyvoice-v3.5-flash`，也支持 `qwen-audio-3.1-tts-flash`。无需本地 TTS，无需逐字原文。

首次需在 API 管理高级设置填写已有私有 OSS 地址、Bucket、专用 AccessKey，并安装主 requirements 中的 `oss2`。克隆上传独立于 ASR 的 temporary/oss 选择。音频支持 WAV/MP3/M4A、≤10 MB、5–60 秒，推荐 10–20 秒单人清晰朗读；用 FFmpeg 转为 PCM16/单声道/24 kHz，自动私有上传和一小时签名 URL。百炼要求公网可获取的 URL；没有将 ASR 临时 `oss://` 支持臆测成声音复刻能力。创建成功或确定失败后清理对象；中断/待审核保留对象，建议 `haike-voice-clones/` 生命周期兜底。

任务在 `.backlot/audio/bailian-clones/` 保存 ID、模型和状态，不记录签名 URL、密钥或原始录音。相同录音+模型+账号复用任务；查询/本机登记失败只恢复已有 ID。创建结果不明不自动重发，核对云端后按已有 ID 添加。UI“移除音色”只移除本机记录，不远端删除。`POST /api/audio-center/bailian-clones` 为有上传授权确认的创建入口；`GET` 读取状态；`POST /{id}/resume` 仅查询已有 ID 并登记。

真实 FFmpeg 与模拟 OSS/百炼接口回归覆盖成功、超时、云端拒绝、审核中、登记失败恢复、账号变化、默认保留、重复创建防护和上传边界；尚未调用真实 Bucket/声音复刻接口。官方依据：[声音复刻 HTTP](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[参考录音要求](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)。

## ASR 音轨存储

- 默认临时上传：不需另外配置 OSS；提取的音轨上传百炼临时存储，约 48 小时过期。当前适配器限制单个上传文件不超过 1 GB。
- 可选自有私有 OSS：安装 `requirements-asr.txt`，在高级设置填写 OSS 地域、Bucket、AccessKey；上传私有对象，使用有效期 48 小时的签名地址；转写完成后尝试删除。建议为 `haike-asr/` 设置生命周期，以处理进程中断和清理失败。未配置此模式也能使用默认 ASR。
- 清除密钥同时清除本机百炼 API Key 和专用 OSS 凭据；保留音色记录及已生成音频。

## 生成与恢复

- TTS 使用 `/services/audio/tts/SpeechSynthesizer`，不使用旧 Qwen3 的 multimodal-generation 接口。文本最多 20000 字符，按不超过 400 字符分段；每段落账、独立恢复下载，最终合并为 PCM16/单声道/24 kHz WAV。时长以实际音频样本为准。
- 输出旁保存 `.wav.bailian.json`，含模型、音色、语速、请求 ID、用量及人民币目录价估算。Qwen-Audio 3.1 按输入/输出 Token 估算；CosyVoice 3.5 Flash 按供应商返回的 `usage.characters` 计算，目录价为每万字符 0.8 元（2026-10-09 核对）。页面按音色模型显示对应计费单位。估算不等于账号账单，不把它伪装为美元费用。
- ASR 先保存提交状态，再保存供应商任务 ID；查询或下载失败后复用同一任务。任务记录位于项目 `artifacts/asr/<素材>/bailian/`；调用结果不明时停止，避免自动重复计费。
- `submitting` 且没有供应商任务 ID 的记录需要人工核对云端记录。不要删除调用记录来自动重发。云端确定失败的任务也不自动重新收费提交。
- TTS 原始结果与调用记录在输出旁的隐藏目录中保存；不要在恢复前清理。下载地址到期且没有本地音频时，需要明确决定是否重新生成。
- UI「服务可用」表示凭据/模型配置就绪；每个音色是否获得账号授权仍以实际试听为准。

## 验证证据（2026-09-24）

- TTS→ASR 实际调用成功：3.2 秒，识别为「你好，欢迎体验这段语音合成。」且返回时间戳；默认临时上传路径已实测。
- 页面添加 `longanyuanfei_v3.1`，经「生成试听」生成 7.6 秒音频，显示在近期试听；TTS 与 ASR 面板均记录最近测试成功。
- 自动化覆盖凭据脱敏、模型/语速冻结、重复音色、异常 WAV 头修复、下载恢复、提交不明防重复、ASR 查询恢复及时间戳单位。
- 自有 OSS 尚未用真实 Bucket 验收；超长素材及整片数字人生产未在此次短句验收中调用。

## CosyVoice 接入验证（2026-10-09）

- 已有云端复刻音色经工作台正式接口录入并出现在配音中心；保留原通用默认音色。
- 真实短句试听完成：4.56 秒、供应商返回 43 个计费字符，目录价估算 0.00344 元；试听和调用记录保存于本机忽略目录，不在文档记录私有音色 ID。
- 百炼与配音中心离线回归 31 项通过，覆盖模型/语速/计费单位冻结、模型错配阻断、字符费用和下载失败后不重复提交。CosyVoice 长文及整片生产尚未真实验收。

## 实现入口

`lib/bailian_speech.py`（传输/记录）、`tools/audio/bailian_tts.py`（TTS）、`backlot/bailian_asr.py`（ASR）、`backlot/bailian_config.py`（本机配置/测试）、`tests/backlot/test_bailian_speech.py`。

官方契约：[TTS HTTP](https://help.aliyun.com/en/model-studio/cosyvoice-tts-http-api)、[录音文件识别](https://help.aliyun.com/zh/model-studio/fun-asr-recorded-speech-recognition-http-api)、[临时上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url/)。
