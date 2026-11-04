# 旧版通过 main 源码升级：Agent 教程

本教程直接使用官方 **main 的固定提交**，由 Agent 完成备份、部署、依赖恢复、前端构建和目标机验收，**不等待、不下载海客 Release 更新包**。适用于 Windows x64 的1027便携版、后续便携版及源码副本。这是 Agent 操作流程；当前没有脱离 Release、自动完成所有历史版本原地迁移的单条 CLI。

## 给旧电脑 Agent 的一句话

> 请按 https://github.com/hrbj18/haike-workflow/blob/main/docs/UPGRADE_FROM_MAIN.md 将我正在使用的海客工作台升级到官方 main 源码，直接获取并固定完整提交，不走 Release 更新入口；先识别实际安装和服务，备份并保留配置、账号、草稿、任务、素材、作品、封面及 Git 工作树和 index，按教程选择原地或独立部署，补齐依赖并构建前端，实际启动验收并逐套报告18套动效的合同、组件与短渲状态，失败保留现场并提供回退；不新增付费调用或发布视频。

## 1027与本期源码的区别

| 项目 | 1027安装 | 本期 main 源码 |
| --- | --- | --- |
| 交付 | 包含当期运行时和编译界面 | Git保存源码、锁文件、公开合同；运行时、编译产物和私人媒体另行恢复 |
| 动效 | 沿原安装已有能力 | 18种首选样式，以精确版本、JSON合同、动作/语义时间线及原渲染实现共同约束；JSON不能代替组件 |
| 模板页 | 原版模板界面 | 固定模板、动效模板两类；原私人封面和绑定保留，展示按目标机实际文件验收 |
| 画面 | 沿原模板输入 | 素材画面类合同使用视频；知识图解类保留图形动画，按选中合同执行 |
| 数字人 | 已有性价比与高质量路线 | 保留用户选择和原任务；高质量工作流不是本期新增，无需为升级重新生成 |

代码核对基线为 `f48ffc6c47eaf539d2fcb1fe177a44005f352254`（2026-11-04 main，PR #14），四项 CI 已通过。本机此前已有隔离旧包升级、组件及短渲记录，**不能等同于下面这条纯 main 源码路线已在另一台物理机端到端通过**。本教程发布只完成代码对照和文档检查，不执行旧电脑升级；目标机步骤必须记录实际结果。

**已知限制（本次只读核对发现）：** 该基线的 `upgrade-closure.json` 所列1624个程序文件中，有477项冻结摘要与该提交的Git blob字节不一致，严格源身份检查会阻断，不能宣称纯源码18套已全部通过。这不等于477种组件缺失，也不证明渲染效果有477处问题；说明现有冻结身份不能直接作为该Git提交的完整通过证据。本教程可先用于基础部署/启动测试，18套严格复刻标为待修/待验；保留错误明细交回维护者，用户Agent不通过改SHA或换旧业务源码伪造通过。本步仅发布教程，不修改该闭包或组件。

## 1. 识别目标，固定源码

读目标的 `AGENTS.md`、`START_HERE.md`、`README.md` 和本教程。记录目标绝对路径、原版本/提交、安装类型、服务PID/命令行和 `/api/health` 的 workspace。多个副本只操作本次明确目标。`PACKAGE-MANIFEST.json`表示便携布局，`.git`可能是文件或目录；历史嵌套目录按实际根识别。

在原目标之外取得源码。以下示例由 Agent 填入真实新目录，在 PowerShell 执行；每条命令失败即停止：

```powershell
$taskRepo = 'https://github.com/hrbj18/haike-workflow.git'
$taskSource = 'D:\Haike-main-待填写的新目录'
if (Test-Path -LiteralPath $taskSource) { throw '保留已有现场，请选择未占用目录。' }
git clone --no-checkout --origin origin $taskRepo $taskSource
if ($LASTEXITCODE) { throw '取得源码失败。' }
git -C $taskSource fetch origin main
if ($LASTEXITCODE) { throw '取得 main 失败。' }
$taskCommit = (git -C $taskSource rev-parse origin/main).Trim()
if ($LASTEXITCODE -or $taskCommit -notmatch '^[0-9a-f]{40}$') { throw '提交身份无效。' }
git -C $taskSource -c core.autocrlf=false checkout --detach $taskCommit
if ($LASTEXITCODE) { throw '固定源码失败。' }
git -C $taskSource remote get-url origin
git -C $taskSource rev-parse HEAD
```

核对官方远端、完整 SHA及该提交的检查结果/相关变更；main 有更新时记录实际采用版本，不能自动把新提交当已验收。把路径、提交和原安装身份存入本机私有回执目录；后续不在构建中追随浮动 main。`core.autocrlf=false`保留Git字节，避免检出时额外转换；它不能修复上述已存在的冻结摘要差异。若采用上面的已核对基线，显式检出其完整 SHA。

