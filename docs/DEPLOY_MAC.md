# Mac 新电脑从 main 源码部署

适用于 macOS 14 或更新版本，支持 Apple Silicon 和 Intel。此入口直接运行当前仓库源码，不经过“关于海客视频”、联网升级器或 Release 更新包。已有旧版要保留原安装并升级时，使用 [Mac 源码升级教程](UPGRADE_FROM_MAIN_MAC.md)。

## 给 Agent 的一句话

> 请从 hrbj18/haike-workflow 的 main 源码为这台 Mac 全新部署海客工作台，按 docs/DEPLOY_MAC.md 使用国内镜像安装，保留已有数据和配置，最后启动验收并生成本地测试视频，不走 Release 更新包。

Agent 先读取根 AGENTS.md、README.md 和本文件。确认源码目录与已有工作台目录不同；记录 `git rev-parse HEAD`，本次安装和回退固定到该提交，不在执行中再次跟随 main。没有 Git 的新电脑也可以从 GitHub 的源码 Download ZIP 开始，不需要先安装 Homebrew 或 Xcode。

## 安装与启动

在已解压或克隆的仓库根目录运行：

```bash
bash scripts/setup-mac.sh
```

也可以双击 `01-安装Mac.command`。若系统未给予命令文件执行权限，在终端运行上述命令。首次下载、安装 Python/npm 依赖并构建前端，需要联网和充足磁盘空间。安装不需要 sudo，运行时和虚拟环境留在本项目目录；默认跳过本地 Qwen TTS。不要运行 Windows 的 setup.ps1，不复制 Windows `.venv`、exe 或 DLL。

双击 `02-启动Mac.command` 启动工作台和账号服务；终端等价命令为：

```bash
bash 02-启动Mac.command
```

实际地址由启动器输出，默认从 14756/8000 寻找空闲端口，只监听本机。它核对服务所属目录，保留其他副本的服务。日志位于 `.local/mac-launcher/`，地址和本副本 PID 位于 `.local/mac-services.json`。

## 国内依赖镜像与版本

可直接查看 [_distribution-tools/macos-runtime.json](../_distribution-tools/macos-runtime.json)：按架构列出 Python、Node、FFmpeg/ffprobe、渲染浏览器和登录浏览器的完整下载 URL、大小、SHA256 和上游来源。下载后先核对摘要再解压，不运行浮动的 latest，也不通过第三方 GitHub 代理转发凭据。

- Python standalone、Node 和 Chrome for Testing 使用 [npmmirror 二进制镜像](https://npmmirror.com/mirrors)，npm 使用 [npmmirror registry](https://npmmirror.com/)。
- Python 包使用[清华 PyPI 镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)。
- 素材采集器另按 `_distribution-tools/mediacrawler-source.json` 获取固定提交的公开源码归档并校验；保留已有采集器及其数据。新机及离线包补齐原生采集依赖，使用抖音仍需本机登录和原有授权检查。
- 动效颜色转换使用 FFmpeg 9.0.2 的固定原生 ZIP，由清单中的构建发布方直连下载并核对公开摘要，不依赖 GitHub 下载代理；该地址不是国内托管镜像。
- 本地安装只设置本次子进程的源，不改全局 pip/npm 配置；公网镜像只获取公开依赖，不接收 API Key。

源码版本不附带依赖二进制；国内镜像是下载入口，当前网络可达性不能保证所有地区、所有时间均可达。镜像下载或摘要校验失败时停止，保留现场，不跳过校验或偷偷换包。

CI 可显式从上游获取相同摘要的公开运行时以避免跨洲镜像延迟；目标 Mac 默认仍使用上述国内镜像。登录用的 Chromium 缓存与项目 Patchright 驱动版本匹配；真实平台写入继续遵循原有系统 Chrome、登录和账号检查。

## 私有部署 ZIP 与数据

用户明确授权的同事部署 ZIP 可以另附 `private-profile/`，其中包含导入文档、音色 ID、形象和原始私有资料。该目录及 `deployment-cache/` 被 Git 忽略，不能上传公开仓库、公开附件或工作日志。包内 `PROFILE-MANIFEST.json` 校验后离线导入；已有非空配置优先，不购买音色、不调用付费模型、不迁移 Cookie、待执行任务或资金数据库。完整离线包自动执行 `--offline`；缺件立即报错，不后台联网补依赖。

公开源码不包含这些私有内容。新用户按 [API_KEY_SETUP.md](API_KEY_SETUP.md) 在本机导入自己的配置。音色需要对应服务账号的权限，保存 ID 不代表已验证新电脑上的云端调用。形象导入到工作台，平台账号仍在该电脑自行扫码登录。

升级前只备份实际配置、Git修改、草稿/任务元数据及一致性数据库；原视频/音频/图片/作品留在原位置并核对绑定，不复制整个旧安装或媒体目录。私有备份不上传Git。全新另一台电脑部署不复制生产队列、排期或账本，避免再次执行旧任务。已有电脑升级一次接入干净Git后，可按 [APP_UPDATES](APP_UPDATES.md) 从页面直接更新 main；无Git的源码ZIP仍须先接入。

## 验收与失败处理

1. 安装进程退出码为 0；`03-检查Mac.command` 检查原生 Python 导入、依赖一致性、媒体工具和 18 套首选模板源码摘要。
2. 打开启动器返回的 `/avatar`，确认页面和两类模板封面可见；调用 `/api/health` 核对 workspace 属于本目录。看见模板不等于该模板已在 Mac 完整渲染验收。
3. Agent 运行包内 Python 执行 `scripts/mac-deploy-smoke.py`：实际导出已有 HeroTitle 动效，检查画面运动、音视频流及 HTTP 封面，输出 `.local/mac-smoke/installation-test.mp4` 和验收 JSON。它使用合成测试音，零付费，不是真实数字人制作。
4. 全部18套动效的双架构完整时长渲染门槛、原生制作入口及恢复见 [MAC_MOTION_VALIDATION.md](MAC_MOTION_VALIDATION.md)。源文件校验不能替代实际渲染；发布验收记录需明确两种架构各18条的结果。
5. 制作真实口播时按 START_HERE.md 的原有预算、真实素材、统一队列和视听验收执行。本地合成测试不代替真实数字人/ASR、平台账号和同事物理机验收。

失败时保留日志、源码提交和配置；安装器不删除已有用户数据。下载失败可修复网络后重跑同一提交；离线包先核对 ZIP SHA256 和缓存完整性。依赖损坏时在保留原 `.venv` 后重建本项目环境；不清理系统 Python、全局 npm 或其他项目。新部署尚未接管生产时，回退只需重新使用原工作台目录；已产生的新数据另行保留，代码回退不回退账户余额。

实际已完成的验证以本次交付验收记录为准；CI 原生 Mac、当前 Windows 和同事物理机是不同证据，不互相代替。
