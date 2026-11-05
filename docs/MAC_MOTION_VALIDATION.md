# Mac 动效执行与交付验证

本文是 Mac 平台适配的执行附录，模板本身仍以 `Haike_video/config/motion-replay/` 的精确 JSON 版本、动作编号和原始源码为真值。首选18个样式由 `motion-preferred-production.json` 选择；既有成片及封面不因移植而重做。

## 实现与恢复

`backlot.motion_platform.owned_module()` 在 Mac 选择固定的原生适配器，Windows 继续调用原模块。`scripts/build-native-motion.py` 生成可直接审阅的派生 Python 文件；`config/motion-native-v1.json` 同时记录原文件、派生文件、生成器和运行时摘要。原冻结文件及其已登记摘要保持原样，动作 JS、TSX、语义时钟、视频原速采样、声音和编码规则继续继承。

Mac 运行时使用原生 Node、Chrome 和 FFmpeg 9.0.2。FFmpeg 6 无法满足这些公开组件的颜色转换规则；安装器保留9版的原规则。[_distribution-tools/macos-runtime.json](../_distribution-tools/macos-runtime.json) 列出发布方固定下载地址、归档及解压后二进制摘要；构建信息来自 [Mac 二进制发布方](https://ffmpeg.martin-riedl.de/)。npm 依赖遵循锁文件；HTML 控件的纯 JS 和 OFL 字体继续核对原始逐文件摘要，Mac 原生依赖另绑本副本安装清单。Windows exe、DLL、旧请求不改名复用。

已冻结 Windows 请求不能在 Mac 上改写为可执行请求。复用其获授权素材，按同一模板精确版本在 Mac 重新准备并冻结平台运行时，保留旧请求和已完成作品。运行时或派生源码变化会拒绝旧任务继续执行；不豁免摘要，也不自动重新提交付费任务。

## Agent 实际制作

安装后运行 `Haike_video/.venv/bin/python scripts/mac-motion-prepare.py --help`。公开组件/2、海报/3按原输入合同填写，本机工具根为 `runtime/macos/<arch>`；HTML依赖根为 `_distribution-tools/motion-html`，原深色 Remotion 依赖根为 `Haike_video/remotion-composer`。`--check` 只读核验；冻结时显式指定本副本队列、项目目录和另存位置。历史纸感/引言/3保留原输入接口与来源校验，本次首选18版本之外的历史修订另验完整成片。

冻结后继续使用 `Haike_video/scripts/motion_replay_production.py` 的 submit/status/execute 及原审批阶段。网页、共用契约准备和父队列执行都通过同一个平台选择入口；阶段批准、实时 claim、预算和未知受理恢复规则继续生效。其他编号模板、知识模板和促销模板继续使用原有准备目录/合同。

## 本次发布门槛

用户要求 Apple Silicon、Intel 都完成18个动效样式验证后才交付 Mac 正式包。

1. 原生安装、离线依赖补齐、两类浏览器启动、61张封面 HTTP 和 HeroTitle 实际导出分别记录。
2. `scripts/build-native-motion.py --check` 与18个首选 JSON 来源摘要通过；纸感/引言的历史公开修订也核对原摘要。
3. `scripts/mac-motion-smoke.py` 对18套首选样式的完整时长逐帧执行原视觉渲染器，使用单独的合成运动视频、字体和测试音，不上传用户文稿、形象、音色ID、Key或真实成片。按两种架构各3份分片运行，合并后必须每种架构都有18个唯一版本。
4. 核对每条全片解码、完整帧数、原画幅/帧率、至少20Mbps视频流、48kHz立体声AAC、画面变化、编码视频SHA和接触表；实际查看接触表并记录范围。失败项保留现场，按原版本修复重验。
5. CI结果全部通过后，制作私有 Mac ZIP，保留既有18条高清有声样片、真实样式封面、获授权本机私有配置和双架构离线缓存，校验归档。用户数据与公开源码的边界见 `DISTRIBUTION.md`。

合成素材的全时长渲染证明原生执行和媒体工具兼容；真实数字人云端权限、真实ASR与口型、设备外放听看、发布和同事物理机安装分别验收。本测试不制造这些证据，不改变生产审批，也不把源文件校验称为渲染通过。通过后在源码标签发布页保存CI结果摘要与验收JSON，在私有ZIP中另存验收副本；这些记录及对应提交的CI报告是实际状态依据。任一架构不足18条通过，Mac正式包保持待交付。