**完成条件：** 唯一目标、可信来源、固定提交和私有回执目录明确，原目标尚未覆盖。

## 2. 选择部署方式，保护数据

| 实际状态 | 操作 |
| --- | --- |
| 干净Git，原提交可快进到固定目标，环境/数据格式兼容 | 外部备份后，可 `git merge --ff-only <已取得的固定SHA>`；保存原HEAD/分支/启动入口，复核涉及的文件没有本机配置覆盖风险 |
| 1027/其他便携、dirty/index、代码冲突、未知布局或ABI不兼容 | 默认使用第1步独立源码目录；保留原安装，验收后再切换入口 |

本教程不提供未经目标核对的便携批量原地覆盖命令。独立部署也要恢复用户可见数据，不能仅保留旧目录就声称迁移完成。

先核对本目标队列和实际worker，等待已受理任务安全停稳，未知付费结果沿原任务查询。只暂停身份匹配的工作台/worker，保留其他副本及账号/资金服务。

在目标之外备份，并验证可读性和 SHA：

- 实际配置、环境文件、Key、账号/Cookie、音色绑定、模板封面绑定、启动入口及版本清单。凭据仅留本机私有备份。
- `Haike_video/projects`、`Haike_video/.backlot`、`creatorhub/data`、`creatorhub/browser_data`，以及配置和数据库实际引用的外部素材/成片/封面目录；此列表不能代替外部路径检查。
- Git原HEAD、分支、工作树差异、暂存差异、未跟踪文件及 index 原文件摘要。dirty/index 路线保持原目录不变。

数据库在所属写入者停止后备份，或使用 SQLite 一致性备份；只复制活跃数据库主文件可能遗漏WAL。抽查数据库能打开、媒体可读，记录程序新增/覆盖文件及恢复位置。数据格式有变化时先确定恢复方案，资金账本单独管理。

**完成条件：** 程序/数据备份可恢复，明确新旧目录、写入范围及原启动入口。

## 3. 补依赖并构建前端

依固定源码的 [README](../README.md)、[setup.ps1](../scripts/setup.ps1) 和 [build-studio.py](../scripts/build-studio.py)执行。准备 Python3.12 x64、Node22+、npm、Git、uv及兼容 MSVC x64运行库。旧依赖只有版本、架构、ABI和实际加载符合时才复用；不直接搬移旧venv。

全新独立目录可使用源码安装入口；下面使用本机已安装的 PowerShell7，无7时按README的系统PowerShell入口：

```powershell
Set-Location -LiteralPath $taskSource
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
if ($LASTEXITCODE) { throw '安装未完成，读取失败日志后恢复。' }
```

脚本同步Python模块锁、检查原生依赖、获取FFmpeg/Remotion浏览器并构建界面，默认跳过本地Qwen TTS。已有环境可由 Agent 按脚本局部补齐，避免无关全量安装。基础Python锁为 `_distribution-tools/locks/Haike_video.txt`、`creatorhub.txt`，采集使用其 `uv.lock`，npm使用各组件 `package-lock.json`；记录来源、版本及下载校验结果。

**基础 setup 不是18套全部组件恢复器。** 另查 `Haike_video/templates/motion-presets/upgrade-closure.json` 的 `files/resources/runtime_bindings`、首选合同及组件说明。setup未执行Snapcn安装；需要时核对 `Haike_video/motion-components/snapcn` 的package/lock，在该目录执行 `npm ci --no-audit --no-fund`并检查退出码。其余字体、HTML/图形运行时、浏览器等按合同逐项恢复。优先从原安装复用 SHA匹配的合法文件；缺件按锁文件/组件声明从上游取得并校验。不能从合法来源还原固定字节时，明确受影响模板，不改摘要来消除错误。

setup成功已包含界面构建；局部依赖恢复时在源码根单独执行：

```powershell
python scripts/build-studio.py
if ($LASTEXITCODE) { throw '前端构建失败。' }
python scripts/check.py
if ($LASTEXITCODE) { throw '源码检查失败。' }
```

前端构建使用npm锁并安装至 `Haike_video/backlot/ui/avatar-generator`，不继续使用旧dist/旧页面。若脚本发现私人示例，先保存至私有目录再构建，原封面通过原绑定恢复。基础FFmpeg安装按上游清单解析版本，未必符合某套合同的固定资源 SHA，需另行核对。

**完成条件：** 基础依赖可加载、前端构建成功；18套资源有明确恢复/缺项记录。下载失败诊断具体上游，不转去等待海客Release。

## 4. 恢复配置和用户数据

独立部署先保留源码默认配置，再逐项合并旧本地设置，保留新版字段。把一致性备份恢复到新副本需要的位置，核对旧绝对路径、SQLite资产路径、作品和草稿引用。路径修改限于已理解的展示/定位字段，保留原任务请求、预算、云端编号和证明，不重提交已完成任务。未知表或格式保留现场并列出迁移缺项。

