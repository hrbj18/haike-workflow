# Codex 批次执行入口

首次接入读根 [Agent 教程](../../START_HERE.md)。Agent 理解要求、写稿、检查画面和事实，以下接口负责制作、发布及生成汇报文档；CLI 不内置定时执行器，由各 Agent 宿主负责唤醒和跟进。目前真实账号实跑来自 Codex，其他 Agent 按通用 CLI/HTTP 接入，尚未实跑验证；既有脚本名和任务标识保持兼容。服务按统一配置文档中的实际 Key 路由，支持多个供应商 Key，不要求把全部能力归为一把 Key。

本入口是现有 Studio、TaskCenter、统一制作队列和作品发布计划的薄客户端。
没有独立数据库、守护进程、定时执行器或供应商调用通道。默认只连接本机14756，
先核对 `edition` 和工作区路径；必须在新副本运行。

## 规格和命令

在工作区根目录使用 `Haike_video/.venv/Scripts/python.exe` 调用
`Haike_video/scripts/codex_video_batch.py <command> --spec <JSON>`。
新指令省略口播参数时，先用 `defaults --spec request.json --output spec.json` 补全；
它读取当前账号的口播默认设置并缓存已有形象，未发起报价、制作或发布。
`request.json`仍须有已查证的选题/稿件或用户要求/来源；发布时明确目标账号，仅制作时令 `publishing.targets=[]`。音色、倍率、模板、目标时长、
每条预算、备用授权、联网素材开关、人物图及模型可省略。明确字段优先，false保留；未设置预算或
不可用音色会报缺项，不自行猜金额或换供应商。未指定批次预算时取各条上限之和。
输出规格包含实际参数和预设快照；输出文件已存在时直接读取它继续，改预设不改变旧批次。
然后命令顺序是 `resolve`（只读）、`init`、`prepare`、`submit`，随后用
`status`、`resume`、`report`。也可由宿主唤醒时调用 `advance` 完成一轮推进。
`prepare/submit/status/resume/report/approve/publish/advance` 可加 `--slot <slot_id>`；
`defaults/resolve/init` 处理整个批次。
CLI本身不等待整个云任务完成；队列由已启动的工作台执行。需要重新获取进展时再次调用。

Agent收到“做三条科技视频”等模糊指令时，先读当前账号
`/api/studio/audio-center/avatar-defaults`，再查询模板、账号、查证并去重具体事件。
已有批次直接使用原spec执行status/report/resume；新批次把明确参数写入request，
用defaults补齐省略项并冻结完整spec。默认值齐全且授权范围明确时常规步骤直接推进。
总控先GET `/api/studio/templates`、`/api/studio/audio-center` 和
`/api/studio/publishing` 读取当前模板、音色预设/关联图及平台账号；需要默认计划时
读取 `/api/task-center/plan` 的保存槽位（它不是已启用的调度器）。使用预设补齐省略项，
再用用户本次明确的模板、音色、倍率、图片和预算覆盖，形成完整spec后运行 `resolve`。
本CLI不解析自然语言，也不会把本次override回写为全局默认。
本地明确portrait优先于云关联图；云image_id为空仍保留为空，不能伪造云画像ready。
冻结后记录实际spec、原图SHA和本期上传asset引用。
账号存在且平台匹配即可登记；invalid等状态在resolve标记待恢复，不能阻止其他平台及制作。
账号不存在或平台不符才拒绝，真实平台登录恢复仍由总控和既有发布入口处理。

规格顶层只有 `batch_id`、整数微元 `limit_micros` 和 `items`。每项需要：

```json
{
  "slot_id": "n1",
  "topic_key": "official-specific-event-2026-10-16",
  "sources": [{"url":"https://example.com/announcement","published":"2026-10-16","publisher":"官方","verified":true}],
  "title": "本期短标题",
  "text": "本期已经核实的口播稿。",
  "template_id": "avatar-deepblue-n1-v1",
  "portrait_path": "本机明确授权的人物图绝对路径",
  "voice_id": "本海客账号已有音色ID",
  "model_id": "haike/internal-tts",
  "speech_rate": 1.15,
  "target_duration_seconds": 25,
  "max_charge_micros": 5000000,
  "allow_graphic_fallback": false,
  "network_materials_enabled": true,
  "publishing": {
    "desc": "本期发布详情",
    "topics": "科技,人工智能",
    "source_rights_status": "confirmed",
    "targets": [{"platform":"douyin","account_id":3}]
  }
}
```

N1可另有 `n1` 对象，沿用 `studio_n1.settings`；模板2/3不得携带它。
支持 `avatar-safe-circle-v1`、`avatar-deepblue-n1-v1`、`avatar-full-width-v2`、
`avatar-template3-card-3x4-v001`。语速传入供应商；目标时长只是验收目标，
不能据此拉伸声音或添加停顿。模板2标题最多16字、模板3最多36字；N1三行按现有校验。
`allow_graphic_fallback` 仅记录授权，当前CLI不会自行换图文或绕过结果未知的原付费任务。

