# OpenMontage 交接入口

更新：2026-11-02

## 读取规则

先读 `AGENT_GUIDE.md`；开发另读本文件与 `CURRENT_STATUS.md`。按Guide限读专题，只查当前任务。

## 任务入口

- 六款招商：[入口](../../templates/investment-six-v1/README.md)；恢复根`.local/codex-runs/investment-six-20261026/`。

- 模板：[库](../../templates/TEMPLATE-LIBRARY.md)含18–21；[22–26验收](../../templates/store-opening-v1/REVIEW.md)。默认.local/store-manager/defaults.json。
- MotionGit：[制作](../MOTION_TEMPLATE_STUDIO.md)共用网页/HTTP/CLI；[包适配](../MOTION_PACK_ADAPTERS.md)。
- [参考理解](../REFERENCE_UNDERSTANDING.md)：同源台词/原生帧/对象事件/语义配对；[粉笔双比例](../../templates/chalkboard-explainer-v1/README.md)本机测试范围见VALIDATION，听看/真机另验。
- [本轮升级](../SINGLE_DEVELOPMENT_GUIDE_TEMPLATE_UPGRADE_20261102.md)：1027升级/四片技术/重启回退通过；听看与发行待验。

- [Mac复刻包](../../template-kit/README.md)：47条目/35实例，字体替代复验，真机待验。

- 招商07/08/09：[手册](../../templates/investment-full-v1/visual-runbooks/README.md)含参数/源码；环境/私材另备、异机未验；08为45秒，听审待验。

- [高质量规则](../高质量数字人工作流.md)：本机Agent新片≤120秒默认高质量；根`.local/runninghub-workflow/default.json`，Studio未切换。
- GitHub稳定版/分支/跨机见 `DEPLOYMENT.md`；新克隆读根 `START_HERE.md`。本机新增不代表远端已发布。
- 模板7的19秒开发样/布局真值/验证见[手册](../../../Haike-Videohub/agent-runbooks/数字人模板7.md)；工作台全片待验。

## 更新规则

实质变化替换旧结论；问答不更新。改后运行：

`python scripts/audit_context_handoff.py`

超出 `context-policy.json` 上限先压缩。
