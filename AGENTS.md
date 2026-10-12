# Haike Workflow 单仓库入口

四个模块已经包含于本仓库，保留固定目录布局。根 README.md 和 scripts/setup.ps1 是本版本首次安装入口。历史部署文档中的多仓 clone/checkout、旧提交锚点和便携包说明不适用于本源码仓库。首次迁移来源见 SOURCE-PROVENANCE.json。

- 安装、升级、打包：先读 README.md、docs/DISTRIBUTION.md；完成后运行 scripts/check.py。版本由根 Git 提交统一管理。
- 生产端开发、视频生产或理解：先读 Haike_video/AGENTS.md，再按其路由。
- 采集端开发：先读 copy_skill/copy_skill-main/AGENTS.md。
- 发布端开发：先读 creatorhub/AGENTS.md。
- 日常跨模块操作：先读 Haike-Videohub/agent-runbooks/README.md，再读匹配手册并核对实时状态。
- 用户明确说「模板图文视频」：读生产端入口后直接读同名手册，不替换成其他制片路线。

凭据仅存放于忽略的本地配置；安装默认跳过本地 Qwen TTS。付费调用和真实发布按各模块审批闸门执行。上传只包含源码、模板和可分发资源。

开发改动在所属模块执行相关检查。共享手册的维护遵循原有提案机制；本次整合未授权把历史经验标为新机实测。单仓库验收通过不代表真实账号、云服务和另一台物理机已验收。