`network_materials_enabled` 控制成片画面的自动搜索，与新闻事实查证、数字人降级分开。
新任务使用账号预设；旧预设未配置时关闭，旧冻结规格和v1快照保持原样。
开启后在报价及实际搜索前验证选定抖音素材账号，复用抖音→Pexels链与素材使用权门禁；
快手/视频号目前支持分享链接下载，不能代替抖音关键词搜索登录。
无有效登录或没有合适画面时保留原任务及已完成产物，明确显示原因，再从原任务恢复。
开启的任务需要实际采用合适网络画面，不自动改纯图文或插画；仅搜索到候选不算已采用。
显式关闭的新任务不自动联网；缺少此字段的历史AI任务保持原策略。
原渲染目录`network-materials.json`记录已选待合成与实际采用，任务总览按原队列冻结版本
展示安全素材摘要、预览和公开来源；它不包含Cookie、供应商地址或本机路径。

## 一张人物图、一条完整音轨和要求

完整音轨使用 `audio_path`，不填写 TTS 的 `voice_id/model_id/speech_rate`。其余模板、预算、
标题和 `text`（用户要求或已核实的口播内容）沿用规格。音轨原速使用，目标时长不会截短或拉伸音频；
现有 Studio 限制音轨最长120秒，上传文件格式为 WAV、MP3、M4A 或 OGG。超过限制会明确拒绝。
这与“上传一段样音再克隆音色”分开：样音路线仍先由已有音色中心创建音色，再走 TTS 规格。

```json
{
  "audio_path": "本机完整口播音轨绝对路径.wav",
  "portrait_path": "本机授权人物图绝对路径.png",
  "text": "按照这条完整音频制作竖屏口播，保持原始声音和语速。",
  "sources": [{"kind":"user_provided","label":"用户提供完整音轨与人物图"}],
  "publishing": {"desc":"本期说明","topics":"","source_rights_status":"owned","targets":[]}
}
```

以上是槽位中的音频及来源字段，需与前述 `slot_id/title/template_id` 等共同组成完整规格。
`defaults` 可补齐模板、预算等已保存的参数；完整音轨无需配置可用 TTS 音色。
来源为用户提供时无需编造公开 URL，公开发布仍须确认使用权和事实。
`prepare` 将完整音轨与人物图上传到该草稿，冻结原文件 SHA；实际生成复用 Studio 的
`soundMode=audio`、原生制作队列和 ASR 时钟，不额外生成或替换配音。

仅制作的 `targets=[]` 在出片后显示等待质量检查。Agent 完成技术、画面和事实检查后，
使用 `approve --spec spec.json --evidence reviewed.json` 确认原作品版本；也可用
`advance --evidence reviewed.json`。证据顶层仍是 `batch_id/spec_sha256/items`，
每条只需 `slot_id/video_sha256/quality_report` 以及明确为 true 的
`technical_checks_passed/frame_review_passed/source_claims_verified`。
仅制作验收不需要封面或 `authorized_publication`，不会创建发布计划，完成后显示
“成片已审核完成，仅制作未发布”；后续 report 保留该状态。未经审核或成片 SHA 改变不会完成。

`init`按批次和槽位哈希得到固定draft/client ID，TaskCenter阶段是“代码接入/待制作”。
完整规格、人物图SHA及明确提供的完整音轨SHA保存在本项目 `artifacts/automation/codex-batch/spec.json`，
准备时规格或原文件变化会停止；TaskCenter仅存相对引用、hash、非秘密快照及执行回执，不存原始音频/图片路径。
不要在规格中放API Key、Cookie、密码或签名下载地址。

每项上限之和必须不超过批次限额；失败/未知不回收给其他项，实际结算未知保持null。
`prepare`上传本机人物图及可选完整音轨到本draft并报价，尚不生成；重启优先复用原portrait/audio/revision/quote。
语音模式初始报价只有已知TTS，实际ASR/人物后续仍受本条总上限检查。
报价丢响应但尚未提交供应商时可重新本地报价；不会换生成调用意图。

`submit`在请求前登记请求中状态。丢响应时先查此draft原队列，未确认存在也不重新发。
原队列queued/running只观察，completed不重做，failed且retryable才retry同一job。
`status`只读；`report`同步原作品attempt并将真实阶段写回TaskCenter，
制作完成继续显示“成片已生成，等待Codex质量检查”；不自动要求用户做QA。
已提交、平台审核、登录阻塞及结果未知分别报告，全部目标done且完整验收后才completed。
费用未知独立展示，不据此将成功任务永久标为uncertain。
`report`只读取本槽位项目、冻结revision对应的原`gateway-state.json`，
累计TTS/ASR/数字人等阶段的原报价上限；同一调用意图/报价/任务去重。
`estimated_micros`是已观察报价上限合计，`reserved_micros`是未明确结算的保守敞口，
并非实扣金额。失败、结果未知或读取不到原状态均不清空已有预留；CAS重读后也不降低
更大的已知预留。仅全部受计阶段都有明确settled与扣款金额才汇总actual，
内部供应商成功但采购费未确认仍保持未知。报告不会把原音频、签名地址或凭据写入总账。
普通报告复用PATCH自带阶段事件，只有显式report_now才追加report并应答，
不会假装实现暂停/恢复命令。原始gateway-state和供应商凭据不进入报告。

