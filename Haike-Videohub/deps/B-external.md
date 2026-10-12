# B 类：必须从第三方下载（三仓不携带）

> **判定依据**：`git ls-files` 查不到 ⇒ 不在库 ⇒ 必须另行获取。
> **本类的每一项都给出：上游 URL + 目标路径 + 获取命令 + 验证命令。**
> **获取顺序建议**：B-1 → B-2 → B-3 → B-4（B-1 是硬依赖，B-4 可延后）

---

## B-1 MediaCrawler ★ 最关键

### 事实陈述（不是推测）

`copy_skill` 仓库**明确不包含** MediaCrawler 的代码。作者本人已在两处写清楚：

**证据 1** —— `copy_skill/copy_skill-main/.gitignore:27-35`：
```
# Third-party MediaCrawler: declared as a submodule in .gitmodules.
# The bundled copy was shipped as a ZIP with .git stripped, so it cannot be
# recorded as a gitlink (it would resolve to 0000000). Ignore the tree and
# re-obtain it with: git submodule update --init third_party/MediaCrawler
third_party/MediaCrawler/
third_party/MediaCrawler/.venv/
third_party/MediaCrawler/data/
third_party/MediaCrawler/browser_data/
third_party/MediaCrawler/*_user_data_dir/
```

**证据 2** —— `copy_skill/copy_skill-main/README.md:38`：
> MediaCrawler 在 `.gitmodules` 里被声明为子模块（上游 `https://github.com/NanmiCoder/MediaCrawler.git`），但**本仓库并没有把它记录成 gitlink**：`git submodule status` 输出为空，`git ls-tree HEAD third_party/` 亦为空。因此 `git clone --recurse-submodules` 与 `git submodule update --init` **都不会把它拉下来**——首次克隆用普通克隆即可

**证据 3** —— `copy_skill/copy_skill-main/README.md:46`：
> 确实需要 MediaCrawler 时，请按 `.gitmodules` 里的 URL 自行获取并放到 `third_party/MediaCrawler/`。该路径（连同 `data/`、`browser_data/`、`*_user_data_dir/`）已被 `.gitignore` 忽略，不会进入版本库。

**证据 4** —— `copy_skill/copy_skill-main/.gitmodules`：
```
[submodule "third_party/MediaCrawler"]
	path = third_party/MediaCrawler
	url = https://github.com/NanmiCoder/MediaCrawler.git
```

**证据 5（本机实测）** —— `third_party/MediaCrawler/.git/HEAD` **不存在** ⇒ 本地那份是**无 git 元数据的裸源码目录**，不是 submodule checkout。

### 三个常见误解（必须先破除）

| 误解 | 事实 |
|---|---|
| ❌「`git clone --recurse-submodules` 会拉下来」 | **不会。** 没有 gitlink 记录，`.gitmodules` 只是一份声明。 |
| ❌「`git submodule update --init` 会拉下来」 | **不会。** 同上。 |
| ❌「本地有 = 仓库里有」 | **不是。** 本地有是因为当初手工放的；`.gitignore` 明确排除，从未入库。 |

### 获取方式

```bash
# 定位到 copy_skill 根
cd copy_skill/copy_skill-main

# 方式 A（推荐）：git clone 到目标路径
git clone https://github.com/NanmiCoder/MediaCrawler.git third_party/MediaCrawler

# 方式 B：若无 git 凭据且网络受限，可用 ZIP
# curl -L https://github.com/NanmiCoder/MediaCrawler/archive/refs/heads/main.zip -o /tmp/mc.zip
# unzip /tmp/mc.zip -d third_party/ && mv third_party/MediaCrawler-main third_party/MediaCrawler
```

> ⚠️ **不要**在 copy_skill 仓库里执行 `git submodule add`。这会把 MediaCrawler 记成 gitlink 并改变仓库结构，与作者的设计相悖。**直接 clone 到被 gitignore 的路径即可。**

### 许可证

