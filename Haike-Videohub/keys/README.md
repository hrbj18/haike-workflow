# 密钥与能力矩阵

> **一句话**：**基础服务不需要任何密钥。** 加密钥只是为了解锁更多能力，不是为了「能跑起来」。

---

## 1. 能力矩阵（人读版）

| 想要的能力 | 最少需要什么 | 层级 |
|---|---|---|
| 从 B站搜片、下载 | **什么都不需要** | 🟢 基础 |
| 用 Remotion 渲染动态画面 | **什么都不需要** | 🟢 基础 |
| 出一个**纯画面 + 字幕**的成片 | **什么都不需要** | 🟢 基础 |
| 给成片加** AI 配音** | 豆包 TTS key（1 把） | 🔴 必须（要配音） |
| 加 **B-roll 素材** | Pexels 或 Pixabay（1 把） | 🟡 建议 |
| **抖音采集** | Chrome + 扫码一次（非 key） | 🔴 需要时才要 |
| **发布到四平台** | 各平台扫码登录（非 key） | 🔴 需要时才要 |
| AI 生图 / 生视频 | RunningHub 或 fal / Replicate | 🟡 进阶 |
| AI 数字人口播 | RunningHub + 数字人工作流 | 🟡 进阶 |
| 给已拍素材加字幕（ASR） | 豆包 ASR key | 🟡 进阶 |

---

## 2. 机读版矩阵

见 `capability-matrix.json`（同目录）。供 Agent 与 `verify/check_all.py` 消费。

---

## 3. 最小可用配置（推荐起步路径）

**第一步：0 key 跑通。**
```
配好 B 类依赖 → clone 三仓 → 启动 Haike → 用 B站源下载 → 渲染 → 得到成片
```
这一步**验证了整条技术链路**，而且零成本、零密钥、零登录。

**第二步：加 1 把 TTS key。**
```
DOUBAO_SPEECH_API_KEY=<你的 key>
```
这一步让成片有配音——**这是「能看」到「能发」的分界线**。

**第三步：配发布。**
```
启动 creatorhub → 扫码登录目标平台 → 得到登录态
```
这一步之后，就能用 `contracts/publish-v1.md` 描述的接口把成片送进待发队列。

**⇒ 三步做完 = 完整工作流。进阶 key 全部是可选的加分项。**

---

## 4. 按「是否需要」分组

### 🟢 完全不需要

| 能力 | 出处 |
|---|---|
| B站采集 | `copy_skill/src/douyin_intelligence/sources/bilibili.py` —— 纯标准库，免登录 |
| 本地渲染 | `Haike_video/remotion-composer/` |
| 本地视频处理 | `static-ffmpeg`（pip 包） |

### 🔴 出配音就必须

| 变量 | 用途 |
|---|---|
| `DOUBAO_SPEECH_API_KEY` | 豆包 TTS（本机默认） |
| `DOUBAO_SPEECH_VOICE_TYPE` | 音色 ID |
| `VOLC_ACCESSKEY` / `VOLC_SECRETKEY` | 腾讯 TTS 备选 |

### 🟡 提质量

