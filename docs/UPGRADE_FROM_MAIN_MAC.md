# Mac 旧版通过 main 源码升级：Agent 教程

直接使用官方 main 的固定提交，在 Mac 上恢复环境、构建界面、迁移数据并制作一条测试视频；不依赖海客 Release 更新包。适用于 Apple Silicon（arm64）和 Intel（x86_64）的旧源码/历史安装目录识别与试运行。名称为“1027”或存在包清单，不代表其中的 Windows 运行时可用于 Mac。

**验证状态：** 本页按 `27e8e23822c1bf181a56de3aa75c2b10d0d69f6f` 的实际代码核对；本次发布只更新文档，未在 Mac 执行安装、迁移或出片。Apple Silicon、Intel 的完整升级及18套动效均为待真机验收；不要把 Windows/Linux CI 或本教程上线当作 Mac 全部能力已通过。

## 用户可直接复制的一句话

> 请按 https://github.com/hrbj18/haike-workflow/blob/main/docs/UPGRADE_FROM_MAIN_MAC.md 将我当前Mac上的海客工作台直接升级到固定的官方main源码，识别Apple Silicon或Intel及实际安装目录，备份并保留用户数据和Git修改，不走Release或Windows安装入口；恢复匹配架构的依赖、构建前端并启动验收，随后选一套本机验证可用的动效模板，复用已有文案、视频素材、音频和数字人成果生成一条完整高清有声测试视频，交付可播放文件、模板编号及验收报告；遇到未适配组件如实记录并提供回退，不绕过合同或校验，不新增付费调用，不发布视频。

## 1. 识别机器、目标和版本差异

先读实际目标的 `AGENTS.md`、`START_HERE.md` 和本页，记录原目录、安装/版本身份、服务PID与命令行、工作台和账号服务端口。只操作身份确认属于本次目标的进程。记录以下只读结果（不要输出Key或完整私有配置）：

```bash
uname -s
uname -m
sw_vers
sysctl -n hw.optional.arm64 2>/dev/null || true
sysctl -in sysctl.proc_translated 2>/dev/null || true
command -v git python3.12 node npm ffmpeg ffprobe
```

结合硬件、当前进程和每个可执行文件的实际架构判断；Rosetta下的 `uname -m` 不能单独证明机器是Intel。Apple Silicon优先整套使用arm64，Intel使用x86_64；已有Rosetta环境单独记录，不把不同架构的Python扩展、Node模块或浏览器混用。不要复制Windows的 `.venv/Scripts` 或 `.exe`，也不要直接搬移旧Mac虚拟环境。

相对1027时期，本期源码增加18种首选动效的精确JSON合同、动作/语义时间线和原渲染实现，前端分固定模板/动效模板两类；视频素材类按合同使用运动画面，知识图解类保留自身动画。高质量数字人路线原本已有，升级不重新生成。Git不包含用户数据、私人封面、完整运行时或编译界面；拉代码、打开页面和模板可制作分别验收。完整差异与通用数据保护规则见[源码升级说明](UPGRADE_FROM_MAIN.md)，Mac不执行其中PowerShell示例。

**完成条件：** 系统/架构、唯一旧目标、服务身份和数据位置已明确。

## 2. 备份并取得固定源码

默认在旧目录之外独立部署，旧版保留可启动。只有干净Git、可快进、环境和数据格式兼容且已核对文件覆盖范围时，才考虑有外部备份的原地快进；dirty/index、历史布局、未知格式走独立目录。

备份项目实际配置、Key/账号/Cookie、音色与封面绑定、草稿/任务/作品数据库、`Haike_video/projects`、`Haike_video/.backlot`、`creatorhub/data`、`creatorhub/browser_data`及其引用的外部素材目录。按[通用备份和恢复规则](UPGRADE_FROM_MAIN.md)第2/4/6节保存原启动入口、Git HEAD/分支/工作树/index及未跟踪文件，核对备份SHA和可读性。数据库停所属写入者后备份或使用SQLite一致性备份，保留WAL一致性；其他副本和资金服务不动。凭据留本机私有目录。

下面示例由Agent填写目录后在 **bash** 执行；每段失败即停止，保留现场。新目录必须不存在，不能把占位符原样使用：

```bash
set -euo pipefail
task_source="$HOME/Haike-main-请改为本次新目录"
task_receipts="$HOME/Haike-upgrade-private-请改为本次回执目录"
test ! -e "$task_source"
mkdir -m 700 "$task_receipts"
git clone --no-checkout --origin origin https://github.com/hrbj18/haike-workflow.git "$task_source"
git -C "$task_source" fetch origin main
task_commit="$(git -C "$task_source" rev-parse origin/main)"
test "${#task_commit}" -eq 40
git -C "$task_source" -c core.autocrlf=false checkout --detach "$task_commit"
git -C "$task_source" remote get-url origin
git -C "$task_source" rev-parse HEAD
printf '%s\n' "$task_commit" > "$task_receipts/source-commit.txt"
```

