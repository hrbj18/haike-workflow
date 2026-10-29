# OpenMontage 内置本地配音

OpenMontage 已内置独立的 Qwen3-TTS 服务。工作台、每日生产和数字人驱动音频不需要安装或启动 Voicebox；历史 Python 类名 `VoiceboxTTS` 仅作为项目状态兼容层保留。

## 先分清两件事（常见误解）

1. **`http://127.0.0.1:17494` 是 OpenMontage 自带的 Qwen3-TTS 服务地址，不是 Voicebox 的端口。**
   独立 Voicebox 早已移除（见 `docs/handoff/DECISIONS.md`）。所以报错
   `TTSServiceUnavailable 无法连接 OpenMontage 本地配音服务 http://127.0.0.1:17494` 的含义是
   **「内置本地配音服务没有在运行」**，而不是「缺少某个第三方组件」。
2. **配音中心可以选择本地 Qwen3-TTS 或已配置的云端服务**。本地服务独立安装和启动，
   没装或没启动**不影响云端生产**：`VoiceboxTTS.get_status()` 会返回不可用，
   `audio_center._local_profiles()` 直接返回空列表且不发网络请求 —— 这是**优雅降级，不是故障**。

写测试时注意：若为了让本地音色出现在目录里而把 `get_status()` 打桩成可用，
就必须同时把音色目录也打桩（`tests/backlot/conftest.py::local_tts_catalog`），
否则 `list_profiles()` 会产生真实 HTTP 调用，用例会隐性依赖一个后台服务。

## 新机器安装

在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_local_tts.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start_local_tts.ps1
```

安装器把重型依赖放在 `.backlot\tts-runtime\.venv`。模型首次使用时下载到 `.backlot\tts\models`；这两个目录都被 Git 忽略。工作台一键启动器会尝试后台启动服务，失败时仍允许工作台打开并显示具体原因。

Windows 安装器默认检测 NVIDIA 显卡与驱动；检测到时安装官方 CUDA 12.8 版 PyTorch 2.11 / Torchaudio，并检查 CUDA 可用性。首次运行库下载约 2.6 GB，之后复用。强制显卡安装使用 `setup_local_tts.ps1 -TorchBackend cuda`，并设置 `OPENMONTAGE_TTS_DEVICE=cuda:0`；此配置显卡不可用会明确失败，不会回退 CPU。无 NVIDIA 驱动的 `auto` 安装使用 CPU。驱动需可用，无需另装完整 CUDA Toolkit。

引擎自带 Qwen Serena、Vivian、Dylan 三个中文预设；配音中心仅展示已有批准角色及录入的克隆音色，不重新展示全部历史预设。默认地址是 `http://127.0.0.1:17494`，服务只允许绑定 localhost。

## 在配音中心新建本地克隆音色

1. 主环境安装项目 `requirements.txt`（包含小型 `python-multipart` 上传依赖），启动本地服务，再打开工作台 `/audio`。
2. 在音色管理的“配音服务”选择“本地 Qwen3-TTS”，填写音色名称，上传清晰、单人、无配乐的参考录音，填写录音实际说出的逐字原文。
3. 点击“创建本地克隆音色”。支持常见音频格式，经项目 FFmpeg 解码为 24 kHz 单声道 PCM16 WAV；网页上传上限 20 MB，录音须为 1–60 秒，超长会拒绝而不会截掉内容。
4. 创建后音色自动出现在目录并选作试听。在独立试听中输入新的口播文案，点击“生成试听”，听审后再用于项目。原全局默认音色不会因创建而自动改变。

录入建立可复用的参考音色，不训练新模型。音频、逐字原文与音色配置仅写入配置的本地数据目录；重复录入相同录音、原文和名称会复用同一音色 ID。服务未启动时，页面会显示启动提示；启动后可点击“刷新服务状态”。命令行录入入口为 `scripts/enroll_local_voice.py`。

已下载原版或精简版项目，以及安装过 v2 增补的电脑可以安装本地声音克隆 v3 显卡增补包，完成源码版本核对、备份、主环境上传依赖和独立 TTS 环境安装，再重启服务与工作台；未知源码改动会整批拒绝，交由 Agent 合并。参考录音、模型及私有配置不随增补包分发。

## 迁移现有雅雅、檬檬

