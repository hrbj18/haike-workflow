# Agent 接入教程

适用于本单仓库。所有命令从包含本文件的仓库根目录执行，路径使用本次 checkout 的实际位置。

本产品采用 **Agent 总控＋项目执行工具**：Agent 理解一句话要求、整理稿件、推进任务、检查结果并写汇报；项目负责素材、配音、数字人、渲染、持久记录和平台发布。通过 Codex 完成连续三条制作、排队发布和晨报已有本机实跑记录；其他 Agent 按下述条件接入，尚未完成 WorkBuddy 等产品的实跑验证。

入口采用标准 Python CLI 和本机 HTTP，没有 Codex 专用 SDK 或聊天身份依赖。`codex_video_batch.py` 等既有文件名、任务前缀和审计标签继续沿用，以保持原任务兼容。

| Agent 所需能力 | 用于什么 |
| --- | --- |
| 读取项目说明、写入 JSON/Markdown 文件 | 读取规则、冻结规格、保存检查点与报告 |
| 在项目所在机器运行 Python 命令或访问本机 HTTP | 调用现有队列、素材与发布工具；云端沙箱的 `127.0.0.1` 并非用户电脑 |
| 查看媒体和检查工具结果 | 完成现有成片、封面和发布证据检查 |
| 继续执行或被再次唤醒，并能读取原任务文件 | 跟进长任务、跨上下文恢复原编号 |
| 夜间任务所需的定时触发 | 由该 Agent 宿主提供，或由调度器唤醒完整 Agent 工作流；单次 CLI 调用只完成对应阶段 |

其他 Agent 若不会自动读取 `AGENTS.md`，将本文件作为接入指令。先只读核对服务身份、目录与模板，再用用户授权的小任务验证完整调用。程序内每日方案的执行器状态不代表外部 Agent 无法推进批次。

## 1. 读取入口并确认任务

先读根 [AGENTS.md](AGENTS.md)，再读 [Haike_video/AGENTS.md](Haike_video/AGENTS.md) 及其要求的文档。制作流程和当前状态以该入口为准，安装以根 [README.md](README.md) 为准。

| 用户任务 | 进入方式 | 本步完成条件 |
| --- | --- | --- |
| 一张图片＋完整口播音频做视频 | 本文第 4 节的已有音频路线 | 确认音频是完整口播，取得图片、制作要求和费用授权 |
| 一张图片＋声音样本＋一句要求 | 本文第 4 节的声音样本路线 | 确认需要克隆声音，由 Agent 将要求整理成实际稿件 |
| 今晚连续做三条、发布并汇报 | 本文第 5 节及[批次接口](Haike_video/docs/CODEX_VIDEO_BATCH.md) | 明确选题范围、预算、目标账号、时间和本次发布授权 |
| 继续已有任务 | 本文第 6 节 | 找到原批次规格、项目与队列/发布编号 |
| 明确说“模板图文视频” | 按生产端入口读取同名手册 | 沿用这个专门流程 |

用户已给出的参数与授权直接沿用；其余先读当前账号预设。只针对确实缺失且阻断执行的输入、预算或授权询问，不让用户重新解释完整任务。

## 2. 安装、启动和只读检查

新环境按根 [README.md](README.md) 准备依赖并运行 `scripts/setup.ps1`。源码包需要安装环境；是否已有可用运行时，以本机检查结果为准。

```powershell
# 已安装环境的启动入口；启动器会核对并启动本副本账号服务。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-workbench.ps1 -NoBrowser
```

默认工作台 `http://127.0.0.1:14756/avatar`、账号服务 `http://127.0.0.1:8000`，以启动器结果为准。发现端口已被其他副本占用时，确认目标副本及实际端口；保留其他副本运行。

```powershell
# 只读检查：这里不创建制作、付费或发布任务。
$taskBase = 'http://127.0.0.1:14756'
$taskHealth = Invoke-RestMethod -Uri "$taskBase/api/health" -Method Get
$taskRoot = (Resolve-Path -LiteralPath '.').Path
if ($taskHealth.edition -ne 'haike-workflow-2' -or
    [IO.Path]::GetFullPath([string]$taskHealth.workspace) -ne $taskRoot) {
    throw '服务身份或工作区不匹配，请核对启动目标。'
}
$taskHealth | Select-Object ok, edition, workspace
```

身份一致后按需读取以下接口，提取当前任务需要的编号、能力和状态；音色等只读接口可能访问网关，需要有效 Key。

