# Codex agent 原生视频制片

适用：用户在 Codex 中提出或审批主题，要求直到待审成片的文本、画面理解和选材判断都由当前 agent 模型完成。用户选择 Luna 就全程记录 Luna；未指定其他模型或中转站时，不调用项目文本/视觉中转站。TTS、数字人、下载和渲染是独立媒体服务，仍按项目配置与预算合同执行。

## 执行权

Codex agent 是编导与视觉判断者，OpenMontage 是证据、时间线、队列和渲染权威。当前 Python 后台不能继承 Codex 对话的模型权限。agent 通过任务包读取本地证据并提交严格 JSON；任何阶段缺输入时继续采集或明确停在可恢复点，不把等待结果自动改走 relay。`gpt-6-sol` 在某中转站不可用不影响 Codex 原生模式。

## 主题到待审片

1. **确认项目和模型**：记录当前 Codex agent 所用模型、主题、目标时长、画幅、来源限制、音乐/配音/数字人选择、预算与发布边界。只有用户显式指定中转站时，模型判断任务才选 `execution_mode=relay`。
2. **脚本与时钟**：将标题、主题和事实材料保存到项目 `intake`，调用 `POST /api/project/{project_id}/workbench/script-draft/agent-task`，传 `mode` 与当前 `model`；agent 按返回的 `prompt`、`context` 写结构化脚本，向同前缀 `/agent-submit` 提交相同 `mode`、`model`、`task_fingerprint` 和 `script`。通过 `/script-draft/review` 以 `reviewer=agent`、相同模型批准，再由 `/scene-plan` 转换为场景。以真实音频时长为最终时钟；镜头时长由场景决定，不设 3 秒常量。脚本不得调用默认 relay 生成器冒充 agent 原生。
3. **先规划画面目标**：`POST /api/project/{project_id}/workbench/material-needs/agent-task` 读取台词、场景时钟、已有画面和数字人版式；agent 按语义和节奏提交 `segments` 到 `/agent-submit`。每段标明 `material`（须找外部视频）、`preserve`（已有完整主体画面）或 `presenter`（已有全屏数字人可独自承接）；时间线无重叠、无空白，镜头数量与时长不按关键词数或 3 秒常量推算。具体对象用 `must_show` 与 `match_policy=exact` 写清楚。
4. **按目标采集**：`POST /api/project/{project_id}/workbench/material-acquisition/agent-task`，携带 `required_platform` 和当前 `model`。`search_required` 时仅对 `gaps` 中目标启动 CopySkill Cookie 搜索下载，保留源 URL、视频 ID、权利状态；`material-catalog/import` 导入时附 `target_id`、实际 `search_query` 与 `acquisition_task_fingerprint`。`index_required` 先分析新资产；`match_required`/`rematch_required` 先匹配已拥有候选；`ready` 无需继续采集。下载整条原片，不预裁成固定长度。
5. **本地证据**：对素材以 `execution_mode=agent`、`model=<当前 Codex 模型>` 启动 `overview` 与 `vision` 索引任务。程序本地抽帧、拼多宫格和切镜；这一步不把图片发往中转站。对应任务入口：`GET /api/project/{project_id}/workbench/assets/{asset_id}/agent-vision/{overview|vision}`。
6. **agent 视觉判断**：agent 读取任务包的本地图像 `path`，按任务包的 `prompt` 和 ID 返回 `chapters` 或 `shots` JSON。用相同路径的 `POST` 提交 `model`、`task_fingerprint`、`proposal`；系统验证来源指纹、章节/镜头 ID、证据单元格/帧 ID、画质和可见文字。提交失败时只修该任务，不重跑整个视频。
7. **按目标匹配与补缺口**：`POST /api/project/{project_id}/workbench/material-selection/agent-task` 返回冻结目标和已通过来源、画质筛选的候选。agent 只为 `material` 目标提交 `targets`，逐镜说明语义匹配依据、置信度、源时间码和目标时长；具体对象必须在镜头视觉证据中出现。缺口按 `acquisition_requests` 返回，只补缺的目标，保留已验证素材和已有画面。指定抖音时不得静默改用 Pexels。
8. **实际源区间审核**：完整方案先调用 `POST /api/project/{project_id}/workbench/material-selection/window-qa-task`，提交当前 `model`、`required_platform`、`request_fingerprint`、`proposal`。系统对新镜头和 `preserve` 保留画面均按最终源入出点，以 3 fps 生成和成片相同中心裁切的分页宫格。agent 查看返回的全部 `sheets[].path`，逐镜判断是否有原字幕、水印、贴纸、文字遮挡及题材不符。合格后把 `window_qa={task_fingerprint,checks:[{sequence_id,clean:true,relevant:true,observation}]}` 与方案一起交给统一队列 `kind=material_selection`；队列在时间线写入前复核源文件、宫格和方案指纹。不合格须改选镜头；若候选不足，把该目标提交为空镜头产生定向补采请求。全屏数字人独自承接且无保留或新外部镜头的方案不需要此审核。
9. **预览和 QA**：通过统一队列渲染待审片。检查镜头衔接、字幕安全区、音轨与时长。局部问题只改受影响镜头并重新渲染同一时间线。最终给人观看；不自动批准、分发或发布。

当前旧版“一键审核预览”默认 `planning_mode=ai_director`，且其缺画面分支走 Pexels；这不是上述 Codex 原生素材路线。已有的抖音选材应从项目素材索引与 `material_selection` 队列进入正式时间线，再走项目渲染队列。若沿用旧预览入口，必须先核实其 `visual` 参数与来源约束，不能由 agent 模式静默触发旧中转站或 Pexels。

## 素材不足时的闭环

`material_selection` 计划返回 `needs_more_material` 时，按 `acquisition_requests` 的目标、缺口时长和语义重新组织检索词，在 CopySkill 执行 `python -m douyin_intelligence.cli material-replication run --theme <目标检索主题> --download-only`；读取交付的 `清单.json` 并用采集任务指纹导入。导入状态转为 `index_required`，新资产完成 overview、V2 后转为 `rematch_required`。已通过证据的资产保留，不因一次补采失败重下整池。导入账本记录检索词、目标、复用资产和是否有新增原片；连续缺素材时停在可恢复缺口，不能自动改用 Pexels 或重复同一请求。

## 路由与恢复门

- `agent` 是 Codex 入口的默认模型执行方式；`relay` 必须显式选用并走原配置及费用确认。任务账本同时记录 `execution_mode`、模型、提示词版本、输入指纹、源 ID 和输出指纹。
- 多宫格概览只能提示候选区间；最终采用须有同一模型/来源的镜头级 V2 证据。模型切换需重新理解素材；不能仅重写模型标签。
- `task_fingerprint` 或源文件变化时拒绝旧回答；已完成的不同回答不可覆盖。已生成的中转站索引及付费媒体成果保留在独立文件，不因切换 agent 模型被覆盖。
- 脚本、素材视觉与选材已有机读交接；视觉导演、每日快报和户外互动的旧 AI 调用仍需逐入口迁移。执行那些旧入口前必须核对是否调用 relay，不能宣称整个项目已原生化。