`third_party/MediaCrawler/LICENSE` 首行：
```
NON-COMMERCIAL LEARNING LICENSE 1.1
```
- 条件 2：「limited to learning and research purposes only」
- 条件 3：「may not be used for any commercial purposes」

**⇒ 本项目定位为内部学习研究，与许可证一致。但不得用于商业用途，不得对外提供服务。**

### 建立自己的 venv

MediaCrawler 需要**独立的 Python 环境**（不要和 copy_skill 的 uv 环境混用）：

```bash
cd third_party/MediaCrawler
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

> 注意 Windows 下路径是 `.venv/Scripts/`，Linux/macOS 是 `.venv/bin/`。`config/content_intelligence.json` 里写死的是 Windows 形式。

### 验证

```bash
cd copy_skill/copy_skill-main
python -c "
import json,os
cfg=json.load(open('config/content_intelligence.json',encoding='utf-8'))
mc=cfg['media_crawler']
root=mc['root']; py=mc['python']
print('root exists :', os.path.isdir(root))
print('main.py     :', os.path.isfile(os.path.join(root,'main.py')))
print('venv python :', os.path.isfile(py))
"
# 期望：三行全 True
```

**或用 doctor 一键体检（更权威）**：
```bash
cd copy_skill/copy_skill-main
uv run python -c "
import json, sys
sys.path.insert(0,'src')
from douyin_intelligence.config import load_config
from douyin_intelligence.doctor import run_doctor
print(json.dumps(run_doctor(load_config())['media_crawler'], ensure_ascii=False, indent=2))
"
# 期望：ok=True, venv_ok=True
```

### ⚠️ 静默失败警告（必读）

MediaCrawler 调用失败时**默认没有任何错误信息**。源码位置：

```python
# copy_skill/src/douyin_intelligence/search_collector.py:100-107
subprocess.run(command, cwd=..., check=False, timeout=timeout_seconds,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # ← stderr 被吞
```

```python
# search_collector.py:121-131
if result.returncode == 0 and files:      status = "success"
elif result.returncode == 0:              status = "empty"
                                          failure = "crawler completed without output files"
else:                                     status = "failed"
                                          # ← failure 保持 None！没有任何错误信息
```

同样问题见 `cli.py:82-95` 的 `_run_crawl_command()`。

**⇒ 表现**：命令返回 `failed`，但 `failure` 是 `None`，你**看不到任何原因**。
**⇒ 排查**：不要猜，直接跑 doctor（上面那条命令），它会明确告诉你 root / venv / chrome 哪一项不满足。

`mediacrawler_runner.py` 的崩点：
```python
os.chdir(root)
sys.path.insert(0, str(root))
import config                                    # ← root 不存在时在此崩
from media_platform.douyin.client import DouYinClient
```

---

## B-2 Python 3.12（64 位）

| 项 | 值 |
|---|---|
| 需求 | **3.12** —— Haike 的 `DEPLOYMENT.md` 明确要求 64 位 Python 3.12 |
| 本机已验证 | `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe` |
| 下载 | https://www.python.org/downloads/release/python-3128/ |
| 验证 | `python --version` → `Python 3.12.x` |

> ⚠️ **不要用 3.13。** Haike 的依赖集在 3.12 上验证过；3.13 可能触发 `EBADENGINE` 类警告或扩展编译失败。
> copy_skill 要求 `>=3.11`，但**它的 venv 由 `uv` 自建**，与系统 Python 解耦，所以系统装 3.12 即可满足两边。

---

## B-3 Node.js 22+

| 项 | 值 |
|---|---|
| 需求 | 22+（Remotion 渲染） |
| 本机已验证 | `C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe` |
| 下载 | https://nodejs.org/ |
| 验证 | `node --version` → `v22.x` |

Haike 的 `remotion-composer/` 需要 `npm install`（依赖不入库）：

```bash
cd <工作根>/Haike_video/remotion-composer
npm install
```

**验证**：
```bash
npx remotion --version        # 期望打印 Remotion 版本号
node -e "console.log(Object.keys(require('./package.json').scripts))"
```

---

## B-4 ffmpeg / ffprobe

| 项 | 值 |
|---|---|
| 需求 | ffmpeg + ffprobe |
| 本机配置位置 | `copy_skill/config/content_intelligence.json:4-7` |
| 本机路径 | `D:\刘宇钊\codex_work\视频下载dy\.tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe` |
| 下载 | https://www.gyan.dev/ffmpeg/builds/ 或 https://github.com/BtbN/FFmpeg-Builds/releases |
| 验证 | `ffmpeg -version` 且 `ffprobe -version` |

> **好消息：已有 PATH 回退，不配也能跑。**
> ```python
> # src/douyin_intelligence/media_tools.py:12-18
> def resolve_media_tool(config, name):
>     configured = ...            # 读配置
>     if configured 存在: return configured
>     return shutil.which(name) or name      # ← 回退到 PATH
> ```
> ⇒ 只要 `ffmpeg` / `ffprobe` 在系统 PATH 上，**不需要改配置**。
> **但**：如果你把 ffmpeg 放在自定义位置又没加进 PATH，就会静默回退失败。**建议放进 PATH**，别改配置。

Haike 侧使用 `static-ffmpeg`（Python 包，`pip install` 即得），**与 copy_skill 的 ffmpeg 是两套，互不影响**。

---

## B-5 Chrome（真实浏览器）

| 项 | 值 |
|---|---|
| 需求 | Google Chrome（MediaCrawler CDP 采集 + creatorhub Patchright 发布**共用**） |
| 本机配置 | `content_intelligence.json` 的 `media_crawler.chrome_path = "C:/Program Files/Google/Chrome/Application/chrome.exe"` |
| 下载 | https://www.google.com/chrome/ |
| 验证 | `ls "C:/Program Files/Google/Chrome/Application/chrome.exe"` |

> **好消息：已有显式报错，不会静默失败。**
> ```python
> # src/douyin_intelligence/collector.py:184-185
> raise FileNotFoundError(f"Chrome 不存在：{chrome}")
> ```
> ⇒ 路径错会明确报错，不会让你猜。

---

## B-6 可选：本地 TTS（Qwen3-TTS）

| 项 | 值 |
|---|---|
| 需求 | **可选**。默认生产配音走云端（`doubao` / `tencent`） |
| 出处 | `Haike_video/docs/handoff/DECISIONS.md:12-13`：「端口 `127.0.0.1:17494` 是内置 Qwen3-TTS」+「当前生产配音统一走云端」 |
| 安装 | `Haike_video/scripts/setup_local_tts.ps1` |
| 配置 | `.env.example:186-199`（`OPENMONTAGE_TTS_BASE_URL=http://127.0.0.1:17494`） |

> **⇒ 干净机器上可跳过。** 用云端 TTS 只需配 API Key（见 `deps/C-human.md`）。

---

## B-7 可选：视觉模型权重

`Haike_video/.gitignore` 排除 `*.onnx`。若要用本地视觉能力（`avatar-spokesperson` 等），需另行下载模型。**基础服务不需要。**

---

## B-8 汇总检查

```bash
# 一键检查所有 B 类依赖
python <videohub>/verify/check_all.py --level=1
# 期望输出中 B 类各项 PASS
```

| 编号 | 项 | 必需? | 已有回退? |
|---|---|---|---|
| B-1 | MediaCrawler | **必需**（抖音采集） | ❌ 无 |
| B-2 | Python 3.12 | **必需** | ❌ 无 |
| B-3 | Node 22+ | **必需**（渲染） | ❌ 无 |
| B-4 | ffmpeg/ffprobe | **必需** | ✅ PATH 回退 |
| B-5 | Chrome | **必需** | ❌ 但会明确报错 |
| B-6 | 本地 TTS | 可选 | ✅ 可走云端 |
| B-7 | 视觉模型 | 可选 | ✅ 基础服务不需要 |

---

**下一步**：见 `deps/C-human.md`（必须人工提供的密钥）。