| GET 接口 | 用途 |
| --- | --- |
| `/api/studio/templates` | 当前模板及其能力 |
| `/api/studio/audio-center` | 当前海客账号可用音色、模型和关联图 |
| `/api/studio/audio-center/avatar-defaults` | 该账号保存的制作预设 |
| `/api/studio/publishing` | 当前发布账号 |
| `/api/studio/download-sessions` | 素材与发布分别检查的登录状态 |
| `/api/task-center/tasks`、`/api/works` | 查已有任务、作品与选题，继续原任务或去重 |
| `/api/task-center/plan` | 已保存的每日槽位；实际夜间唤醒由 Agent 宿主的定时能力承担 |

本步完成条件：服务属于本 checkout，能说明本次模板、声音来源、预算和账号；读取失败时报告具体缺项。

## 3. 新用户的一次性配置

1. 在工作台“API设置”配置用户自己的海客 Key 和网关，检查本次所需模型是否可用。凭据经本机私有配置保存，教程、规格和汇报只记录配置状态。
2. 上传用户授权的人物图；按需要上传完整录音，或克隆/选择当前账号可用的音色。私人音色和内部备用服务不会随源码自动迁移；接口缺失时说明实际服务错误，由管理员补部署或开通。
3. 在“平台账号”中分别扫码登录本次需要的平台，检查素材与发布两项。绿色表示最近 8 小时检查正常，执行前仍验证实时登录；用户无需手工复制 Cookie。
4. 需要复用时保存默认形象、音色、模板、预算和联网素材选择；执行本次明确参数时只覆盖本次任务。历史任务使用已冻结参数。

本步完成条件：本次所需服务、输入和账号可用。已有完整录音的路线不需要先克隆音色。

## 4. 单条视频

### 已有完整口播录音

由 Agent 根据用户要求整理录音对应的文案和标题，音频直接驱动数字人。使用 `/avatar` 的已有音频入口，或调用同一组 Studio 接口：

| 顺序 | 接口和读回点 |
| --- | --- |
| 保存草稿 | `POST /api/studio/drafts`，保存 `template_id`、`title`、`text`、`input`；读取 `id` 和 `revision` |
| 上传输入 | `POST /api/studio/assets?draft_id=…&kind=image&filename=…` 和 `kind=audio`，以二进制请求体上传，读取资产对象 |
| 绑定资产 | 再保存同一草稿和最新 `revision`；`input.soundMode="audio"`，绑定返回的 `portrait`、`audio` 资产对象 |
| 获取报价 | `POST /api/studio/drafts/{id}/quote`，请求包含当前 `revision`；读取报价与预算 |
| 提交制作 | 在已获费用授权范围内调用 `POST /api/studio/drafts/{id}/generate`，传 `revision`、`quote_id`、`max_charge_micros`、`confirmed=true`；保存返回的队列编号 |
| 跟进结果 | `GET /api/studio/drafts/{id}/avatar-job` 及 `/api/production-queue/jobs/{job_id}`，读取最终 `result.work_id` 和成片 |

HTTP 写请求带当前工作台的 `Origin`；JSON 请求用 `application/json`，资产上传用 `application/octet-stream`，查询参数进行 URL 编码。草稿字段与版本冲突处理以 [studio.py](Haike_video/backlot/studio.py)、[Studio 路由](Haike_video/backlot/studio_api.py) 和前端 [App.jsx](prototypes/haike-avatar-generator/src/App.jsx) 为准。

### 声音样本＋一句制作要求

Agent 先把主题要求整理成实际口播稿。需要声音克隆时，通过工作台配音中心完成样音上传、报价、用户已授权范围内的克隆，读取当前账号返回的真实音色编号；后续使用该音色生成口播，再走数字人与合成。

音色中心入口见 [studio_audio_api.py](Haike_video/backlot/studio_audio_api.py) 和 [studio_audio.py](Haike_video/backlot/studio_audio.py)。已有可用音色直接复用。云端接口未发布或未开通时，报告这一具体阻塞；本机历史音色编号不能当作新用户的音色。

只有一个槽位时也可使用第 5 节的批次入口。当前批次 CLI 采用“稿件＋音色”的路线，完整口播录音走上面的 Studio 入口。

本步完成条件：原队列完成、最终成片存在且可完整解码、作品记录与当前版本一致。技术和必要内容检查按生产端规则执行；有发布授权时继续原作品发布流程。

## 5. Agent 夜间三条批次

详细规格、命令副作用、审核证据和发布幂等以 [CODEX_VIDEO_BATCH.md](Haike_video/docs/CODEX_VIDEO_BATCH.md) 为唯一接口说明。Agent 为三条分别整理选题、来源、稿件与目标，读取账号预设，生成本批 `request.json`；明确字段优先。

把本批请求、冻结规格和汇报放在忽略目录 `.local/codex-runs/<batch_id>/`；保存真实批次 ID 和规格位置，供下一次唤醒或上下文交接读取。JSON 写为 UTF-8 无 BOM；Windows PowerShell 5.1 的默认重定向编码不能直接用于这些文件。使用本 checkout 的 `Haike_video/.venv/Scripts/python.exe` 调用 `Haike_video/scripts/codex_video_batch.py`，非默认端口通过 `--base` 指定本机工作台根地址。