`report` 与 `advance` 自动写入 UTF-8 Markdown 汇报文档，JSON 返回绝对路径 `report_path`：
`Haike_video/.backlot/codex-batches/batch-<批次hash>/汇报文档.md`。
文档包含各条阶段、队列/作品/发布任务编号、逐平台状态、排期、来源、未知费用及恢复事项，
无需 Agent 手抄台账。重复报告原子更新自动内容；人工分析另存，避免被下一次自动报告覆盖。
`--slot` 写独立槽位文档，保留整批汇报。回执同步暂时不可用时不把已完成发布改判为未提交。

## 夜间三条与恢复

宿主按用户要求定时唤醒 Agent。固定原规格后，调用：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/codex_video_batch.py advance --spec night-spec.json --base http://127.0.0.1:14756
```

首次推进登记、准备、提交到原队列；后续调用读取原任务，不重复制作。队列完成后，Agent
按下节执行真实技术/画面/事实/封面检查，在用户已授权范围内生成原批次证据，再调用：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/codex_video_batch.py advance --spec night-spec.json --evidence approved-evidence.json --base http://127.0.0.1:14756
```

未提供证据时只报告“等待质量检查”，不会伪造审批或发布。已确认的每个目标可包含
`scheduled_at`，例如 `2026-10-18T08:00:00+08:00` 或对应的 UTC 时间；它传入既有
作品发布计划和 CreatorHub，继续受未来时间、账号登录、发布间隔和平台风控约束。
排期不会自行唤醒 Agent 或提前绕过质检。已有发布计划重入继续使用同一 plan/提交键；
中断或丢响应不会新增替代任务。部分槽位失败时其余条目可继续，文档明确记录失败；
`advance` 返回 `ok=false/errors` 且退出码2，不把失败当作完成。已排队等待不是失败。
可恢复的制作失败需显式 `resume` 原槽位；`advance` 不自行反复 retry。
暂停和取消继续使用队列原状态；已取消任务不会被假报为正常等待。

隔离验收入口：`tests/backlot/test_codex_batch.py` 与 `test_codex_batch_flows.py`。
后者从实际 CLI 进入本地 HTTP 路由、Studio、SQLite 队列、制作器和发布计划，
以假供应商/渲染器/发布器覆盖完整音轨单条、三条排期发布、丢响应重入和文档落地。
它不调用真实供应商或账号，不代替另一台机器、真实渲染与真实平台验收。

历史去重使用规范化topic_key及已完成/已提交记录，同标题已发布也会阻止。
来源URL和标题只是辅助证据；同一事件换标题不等于新事件，总控必须先做语义和来源核查。

## 显式发布边界

制作完成不等于允许发布。`publish --evidence <JSON>`还需要：

```json
{
  "batch_id": "与规格相同",
  "spec_sha256": "init返回的完整规格hash",
  "items": [{
    "slot_id": "n1",
    "video_sha256": "当前成片SHA",
    "technical_checks_passed": true,
    "frame_review_passed": true,
    "source_claims_verified": true,
    "authorized_publication": true,
    "cover_path": "本项目内已审封面的绝对路径",
    "cover_sha256": "实际封面SHA",
    "cover_reviewed": true,
    "quality_report": "本项目内技术报告绝对路径",
    "source_rights_status": "confirmed"
  }]
}
```

技术报告须 `status=technical_checks_passed` 且 `video.sha256_after` 一致。
从仓库根目录用本项目 Python 调用 `Haike_video/scripts/codex_video_quality.py`，
必需参数为 `--project <本条项目目录> --video <最终成片> --template <模板ID>`，
已有驱动音轨时另加 `--audio <驱动WAV>`。检查原队列的
`renders/studio-<冻结revision>/avatar-preview.mp4`；`avatar-render.mp4`是Remotion中间片，
不能拿它的QA替代最终封装。逐一检查九宫格、3:4封面和模拟平台UI；模拟与真实播放分开记录。
root/总控实际观看、核事实及复核封面后才能填写人工字段。CLI不把解码当作视觉、
听感或平台验收。先以同一作品入库确认当前版本，保存指定封面/资料/目标，
再冻结既有works plan并提交；重入复用plan和原平台提交键，不能另建重复任务。
各平台失败、未知或部分成功必须查看原attempt，不得用其他平台结果替代。
公开播放、平台实际缩略图与唯一作品的正式验收仍由现有acceptance流程单独记录。

旧 `.local/bailian-asr-20261016/operator.py` 和 `publish_n1.py` 固定原N1及任务1/2/3，
只能作为恢复模式的参考，不得用于新批次；本入口不调用它们。
