# C 类：必须人工提供（API Key / 账号登录态）

> **判定依据**：无法自动化获取 ⇒ 必须人工。**本类是本方案里唯一允许要求人工介入的部分**（除首次扫码外）。
> **原则**：**能不给就不给。** 下面按「基础服务 / 进阶服务」分层，基础服务只需 0 把 key。

---

## C-0 分层总览

| 层级 | 能力 | 需要什么 | 是否必需 |
|---|---|---|---|
| **基础服务** | B站免登录下载 + Remotion 本地渲染 + 本地成片 | **0 把 key** | 可选起步 |
| **L1 必备** | 云端 TTS 配音 | 1 把（豆包 或 腾讯） | **要出带配音的片就必须** |
| **L2 素材** | 免版权视频/图片素材库 | Pexels 或 Pixabay | 建议 |
| **L3 采集** | 抖音采集 | Chrome 登录态（扫码，非 key） | 要抖音数据才需要 |
| **L4 发布** | 四平台发布 | 各平台扫码登录态（非 key） | 要发布才需要 |
| **L5 进阶** | AI 生图/生视频/AI 数字人 | RunningHub / fal / Replicate / Kling 等 | 按需 |

---

## C-1 🟢 基础服务：不需要任何 key

**这不是妥协，是完整可用的链路：**

| 能力 | 出处 | 说明 |
|---|---|---|
| B站搜索与下载 | `src/douyin_intelligence/sources/bilibili.py` | 模块 docstring 逐字声明：**「Standard library only. `urllib`/`http.cookiejar`/`hashlib`/`json`/`time`/`re` — no `requests`, no `httpx`, no `yt_dlp`, no Playwright. A keyword search is three plain GETs.」** |
| 视频渲染 | `Haike_video/remotion-composer/` | Remotion 本地渲染，**零付费** |
| 成片输出 | Haike 工作台 | 本地 ffmpeg |

**B站为什么免登录也能用**（源码 docstring 原文）：
> Empirically, an anonymous request with a valid guest cookie (`buvid3`, warmed from the homepage) plus `wbi` signing is *enough*: no login is required.

**`wbi` 签名的关键洞察**（同上）：
> a subset of a `img_key`/`sub_key` pair fetched from `/x/web-interface/nav` is used as an MD5 salt over the sorted query string. The `nav` endpoint answers `code=-101` ("not logged in") for a guest **but still carries the keys**, so a missed `-101` is precisely the trap MediaCrawler falls into (it treats `-101` as a failure and then runs a header-less fallback that bilibili rejects with HTTP 412).

⇒ **这是本项目唯一「零 key 也能真跑」的采集通道**，建议干净机器上**先跑通它**，验证整条链路，再考虑加 key。

---

## C-2 🔴 L1 必备：云端 TTS 配音

依据：`Haike_video/docs/handoff/DECISIONS.md:13` —— 「当前生产配音统一走云端（`doubao`/`tencent`）」。

### 选项一：豆包（火山方舟）—— 本机默认

| 变量 | 位置 | 说明 |
|---|---|---|
| `DOUBAO_SPEECH_API_KEY` | `.env.example:69` | **TTS 主 key** |
| `DOUBAO_SPEECH_VOICE_TYPE` | `:71` | 音色 ID |
| `DOUBAO_SPEECH_PUBLIC_RESOURCE_ID` | `:82` | 默认 `seed-tts-2.0` |
| `DOUBAO_SPEECH_YAYA_VOICE_TYPE` | `:74` | 音色「雅雅」 |
| `DOUBAO_SPEECH_YAYA_RESOURCE_ID` | `:75` | |
| `DOUBAO_SPEECH_MENGMENG_VOICE_TYPE` | `:77` | 音色「萌萌」 |
| `DOUBAO_SPEECH_MENGMENG_RESOURCE_ID` | `:78` | |
| `DOUBAO_SPEECH_PUBLIC_MALE_VOICE_TYPE` | `:85` | 公开男声 |

### 选项二：腾讯

