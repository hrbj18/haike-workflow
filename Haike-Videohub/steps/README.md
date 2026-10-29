# 步骤总览

> **执行原则**：每一步结尾都有可复制的验证命令。**验证不通过不要进下一步。**
> **顺序不可颠倒**：01 先装依赖 → 02 摆仓库 → 03~05 起三个服务 → 06（可选）补采集 → 07 配 key → 08 统一体检。

---

## 三个可跳过的降级点

| 想省什么 | 跳过哪步 | 代价 |
|---|---|---|
| 不发布 | 不配 creatorhub 登录态 | 只出片不发 |
| 不采集抖音 | 跳过 step 06 | 只能用 B站源 |
| 不配音 | 不配 TTS key | 无配音成片 |

**⇒ 最小路径 = 01 → 02 → 03 → 08。零 key、零扫码、零付费。**

> **口径一致说明**：跳过 step 06（不装 MediaCrawler）后，`check_all.py` 把
> `B.mediacrawler` 记为 **WARN**（消息注明「未启用抖音采集（可选），跳过」），
> **不算 FAIL**。判定依据是 `third_party/MediaCrawler` 目录是否存在：
> 目录不存在 = 未启用抖音采集 ⇒ WARN；目录存在 = 已启用 ⇒ 检查不过仍 **FAIL**。
> 因此最小路径依然是 **0 FAIL**，与 [step 08](08-verify.md) 的「0 FAIL 是唯一判据」不冲突。

---

## 步骤清单

| 步骤 | 内容 | 需要人工? | 可跳过? |
|---|---|---|---|
| [01-prereq](01-prereq.md) | 装 Python 3.12 / Node 22 / Git / Chrome / ffmpeg | 是（安装） | 否 |
| [02-clone-repos](02-clone-repos.md) | 按 layout.json 摆放三个仓库 | 是 | 否 |
| [03-haike](03-haike.md) | Haike 安装与启动（端口 4754） | 首次 | 否 |
| [04-copyskill](04-copyskill.md) | copy_skill 安装（uv）与 doctor | 否 | 否 |
| [05-creatorhub](05-creatorhub.md) | creatorhub 安装与启动（端口 8000） | 否 | 是 |
| [06-mediacrawler](06-mediacrawler.md) | MediaCrawler 获取与 venv | 否 | 是 |
| [07-keys](07-keys.md) | 按能力矩阵配密钥 | **是** | 部分 |
| [08-verify](08-verify.md) | 统一体检 + 反例自测 | 否 | 否 |

---

## 统一入口

每一步的验证都可以用同一个命令：

```bash
cd <videohub>
python verify/check_all.py --level=1     # 静态探活
python verify/check_all.py --all         # 加契约连通
```

---

## 关键路径速查

```
D:\刘宇钊\codex_work\                    ← 工作根（可换，但三仓相对关系不能变）
├── Haike_video\                         ← 深度 1
├── copy_skill\copy_skill-main\          ← 深度 2 ★必须两层
├── creatorhub\                          ← 深度 1
└── Haike-Videohub\                      ← 本仓库
```

> ⚠️ **`copy_skill/copy_skill-main/` 必须两层。** 写成单层会让 Haike 的跨仓测试静默 skip，不报错。