只需在旧数据仍存在时执行一次：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_local_tts.ps1 -MigrateVoicebox
```

迁移器只读 `%APPDATA%\sh.voicebox.app\voicebox.db`，保留 profile ID，并把参考 WAV 复制到 `.backlot\tts\profiles`。原数据库和原音频不会被修改。若要复用已经下载的模型，可显式增加 `-ImportModels base`、`custom` 或 `all`，并用 `-LegacyModelCache` 指定旧模型缓存；同盘默认使用硬链接，不重复占用模型空间。

## 跨机器保留私有角色音色

克隆音色可能包含个人或角色声音，不能随公开 Git 仓库提交。使用私有音色包单独迁移：

```powershell
# 旧机器导出，可重复指定 --profile-id
$voicePack = Join-Path $env:USERPROFILE 'OpenMontage-private\voices.zip'
python scripts\local_tts_profiles.py export --output $voicePack --profile-id <PROFILE_ID>

# 新机器完成依赖安装后导入
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup_local_tts.ps1 -ImportProfilePack $voicePack
```

音色包不包含模型权重；新机器仍由官方加载器下载模型。请把音色包按私有素材管理，不要提交到公共仓库。

## 运行机制

- Base 模型用于参考音频克隆；CustomVoice 模型用于无需样本的官方预设。
- 模型按需加载并常驻，同类型连续生成不重复冷启动。
- 默认一次只驻留一个 1.7B 模型，切换预设/克隆时释放旧模型，避免同时占用过多内存。
- 所有任务进入全局串行队列，避免多个片段同时抢显存或内存。
- 超长文本按句号、问号、感叹号等边界分段生成，再以短静音拼接。
- 服务重启会把残留的 queued/generating 任务标为失败并提示重试，不会永久假卡住。

## 常用配置

在 `.env.local` 或 `.env.secrets.local` 中配置，均为可选：

```dotenv
OPENMONTAGE_TTS_BASE_URL=http://127.0.0.1:17494
OPENMONTAGE_TTS_DEVICE=auto
OPENMONTAGE_TTS_PROFILE_NAME=Qwen Serena
OPENMONTAGE_TTS_PROFILE_ID=
OPENMONTAGE_TTS_DATA_DIR=
OPENMONTAGE_TTS_MODEL_CACHE=
OPENMONTAGE_TTS_MAX_LOADED_MODELS=1
OPENMONTAGE_TTS_MAX_CHARS=500
```

`auto` 会优先使用可用 CUDA，否则使用 CPU。需要显卡的电脑应设为 `cuda:0`，防止运行环境异常时悄悄回退。1.7B 模型第一次冷加载较慢，后续同模型任务会复用内存。

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:17494/health
Invoke-RestMethod http://127.0.0.1:17494/profiles
```

健康结果必须同时满足 `status=healthy`、`service=openmontage-local-tts`，且 `data_dir` 与当前配置目录一致。启动器不会复用或停止另一份项目的服务。日志默认位于 `.backlot\tts\logs`；自定义数据目录时日志随该目录保存。

`configured_device` 表示配置要求；模型实际生成后，`execution_devices` 应包含 `cuda:0`，任务结果的 `execution_device` 也应为 `cuda:0`。仅看到“服务可用”不代表实际使用了显卡。

## 本次本机验证（2026-10-09）

Windows RTX 3050 6 GB、官方 PyTorch 2.11.0+cu128、原 1.7B Base 模型：用用户已录入“克隆测试1”真实生成；模型参数与任务结果均为 `cuda:0`。冷启动短句用时 43.22 秒，后续同进程原试听文案用时 28.39 秒、输出 5.84 秒音频（24 kHz、单声道、PCM16）。峰值模型显存分配约 4758 MiB，测试时 GPU 使用率约 86%。此前同音色同文案 CPU 任务用时约 47 分钟，工作台等待超过 1800 秒后已报告超时；原任务与最终输出保留。速度仅代表本机和当次输入。

此前配音中心页面上传创建接口返回 201，新音色自动选中，并真实生成短句显示在近期试听中。本次 88 项聚焦测试、独立显卡环境依赖检查，以及增补包原版/精简版/v1/v2 升级检查通过。音色相似度仍需本人听审，同事实体电脑安装与显卡能力须在目标电脑核验。

正式本地服务已设为 `cuda:0`，使用同一音色目录与缓存；原 CPU 环境保留在 `.backlot/tts-runtime/.venv-cpu-20261009`。从 `14762/audio` 页面点击生成，试听 `VP-38ca886ae3` 完成并显示播放器，首次完整试听约 75 秒（含服务重启后的模型加载）；对应 TTS 任务结果为 `execution_device=cuda:0`。截图和测量仅在私有 `.backlot/tts-gpu-check/` 保存。
