# 旧版通过 main 源码升级：Agent 教程

Mac用户进入[Mac专用教程（Apple Silicon/Intel）](UPGRADE_FROM_MAIN_MAC.md)，包含更新后生成完整测试视频的步骤。本页命令和运行时检查面向Windows；共用数据保护原则供Mac教程引用。

本教程直接使用官方 **main 的固定提交**，由 Agent 完成备份、部署、依赖恢复、前端构建和目标机验收，**不等待、不下载海客 Release 更新包**。适用于 Windows x64 的1027便携版、后续便携版及源码副本。这是 Agent 操作流程；当前没有脱离 Release、自动完成所有历史版本原地迁移的单条 CLI。

**1.2.4 起：一次接入后可在页面更新。** 本次交付目标应为官方干净 Git checkout（main 或固定提交），运行 Git/Node/npm 可用；本机配置写入忽略的覆写文件，不能把私人配置当源码提交。验证“关于海客视频”实际读取 main 提交并显示正确状态；后续从页面检查、确认并重启，详见 [APP_UPDATES](APP_UPDATES.md)。已有 dirty/index 不强制清理，按下文独立部署保留现场。

## 给旧电脑 Agent 的一句话

> 把本机海客工作台升级到 hrbj18/haike-workflow 的 main 最新已通过检查的源码，按仓库 docs/UPGRADE_FROM_MAIN.md 识别 Windows/Mac 和实际安装目录，接通“关于海客视频→检查更新”，不走 Release 更新包。保留 Key、音色形象、账号、草稿任务及 Git 修改；只备份配置、数据库等元数据，不复制视频音频图片，原路径复用。依赖走国内镜像并复用已有环境；完成启动和模板验收后，复用已有素材及数字人成果导出一条完整高清有声测试视频，不新增付费或发布；失败按回执回退。

## 1027与本期源码的区别

| 项目 | 1027安装 | 本期 main 源码 |
| --- | --- | --- |
| 交付 | 包含当期运行时和编译界面 | Git保存源码、锁文件、公开合同；运行时、编译产物和私人媒体另行恢复 |
| 动效 | 沿原安装已有能力 | 18种首选样式，以精确版本、JSON合同、动作/语义时间线及原渲染实现共同约束；JSON不能代替组件 |
| 模板页 | 原版模板界面 | 固定模板、动效模板两类；原私人封面和绑定保留，展示按目标机实际文件验收 |
| 画面 | 沿原模板输入 | 素材画面类合同使用视频；知识图解类保留图形动画，按选中合同执行 |
| 数字人 | 已有性价比与高质量路线 | 保留用户选择和原任务；高质量工作流不是本期新增，无需为升级重新生成 |

代码核对基线为 `f48ffc6c47eaf539d2fcb1fe177a44005f352254`（2026-11-04 main，PR #14），四项 CI 已通过。本机此前已有隔离旧包升级、组件及短渲记录，**不能等同于下面这条纯 main 源码路线已在另一台物理机端到端通过**。本教程发布只完成代码对照和文档检查，不执行旧电脑升级；目标机步骤必须记录实际结果。

**2026-11-05源码补充：** 当前源码直接携带61张既有封面、4份知识模板OFL字体及已登记的准备适配器；47份首选实现文件恢复原字节并用逐文件Git属性保持原摘要。用下述 `verify --preferred` 检查当前18套的来源与可调用入口，再验目标机运行时、本期输入和出片。历史教程报告的1624项便携闭包及477项差异包含旧编译产物与输运差异，不能等同于当前18套的实际来源结果；该旧闭包仍独立保留，不能改SHA、换回旧业务API或伪造发行清单来消除错误。来源检查通过也不证明运行时、完整视频或另一台电脑已验收。

## 1. 识别目标，固定源码

读目标的 `AGENTS.md`、`START_HERE.md`、`README.md` 和本教程。记录目标绝对路径、原版本/提交、安装类型、服务PID/命令行和 `/api/health` 的 workspace。多个副本只操作本次明确目标。`PACKAGE-MANIFEST.json`表示便携布局，`.git`可能是文件或目录；历史嵌套目录按实际根识别。

在原目标之外取得源码。以下示例由 Agent 填入真实新目录，在 PowerShell 执行；每条命令失败即停止：

