# Step 08 · 统一体检

> **目标**：`verify/check_all.py --all` 全部 PASS。
> **这是部署完成的唯一判据。**

---

## 8.1 三层验证体系

| 级别 | 内容 | 能自动验? |
|---|---|---|
| **L1** | 静态探活：路径、哨兵文件、JSON、版本、外部依赖、配置 | ✅ |
| **L2** | 契约连通：用**假数据**跑跨仓读取函数，断言不抛异常 | ✅ |
| **L3** | 端到端：真采集 + 真发布 + 干净机器复现 | ❌ 需人工 |

---

## 8.2 生成假数据（首次或 fixtures/ 被清空时）

**前置链（缺一不成立）**：

```
Haike_video 已就位（按 step 02 摆到 <工作根>/Haike_video）
  → step 02/03 的哨兵通过（haike.sentinel / frozen.consumer-test）
  → 先跑 make_fixtures.py 生成夹具
  → 再跑 check_all.py
```

> ⚠️ L2 夹具**必须由 `verify/make_fixtures.py` 从 Haike 侧 import 消费端模块**生成
> （用它的 `content_sha256()` 算哈希），所以 **Haike 缺失时无法生成夹具**。
> 若 Haike 缺失就直接跑 `check_all.py`，L2 会 FAIL 并提示「假数据不存在」，
> 该 FAIL 消息里已附上同一条生成命令的指引。

```bash
cd <videohub>
python verify/make_fixtures.py --clean --haike <Haike 路径>
# <Haike 路径> 例：D:/刘宇钊/codex_work/Haike_video
# 省略 --haike 时默认取第四仓的兄弟目录 <工作根>/Haike_video
```

**为什么需要这一步**：L2 验证靠的是一份**sha256 自洽的最小假包**。
生成脚本会 `import` 消费端模块，用它自己的 `content_sha256()` 算哈希 ——
所以产出的包**天然满足消费端校验**。

**这正是 L2 能验证契约的技术基础**：消费端会亲自核对 sha256、重启指纹、三方一致
（`current.json` / `_READY.json` / 实际文件），所以一份正确的假包能真实走完所有校验分支。

**期望输出**：
```
[fixture] candidate-pool  -> ...\fixtures\mini-candidate-pool\2026-09-21_每日素材\packs\run-...
          manifest_sha256  = cd32b250...
[fixture] research-pack   -> ...\fixtures\mini-research-pack\2026-09-21_研究包\...
          content_sha256   = ...
          manifest_sha256  = ...
```

---

## 8.3 跑完整体检

```bash
cd <videohub>
python verify/check_all.py --all
```

**期望**（启用抖音采集时 **38 项，0 FAIL**；未启用时 `config.mc.*` 两项降为 WARN、共 **36 项，0 FAIL**）：

> ★ 项数是**条件口径**，取决于环境：
> - `adapter.*` 4 项要求 Haike_video ≥ `395890c`（`backlot/publish_adapter.py` 已随仓分发）；
>   若 Haike 更旧，4 项塌成 1 条 WARN、总数变 33 —— 按 step 02 §2.4.1 检出锚点即可修复。
> - 未启用抖音采集（无 MediaCrawler）时 `config.mc.*` 两项为 WARN 且不计入总数。
> 下列 WARN 是允许的，FAIL 不允许：
```
[PASS] layout                        contracts/layout.json 可解析
[PASS] haike                         仓库存在: Haike_video
[PASS] haike.sentinel                7 个哨兵文件全部存在
[PASS] copyskill                     仓库存在: copy_skill\copy_skill-main
[PASS] copyskill.sentinel            6 个哨兵文件全部存在
[PASS] creatorhub                    仓库存在: creatorhub
[PASS] creatorhub.sentinel           3 个哨兵文件全部存在
[PASS] LAYOUT-1                      copyskill 两层路径正确: copy_skill/copy_skill-main
[PASS] contract-doc                  冻结合同文档存在
[PASS] versions                      creatorhub 未推送 commit 数已登记: 10
[PASS] versions.origin               已登记 creatorhub 无 origin 的事实
[PASS] frozen.producer               冻结 content_sha256 一致
[PASS] frozen.consumer-test          冻结 content_sha256 一致
[PASS] B.python                      Python 3.12 ✓
[PASS] B.node                        Node v22.x ✓
[PASS] B.ffmpeg                      PATH 上找到
[PASS] B.ffprobe                     PATH 上找到
[PASS] B.chrome                      找到
[PASS] B.mediacrawler                MediaCrawler 已就位
[WARN] B.mediacrawler.git            无 .git 元数据（本机现状，允许）
[PASS] B.mediacrawler.venv           venv 已建 ✓
[PASS] config.mc.root                相对路径: third_party/MediaCrawler
[PASS] config.mc.python              相对路径: third_party/MediaCrawler/.venv/Scripts/python.exe
[PASS] config.mc.chrome_path         C:/Program Files/.../chrome.exe (存在)
[WARN] config.hotspot                copy_skill_hotspot_feed.enabled = false（允许）
[PASS] adapter.G1                    G1 探活闸 在位
[PASS] adapter.G2                    G2 零字节阻断闸 在位
[PASS] adapter.G3                    G3 显式确认闸 在位
[PASS] adapter.norunnow              run-now 仅出现在说明性文字中 ✓
[PASS] L2.candidate-pool             load_copy_skill_hotspot_feed() 成功，run_id=...
[PASS] L2.candidate-pool.candidates  规范化候选数: 1
[PASS] L2.candidate-pool.manifest    manifest 校验通过，file_count=4
[PASS] L2.candidate-pool.sha         package_manifest_sha256 三方一致
[PASS] L2.candidate-pool.try         try_ 版本返回: dict
[PASS] L2.research-pack              load_research_pack() 成功
[PASS] L2.research-pack.counts       sources=1 claims=2 materials=1
[PASS] L2.research-pack.ready        _READY 校验通过
[PASS] L2.research-pack.edges        argument_graph.edges 非空（1 条）
```