核对官方远端、完整提交和该提交的检查结果，再执行依赖安装；后续固定此提交，不边构建边追随main。回执目录在项目之外且仅自己可读。中断后读取已有回执恢复，不重复创建并覆盖现场。Git检出的业务源码保持固定身份，平台适配缺口交回维护者，不在旧用户电脑上静默修改生产代码。

**完成条件：** 外部备份可恢复，源码来源和完整提交已固定，旧目录及Git状态保留。

## 3. 恢复Mac基础依赖

以下是待Mac真机验证的分步安装方式；不运行Windows的 `scripts/setup.ps1`、`portable/setup.ps1`、`_distribution-tools/portable.py runtime` 或 `_distribution-tools/setup_msvc.py`。准备与当前架构一致的Python3.12、Node22+、npm、Git、FFmpeg/FFprobe；Agent先核对已有工具，缺工具按目标机已有可信安装渠道补齐，记录实际来源/版本。无需为本次升级安装本地Qwen TTS或额外音频审核模型。

```bash
set -euo pipefail
cd "$task_source"
python3.12 -c 'import platform,struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize("P")==8; print(sys.executable,platform.machine())'
node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1); console.log(process.execPath,process.arch)'
ffmpeg -version
ffprobe -version
python3.12 scripts/check.py
```

根 `_distribution-tools/locks/*.txt` 包含Windows分发环境的解析结果，例如制片锁含 `pywin32-ctypes`；不能把这些当已验证的Mac架构锁。原Mac环境有合法有效依赖时先核对复用条件；独立新目录可按本提交的源requirements解析安装，并把**实际Mac解析结果**冻结到私有回执。这是本机候选环境，不冒充已验收的官方Mac锁；明确固定版本无对应wheel、原生库不兼容或源码构建失败时保留日志，不能随意换版本或删依赖制造通过。

```bash
set -euo pipefail
cd "$task_source"
python3.12 -m venv Haike_video/.venv
task_python="$task_source/Haike_video/.venv/bin/python"
"$task_python" -m pip install -r Haike_video/requirements.txt
"$task_python" -m pip check
"$task_python" -m pip freeze > "$task_receipts/haike-macos-resolved.txt"
python3.12 -m venv creatorhub/.venv
creatorhub/.venv/bin/python -m pip install -r creatorhub/requirements.txt
creatorhub/.venv/bin/python -m pip check
creatorhub/.venv/bin/python -m pip freeze > "$task_receipts/creatorhub-macos-resolved.txt"
"$task_python" -c 'import fastapi,uvicorn,PIL,numpy,jsonschema,docx; print("core imports passed")'
```

已存在新副本venv时先验证，不无条件重建。只有所选功能需要本地ASR时，才评估 `Haike_video/requirements-asr.txt` 对该Mac架构的支持；复用已有完整音频/时钟不要求下载新模型。采集模块需要时按其 `pyproject.toml/uv.lock` 和说明执行，不能把只完成视频工作台说成全部采集/发布已配置。

**完成条件：** 目标架构正确、基础依赖可加载、依赖解析与失败日志可追溯；未覆盖的可选能力明确列出。

## 4. 构建界面，恢复配置和数据

在固定源码中新安装匹配架构的Node依赖并构建，不复制旧node_modules或dist：

```bash
set -euo pipefail
cd "$task_source"
(cd Haike_video/remotion-composer && npm ci --no-audit --no-fund && npx --no-install remotion browser ensure)
(cd creatorhub && npm ci --no-audit --no-fund && npm run build:ui)
"$task_python" scripts/build-studio.py
```

`build-studio.py`已按平台选择 `npm`，产物安装至 `Haike_video/backlot/ui/avatar-generator`。若发现旧私人示例导致拒绝构建，先将文件和绑定保存至私有目录；不删除原封面。需要Snapcn时，在 `Haike_video/motion-components/snapcn` 核对锁后另执行 `npm ci --no-audit --no-fund`，基础构建不包含它。

不要直接执行 `scripts/configure.py`来配置Mac全模块：它给采集模块新生成的FFmpeg路径仍是 `.exe`。Agent核对源码默认配置，逐项合并旧本地配置并修正本机工具路径，保留新字段；Key、账号、音色绑定只在私有配置中恢复。基础媒体工具可走 `Haike_video/lib/ffmpeg_locator.py` 的实际发现逻辑，但这不表示所有动效渲染器都使用它。

恢复数据库/素材到新副本，核对草稿、作品及封面引用的绝对路径；只更改已理解的展示/资产定位字段。原付费任务、预算、云端编号和证明保持冻结，不重新提交。未知数据库格式、发布器账号或浏览器profile绑定单独核对，不将文件复制等同于登录已验证。首次测试前检查恢复的队列/排期，保持历史任务暂停，避免启动时重执行。

**完成条件：** 前端构建成功、配置和用户数据可定位，未迁移或未登录项明确。

## 5. 分别启动并验收