```powershell
$taskRepo = 'https://github.com/hrbj18/haike-workflow.git'
$taskSource = 'D:\Haike-main-待填写的新目录'
if (Test-Path -LiteralPath $taskSource) { throw '保留已有现场，请选择未占用目录。' }
git clone --depth 1 --single-branch --branch main --no-checkout --origin origin $taskRepo $taskSource
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

核对官方远端、完整 SHA及该提交的检查结果/相关变更；main 有更新时记录实际采用版本，不能自动把新提交当已验收。把路径、提交和原安装身份存入本机私有回执目录；后续不在构建中追随浮动 main。`core.autocrlf=false`避免额外转换，项目逐文件属性保存已冻结的原字节；仍须运行实际来源检查。若采用历史基线，显式检出其完整SHA，并保留该基线的缺项限制。

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
- 上述目录中的草稿/任务元数据及 SQLite 一致性快照；媒体文件不复制。逐一核对数据库引用的原素材、成片和封面路径仍可读，保留原目录与绑定。不要复制整个 projects、browser_data、旧安装或外部媒体目录作为备份。
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

1.2.5脚本同步Python模块锁、检查原生依赖、获取缺少的FFmpeg并构建界面；复用本机Chrome/Edge，默认跳过浏览器下载、Whisper和本地Qwen TTS。已有环境可由Agent按脚本局部补齐，避免无关全量安装。基础Python锁为`_distribution-tools/locks/Haike_video.txt`、`creatorhub.txt`，采集使用其`uv.lock`且不启用local-asr extra，npm使用各组件`package-lock.json`；记录来源、版本及下载校验结果。

当前setup默认使用[国内依赖镜像](WINDOWS_DEPENDENCY_MIRRORS.md)，补齐Snapcn和HTML npm组件，复用可用FFmpeg和本机浏览器，并为新任务登记独立原生运行绑定。按首选合同核对字体、组件及运行绑定；来源SHA匹配和短渲分别验收。缺件按声明来源取得并校验，不能还原固定字节时明确影响模板。

setup成功已包含界面构建；局部依赖恢复时在源码根单独执行：

```powershell
python scripts/build-studio.py
if ($LASTEXITCODE) { throw '前端构建失败。' }
python scripts/check.py
if ($LASTEXITCODE) { throw '源码检查失败。' }
```

前端构建使用npm锁并安装至 `Haike_video/backlot/ui/avatar-generator`，不继续使用旧dist/旧页面。若脚本发现私人示例，先保存至私有目录再构建，原封面通过原绑定恢复。基础FFmpeg安装按上游清单解析版本，未必符合某套合同的固定资源 SHA，需另行核对。

18套动效上次已完成视频的实际封面随main保存于 `Haike_video/templates/public-covers/`，无需等待更新包；按 `manifest.json` 的画廊ID、图片SHA及来源成片身份校验。图库优先显示这套成片画面，本机原封面通过“查看本机原封面”保留，原样片和绑定不改写。逐个验证实际poster响应及图片内容；同一通用三卡片换标题或替代素材演示图不算完成，不重新渲染18条视频补图。

**完成条件：** 基础依赖可加载、前端构建成功；18套资源有明确恢复/缺项记录。下载失败诊断具体上游，不转去等待海客Release。

## 4. 恢复配置和用户数据

独立部署先保留源码默认配置，再逐项合并旧本地设置，保留新版字段。只恢复配置及一致性数据库/元数据，原素材、音频、图片和作品继续绑定旧绝对路径，不复制媒体；原路径不可读即报告并停止相关测试，不悄悄全量搬移。路径修改限于已理解的展示/定位字段，保留原任务请求、预算、云端编号和证明，不重提交已完成任务。未知表或格式保留现场并列出迁移缺项。

`portable/source_candidate_recovery.py`包含已支持的Studio草稿/资产、WorkCatalog绑定实现可供核对，但其正式自动调用需要同一期feed/资源身份；本教程不伪造Release/feed来调用它，也不承诺迁移任意旧表。账号/Cookie文件保留不代表新副本已登录，发布器绑定另作只读验证。

**完成条件：** 原数据不变，新目标内原草稿、任务、作品、素材及封面可打开；“已备份”和“已迁移”分别报告。

## 5. 启动、18套组件及短渲验收

按目标启动器选择不冲突端口，例如在源码根执行：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\start-workbench.ps1 -Port 14866 -NoBrowser
```

端口仅为示例，以实际结果为准；启动器会检查本副本账号服务。读 `/api/health`，核对edition、workspace等实际字段属于新目录；源码可显示开发版本，不冒充已安装Release。查看 `/avatar`、两类模板和18个首选、实际封面请求、草稿保存/重载及原作品，分别留证。

**源码检查须注意：** Git没有生成的 `delivery.json`/发行元数据；默认 `template_capability.py --root ...`可能返回 `not-declared`，这不是18套通过。先在源码根执行下面的只读检查，确认JSON的 `source_status: verified`、`template_count: 18`，并保留实际输出；它检查当前首选的470份来源和可调用准备入口，不启动队列或付费：

```powershell
$taskPython = Join-Path $taskSource 'Haike_video\.venv\Scripts\python.exe'
& $taskPython Haike_video/scripts/motion_replay.py verify --preferred
if ($LASTEXITCODE) { throw '当前18套来源或准备入口未通过；保留原摘要并修复具体缺项。' }
```

随后向每个首选卡片的 `/api/studio/template-library/<画廊ID>/prepare` 传入该合同已有的合法本期输入，检查 `status: prepared`、精确版本、制作入口和 `submitted: false`；缺输入应阻断，不能走回普通口播。实际制片继续使用所属入口、依赖和统一队列，准备成功不代表已生成视频。

以下是**便携闭包专用诊断**：仅在实际使用该闭包且源码基线匹配时执行。纯main源码以当前首选合同的来源、实际准备和所需本机依赖/短渲验收；不将旧闭包中非本期实现或旧编译产物的差异当作所有18套的统一阻断。旧闭包不适用时记录理由，实际首选来源或必需依赖错误仍须处理，不靠改摘要跳过：

```powershell
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

本教程为“官方Git → 固定提交 → 本机依赖/构建/数据绑定 → 验收 → 页面 main 更新”。旧 `scripts/upgrade-haike.py apply`、`update-from-github.py`仍读取Release清单，不用于这次接入，也不使用内部 `apply-candidate`。新版“关于海客视频”已按 Git 源码/便携安装分通道，源码不再依赖Release。

代码依据：[安装](../scripts/setup.ps1)、[前端构建](../scripts/build-studio.py)、[组件检查](../portable/motion_delivery_runtime.py)、[能力CLI](../portable/template_capability.py)、[发行源码恢复](../portable/source_upgrade.py)、[数据恢复范围](../portable/source_candidate_recovery.py)。
