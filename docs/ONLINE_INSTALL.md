# Windows 轻量联网安装包

v1.0.0 公开附件只包含程序、模板、可分发资源和已编译界面。Python、Node、FFmpeg、渲染浏览器和依赖库首次安装时下载，后续程序补丁不重复携带这些文件。无需管理员权限，不修改系统 Python、Node 或全局 PATH。

## 使用

1. 下载 `haike-video-v1.0.0-windows-x64-online.zip` 和对应 `.sha256`，核对后解压到新的可写目录，例如 `C:\HaikeVideo`。不要覆盖正在使用的旧副本；Windows 建议使用较短路径。
2. 双击 `01-setup.cmd`，保持联网，等待提示成功。首次需要下载数百 MB 以上依赖并占用数 GB 磁盘；安装过程写入 `.portable/logs/online-install.log`。失败后重新执行，已校验的下载会复用。
3. 按 [API Key 配置](API_KEY_SETUP.md) 导入自己的配置，再双击 `02-start.cmd`。也可用 `01-setup.cmd -ConfigDocument '私有文档绝对路径' -Full` 一次完成安装、导入和诊断。默认保留已有配置。
4. 日后在“关于海客视频”检查版本。兼容补丁只替换程序，保留配置、平台账号、素材和作品；安装失败自动恢复旧程序。首版是完整程序基线，旧副本先按 [更新说明](APP_UPDATES.md) 迁移。

需要 Python 虚拟环境、npm 库、视频编解码和浏览器，轻量包仍需完成首次依赖安装才能运行；它不是离线包。重复初始化不搬移或清空平台账号、项目和作品。

## 国内网络直连下载地址

安装器使用下列 HTTPS 地址。发布前已在本机直接访问并下载核验；地区、运营商和镜像同步情况可能不同。无需使用 GitHub 代理下载这些依赖。固定版本和 SHA256 保存在 [下载清单](../config/online-downloads.json)，不接受 HTML 提示页或错误文件。

| 依赖 | 主地址 | 备用 / 说明 |
| --- | --- | --- |
| Python 3.12.8 x64 ZIP | [华为云](https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.zip) | [华为云备用域名](https://repo.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.zip) |
| Node 22.23.4 x64 ZIP | [npmmirror](https://registry.npmmirror.com/-/binary/node/v22.23.4/node-v22.23.4-win-x64.zip) | [华为云](https://mirrors.huaweicloud.com/nodejs/v22.23.4/node-v22.23.4-win-x64.zip) |
| Python 库 | [阿里云 PyPI](https://mirrors.aliyun.com/pypi/simple/) | [清华 PyPI](https://pypi.tuna.tsinghua.edu.cn/simple/)、[华为云 PyPI](https://repo.huaweicloud.com/repository/pypi/simple/) 备用 |
| uv、微软本地运行库 | [清华 PyPI](https://pypi.tuna.tsinghua.edu.cn/simple/) | [华为云 PyPI](https://repo.huaweicloud.com/repository/pypi/simple/)；具体 wheel 地址和校验值见清单 |
| npm 库、Remotion、Hyperframes | [npmmirror npm](https://registry.npmmirror.com/) | 项目锁文件记录版本与包完整性 |
| 渲染浏览器 149.0.7790.0 | [npmmirror Chrome Headless Shell](https://registry.npmmirror.com/-/binary/chrome-for-testing/149.0.7790.0/win64/chrome-headless-shell-win64.zip) | 与锁定 Remotion 版本匹配 |
| FFmpeg / ffprobe 9.0.2 | [Gyan 固定版本 ZIP](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip) | 发布者原站，本机可直连；[发布者 SHA256](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256) |

上述依赖安装在本副本的 `runtime/`、各模块 `.venv/` 和 `node_modules/`。下载缓存在 `.portable/downloads/`，以 SHA256 命名。Python 和二进制资源校验后才解压；Python/npm 库分别按锁定版本和 npm integrity 安装。

安装失败时保留日志、检查网络和磁盘，再执行 `01-setup.cmd`；不要用来源不明的文件替换校验值，也不要删除用户配置来修复依赖。程序更新回退不负责回滚手工修改的依赖；依赖修复的旧树保留在 `.portable/dependency-backups/`。

## 可选资源

默认不下载本地 Whisper-small、Qwen TTS、大型模型或完整交互浏览器。识别、配音和数字人按现有云端配置使用；需要本地识别时另行安装模型，未安装不宣称离线识别可用。平台扫码/发布使用系统 Chrome，按 [Chrome 官方页面](https://www.google.cn/chrome/) 安装。MediaCrawler、ADu 等可选工具按原许可和模块说明单独配置。

公开包不含 Key、Cookie、账户数据库、私人截图、样片、人物、音色、项目或作品。首次联网安装和隔离诊断不代表真实云服务、付费制作、账号发布或另一台物理机已经验收。