| 变量 | 说明 |
|---|---|
| `VOLC_ACCESSKEY` / `VOLC_SECRETKEY` | `.env.example:140,142` |

### 相关但不必须

| 变量 | 位置 | 用途 |
|---|---|---|
| `DOUBAO_API_KEY` | `:61` | 豆包**文本**模型（写台词专用） |
| `DOUBAO_BASE_URL` | `:63` | 默认 `https://ark.cn-beijing.volces.com/api/v3` |
| `DOUBAO_TEXT_MODEL` | `:65` | 默认 `doubao-seed-2-1-pro-260628` |
| `DOUBAO_ASR_API_KEY` | `:92` | **语音识别**（给已拍素材加字幕用） |
| `DOUBAO_ASR_MODE` | `:93` | 默认 `flash` |
| `BACKLOT_PUBLIC_BASE_URL` | `:99` | ASR 需要可公网访问的媒体地址 |
| `DOUBAO_ASR_MEDIA_SIGNING_SECRET` | `:100` | 媒体签名 |

> 豆包文本模型**未配置时会自动回落主模型**（`.env.example:59-60`），所以不配也能跑。

---

## C-3 🟡 L2 素材：免版权素材库

| 变量 | 位置 | 获取 |
|---|---|---|
| `PEXELS_API_KEY` | `.env.example:152` | https://www.pexels.com/api/ |
| `PIXABAY_API_KEY` | `:154` | https://pixabay.com/api/docs/ |

**二者任一即可**，用于 B-roll 素材补充。

> 记忆里有一条相关红线：**「B-roll 与台词非一一对应时须多来源、每 2.2–3.5 秒换画面，别让同一素材扛整段口播。」** ⇒ 素材库 key 实质上是**质量要求**，不是可选项。

---

## C-4 🔴 L3 采集：抖音登录态（**不是 key，是扫码**）

| 项 | 值 |
|---|---|
| 配置位置 | `content_intelligence.json` → `media_crawler.user_data_dir = "third_party/MediaCrawler/browser_data/cdp_dy_user_data_dir"` |
| 获取方式 | **首次运行时扫码**（`--lt qrcode`） |
| `keep_open_on_needs_login` | `true` —— 需要登录时**保持浏览器打开**等你扫 |
| `reuse_persistent_profile` | `true` —— 复用持久化 profile，扫一次可长期用 |

**⇒ 这是唯一一个「必须人工扫一次码」的环节。**
**⇒ 干净机器上若只做基础服务 + 发布，可以完全跳过抖音采集。**

---

## C-5 🔴 L4 发布：四平台登录态（**不是 key，是扫码**）

| 平台 | creatorhub 需要的登录态 | 字段 |
|---|---|---|
| 抖音 | `creator_storage_state` 或 `storage_state` | 见 `app/main.py:9107-9126` |
| 快手 | 同上 | |
| 视频号 | 同上 | |
| 小红书 | `creator_storage_state` 或 `has_creator_cookies(storage_state)` | 走 `validate_publish_files()` |

**获取方式**：在 creatorhub 面板里逐个账号扫码登录，登录态保存在 `data/`（**已被 gitignore，不会入库**）。

**⚠️ 视频号特别警告**（记忆红线）：
> **视频号每条作品只允许改一次封面/描述且不可撤回** ⇒ 回填脚本任何猜测都不可接受。

---

## C-6 🟡 L5 进阶：AI 生成能力（全部可选）

### 视频生成

| 变量 | 位置 | 服务 |
|---|---|---|
| `RUNNINGHUB_API_KEY` | `.env.example:114` | RunningHub（**本机 ComfyUI 工作流主力**） |
| `RUNNINGHUB_WORKFLOW_ID` | `:117` | 默认 `2094449979141218305` |
| `FAL_KEY` / `FAL_AI_API_KEY` | `:7,9` | fal.ai |
| `REPLICATE_API_TOKEN` | `:15` | Replicate |
| `KLING_API_KEY` | `:26` | 可灵官方 |
| `HIGGSFIELD_API_KEY` / `_API_SECRET` | `:20,21` | Higgsfield |
| `RUNWAY_API_KEY` | `:138` | Runway |
| `HEYGEN_API_KEY` | `:136` | HeyGen |
| `SUNO_API_KEY` | `:124` | Suno 音乐 |
| `MODAL_LTX2_ENDPOINT_URL` | `:148` | Modal LTX2 |
| `VIDEO_GEN_LOCAL_ENABLED` / `_MODEL` | `:144,146` | 本地视频生成 |

