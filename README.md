# Haike Workflow

海客科技视频工作台与统一API收费中转站的源码仓库。自己的私有仓库为 [vincent841218449/haike-workflow](https://github.com/vincent841218449/haike-workflow)，原上游历史保留；后续迭代、分支和提交见 [Git管理](docs/GIT_WORKFLOW.md)。安装时保留以下布局：

2026-10-13工作台V2：默认进入图文视频，数字人口播为另一制作入口；共用“我的作品、发布日历、API设置”。界面保持海客科技品牌，旧独立工具页面已归档移除，历史素材、作品及底层生产依赖保留。功能、清理与验证范围见[工作台V2](docs/PRODUCT_STUDIO_V2.md)。

| 目录 | 用途 |
| --- | --- |
| Haike_video | 制片工作台、素材与作品管理、音频、字幕、渲染 |
| copy_skill/copy_skill-main | 采集分析、素材交付、研究包 |
| creatorhub | 多平台发布面板 |
| Haike-Videohub | 契约、操作手册与跨模块检查 |
| api-platform | 用户账户、充值兑换、统一模型网关、定价与调用账单 |
| prototypes/haike-avatar-generator | 视频工作台React界面源码 |

## Windows 源码安装

准备 64 位 Python 3.12、Node.js 22+、Git、uv 和兼容 MSVC 14.4x 的 Visual C++ x64 运行库，确保 `python`、`node`、`npm`、`uv` 在 PATH。安装需要联网获取 Python/npm 依赖、FFmpeg 和渲染浏览器。平台采集/发布另需系统 Chrome。原生 OCR/ASR 若报告 DLL 错误，按采集模块 native_runtime.py 的说明配置匹配的运行库；本源码不捆绑本机 DLL。

```powershell
git clone https://github.com/vincent841218449/haike-workflow.git
cd haike-workflow
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

私有仓库需要已获授权的 GitHub 身份。安装脚本分别创建三个模块的虚拟环境，保留已有本地配置，不启动发布任务、不调用付费服务。默认不安装本地 Qwen3-TTS；明确需要时传 `-LocalTts install`，会额外下载数 GB 依赖/模型。百炼云端克隆不需要本地 TTS。

基础运行环境安装后，双击「一键启动工作台.cmd」，默认端口 14754。发布面板独立启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start-publisher.ps1
```

发布面板需登录自己的账号；创建真实发布任务可能立即执行，必须先确认内容、账号和授权。启动后不会继承原机器的任务、Cookie、数据库或排期。

## 按能力配置

- 新工作台云端模型、配音、数字人：在“API设置”填写账户中心生成的海客Key及网关地址。旧项目底层适配器仍可读取`.env.local`，新入口通过统一网关调用。
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

源码打包仅导出已提交 HEAD，工作区有源码改动时拒绝打包；ZIP 与 SHA256 写入忽略的 dist。源码 ZIP 不包含虚拟环境和运行时，不是离线安装包。

## 统一 API 商业化设计

充值、客户 Key、模型定价与调用账单见 [商业额度与统一网关](docs/api-platform/商业额度与统一网关.md)。已新增 [api-platform](api-platform/README.md) 的本地账户中心：双击「启动API账户中心-Mac.command」或「启动API账户中心-Windows.cmd」，访问 `http://127.0.0.1:17894/`，首次自行设置管理员，已有账户保留。

包含客户注册/管理员开户、管理员充值、一次性兑换码、统一Key、供应商加密配置、成本×1.5定价、报价与实际调用账单。账户中心已部署于 `https://8.138.207.71:17894/`，工作台已接 `/v2` 云端网关。配音、腾讯配音、识别、素材已开通；缺少采购价的文本/视觉与RunningHub数字人仍不开通。真实收费与在线支付结算未在本轮验收；不包含激活码和防转售功能。

新增 [动效口播](docs/PRODUCT_AVATAR_MOTION.md) 接入ADu完整目录、九种轻量动画、字幕与可编辑工程；原三套口播版式保留。工作台嵌入静态界面为构建产物，运行 `python scripts/build-studio.py` 生成，不提交生成文件。

导入来源见 `SOURCE-PROVENANCE.json`，交付范围、许可边界与验收记录见 `docs/DISTRIBUTION.md`、`THIRD_PARTY_NOTICES.md` 和 `docs/VERIFICATION.md`。本次统一入口优先于模块内历史多仓部署、旧版本和旧便携包说明。
