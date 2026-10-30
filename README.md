# Haike Workflow

已有安装需要更新时，从[GitHub地址联网升级](docs/UPDATE_WITH_CODEX.md)进入：Codex负责识别目标副本、自动下载与校验，后续在“关于海客视频”检查并下载安装。不要用Git覆盖运行目录或重新执行全量setup。1.2联网修订规范版本号为1.2.1，实际上线状态以GitHub Release及其更新清单为准。

当前稳定源码入口为`main`（2026-10-27），版本范围与验收见[稳定版说明](docs/releases/20261027-stable.md)。本地新版ZIP另含40张用户授权截图，入口见[模板交付](docs/TEMPLATE_DELIVERY.md)；私人截图和样片不进入公开Git。Windows便携包按根`使用说明.txt`初始化并导入自己的私有配置；已有独立APIKey包也可用`00-install.cmd`，再运行`02-start.cmd`。Key不进入项目ZIP。两条RunningHub工作流都包含，性价比默认，高质量需明确指定；详情见`Haike_video/workflows/runninghub-high-quality/README.md`。

海客科技视频工作台与统一API收费中转站的源码仓库。用户确认的仓库为 [hrbj18/haike-workflow](https://github.com/hrbj18/haike-workflow)，保留公开可见性和原提交历史；后续迭代、分支和提交见 [Git管理](docs/GIT_WORKFLOW.md)。`main`为稳定交付入口，旧基线保存在`legacy-main-before-20261027`及原有历史标签，功能分支继续保留。

**解压便携包后，根目录有 `PACKAGE-MANIFEST.json`：先读[便携包初始化](docs/PORTABLE.md)，用 `01-setup.cmd -ConfigDocument '私有文档绝对路径' -Full` 一次初始化并导入，再运行 `02-start.cmd`。** 包内已有运行时，使用这条入口；后续可用 `03-check.cmd` 诊断。把实际需要的 Keys、服务地址、音色和预设集中到单独的私有配置文档，步骤与三平台扫码见[首次配置说明](docs/API_KEY_SETUP.md)。源码 checkout 按下文“Windows 源码安装”准备环境。保留以下布局：

Codex / Agent 首次接入请读[基础教程](START_HERE.md)：Codex 总控、首次配置、单条制作、夜间三条与发布汇报、原任务恢复；接口详情继续由各模块文档维护。

工作台底部“关于海客视频”提供版本、稳定版检查和兼容便携包的一键更新；发布清单、数据保留及故障恢复见[应用更新说明](docs/APP_UPDATES.md)。

2026-10-13工作台V2：默认进入图文视频，数字人口播为另一制作入口；共用“我的作品、发布日历、API设置”。界面保持海客科技品牌，旧独立工具页面已归档移除，历史素材、作品及底层生产依赖保留。功能、清理与验证范围见[工作台V2](docs/PRODUCT_STUDIO_V2.md)。

独立新版的当前测试结果与交付范围见[2026-10-16交付回归](docs/RELEASE_READINESS_20261016.md)。本机回归通过不代表云端功能已发布，或新电脑仅填Key即可恢复全部能力。

| 目录 | 用途 |
| --- | --- |
| Haike_video | 制片工作台、素材与作品管理、音频、字幕、渲染 |
| copy_skill/copy_skill-main | 采集分析、素材交付、研究包 |
| creatorhub | 多平台发布面板 |
| Haike-Videohub | 契约、操作手册与跨模块检查 |
| api-platform | 用户账户、充值兑换、统一模型网关、定价与调用账单 |
| prototypes/haike-avatar-generator | 视频工作台React界面源码 |

## Windows 源码安装

准备 64 位 Python 3.12、Node.js 22+、Git、uv 和兼容 MSVC 14.4x 的 [微软 Visual C++ x64 运行库](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)，确保 `python`、`node`、`npm`、`uv` 在 PATH。安装需要联网获取 Python/npm 依赖、FFmpeg 和渲染浏览器。平台采集/发布另需系统 Chrome。本源码不捆绑本机 DLL。

```powershell
git clone --branch main https://github.com/hrbj18/haike-workflow.git
cd haike-workflow
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

私有仓库需要已获授权的 GitHub 身份。安装脚本分别创建三个模块的虚拟环境，保留已有本地配置，不启动发布任务、不调用付费服务。默认不安装本地 Qwen3-TTS；明确需要时传 `-LocalTts install`，会额外下载数 GB 依赖/模型。百炼云端克隆不需要本地 TTS。

安装时会在依赖同步后分别验证制片和采集两个虚拟环境的 ONNX、CTranslate2 和 VAD 能否加载，检查位于隐藏、限时的子进程，失败会停止安装并提示修复。系统运行库冲突时，可提供有合法分发来源的同版本微软 x64 DLL 目录（`vcruntime140.dll`、`vcruntime140_1.dll`、`msvcp140.dll`，14.44 或更新）：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -MsvcSource 'D:\runtime-source'`。脚本检查架构、签名和版本后只配置 `Haike_video/.venv/msvc`、`copy_skill/copy_skill-main/.venv/msvc` 及各自的 `Lib/site-packages/sitecustomize.py`，保留其他启动钩子；不修改全局系统运行库或发布服务环境。已有环境可单独运行 `python _distribution-tools/setup_msvc.py --source-dir 'D:\runtime-source'`，省略来源则复用已有本地成套运行库并重新验证这两个环境。回退时仅移除对应虚拟环境的这三个本地 DLL 和脚本创建的启动钩子，然后改用有效的系统运行库或重建该虚拟环境；勿删除自行创建的启动钩子。

基础运行环境安装后，双击「一键启动工作台.cmd」。新版统一进入 `/avatar`，默认 `http://127.0.0.1:14756/avatar`；以启动器实际端口为准，旧预览页不会自动升级。口播页可直接查看和编辑默认设置，查看任务进度与结果。启动器先检查本副本账号服务（默认 `http://127.0.0.1:8000`，可用 `HAIKE_CREATORHUB_URL` 指定本机 HTTP 端口）；只复用工作区身份匹配的服务，不停止其他副本。启动日志在忽略的 `.local/launcher/`，不复制登录记录。发布面板也可独立启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-publisher.ps1
```

发布面板需登录自己的账号；创建真实发布任务可能立即执行，必须先确认内容、账号和授权。启动后不会继承原机器的任务、Cookie、数据库或排期。

## 按能力配置

- 新工作台默认由当前 Agent 自身模型完成文案、视觉分析、选材与审核，百炼负责配音/克隆/ASR，RunningHub 负责数字人，Pexels 是可选备用素材源。按[一次导入说明](docs/API_KEY_SETUP.md) 集中导入配置，无需腾讯、GPT 或海客网关 Key；旧网关路线保留兼容。私人音色映射与服务/账号绑定，实际可用性须检查；历史云端发布边界见[交付回归](docs/RELEASE_READINESS_20261016.md)。
- 发布：安装时从 `creatorhub/config.example.yaml` 生成忽略的 `config.yaml`。
- 采集：公开默认配置为 `copy_skill/copy_skill-main/config/content_intelligence.json`；本机覆写写到同目录 `content_intelligence.local.json`（递归合并对象，列表整体替换）。显式传配置路径时不加载覆写。
- 抖音采集：MediaCrawler 为独立可选依赖；按 `Haike-Videohub/deps/B-external.md` 配置，先核对其许可。没有将第三方源码复制进本仓库。
- 模板图文的人脸检查模型：运行 `python scripts/fetch-models.py` 获取固定版本 YuNet 并验证 SHA256。其他 ASR/TTS 模型按能力另行安装。
- 人物图、私人音色、背景音乐、历史素材和成片由使用者自行导入；这些资料不随 Git 交付。

## 检查与打包

```powershell
python scripts/check.py
python -m unittest discover -s tests -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
python scripts/package-source.py
```

`check.py` 无第三方依赖，检查暂存/跟踪文件的边界、Python 语法、关键布局与配置。`check.ps1` 额外检查本机依赖并用假数据执行跨模块契约校验。它不采集、不发布。

GitHub Actions已启用，自动执行源码边界、迁移测试、PowerShell解析、凭据扫描，以及收费中转站、视频工作台和前端组件检查。配置见 `.github/workflows/`；没有生产密钥，不自动部署或执行真实收费与发布任务。

源码打包仅导出已提交 HEAD，工作区有源码改动时拒绝打包；ZIP 与 SHA256 写入忽略的 dist。源码 ZIP 不包含虚拟环境和运行时。便携 ZIP 单独包含经清单核对的运行环境与干净前端产物，初始化方法和实际验证范围见[便携包说明](docs/PORTABLE.md)。

项目内页的可选浏览器回归使用独立列出的开发依赖，不影响基础运行配置。首次运行前准备对应的 Chromium；已有匹配缓存时安装器会复用：

```powershell
uv pip install --python Haike_video/.venv/Scripts/python.exe -r Haike_video/requirements-browser-tests.txt
& .\Haike_video\.venv\Scripts\python.exe -m playwright install chromium --only-shell
Push-Location Haike_video
try { & .\.venv\Scripts\python.exe -m pytest tests/backlot/test_ui_bug_bash.py } finally { Pop-Location }
```

这些用例创建临时假项目和自有本地服务，结束后回收进程树，不连接真实账号或调用付费供应商。未安装可选依赖时会明确跳过；跳过不代表浏览器行为已验证。

## 统一 API 商业化设计

充值、客户 Key、模型定价与调用账单见 [商业额度与统一网关](docs/api-platform/商业额度与统一网关.md)。已新增 [api-platform](api-platform/README.md) 的本地账户中心：双击「启动API账户中心-Mac.command」或「启动API账户中心-Windows.cmd」，访问 `http://127.0.0.1:17894/`，首次自行设置管理员，已有账户保留。

包含客户注册/管理员开户、管理员充值、一次性兑换码、统一Key、供应商加密配置、成本×1.5定价、报价与实际调用账单。账户中心部署入口为 `https://8.138.207.71:17894/`，工作台接 `/v2` 网关。既有默认配音已完成真实结算；RunningHub数字人样片已生成，该次0.72元仍待对账。新账号的模型权限、报价与实际能力须按账号核验，当前状态见[交付回归](docs/RELEASE_READINESS_20261016.md)；在线支付结算未在本轮验收。不包含激活码和防转售功能。

[动效口播](docs/PRODUCT_AVATAR_MOTION.md) 保留ADu目录、九种轻量动画、字幕与可编辑工程的代码适配；当前独立ADu引擎未安装，基础安装不自动获取，真实动效生产尚未验收。原三套口播版式保留。工作台嵌入静态界面为构建产物，运行 `python scripts/build-studio.py` 生成，不提交生成文件。

导入来源见 `SOURCE-PROVENANCE.json`，交付范围、许可边界与验收记录见 `docs/DISTRIBUTION.md`、`THIRD_PARTY_NOTICES.md` 和 `docs/VERIFICATION.md`。本次统一入口优先于模块内历史多仓部署、旧版本和旧便携包说明。
