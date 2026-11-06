# Mac 旧电脑接入 main 源码与页面更新

适用于 macOS14+，Apple Silicon / Intel。新电脑先读 [DEPLOY_MAC](DEPLOY_MAC.md)。本教程直接使用官方 main 的固定提交，不等待海客 Release 包；旧 Windows .venv、exe、DLL 不用于 Mac。

本次稳定交付固定为官方 `v1.2.5` 标签所指提交，首次接入按下文检出该标签；今后选择新版本另行核对其检查结果。

## 给 Agent 的一句话

> 把本机海客工作台升级到 hrbj18/haike-workflow 的官方 v1.2.5 固定源码，按 docs/UPGRADE_FROM_MAIN_MAC.md 识别架构和安装位置并接通页面检查更新。保留 Key、音色形象、账号、草稿任务和 Git 修改；只备份配置、数据库等元数据，不复制视频音频图片，原路径复用。依赖走国内镜像，复用本机Chrome/Edge，不下载浏览器或Whisper；完成启动和模板验收后复用已有素材及数字人成果导出一条完整高清有声测试视频，不新增付费或发布；失败按回执回退。

## 1. 识别唯一目标

读目标的 AGENTS.md、START_HERE.md 与本页，记录旧根目录、版本/提交、运行服务的 workspace/PID/端口及启动入口。用 `uname -m`、`sysctl -n hw.optional.arm64`、`sw_vers` 结合实际可执行文件判断原生架构；Rosetta 下不能只看 uname。macOS低于14停止此路线，不能声称已支持。

只有官方干净 Git checkout、main/固定提交、环境/数据格式兼容时才考虑受控原地升级；便携、源码ZIP、dirty/index、未知布局默认独立部署，原目录保持可启动。Git（可真实执行）、Python3.12与Node22+/npm是后续页面更新条件，源码ZIP本身不提供 Git 身份。

完成条件：原目标、架构、服务身份、数据位置和本次新目标唯一明确。

## 2. 保留数据、固定源码

按 [共用备份规则](UPGRADE_FROM_MAIN.md#2-选择部署方式保护数据)保存实际配置、Key/账号、音色形象及封面绑定、SQLite一致性快照、草稿/任务元数据，保存 Git HEAD、分支、工作树/index及未跟踪改动。**不复制整个旧目录或媒体目录；原视频、音频、图片、作品保留在原位置，核对可读并继续绑定。** 凭据和快照只留本机私有目录。资金账本独立管理，不作为程序升级的恢复对象。

在已核对的旧目标之外选择未占用的新目录，Agent填写实际路径；以下在 bash 执行：

```bash
set -euo pipefail
task_source="$HOME/Haike-main-待填写新目录"
test ! -e "$task_source"
git clone --depth 1 --single-branch --branch main --no-checkout https://github.com/hrbj18/haike-workflow.git "$task_source"
git -C "$task_source" fetch --depth 1 origin tag v1.2.5
task_commit="$(git -C "$task_source" rev-parse 'refs/tags/v1.2.5^{commit}')"
git -C "$task_source" -c core.autocrlf=false checkout --detach "$task_commit"
git -C "$task_source" rev-parse HEAD
```

核对官方来源、`v1.2.5`所指完整提交及该提交的 Source delivery checks / Component checks，记录到本机回执。标签不可核对或检查失败时保留原版本；后续安装不再次追随浮动main。不通过检查的提交不作为可交付目标。

完成条件：固定源码身份可信，原目录/媒体/Git修改保留，元数据快照可读且数据库一致。

## 3. 使用原生镜像入口恢复环境

在新目录运行：

```bash
cd "$task_source"
bash scripts/setup-mac.sh
```

此入口按本机架构安装固定原生 Python/Node/媒体工具和五组 Python/npm依赖并构建工作台，复用本机Chrome/Edge，不下载浏览器、Whisper，默认跳过本地Qwen TTS。国内源、固定摘要及上游例外见 [DEPLOY_MAC](DEPLOY_MAC.md#国内依赖镜像与版本)。不要手工运行 Windows setup.ps1，或按旧教程从Google下载浮动浏览器。

已有本地运行时只有架构、ABI、版本/摘要及实际加载匹配才可复用；不搬移旧venv。原生环境已就绪的干净源码原地更新由页面增量补依赖，不无条件重跑全量setup。独立部署首次安装与常规更新是不同步骤。

逐项合并旧本地覆写，保留新版默认字段；按目标恢复配置及一致性数据库/元数据，绑定原媒体绝对路径。未知表、profile/账号登录或外部路径不可读时保留现场并报告，不能把复制文件等同于登录通过。旧付费任务/预算/云端ID冻结，不重提交；先核对队列/排期再启动，避免历史任务被再次执行。

完成条件：原生环境和前端可用，配置/元数据及原媒体绑定可读，Git源码保持干净，未迁移项明确。

## 4. 启动、页面更新与制作验收

```bash
bash 02-启动Mac.command
bash 03-检查Mac.command
```

启动器寻找本机空闲端口，地址/PID见 `.local/mac-services.json`。核对 `/api/health` 的 workspace、version、source_commit与实际目标一致；打开 `/avatar`，确认固定模板/动效模板及每套真实封面，保存和重载草稿、读取旧任务/作品。原生18套的具体证据和门槛见 [MAC_MOTION_VALIDATION](MAC_MOTION_VALIDATION.md)，源摘要通过不等于当前输入已制作。

打开“关于海客视频”，检查应读取官方main提交；同提交显示源码已一致，新提交可下载并确认重启。网络失败不能显示最新。干净源码之外的阻断项按 [APP_UPDATES](APP_UPDATES.md)处理；不伪造版本回执或清理用户改动来启用按钮。

选一套本机已验证的动效合同，复用已有文案、真实视频素材、完整音频和数字人成果，导出一条完整高清有声测试视频。缺素材或合同组件则明确阻断，不替换为静态图或普通口播，不新增付费调用/审核模型。核对全程可解码、时长/音轨、画面运动、字幕与关键转场，并实际观看/听审，交付文件、模板编号和验收记录。

完成条件：目标服务、数据、模板、页面更新及完整测试视频分别有真实回执，未听审/未执行项明确待验。

## 5. 失败回退与验证边界

独立部署失败只停止身份确认的新副本，保留日志与新数据，切回原启动入口；原媒体不搬动。页面更新由独立助手保存旧提交、依赖版本、界面及元数据，自动检查并回退；中断或并发修改导致无法安全恢复时，按 [APP_UPDATES](APP_UPDATES.md) 的本任务冻结助手和回执恢复，不强制覆盖现场。

历史Mac双架构18套完整时长导出属于已有原生渲染证据；本轮源码更新的 Git/重启/回退自动测试与页面检查单独记录。它们不代替同事物理机、真实云端账号、付费数字人和平台发布验收。仅把实际执行成功的目标机步骤记为通过。