`portable/source_candidate_recovery.py`包含已支持的Studio草稿/资产、WorkCatalog绑定实现可供核对，但其正式自动调用需要同一期feed/资源身份；本教程不伪造Release/feed来调用它，也不承诺迁移任意旧表。账号/Cookie文件保留不代表新副本已登录，发布器绑定另作只读验证。

**完成条件：** 原数据不变，新目标内原草稿、任务、作品、素材及封面可打开；“已备份”和“已迁移”分别报告。

## 5. 启动、18套组件及短渲验收

按目标启动器选择不冲突端口，例如在源码根执行：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\start-workbench.ps1 -Port 14866 -NoBrowser
```

端口仅为示例，以实际结果为准；启动器会检查本副本账号服务。读 `/api/health`，核对edition、workspace等实际字段属于新目录；源码可显示开发版本，不冒充已安装Release。查看 `/avatar`、两类模板和18个首选、实际封面请求、草稿保存/重载及原作品，分别留证。

**源码检查须注意：** Git没有生成的 `delivery.json`/发行元数据；默认 `template_capability.py --root ...`可能返回 `not-declared`，这不是18套通过。先在源码根用已准备的Python直接检查当前组件：

```powershell
$taskPython = Join-Path $taskSource 'Haike_video\.venv\Scripts\python.exe'
& $taskPython -B -c 'import json; from pathlib import Path; from portable.motion_delivery_runtime import report; print(json.dumps(report(Path.cwd()),ensure_ascii=False))'
if ($LASTEXITCODE) { throw '源身份检查失败，保留日志并恢复。' }
& $taskPython -B portable/template_capability.py --root $taskSource --component-selftest
if ($LASTEXITCODE) { throw '组件检查失败，读取明确缺项。' }
& $taskPython -B portable/template_capability.py --root $taskSource --diagnostic-plan
if ($LASTEXITCODE) { throw '诊断计划未就绪。' }
```

第一条可能以退出码0返回 `status: blocked`，还须核对JSON中的 `status/resource_issues/template_count`；源文件漂移也可能直接抛错。后两条默认期待闭包的便携路径；源码环境的系统/只读运行时可用 `--runtime-bindings <本机映射.json>`显式映射，格式与允许前缀见 `portable/motion_delivery_runtime.py` 的 `checked_bindings`。每项资源仍按原 SHA核验，业务源码不能映射旧目录；字体需在目标声明位置恢复。不删除缺项、不改冻结SHA、不伪造发行清单来制造通过。

组件检查只执行import/计算、字体等，不生成媒体。按实际诊断计划和每套原渲染接口，以合法已有输入执行必要短区间渲染及音视频编解码，确认帧变化、应有音轨、输出可解码，记录模板/区间/工具/输出SHA。既有证据仅在身份和机器环境适用时复用；不重做18条完整片，不新增付费数字人或审核模型。`production_ready: false`可能表示本期输入未准备，按实际返回解释。

**完成条件：** 分别报告源码/启动、数据、18套合同、组件、短渲。资源未齐只能报告已验收范围；另一台电脑、连续听看和真实账号未执行的明确待验。

## 6. 失败回退和交付

独立部署失败时只停止新副本，保存日志/缺项并切回原启动入口。原地Git失败先保存更新后新增修改，再按外部备份逐文件恢复本次覆盖和核对新增文件；需要代码回退时采用可追踪回退提交或独立检出旧提交，保留工作树/index。若新版已写数据库，先保存新现场，再恢复与旧代码匹配的一致性备份，避免丢弃新增用户数据；资金账本另按独立备份流程处理。

回执列出原/新绝对目录、完整提交、部署方式、备份/回退入口、依赖复用与下载、前端构建、服务身份、数据核对、每套组件/短渲及未验项。源码更新、页面可见和可制作分别报告，缺证据时明确部分完成及剩余问题。

## 与发行包更新入口的边界

本教程为“官方Git → 固定提交 → 本机依赖/构建/数据恢复 → 验收”。[UPDATE_WITH_CODEX](UPDATE_WITH_CODEX.md)、[APP_UPDATES](APP_UPDATES.md)的 `scripts/upgrade-haike.py apply`、`update-from-github.py`及“关于海客视频”仍读取Release清单，即使CLI来自main也不自动变成源码升级；本教程不使用这些入口或内部 `apply-candidate`。

代码依据：[安装](../scripts/setup.ps1)、[前端构建](../scripts/build-studio.py)、[组件检查](../portable/motion_delivery_runtime.py)、[能力CLI](../portable/template_capability.py)、[发行源码恢复](../portable/source_upgrade.py)、[数据恢复范围](../portable/source_candidate_recovery.py)。
