# Windows 依赖镜像与增量更新

适用于源码 `scripts/setup.ps1`、`scripts/build-studio.py` 及页面 main 更新。共享设置在 `portable/dependency_sources.py`，仅传给本次子进程，不改用户全局 pip/npm 配置。

| 内容 | 默认来源 / 复用 |
| --- | --- |
| Python 包（pip / uv） | `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple` |
| npm 包 | `https://registry.npmmirror.com`（实际包可由其 CDN 提供） |
| uv 按需取得 Python | npmmirror 的 python-build-standalone 镜像；优先复用已安装 Python 3.12 |
| 渲染浏览器 | 1.2.5起寻找并复用已安装Chrome/Edge，不下载浏览器；`HAIKE_BROWSER_PATH`可显式指定已有浏览器 |
| FFmpeg / ffprobe | 先检测并复用已有可启动工具；缺失时使用同一 JSON 的固定加速地址、发布方直连地址及 SHA256。此项不是承诺全部由国内镜像托管 |
| 源码与更新检查 | 官方 GitHub main；不经过第三方代理转发账号或 Key |

1.2.5的制片Python锁已去除Whisper及其专用推理依赖，采集端将本地ASR移入显式`local-asr`extra，默认export/install不启用。云端ASR使用用户自己的配置；旧机器的模型和已受理任务保留，安装检查不要求本地模型。历史浏览器下载描述仍供旧版工具识别，不参与1.2.5源码安装。

缺少FFmpeg时，安装器优先使用有界并行分段下载；镜像不支持分段时使用普通下载，失败尝试下一地址。每段检查范围和长度，完整文件仍必须通过固定SHA256，已有合格缓存直接复用。实际速度取决于所选源和目标网络。

采集的 `uv.lock` 内保存了原 PyPI wheel URL，单独改环境变量再 `uv sync --locked` 仍可能走旧地址。Windows 安装先 `uv export --frozen --all-groups --no-emit-project`，保留固定版本和哈希，再通过镜像安装导出的清单；不改用户的 uv.lock。源码增量更新沿用此路线。

安装显式覆盖本次进程继承的旧 pip/uv/npm 源及离线标记，防止旧便携启动环境阻止补依赖。需要自定义镜像时设置 `HAIKE_PIP_INDEX_URL` / `HAIKE_NPM_REGISTRY`；只接受无凭据的 HTTPS 地址。安装结束后原进程/全局配置保留。下载/摘要失败停止并保留现场，不忽略锁或偷偷换版本。

页面更新按原/新提交比较 Python、npm 输入文件；锁文件未变且环境存在时跳过重装，工作台界面重新构建。CreatorHub 的编译界面随源码提交交付，客户机不重写该组已跟踪文件，避免更新后变为 dirty。缺少系统工具、原生 ABI 或运行时需要另行处理时如实报错，不把所有历史版本当同一种环境。

新机按 README 准备 Python3.12 x64、Node22+、Git、uv和微软运行库后运行 setup。旧电脑按 [源码接入教程](UPGRADE_FROM_MAIN.md)复用经过核对的工具；不要把整套 .venv 当可任意搬移的文件夹。