| 阶段 | 命令 | 完成条件 |
| --- | --- | --- |
| 补预设 | `defaults --spec request.json --output spec.json` | 得到新的冻结规格；已有 `spec.json` 时继续原文件 |
| 核对 | `resolve --spec spec.json` | 当前模板、图片、音色、目标账号和预算匹配 |
| 登记 | `init --spec spec.json` | 取得本批固定草稿、任务编号，记录到本批工作目录 |
| 报价 | `prepare --spec spec.json` | 上传输入并报价，金额在本次授权上限内 |
| 制作 | `submit --spec spec.json` | 取得原制作队列编号，后续观察原任务 |
| 跟进 | `status`、`report`，必要时 `resume`，均带原 `--spec` | 三条各自成片就绪，或有明确阻塞与恢复点 |
| 检查与发布 | 依批次文档完成实际检查，`publish --spec spec.json --evidence evidence.json` | 在本次发布授权内提交原发布计划，逐平台保存回执 |
| 晨报 | 按第 7 节写文件 | 生成可打开的汇报并给用户文件链接 |

每条命令检查退出码和返回状态后才推进下一步。`prepare` 有资产上传和报价操作，`submit` 会进入付费制作，`resume` 可能在原预算与调用意图内继续未完成的付费阶段，`publish` 会提交真实平台发布。取得用户对本批预算和发布范围的授权后，常规步骤连续执行，无需逐阶段重复询问。`report` 返回数据并同步任务台账，Markdown 汇报由 Agent 据此生成。

用户要求未来夜间或每天执行时，核对当前 Agent 环境实际提供的定时/唤醒能力。Codex 可使用其自动化工具；其他 Agent 使用各自宿主支持的工具，读回实际配置。把本 checkout、任务输入/预设、预算、目标、授权范围、原批次位置和报告位置写进定时提示。新一期创建新批次，继续本期读取原规格；执行端每次醒来先判断属于哪一种。

保存定时任务后读回启用状态、时区和下一次触发时间。需要跨长时间等待时配置后续唤醒；仅让当前 CLI 退出不会继续指挥后续检查和发布。保持执行机器、Agent 执行环境及项目服务在约定时段可用。

批次规格的 `targets` 只含平台和账号，不能添加排期字段。按本入口执行夜间批次时，由 Agent 在授权时刻调用；发布器继续遵守账号间隔和允许时段。发布等待先看原任务的 `next_allowed_at`、账号间隔和允许发布时段；夜间窗口按用户授权配置，保留平台风控和原任务编号。本步完成条件：每条的制作、排期/提交、平台结果和晨报分别有真实记录。

## 6. 恢复和联网素材

- 新上下文先读本批原 `spec.json`，调用 `status/report` 对照原草稿、队列、作品、发布计划和平台任务。排队/执行中继续观察，完成的阶段复用产物；可重试失败才对原任务 `resume`。
- 付费结果或发布响应未知时，查询原意图与原提交，保留预算预留及已有产物。只有明确需要的缺失输入或人工验证才请求用户处理。
- 联网素材采用本次明确选择或账号预设。搜索前验证支持关键词搜索的素材账号；当前抖音支持关键词搜索，快手/视频号支持范围按实时能力读取，不能据登录绿灯推定同样支持搜索。
- 已启用联网素材的任务找不到合适画面时，记录“待补素材”和恢复点，保留原任务。取得并实际采用网络画面后才记录已采用；数字人完成不能代替素材完成。

本步完成条件：所有结果都能追溯到原编号，阻塞原因与恢复位置明确，完成阶段没有重复制作或重复发布。

## 7. 汇报和交付

Agent 在本批工作目录生成 `REPORT.md`，内容来自原任务和平台回执，至少包含：

1. 批次 ID、执行时间、三条选题，以及每条制作/发布的实际状态。
2. 成片、封面、作品和任务链接；已获取的公开作品链接。
3. 各平台排期、提交、公开核验状态，逐项区分。
4. 报价/预算预留与已确认实扣；未知费用标明未知。
5. 失败或待补项、原编号和下一步恢复动作。

向用户提供实际成片与 `REPORT.md` 的可点击路径，并让工作台能看到作品/进度。总报告可汇总到三条，但保留逐条、逐平台结果。报告不包含 Key、Cookie、供应商签名地址或私人配置。

接入完成的最小核验：新 Agent 只依靠本入口找到正确服务和当前账号预设，能沿现有工具完成一条已授权任务、交接后继续原任务，并交付真实报告。只读安装检查不发起付费或发布；完整生产验证使用用户明确授权的样本与预算。
