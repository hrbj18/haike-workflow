# OpenMontage 交接入口

更新：2026-10-26

## 读取规则

1. 每轮只强制读取仓库根目录 `AGENT_GUIDE.md`。
2. 涉及项目开发、诊断、状态或规划时，再读本文件和 `CURRENT_STATUS.md`。
3. 只按任务追加读取一个专题文件：产品边界读 `PRODUCT_RULES.md`；历史决策读 `DECISIONS.md`；定位代码读 `CODE_MAP.md`；每日快报读 `DAILY_TECH_BRIEF.md`；GitHub 与跨电脑安装读 `DEPLOYMENT.md`。
4. 仅检查本任务项目、媒体和差异；不默认扫描旧日志及批次。

## 当前任务入口

- 六款招商：[入口](../../templates/investment-six-v1/README.md)；恢复根`.local/codex-runs/investment-six-20261026/`。

- 模板：[库](../../templates/TEMPLATE-LIBRARY.md)（含18–21手册）；[22–26v002验收](../../templates/store-opening-v1/REVIEW.md)。默认.local/store-manager/defaults.json。
- MotionGit/Hallmark：[入口](../../templates/motiongit-integration/README.md)。

- Mac模板交付：[复刻包入口](../../template-kit/README.md)，47条目/35冻结实例，字体替代须复验；Mac真机待验。

- 招商07蓝米／08青炭／09黑粉：[视觉Runbook](../../templates/investment-full-v1/visual-runbooks/README.md)含参数/源码，环境与私人素材另备、异机未验；08扩展45秒，听审待验。

- 高质量数字人：读[规则](../高质量数字人工作流.md)；本机Agent新片≤120秒默认高质量；条件在根`.local/runninghub-workflow/default.json`，Studio未切换。
- GitHub 稳定版、分支和跨电脑安装：读 `DEPLOYMENT.md`；克隆后的同事从根目录 `START_HERE.md` 开始。
- 本机新增功能不代表 GitHub 已发布。
- 数字人模板7的19秒本地开发短样、布局真值与验证范围见[同名手册](../../../Haike-Videohub/agent-runbooks/数字人模板7.md)；工作台全片接入待验证。

## 更新规则

实质变化更新，覆盖旧结论；问答不更新。改后运行：

`python scripts/audit_context_handoff.py`

超出 `context-policy.json` 上限先压缩。
