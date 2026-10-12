# Agent 原生模型路由：任务合同

## 用户目标

用户在 Codex 中选用的 agent 模型负责主题到待审成片的文本和视觉判断。例如选择 `gpt-6-luna`，同一次任务的脚本、九宫格概览、镜头级分析和选材都由该 agent 完成。项目负责采集、抽帧、证据整理、结构校验、媒体合成和任务账本。中转站仅在用户明确选择时使用，打包安装不应以填写中转站密钥为默认前提。

## 关键运行边界

- 项目 Python 后台不能直接继承当前 Codex 对话的模型调用和图像能力。默认方案由 Codex agent 主动读取项目产生的待判断任务，使用其原生文本/视觉能力，提交结构化结果；项目不能自行宣称已调用当前 agent。
- 当前 Codex 接口未向项目后台提供可核验的会话模型证明；`model` 由执行任务的 agent 申报，项目只校验同一次任务中脚本、视觉证据与选材的标识一致性，不能把此字段当成外部可证明的调用账单。
- 独立工作台离开 Codex 对话仍要无人值守时，需要另一个可认证的 agent 运行环境（例如 Agents API/SDK），这是单独的部署模式和凭证合同。未安装该运行环境时明确显示“等待 agent 执行”，不得静默退回中转站。
- 一次任务冻结 `execution_mode=agent|relay`、模型标识、证据指纹和提示词版本。`agent` 模式不要求项目保存 AI API key；`relay` 模式使用用户显式配置的模型和密钥。两种模式共享验证器与成片时间线。

## 分阶段改造

1. 将“准备证据”与“模型作答”拆开：本地先完成视频抽帧、多宫格、镜头切分，生成可供 agent 读取的任务包，包含绝对本地图片路径、稳定单元格/帧 ID、场景文案、来源和源文件指纹。
2. 给概览、镜头描述、整片选材各建一个提交入口。agent 返回严格 JSON；程序校验 ID、图像证据、时码、来源、字幕/水印、模型身份、任务指纹和版本，再写索引或采用时间线。
3. 统一队列管理媒体及状态转换；等待 agent 时记录可恢复任务，不占用付费工作通道，也不把等待误报为失败。
4. 中转站提供显式可选适配器，走相同任务包和提交验证器。禁止后台根据模型 404 自动更换模型或提供方。
5. 打包时按运行环境展示最少配置：Codex 内使用只需登录 Codex 和各素材/媒体服务；独立无人值守版另外引导 agent 运行环境的认证；仅用户启用中转站时显示其密钥设置。

## 验收

- 无中转站密钥时，Codex agent 模式仍能完成文本、概览、V2 镜头分析、选材和待审预览；模型账本统一记为用户所选 agent 模型。
- 9 秒模板和长数字人口播均使用同一证据和选择合同，不设固定 3 秒片段时长。
- 中断后能从已完成的任务包/索引恢复；输入文件或脚本变化、模型切换、伪造 ID/时码均拒绝提交。
- `agent` 模式的后台不会调用中转站；`relay` 模式需要显式选择、检查凭证和费用。
- 真实 V900 完成全链路待审片；再用至少一条长数字人口播验证镜头时长和视觉证据。最终成片由人观看，不自动发布。

## 当前状态

Codex CLI 在当前 Windows 应用安装路径执行被系统拒绝，不能把它当作本机后台默认运行环境。

已实现素材支线的 agent 原生交接：

- `POST /api/project/{project_id}/workbench/script-draft/agent-task` 给出当前 agent 模型的脚本提示、项目上下文和指纹；`/agent-submit` 验证结构、时码、来源指纹与模型后写入草案，不调用中转站。脚本可由相同模型以 `reviewer=agent` 进入场景规划，账本保留审核者。
- `material-needs/agent-task` 与 `/agent-submit` 使 agent 在检索前按语义和可渲染底层规划可变时长目标；`material`/`preserve`/`presenter` 分开承接，只有外采目标计入缺口。画中画数字人不能掩盖缺主体画面，全屏数字人须有源文件。已有画面可在目标区间局部保留。
- `material-acquisition/agent-task` 区分 `search_required`、`index_required`、`match_required`、`rematch_required`、`ready`；导入时按任务指纹登记检索轮次，原片池按 SHA、视频 ID 与源 URL 去重；导入后先索引或重匹配，不反复下载。

- 单素材及批量 `overview`/`vision` 支持 `execution_mode=agent`，只在本地抽帧、拼多宫格或切镜，生成带模型与源指纹的任务包；视觉请求不进入中转站。
- `GET /api/project/{project_id}/workbench/assets/{asset_id}/agent-vision/{overview|vision}` 提供当前 Codex agent 可读的图片路径、ID、时间与提示词；对应 `POST` 接受描述，核对任务指纹、模型、章节/镜头与证据 ID 后写索引。已有不同结果不能覆盖。
- `POST /api/project/{project_id}/workbench/material-selection/agent-task` 返回筛过来源、质量和模型身份的场景与候选。统一队列 `material_selection` 默认要求 agent 提交 `proposal`；只有显式 `execution_mode=relay` 才调用中转站。
- `skills/creative/agent-native-video-production.md` 固定 Codex 入口的主题、脚本、素材、视觉任务、选材、渲染、QA 顺序，并标明旧 AI 入口的迁移边界。

仍需接线：主题事实核验、视觉导演、每日科技快报及户外互动等其他模型入口仍调用原文本/视觉适配器；CopySkill Cookie 搜索下载及渲染的全程调度仍由 Codex agent 顺序调用。画面目标与缺口循环已具备机读合同，但尚未完成真实 V900 与长数字人口播的端到端验收，也尚无自动的最终裁切区域文字/水印 QA。用户选定 Codex 作为生产入口，独立无人值守工作台暂不属于默认部署模式。

本轮验证：真实 FFmpeg 视频走单个与批量 agent 证据准备、概览/V2 原生结果提交、伪造 ID/旧指纹拒绝、relay 不被调用、已付费 relay 索引保留；脚本任务与提交不调用 relay，重复提交幂等，旧任务/不同结果/错模型审核拒绝。`test_autonomous_material_selection.py` 与 `test_workbench.py` 全量 200 项通过。尚未用真实 V900 和长数字人口播制作一条 agent 原生待审片；这一条仍是生产验收门。旧“一键审核预览”默认 AI 导演加 Pexels，不能作为 Codex 原生抖音路线的默认完成入口。