### 图像生成

| 变量 | 位置 | 服务 |
|---|---|---|
| `GOOGLE_API_KEY` | `.env.example:35` | Google（**一把 key 解锁生图 + TTS + 视频**） |
| `GOOGLE_APPLICATION_CREDENTIALS` | `:40` | 服务账号 JSON 路径（替代 API key） |
| `GOOGLE_CLOUD_PROJECT` | `:42` | Vertex AI 需要 |
| `GOOGLE_CLOUD_LOCATION` | `:44` | 默认 `us-central1` |
| `DASHSCOPE_API_KEY` | `:108` | 阿里通义（`DASHSCOPE_WORKSPACE_ID` `:110`） |
| `OPENAI_API_KEY` | `:50` | 可选，作 TTS 回退 |
| `OPENAI_BASE_URL` | `:53` | 可选，OpenAI 兼容网关 |

### 文本模型

| 变量 | 位置 |
|---|---|
| `OPENAI_SCRIPT_MODEL` | `.env.example:55` |
| `OPENAI_VISION_MODEL` | `:57` |
| `XAI_API_KEY` | `:67` |
| `ELEVENLABS_API_KEY` | `:48` |

---

## C-7 密钥存放规则（**硬约束**）

依据：`Haike_video/docs/handoff/DEPLOYMENT.md`

```
✅ 写到 .env.local / .env.secrets.local
❌ 绝不提交 .env* 实值
❌ 绝不提交 gcp-*.json / *-service-account.json
```

`.gitignore` 已验证排除：
```
.env
.env.local
.env.secrets.local
*.env
gcp-*.json
*-service-account.json
```

| 仓库 | 密钥文件 | gitignore 覆盖 |
|---|---|---|
| Haike | `.env.local` / `.env.secrets.local` | ✅ |
| copy_skill | `config/content_intelligence.json`（可能含 key） | ⚠️ **该文件已入库** ⇒ 只写公开字段，key 走环境变量 |
| creatorhub | `config.yaml` | ✅ |

> ⚠️ **copy_skill 的 `config/content_intelligence.json` 是入库文件。**
> 在里面写 API key 会直接进 public 仓库。**必须用环境变量覆盖。**

---

## C-8 人工操作清单（干净机器上要做的）

按顺序，**任一环节都可跳过并降级**：

```
□ 1. 装 Python 3.12 / Node 22 / Git / Chrome / ffmpeg     （B 类，手动安装）
□ 2. clone 三个仓库到 layout.json 指定位置                 （见 steps/02）
□ 3. （可选）clone MediaCrawler 到 third_party/            （见 steps/06）
□ 4. 配 TTS key（要配音就配）                              ← 第一处人工提供
□ 5. （可选）配 Pexels/Pixabay key（要 B-roll 就配）
□ 6. （可选）配进阶能力 key（RunningHub 等）
□ 7. 启动 Haike 工作台（4754），跑 preflight.ps1
□ 8. 启动 copy_skill，跑 doctor
□ 9. 启动 creatorhub（8000），登录四平台账号                ← 第二处人工操作（扫码）
□ 10. 跑 verify/check_all.py --level=1 && --level=2        ← 自动验证
□ 11. （要抖音采集）首次采集扫码                            ← 第三处人工操作（扫码）
```

**关键点：只有第 4、9、11 步需要人。而且 4 有替代（用基础服务）、9 和 11 只在需要时才做。**

---

**下一步**：见 `deps/D-never-copy.md`（绝不复制的东西）。
