# GitHub 与跨电脑部署

私有开发迁移按根`docs/DEVELOPMENT_RECOVERY.md`恢复；有migration清单时以其必读记录核对最新.motion中断点，原冻结证据保留。

更新时间：2026-10-28

应用更新首版：根docs/APP_UPDATES.md，VERSION.json引入1.0.0产品编号，源码显示开发态。studio_update_api.py与根portable/{app_update,update_service,update_worker}.py负责HTTPS清单、兼容程序补丁、任务维护闸门、独立重启/回退；AboutDialog.jsx为入口。根test_*update*.py及test_studio_update_api.py覆盖数据保留和启动失败恢复。线上清单/包仍需正式发布，其他安装/云服务未同步。

10/28运行修复：14756旧进程导致版本接口404，队列空闲后重启本副本，实读1.0.0开发版；关于弹窗区分本地版本读取失败与在线检查失败，停止持续“正在读取”提示。线上清单尚未发布。

10/27：用户授权将已验收交付快照21d1ff2发布为main稳定版，旧main保留legacy-main-before-20261027，合入后固定stable-20261027；见根[稳定版说明](../../../docs/releases/20261027-stable.md)。模板[交付说明](../../../docs/TEMPLATE_DELIVERY.md)含40张本地ZIP截图/42目录及备份回退。发布不混入其他窗口新改动；未声称异机/付费/发布验收。

## 权威入口

- 10/21交付分支`feat/avatar-template6-zhaoshang-a`为历史入口；当前稳定入口main。便携包从提交导出并重建界面；APIKey私有ZIP禁止上传GitHub。初始化见根`使用说明.txt`、`01-setup.cmd`；既有10/21证据在根`.local/release-20261021/`。
- 两条RunningHub路线随源码交付：性价比2094449979141218305仍为默认；V5.3.1高质量2112180419025260546的独立执行器及完整JSON位于`workflows/runninghub-high-quality/`。新任务读取根`scripts/runninghub-workflow.py show`，仅用户明确要求才保存长期Agent偏好；不修改Studio路由/旧任务。普通Studio与高质量统一父队列适配仍待验。公开附件不带私人图/声音/音色。

- 用户确认单仓为`https://github.com/hrbj18/haike-workflow`，保留公开可见性。根README及 `docs/GIT_WORKFLOW.md` 是安装、分支、CI和迭代入口。
- 原`feat/retain-capabilities-ui`与`legacy-before-v2-20261017`保留；旧main为0518367。`dev-ybw`集成分支不自动移动；后续基线与分支流程以根`docs/GIT_WORKFLOW.md`为准。
- 旧单模块仓库、旧标签和便携包不代表新版已发布能力；共享分支通过PR审阅，保留原历史。
- Windows完整安装：根 `scripts/setup.ps1`，Python3.12、Node22+、Git/uv；默认跳过本地Qwen TTS。安装新增前端构建，不继承账号、任务或素材。
- 工作台静态文件由根 `scripts/build-studio.py`生成；源码目录为 `prototypes/haike-avatar-generator`。Mac源码checkout与14754安装副本分离，更新须明确同步目标。
- ADu仍需安装固定的同级引擎与媒体依赖；详见根 `docs/PRODUCT_AVATAR_MOTION.md`，未声称Windows实机已验。

## 云端与状态

- 收费中转站当前入口 `https://8.138.207.71:17894/`，网关 `/v2`；部署在独立版本目录，通过current切换，私有账本与主密钥在代码目录之外。根 `api-platform/deploy/README.md` 是更新、备份、恢复入口。
- 旧统一网关和内部配音保留兼容，历史任务使用冻结路由；新版便携包默认直连路线见下文。既有配音曾真实结算；RunningHub旧样片该次0.72元仍待对账。新账号能力、权限与报价须核验；状态见`CURRENT_STATUS.md`及根`docs/RELEASE_READINESS_20261016.md`。不得重启旧账本形成双重余额。
- CI只有读取源码权限、隔离数据及假供应商，不自动部署、真实收费或发布。代码回退不能自动回退账本。
- 旧Linux视频工作流、旧便携包及其他服务的运行证据保留于既有任务/部署文档；此次Git初始化未修改它们，也不把本机验收称为另一台机器验收。

## 新机器验收

克隆当前仓库后运行根源码检查及安装；配置自己的平台Key和发布账号，私下导入自有素材。模型和运行依赖按对应模块安装，完成环境检查、无付费测试及短样本审核后再接受生产任务。

便携包使用根`01-setup.cmd -ConfigDocument <私有文档>`，按`docs/API_KEY_SETUP.md`唯一JSON块一次导入Key、地址、预算及预设；默认保留本机已有配置。真实文档单独交付，ZIP/Git只有空模板。导入离线、不搬Cookie或伪造验证记录。当前默认由工作Agent自身完成文案/视觉/分镜与审核，百炼负责配音/克隆/ASR，RunningHub负责数字人，Pexels作为可选备用；不要求GPT、腾讯或海客网关Key。三平台在本机扫码，制作发布仍按授权范围执行。

默认单条5元中为数字人预留4元、百炼字幕0.1元；配置检查核对阶段预算合计并给配音留余量。百炼明确启用、Key与成本预算齐全即可首次执行，历史verified保持真实状态，初始化不伪造实测。旧已冻结任务仍复用其原识别和分析路线。

批次入口支持完整音轨`audio_path`，保持原音频并跳过TTS；`advance`推进原队列、质量门与发布计划，支持既有平台排期，`report_path`落Markdown汇报。宿主负责定时唤醒，未质检或未确认的发布不标完成。明确配置Pexels素材来源时无需代填抖音使用授权；仍执行实时登录检查，无合适画面暂停。隔离CLI/HTTP/队列/发布器假供应商联测与真实平台回执分别记录。

Agent素材分析通过Studio的`agent-materials`读写：真实音轨/ASR后提供原版本与clock；Agent按真实cue安排分镜、观看保留候选代表帧并提交SHA绑定结论，再恢复原任务。没有分析结果时可恢复暂停，不后台调用中转模型，不重做已成功的TTS/ASR。已有上传素材也须提供来源/使用权和实际观察依据，最终汇报不包含私人配置。

2026-10-17源码隔离回归：Studio及批次419项、根初始化84项、前端128项通过。N1可在明确关闭联网后使用Agent已审本地素材；开启联网仍要求采用真实网络来源，未找到素材不降级。证据在忽略目录`.local/portable-build/`，本轮未产生费用或真实发布。

最终便携包源码固定`53f47b0`，交付`dist/Haike_videoflow_20261017_v2/`仅ZIP和私有配置文档。完整解压77,499项CRC/SHA及凭据扫描通过；新目录一键导入、419项隔离回归、本地渲染、报价、设置页和重复启动/初始化通过，7份配置保持字节一致。未搬账号或伪造云端验证，旧ZIP/main不动；最终证据`.local/portable-build/verification-agent-final.json`。这是本机独立目录验收，不是另一台物理机或真实收费发布验收。

Git仅保存源码、测试、公开配置模板、可分发品牌资源与设计文档。凭据、账本、主密钥、Cookie、项目素材、成片及备份被忽略，另行加密备份。新机静态测试通过不代表真实供应商、付费结算或账号发布已经验收。
