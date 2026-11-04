# 独立公开动效组件（开发验收中）

本目录是新执行身份 `haike.observed-controls/1`，来自可独立获取的 MIT 源及项目自有控件实现。不是原 motion-kit/poster-kit 的保护核心，也不声称全部原动作已等价实现。完整模板验证状态由本期真实队列与原片对照回执给出；54 个公开场景的 guard 通过不能代替五套全片验收。

真实制作入口：[motion_public_production_v1.py](../../scripts/motion_public_production_v1.py)。输入先由 `backlot.motion_public_runtime.prepare` 核验，`motion_replay_production.submit_frozen/execute` 负责统一队列。JSON 不提供任意模块或命令。四套观察控件固定输出1080×1920、60fps；[自有深色十组](dark-v1/README.md) 用1440×1800、30fps原Remotion renderer，隔离实际执行验收待完成，实验bridge未准入公共入口。原参考画廊身份在 [presentation-bindings.json](presentation-bindings.json) 单独记录，不把template_id当gallery_id。

Agent 使用 [制作手册](runbook.md) 组装本期完整输入。[默认配方](defaults.json) 只包含可分发的样式选择与控件组合；实际脚本、ASR、PCM 口播、真实素材及工具位置必须由本期输入绑定，不把私人 QA 文件当默认素材。

源闭包由 `COMPONENT.json`、`DEPENDENCIES.json`、`TOOLS.json`、`FFMPEG9.json` 及固定执行文件逐字校验。许可沿 `upstream/LICENSE`、各 pack 的 licenses、依赖原 LICENSE/NOTICE/OFL 保留；外部二进制的来源和摘要固定，源码目录不包含其二进制。私包、Key、人物/亲子图像、声音和完整私有 QA 输入不在本目录。

未实现控件变体会拒绝。海报的原 CJK WOFF2 摘要差异保留，当前正在用公开同族 TTF 实测字形、字距和断行作格式适配，当前字体/版式未通过。03优先保留C已验证的Remotion 4.0.506、十组TSX及渲染命令，源继承项目AGPLv3，Remotion与其他依赖各自保留许可；静态真实输入已核，不以公开场景数或44帧bridge实验代替原renderer隔离全片再生。正式 preferred 版本、画廊和发行绑定由总控全验后显式完成。