> 以上 38 项是 **MediaCrawler 已就位**（启用抖音采集）时的完整清单，与
> `contracts/versions.json` 的 `hub.self_check.expected` 一致。
> 若**未启用抖音采集**（`third_party/MediaCrawler` 目录不存在），
> `B.mediacrawler` / `B.mediacrawler.git` / `B.mediacrawler.venv` 三行合并为
> **一行 WARN**（消息「未启用抖音采集（可选），跳过」），总项数随之减少，
> **但仍是 0 FAIL**。

**WARN 是允许的**（例如候选池开关默认关闭、MediaCrawler 无 git 元数据、未启用抖音采集），**FAIL 不允许**。

---

## 8.4 ★ 反例自测（证明校验不是空转）

**这一步很多人会跳过，但它才是验证体系的价值所在。**
一个永远返回 PASS 的校验器毫无意义。

```bash
# 反例 1：注入单层路径假设
python verify/check_all.py --level=1 --mutate=layout
# 期望：MUTATE-layout PASS + "反例测试符合预期：注入的错误被捕获 ✓"

# 反例 2：篡改假包的 sha256
python verify/check_all.py --all --mutate=sha256
# 期望：MUTATE-sha256-check PASS + "反例测试符合预期"
```

**反例 2 的原理**：脚本会把 `_READY.json` 的 `package_manifest_sha256` 改成全 0，
然后期待消费端抛 `CopySkillHotspotFeedError`。**能抛出来就说明三方一致性校验真的在工作。**

> ⚠️ 反例 2 会破坏假包。`check_all.py` 现在会在反例结束后**自动重建夹具**
> （`_restore_after_mutation()`），因此「反例 → 正常体检」可连续执行。
> 若自动重建失败，手动补一次：
> ```bash
> python verify/make_fixtures.py --clean --haike <Haike 路径>
> ```

---

## 8.5 跑三仓既有测试（可选但推荐）

```bash
# Haike（必须带这两个参数）
cd <工作根>/Haike_video
python -m pytest tests/backlot/test_copy_skill_research_pack.py \
  --import-mode=importlib --basetemp=.p -v

# copy_skill
cd <工作根>/copy_skill/copy_skill-main
uv run pytest -p no:cacheprovider
```

**重点关注**：跨仓用例**不应该是 `SKIPPED`**。
若显示 skip，说明 `layout.json` 的 LAYOUT-1 没被满足（见 [step 02](02-clone-repos.md)）。

---

## 8.6 L3：需要人工的验证

以下三项**无法自动完成**，已登记在 `docs/pending-manual-checks.md`：

| 项 | 为什么不能自动 |
|---|---|
| MediaCrawler 真采集 | 可能弹扫码 / 触发风控 |
| 真发布验证 | 需人工确认 + 创作者后台核对 |
| 干净机器端到端复现 | 需要另一台机器 |

**⇒ 本节通过 ≠ 端到端可用。要真正验收，必须人工做这三项。**

---

## 8.7 验收记录

把结果记到 `docs/verification-report.md`：

```
时间 | 命令 | 退出码 | 结论 | 未通过原因
```

**下一步** → 回到 [README](../README.md)，或查看 `docs/pending-manual-checks.md`
