# Haike Workflow 单仓库入口

工作台、采集、发布、跨模块手册及API账户中心包含于本仓库，保留固定目录布局。根目录存在 PACKAGE-MANIFEST.json 时，先读 docs/PORTABLE.md，使用包内运行时初始化；源码 checkout 的安装入口为 README.md 和 scripts/setup.ps1。历史部署文档中的多仓 clone/checkout、旧提交锚点和旧便携包说明不适用于本版本。首次迁移来源见 SOURCE-PROVENANCE.json。

- 首次用 Agent 接入、单条做片、夜间批次或交接恢复：先读根 START_HERE.md，按任务进入现有接口和模块规则；Agent 负责总控，项目工具负责执行，接入条件见教程。
- 安装、升级、打包：先读 README.md、docs/DISTRIBUTION.md；便携包按 docs/PORTABLE.md 运行诊断，源码改动完成后运行 scripts/check.py。版本由根 Git 提交统一管理。
- 一次导入 Keys/服务地址/音色/预设、三平台扫码或判断新账户能力：读 docs/API_KEY_SETUP.md；实际私有配置文档独立留在本机，配置检查与制作发布验收分别记录。
- 生产端开发、视频生产或理解：先读 Haike_video/AGENTS.md，再按其路由。
- 新建、修改或审查视频模板：先读 Haike-Videohub/agent-runbooks/视频模板编写标准.md；「数字人口播模板6-招商A」按同名 runbook 执行。
- 采集端开发：先读 copy_skill/copy_skill-main/AGENTS.md。
- 发布端开发：先读 creatorhub/AGENTS.md。
- API收费中转站：先读api-platform/README.md；部署另读api-platform/deploy/README.md，测试使用隔离数据库和假供应商。
- 日常跨模块操作：先读 Haike-Videohub/agent-runbooks/README.md，再读匹配手册并核对实时状态。
- 用户明确说「模板图文视频」：读生产端入口后直接读同名手册，不替换成其他制片路线。

凭据仅存放于忽略的本地配置；安装默认跳过本地 Qwen TTS。付费调用和真实发布按各模块审批闸门执行。上传只包含源码、模板和可分发资源。

开发改动在所属模块执行相关检查。共享手册的维护遵循原有提案机制；本次整合未授权把历史经验标为新机实测。单仓库验收通过不代表真实账号、云服务和另一台物理机已验收。

## Git迭代管理

用户确认的仓库为hrbj18/haike-workflow，保留公开可见性，origin指向它。main为旧交付基线，dev-ybw为现有集成分支；新版上传feat/retain-capabilities-ui并给旧main打保留标签，不合并main。先前源码上传阶段的“不打包”范围已结束，当前另行授权制作干净便携ZIP，交付边界见docs/DISTRIBUTION.md。后续修改从集成分支建立feat/fix分支，通过检查、PR审阅和已授权推送管理迭代。流程见docs/GIT_WORKFLOW.md。

实际14754安装副本与Git源码checkout分离：优先修改版本管理的源码，验收后向明确安装目标同步，不把安装副本的运行数据当作源码。前端用scripts/build-studio.py构建，编译目录被忽略。Git提交与生产部署分开；云端账本和主密钥独立备份，代码回退不自动恢复资金数据库。