当前Windows总启动器不能直接用于Mac。使用已有Python模块入口，在两个由Agent管理的终端/会话分别启动；示例端口须先确认空闲。继续同一终端时沿用上面的变量，新终端先从回执恢复 `task_source` 的实际绝对路径：

```bash
set -euo pipefail
cd "$task_source/creatorhub"
./.venv/bin/python creatorhub.py start --skip-install --host 127.0.0.1 --port 18001 --no-open
```

```bash
set -euo pipefail
cd "$task_source/Haike_video"
export HAIKE_CREATORHUB_URL='http://127.0.0.1:18001'
./.venv/bin/python -B -m backlot serve --port 14866
```

这是分步启动，不会自动完成Windows总启动器的跨服务身份/端口选择检查；Agent须自行读账号服务的 `/api/download-sessions` 身份及工作台 `/api/health`，核对实际目录和源码提交。服务未就绪时读取该会话日志，只停止自己启动的进程，不杀占用端口的其他副本。不要把 `启动API账户中心-Mac.command` 当成视频工作台启动器。

验证 `/avatar`、固定/动效两类、18个首选、每张实际可读封面、草稿保存重载、旧作品/素材访问，以及两服务连接。浏览器打开页面不等于组件可制作。

**18套检查的当前限制：** `portable/motion_delivery_runtime.py`、`portable/source_candidate_recovery.py`仍使用 `runtime/python/python.exe`、Windows Node/FFmpeg/浏览器路径；例如 `backlot/motion_public_execution_v2.py` 的 `_ffmpeg/_ffprobe`仍固定 `.exe`。此外[源码教程中的冻结摘要差异](UPGRADE_FROM_MAIN.md)也需按实际提交核对。不能拿Windows运行时SHA核验Mac二进制，不能将Mac工具改名为.exe、删除校验或伪造清单来假装支持。`--runtime-bindings`只允许原身份映射，不解决这些平台差异；默认 `not-declared`也不是通过。

Agent逐套记录“合同/业务源码”“该平台依赖”“实际组件调用”“媒体输出”状态。确认某条原渲染实现支持本机且身份有效后才测试；被Windows路径或冻结身份阻断的具体路线标为待适配，其他路线继续核对。18套都未验证可用时，不能任取固定模板冒充动效验收。

**完成条件：** 新副本身份、数据及前端可用性有实际证据；18套能力和阻断逐项报告，Apple Silicon与Intel结果分开留证。

## 6. 更新后直接制作一条完整测试视频

这是用户要求的交付步骤，不能只交页面截图或一秒短检。选一套**在这台Mac已验证可用**的精确动效模板/版本，复用本机合法文案、运动视频素材、原完整音频及数字人成果，通过该模板已登记的项目制作接口/统一队列完成。遵循[Agent接入](../START_HERE.md)、[批次接口](../Haike_video/docs/CODEX_VIDEO_BATCH.md)及实际模板runbook；文档中的Windows Python路径在Mac改用目标已建立的 `.venv/bin/python`，接口语义和费用门禁保留。

升级不授权新的配音、ASR、数字人付费调用或发布；模板所需输入/回执不完整时先核对已有资料，记录确实缺项，不绕过模板合同，也不因为通用Studio入口可用就假定18套都能自动提交。已验证路线若不存在，保留已完成的基础升级，交付“动效出片待适配”及具体原因，不能伪造测试视频成功。

测试片保留完整时间线和声音，按[画质与混音标准](../Haike_video/docs/VIDEO_QUALITY.md)检查高清尺寸、实际视频码率、全片解码、字幕、人物同步、素材内容运动及混音；技术检查不能代替未执行的连续听看。交付实际可播放文件、模板编号/版本、时长/分辨率/码率、素材/输出SHA、原任务编号及真实检查结果。仅提供旧成片或改文件名不是本次Mac渲染通过。

**完成条件：** 一条本机实际生成的完整高清有声动效视频可播放且检查通过；否则明确未完成阶段、恢复位置和已保留成果。

## 7. 回退、交付和维护边界

独立部署失败时只停止新副本、保存日志和新数据，切回原启动入口。原地快进路线按外部备份逐文件恢复，先保护更新后新增修改；不要清空工作树/index。数据恢复使用与旧版本匹配的一致性备份，先保存更新后现场；资金账本另按独立备份处理。

回执记录系统/硬件/进程架构、原/新路径、固定提交、备份与回退入口、依赖解析、前端构建、服务身份、用户数据检查、18套能力、测试视频和未验项。共用数据原则只在[源码升级说明](UPGRADE_FROM_MAIN.md)维护，本页维护Mac差异。大批量推广前分别取得Apple Silicon和Intel真实升级+出片回执；当前发布不宣称已完成该批量验证。

本页不调用读取Release的 `upgrade-haike.py apply`/`update-from-github.py`/“关于海客视频”更新或内部候选安装。文档上线不会自动部署旧Mac，也不会完成底层组件平台适配。