| 变量 | 用途 |
|---|---|
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` | B-roll 素材 |
| `DOUBAO_ASR_API_KEY` | 语音识别加字幕 |

### 🟡 进阶（AI 生成）

| 变量 | 用途 |
|---|---|
| `RUNNINGHUB_API_KEY` | ComfyUI 工作流（本机主力） |
| `GOOGLE_API_KEY` | 一把解锁生图 + TTS + 视频 |
| `FAL_KEY` / `REPLICATE_API_TOKEN` | 视频生成 |
| `KLING_API_KEY` / `RUNWAY_API_KEY` / `HEYGEN_API_KEY` | 各平台 |

### 🔵 非密钥但需人工

| 项 | 方式 |
|---|---|
| 抖音采集登录 | 首次扫码（`--lt qrcode`） |
| 四平台发布登录 | creatorhub 面板扫码 |

---

## 5. 写入位置（重要）

| 仓库 | 写在哪 | gitignore 覆盖 |
|---|---|---|
| Haike | `.env.local` 或 `.env.secrets.local` | ✅ 已排除 |
| creatorhub | `config.yaml` | ✅ 已排除 |
| copy_skill | 环境变量优先；其次 `<copy_skill>/.env.local`（见 §5.1）。**绝不写 `config/content_intelligence.json`** | `.env.local` ✅ 已排除 / `config/content_intelligence.json` ❌ **已入库** |

> ⚠️ **copy_skill 的 `config/content_intelligence.json` 是入库文件。**
> 往里写 key = 直接推到 public 仓库。**必须走环境变量（或已 gitignore 的 `.env.local`）。**

### 5.1 copy_skill 实际读取的环境变量（源码实测）

以下变量名来自 `copy_skill-main/src` 里对 `os.environ` / `os.getenv` 的**实际读取点**（只读未改）。
读取优先级：`os.environ` → `<copy_skill 根>/.env.local`，由 `local_secrets.secret_value()` 实现
（`src/douyin_intelligence/local_secrets.py:25-30`）。

| 变量 | 读取位置 | 默认值 | 用途 |
|---|---|---|---|
| `DOUYIN_LLM_API_KEY` | `local_secrets.py:35`、`llm_analysis.py:34,91` | 空（未配置 ⇒ AI 深度分析不可用） | **唯一的真正密钥**：AI 深度分析（OpenAI 兼容）API Key |
| `DOUYIN_LLM_BASE_URL` | `llm_analysis.py:59` | 回退到 `config` 的 `materials.llm.base_url` | 覆盖 LLM 基址（非密钥） |
| `DOUYIN_LLM_MODEL` | `llm_analysis.py:78` | 回退到 `config` 的 `materials.llm.model` | 覆盖模型名（非密钥） |
| `DOUYIN_MSVC_RUNTIME_DIR` | `native_runtime.py:107,156` | None（自动搜 `onnxruntime/capi`、`ctranslate2`） | 指定含 `vcruntime140*.dll` / `msvcp140.dll` 的目录 |
| `COPY_SKILL_WORKBENCH_SMOKE_MS` | `workbench_launcher.py:14,32` | None（不自动关闭） | 工作台冒烟测试自动关闭毫秒数（开发用） |
| `HF_ENDPOINT` | `media_processing.py:50` | None（用 HuggingFace 官方） | HuggingFace 镜像端点（下载 ASR / 视觉模型） |
| `HF_HUB_OFFLINE` | `media_processing.py:58` | False（`1/true/yes/on` 为真） | 强制离线，只用本地缓存模型 |

**逐个验证**（在 `copy_skill/copy_skill-main` 下执行）：

```bash
# LLM 三件套：走真实读取函数
uv run python -c "import sys;sys.path.insert(0,'src');from douyin_intelligence.local_secrets import llm_secret_status;print(llm_secret_status())"
# 期望：{'api_key_configured': True, 'base_url_override_configured': ..., 'model_override_configured': ...}

# 其余五个：直接读环境
uv run python -c "import os; [print(n,'=',os.environ.get(n,'<未设>')) for n in ('DOUYIN_LLM_BASE_URL','DOUYIN_LLM_MODEL','DOUYIN_MSVC_RUNTIME_DIR','COPY_SKILL_WORKBENCH_SMOKE_MS','HF_ENDPOINT','HF_HUB_OFFLINE')]"
```

> 另有 `TEMP`/`TMP` 被读取（`face_metrics.py:242`），但那是系统临时目录、不是项目配置；
> `NO_PROXY`/`no_proxy` 由 `mediacrawler_runner.py:50-51` **写入**（不是读取），无需人工配置。

---

## 6. 验证密钥是否生效

```bash
# Haike 侧：确认 .env.local 被读取且未入库
cd Haike_video
git check-ignore -v .env.local          # 期望：命中 .gitignore
python -c "from dotenv import dotenv_values; print([k for k in dotenv_values('.env.local') if 'KEY' in k or 'TOKEN' in k])"

# creatorhub 侧
cd ../creatorhub
ls config.yaml && git check-ignore -v config.yaml

# 统一体检
python <videohub>/verify/check_all.py --level=1
```

---

## 7. 成本提示

依据：Haike 的 `AGENT_GUIDE.md` 第 4 节「Providers-cost-failures」。

> **付费调用前必须先声明 provider / model / 成本。**

**⇒ 在干净机器上启用任何付费 key 之前，先确认这条约定被遵守。**

常见付费点：
- TTS 按字符计费（配音越长越贵）
- 视频生成按秒计费（最贵）
- ASR 按音频时长计费
- LLM 按 token 计费

**零付费路径**：B站源 + Remotion 渲染 + 无配音 = **完全免费**。

---

**相关**：`deps/C-human.md`（完整变量清单与获取链接） · `contracts/publish-v1.md`（发布契约）
