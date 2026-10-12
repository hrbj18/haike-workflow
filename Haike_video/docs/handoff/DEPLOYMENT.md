# GitHub 与跨电脑部署

更新时间：2026-10-12

## 权威入口

- 私有仓库：`https://github.com/hrbj18/Haike_video`
- 发布状态：`main`/`v0.1.1` 稳定版为 `50352aaa`；`dev` 已于 2026-09-10 纳入 `dae5886c` 源码候选，在既有统一生产队列、豆包 ASR、本地素材理解、户外互动两次剪辑和多标题图层基础上，补充输出响度控制、原音轨精确定时字幕/时间线、单段库存素材同步及数字人尾帧安全规范化。
- 同事入口：GitHub 根目录 `START_HERE.md`；版本由 `VERSION`、`CHANGELOG.md` 和 `docs/handoff/RELEASE_STATUS.md` 共同定义。
- Windows 完整步骤：`docs/DEPLOYMENT_WINDOWS_ZH-CN.md`
- 环境变量模板：`.env.example`
- 一键安装：`scripts/setup.ps1`
- 启动与预检：`启动工作台.bat`、`scripts/preflight.ps1`
- 工作区外层双击`一键启动工作台.cmd`；调用`start-workbench.ps1`。验证Python3.12，迁移失效venv可复用随包Python+已有库；14754优先、端口受限自动避让，默认不启动可选TTS、不下载。原4754在本机4715–4814系统保留范围内。

## 新电脑顺序

离线入口：工作区 `_distribution-tools/offline/README-START-HERE.md`；首启迁移，Qwen可选，封包复位venv并清理私人路径。主包缺数字人Whisper/模板YuNet，须配`dist/haike-offline-models-supplement-20261012.zip`；API与新机逐项验收文档同在dist。中转仅契约/mock，新机/真实云调用另验。

旧精简包：`dist/haike-workflow-windows-x64-slim-20261010.zip`；浏览器/FFmpeg首次下载。新离线包的根说明优先于下列源码安装步骤。

Windows 初始化询问可选本地 Qwen3-TTS；云端克隆不需要它，`-LocalTts skip/install` 依用户选择，回车跳过。已安装环境保留；未安装不阻断工作台。便携项目增量包 `dist/haike-bailian-cloud-clone-update-20261010-v2.zip`：停本工作台、整批预检/备份、未知源码合并，保留默认和项目。支持原/精简/本地v1–3/云端V1；新增录音上传→百炼创建→审核查询→ID登记，需百炼密钥+私有OSS配置，上传依赖multipart/oss2，无本地模型。旧版升级和83项离线回归过；真实OSS/创建、新机权限未验。

1. 安装 Git、64 位 Python 3.12、Node.js 22+。
2. 克隆 `main` 稳定版，在根目录先读 `START_HERE.md`，再运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1`。
3. 只在 `.env.local` 或 `.env.secrets.local` 写密钥；不要把真实值写回模板。
4. 私下导入克隆音色、人物参考图和音乐。模型由安装器/官方加载器下载，不从 Git 获取。
5. 配置 Pexels；有数字人路线再配置 RunningHub key、已发布 workflow ID、两位角色图与音色。
6. 运行 `scripts/preflight.ps1`、上下文审计，以及 `tests/backlot tests/contracts tests/lib tests/tools tests/unit` 自动套件；pytest 必须带 `--import-mode=importlib --basetemp=.p`，全部通过后才进行短样本真实验收。不要把旧 `tests/qa` 脚本当作默认自动套件。

## Linux 轻量版服务器现状

- 2026-09-01 已将本机忽略的核心密钥配置安全同步到服务器仓库，并按变量名合并进 Docker 持久化 `.env.local`；未覆盖既有 Linux 路径、本地 Qwen3-TTS 或 faster-whisper 配置。
- `haike-video` 容器重启后，只读接口确认 GPT 中转站、豆包文本和 RunningHub 均已配置，RunningHub 配置问题数为 0；本地音频中心仍为 `available`，可见 3 个音色并保留默认音色。
- HyperFrames 已在 Linux 容器内完成 CPU 基线初始化：CLI `0.8.22`、Chrome Headless Shell、`unzip`、FFmpeg 和 FFprobe 均通过关键预检；容器 `/dev/shm` 已提升到 `512 MB`，npm 与浏览器缓存均挂载到 `/opt/Haike_video/cache` 持久化。项目运行时返回 `runtime_available=true`，本轮未执行视频渲染。
- 2026-09-02 已在广州 Linux 轻量服务器通过真实浏览器完成无数字人全流程：新建“键盘排序的秘密”项目、Luna 自动写稿、人工审核闸门确认、本地 Qwen3-TTS、Pexels/HyperFrames 配画面、字幕与 FFmpeg 全片合成，最终到达 `preview_ready`。父任务 `RPP-8b51022434c9` 为 16/16、失败 0，预览 `renders/previews/full-preview-v001.mp4`（H.264/AAC、1080×1920、30 FPS、127.5 秒）；没有自动批准或发布。
- 服务器本地 TTS 的生产默认模型已改为可配置的官方 `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`，通过 `HAIKE_VIDEO_TTS_CUSTOM_MODEL` 选择，并使用 `HF_ENDPOINT=https://hf-mirror.com` 完成模型缓存。1.7B 官方模型缓存仍保留，可通过配置切回；未把云 TTS 写死为唯一实现。0.6B 在该 CPU 服务器上的短句实测冷启动约 112 秒、热调用约 38 秒，完整 16 句流程约 90 分钟，因此“可运行”不等于“高并发实时”。
- 2026-09-03 服务器已从旧 `main/b29f0f4` 更新至 GitHub `dev/b9a0db4`：`haike-video:b9a0db4` 继承原运行镜像重建，所有原持久化挂载（含 `.env.local`、项目、任务状态、渲染、缓存）原样复用。容器健康、`/api/health` 与首页 HTTP 200 已通过；旧 `haike-video-previous-b29f0f4` 停止保留，可回退，勿清理。
- 2026-09-03 服务器配置加载已统一修复：容器由 Python dotenv 启动引导读取权限 `600` 的持久化 `.env.local`，不再用 Docker `--env-file` 直接解析。豆包 TTS 与中转站文本配置均可用；健康、地址解析、TCP 连通性及 `gpt-5.6-luna` 固定 JSON 连接测试均通过。该测试不生成脚本、视频或音频，但会产生极少量文本调用用量；豆包实际音色授权仍待人工短试听验证。
- 本轮没有调用 Pexels、文本模型、RunningHub 或其他付费服务。一次性 SSH 公钥已从服务器撤销，本机临时私钥目录已删除。
- 服务器密钥文件权限为 `600` 且被 Git 忽略；后续更新不得把 `.env.local` 或 `.env.secrets.local` 纳入提交。

## 发布边界

Git 只保存源码、测试、公开配置模板、精确帧 RunningHub API 模板和交接文档。禁止提交 `.env*` 实值、`.backlot/`、`projects/`、模型、私有音色、人物图、音乐、渲染、付费任务产物、审计证据、pytest 临时目录或个人黄金样稿。

RunningHub新任务/冻结旧任务规则以 `AGENT_GUIDE.md` 第4节为准；未知状态停止，不得复制提交。

## 验收边界

本机已验证无数字人与有数字人审核预览路线；有数字人 4 句双主持真实任务达到 `review_ready`，切点由 V2 精确帧清单自动批准，Whisper 仅诊断。新电脑的安装/静态测试通过不等于云端账号、私有素材或付费工作流已经验收，必须按本机配置重新做短样本验证。
