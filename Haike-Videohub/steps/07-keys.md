# Step 07 · 配置密钥

> **目标**：按需要的能力配 key。
> **⚠️ 本步是唯一必须人工提供的部分。**
> **重要认知：基础服务不需要任何 key。**

---

## 7.1 先决定你要什么

| 层级 | 能力 | 需要 |
|---|---|---|
| 🟢 基础 | B站采集 + Remotion 渲染 + 成片 | **0 把 key** |
| 🔴 配音 | 云端 TTS | 1 把（豆包） |
| 🟡 素材 | B-roll 素材库 | 1 把（Pexels 或 Pixabay） |
| 🔴 采集 | 抖音采集 | 扫码（非 key） |
| 🔴 发布 | 四平台发布 | 扫码（非 key） |
| 🟡 进阶 | AI 生图/生视频/数字人 | 可选 |

完整矩阵见 `keys/README.md` 与 `keys/capability-matrix.json`。

---

## 7.2 写入位置（★ 三条铁律）

| 仓库 | 写在哪 | 是否已 gitignore |
|---|---|---|
| **Haike** | `.env.local` 或 `.env.secrets.local` | ✅ 已排除 |
| **creatorhub** | `config.yaml` | ✅ 已排除 |
| **copy_skill** | ⚠️ **环境变量** | ❌ **`config/content_intelligence.json` 是入库文件！** |

### ⚠️ 最重要的一条

**`copy_skill/config/content_intelligence.json` 已被 git 跟踪。**
往里写 API key = **直接推到 public 仓库**。

**⇒ 必须用环境变量覆盖。**

```bash
# 正确做法示例
export DOUBAO_SPEECH_API_KEY="your-key"
```

---

## 7.3 Haike 侧配置

```powershell
cd <工作根>\Haike_video
Copy-Item .env.example .env.local
notepad .env.local
```

### 最小配置（要配音）

```ini
DOUBAO_SPEECH_API_KEY=你的key
DOUBAO_SPEECH_PUBLIC_RESOURCE_ID=seed-tts-2.0
DOUBAO_SPEECH_PUBLIC_VOICE_TYPE=你的音色ID
```

### 常用可选

```ini
# 素材库（要 B-roll）
PEXELS_API_KEY=
PIXABAY_API_KEY=

# 语音识别（给素材加字幕）
DOUBAO_ASR_API_KEY=
DOUBAO_ASR_MODE=flash

# 进阶：AI 生成
RUNNINGHUB_API_KEY=
GOOGLE_API_KEY=
```

> **豆包文本模型未配置时会自动回落主模型**（`.env.example:59-60`），不影响生产。

---

## 7.4 creatorhub 侧配置

`config.yaml` 一般**不需要填 key**（登录靠扫码，不是 key）。确认服务端口即可：

```yaml
server:
  host: 127.0.0.1
  port: 8000
```

---

## 7.5 付费前必读

> **Haike 的 `AGENT_GUIDE.md` 第 4 节约定：付费调用前必须先声明 provider / model / 成本。**

常见付费点：
- TTS：**按字符**计费
- 视频生成：**按秒**计费（最贵）
- ASR：按音频时长
- LLM：按 token

**零付费路径**：B站源 + Remotion 渲染 + 不加 AI 配音 = **完全免费**。

---

## 7.6 验证

```bash
# 1) 确认密钥文件确实被 gitignore
cd <工作根>/Haike_video
git check-ignore -v .env.local
# 期望：命中 .gitignore

# 2) 确认仓库里没有残留密钥样式
git grep -nE '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})' -- .
# 期望：无匹配

# 3) 统一体检
cd <videohub>
python verify/check_all.py --level=1
```

---

## 7.7 已知陷阱

| 陷阱 | 后果 | 处理 |
|---|---|---|
| key 写进 `content_intelligence.json` | **泄漏到 public 仓库** | 改环境变量 |
| key 写进 `config.yaml` 并提交 | 泄漏 | 确认已 gitignore |
| ffmpeg 用自定义路径但不进 PATH | 静默回退失败 | 放进 PATH |
| `consumer_root` 未配置 | 只影响工作台面板显示 | 可选，见下 |

### `consumer_root` 说明

`copy_skill/config/content_intelligence.json:839` 有 `consumer_root`，本机值为
`"D:/刘宇钊/codex_work/Haike_video"`。

**它支持相对路径，且未配置时只影响工作台面板显示**（`workbench.py:696-704` 弹提示），
**不影响生产**（`consumer_root()` 未配置时返回 `None`）。

**⇒ 干净机器上要改这个值，但配错也不阻断。** 建议改为相对路径或留空。

**下一步** → [08-verify](08-verify.md)
