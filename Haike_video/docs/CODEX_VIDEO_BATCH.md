# Codex 批次执行入口

首次接入读根 [Agent 教程](../../START_HERE.md)。本方案由 Agent 理解要求、写稿、推进和汇报，以下接口负责实际制作与发布；CLI 不内置定时执行器，由各 Agent 宿主负责唤醒和跟进。`report` 的台账数据由 Agent 整理成报告文件。目前实跑来自 Codex，其他 Agent 按通用 CLI/HTTP 接入，尚未实跑验证；既有脚本名和任务标识保持兼容。

本入口是现有 Studio、TaskCenter、统一制作队列和作品发布计划的薄客户端。
没有独立数据库、守护进程、定时执行器或供应商调用通道。默认只连接本机14756，
先核对 `edition` 和工作区路径；必须在新副本运行。

## 规格和命令

在工作区根目录使用 `Haike_video/.venv/Scripts/python.exe` 调用
`Haike_video/scripts/codex_video_batch.py <command> --spec <JSON>`。
新指令省略口播参数时，先用 `defaults --spec request.json --output spec.json` 补全；
它读取当前账号的口播默认设置并缓存已有形象，未发起报价、制作或发布。
`request.json`仍须有已查证的选题/稿件/来源/发布账号；音色、倍率、模板、目标时长、
每条预算、备用授权、联网素材开关、人物图及模型可省略。明确字段优先，false保留；未设置预算或
不可用音色会报缺项，不自行猜金额或换供应商。未指定批次预算时取各条上限之和。
输出规格包含实际参数和预设快照；输出文件已存在时直接读取它继续，改预设不改变旧批次。
然后命令顺序是 `resolve`（只读）、`init`、`prepare`、`submit`，随后用
`status`、`resume`、`report`。`prepare/submit/status/resume/report/publish` 可加 `--slot <slot_id>`；
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

`init`按批次和槽位哈希得到固定draft/client ID，TaskCenter阶段是“代码接入/待制作”。
完整规格和人物图SHA保存在本项目 `artifacts/automation/codex-batch/spec.json`，
规格或图片变化会停止；TaskCenter仅存相对引用、hash、非秘密快照及执行回执。
不要在规格中放API Key、Cookie、密码或签名下载地址。

每项上限之和必须不超过批次限额；失败/未知不回收给其他项，实际结算未知保持null。
`prepare`上传本机人物图到本draft并报价，尚不生成；重启优先复用原portrait/revision/quote。
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
