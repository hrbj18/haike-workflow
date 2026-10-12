# 踩坑记录

> 本文件保存历史事故和诊断线索，不是现行操作入口。每条给出：现象 → 当时真因（源码位置可能随版本变化）→ 处置方向。动手恢复前先核对当前代码、任务状态和所属项目的正式手册。

---

## 0 ★★ 最贵的一课：默认 dry-run ≠ 分支安全

**时间**：2026-09-22 01:35
**后果**：**误触发了一次真实发布**（任务 id=78，抖音，`publishing` 卡住不可删）

### 发生了什么

Haike 侧发布适配器 `backlot/publish_adapter.py` 的设计里，
`--dry-run` 是**默认值**，并且明确写了「绝不调用 `/run-now`」。

但测试 `--commit` 分支时出了事：

```
1. creatorhub 服务恰好在跑（127.0.0.1:8000）
2. 适配器只调了 POST /api/publish（确实没调 run-now）
3. 但 creatorhub 的默认引擎配置下，创建任务就会立即进入执行
4. 结果：status = publishing，无法删除（409）
5. 用的还是 0 字节的假文件
```

### 三个真因

| # | 真因 | 性质 |
|---|---|---|
| 1 | 测试「真执行」分支前**没有探测执行目标的状态** | **设计缺陷，不是意外** |
| 2 | 只检查了 `is_file()` 与扩展名，**没检查文件大小** | 校验不足 |
| 3 | `--commit` 与 `--dry-run` 是**同一可靠度**的开关 | 危险动作缺确认 |

### ★ 核心教训

> **「默认安全」不等于「分支安全」。**
> 安全必须**每一个分支各自成立**。
> 一个工具有 9 个安全分支和 1 个危险分支，它的安全性是**危险分支**决定的。

### 已实施的修复（三道闸）

```python
# G1：--commit 前强制探活
alive, detail = probe_service(args.base_url)
if not alive:
    return EXIT_NOT_CONFIGURED      # 服务不可达就不执行

# G2：0 字节文件直接阻断
if size == 0:
    result.blocked.append(
        f"成片是 0 字节空文件，拒绝入队：{video}。"
    )

# G3：--commit 必须配显式确认开关
if not args.acknowledge:      # --i-know-this-creates-a-real-task
    return EXIT_BLOCKED
```

**G3 之后还有一层**：如果 stdin 是 TTY，会**再问一次** `yes`。

### 顺带发现的一条重要事实

> **`POST /api/publish` 本身就是「危险动作」。**
> 之前我基于接口名 `submit_once` / `scope="publish"` 以为它只是「创建草稿」。
> 实测证明：**在默认引擎配置下，创建即执行。**
> ⇒ 这个事实已写进 `contracts/publish-v1.md` 与本节。

### 处置流程（遇到同类情况）

```
1. 先 GET /api/publish，记录原任务 ID、状态、日志和队列信息；不得因一次超时新建第二单
2. publishing / uncertain：不删除、不重发，等待并到平台后台核对真实结果
3. 其他状态：依据 CreatorHub 当前代码及用户意图决定是否取消；不要把 DELETE 当成统一恢复办法
4. 记录事故证据和人工待核对项，修复误触发路径
```

---

## 0b ★ 反例测试会污染夹具（已修，但机制值得记住）

### 症状

跑完反例后**紧接着**跑正常体检，会看到一条莫名 FAIL：

```
[FAIL] L2.candidate-pool  加载失败: CopySkillHotspotFeedError:
       READY manifest hash 不匹配：期望 cd32b250...，实际 000000...0
```

看上去像真缺陷，其实是**上一次反例留下的痕迹**。

### 根因

反例的实现方式是「真的把夹具改坏」：
- `--mutate sha256` → 篡改 `package-manifest.json`（哈希变全 0）
- `--mutate layout` → 把 `copy_skill/copy_skill-main` 挪到错误层级

反例**只负责注入，不负责还原**。于是「反例 → 正常体检」这条最常见的连续操作
必然看到残留 FAIL，而脚本又不会提示「请先重建夹具」。

### 修法（2026-09-22 已实施）

`check_all.py` 的反例分支末尾统一调 `_restore_after_mutation()`：
跑 `make_fixtures.py --clean --haike <root>/Haike_video` 重建，并输出
`[OK] MUTATE-restore 夹具已自动重建，可继续正常体检`。
重建失败只告警不报错——反例的核心判据是「错误被捕获」，恢复属附加保障。

### 为什么值得记

**它检验的不只是被校验对象，也包括校验脚本自己的可用性。**
一个会留下脏状态的测试工具，会让下一个人误判「校验器坏了」而去改本来正确的代码。
判据：反例跑完后 `--all` 必须仍是 **38 项 0 FAIL**。

---

## 1 ★ MediaCrawler 失败时没有任何错误信息

**现象**：采集返回 `status = "failed"`，但 `failure` 字段是 `None`。**看不到任何原因。**

**真因**：stderr 被吞，且非零退出码分支不填错误信息。

```python
# copy_skill/src/douyin_intelligence/search_collector.py:100-107
subprocess.run(command, cwd=..., check=False, timeout=timeout_seconds,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # ← 吞掉 stderr
```

```python
# search_collector.py:121-131
if result.returncode == 0 and files:      status = "success"
elif result.returncode == 0:              status = "empty"
                                          failure = "crawler completed without output files"
else:                                     status = "failed"
                                          # ★ failure 保持 None
```

同样问题：`cli.py:82-95` 的 `_run_crawl_command()`。

**崩点**（`mediacrawler_runner.py:44-55`）：
```python
os.chdir(root); sys.path.insert(0, str(root))
import config                              # ← root 不存在时在此崩
from media_platform.douyin.client import DouYinClient
```

**处置**：
1. **不要猜。** 直接跑 doctor：`uv run python -c "... run_doctor(...) ..."`
   （见 `steps/04-copyskill.md` §4.3）
2. doctor 会明确报 `media_crawler.ok` / `venv_ok` 哪一项不满足
3. 本仓已在 `contracts/versions.json` 登记此问题；**修复方式是捕获 stderr**（见 §2）

---

## 2 静默失败家族（同源问题）

**共同模式**：配置失效时**不报错，而是降级或悄悄跳过**。

| # | 位置 | 表现 | 严重度 |
|---|---|---|---|
| 2a | `search_collector.py` stderr DEVNULL | 无错误信息 | 🔴 高 |
| 2b | 跨仓测试 `pytest.skip` | 测试「通过」但没跑 | 🔴 高 |
| 2c | `resolve_media_tool()` PATH 回退 | 静默换用别的 ffmpeg | 🟡 中 |
| 2d | `consumer_root()` 未配置 | 只影响面板显示 | 🟢 低 |
| 2e | `copy_skill_hotspot_feed.enabled = false` | 有数据但读不到 | 🟡 中 |

### 2b ★ 最危险：跨仓测试静默 skip

```python
# Haike_video/tests/backlot/test_copy_skill_research_pack.py:1310-1321
def _producer_module():
    src = Path(REPO_ROOT).parent / "copy_skill" / "copy_skill-main" / "src"
    if not (src / "douyin_intelligence" / "episode_research_pack.py").is_file():
        pytest.skip("CopySkill producer 仓库不在本机，跳过跨仓互操作")   # ← 静默
```

**⇒ 路径写错时显示的是 `SKIPPED`，不是 `FAILED`。**
在默认非 `-v` 输出下，skip 和 pass 几乎看不出区别。

**处置**：`python verify/check_all.py --level=1` 的 `LAYOUT-1` 项会明确检查这一点。

### 2c ffmpeg 的 PATH 回退

```python
# src/douyin_intelligence/media_tools.py:12-18
def resolve_media_tool(config, name):
    configured = ...            # 读配置里的绝对路径
    if configured 存在: return configured
    return shutil.which(name) or name      # ← 回退
```

**⇒ 不是硬故障。** 但如果 ffmpeg 既不在配置路径上、也不在 PATH 上，
最终会以含糊的错误失败。

**处置**：把 ffmpeg 加进系统 PATH，不要改配置。

### 2e 候选池开关默认关闭

```json
// Haike_video/config/daily_tech_brief.json
{ "copy_skill_hotspot_feed": { "enabled": false, "root": "integrations/copy_skill_hotspot" } }
```

**⇒ 默认关闭。** 表现为「明明有数据但读不到」，而不是报错。

---

## 3 ★ 换镜后绝不能跑 `pp8.py retime`

**现象**：人工换镜后，改动被静默覆盖。

**真因**：`pp8.py retime` **不读 `visual_timeline.blocks`**，
而是从 `remake-spec.json` 重建并 PUT 全量覆写 ⇒ 人工换镜丢失。
素材池一变还会 `IndexError`。

**⇒ `pp8.py all` 同样不可用**（它从 retime 起跑）。

**正确路径**：
```
_diag/swap960.py --stage --emit
  → scripts/remake_retime_shots.py --patch … --apply
  → 逐条 overlay,audio,music,preview,approve,final
```

写 blocks 会自动置 `preview_render.status = needs_refresh`；幂等跳过 ⇒ 零付费。

---

## 4 ★ 视频号封面只能改一次，且不可撤回

**现象**：改错了无法回滚。

**⇒ 任何回填脚本的猜测都不可接受。**
**⇒ 回填前一律先 `--dry-run`。**

**另一条同源坑**：管理页**卡片文案 = 视频描述（`desc`），不是标题（`title`）**。
⇒ 关键词必须取 `desc` 开头。

---

## 5 `title` 被服务端静默截断到 20 字

```python
# creatorhub/app/main.py:9130-9132
title=body.title.strip()[:20]
location=body.location.strip()[:60]
cover_path=body.cover_path.strip()[:500]
```

**⇒ 超长直接切掉，不报错、不提示。**

**处置**：在客户端**先自己截断**，并告警。见 `contracts/publish-v1.md` §3。

---

## 6 `GET /api/publish/published` 仅支持小红书

```python
# creatorhub/app/main.py:9256 起
if not acc or acc.platform != "xhs":
    raise HTTPException(400, "请选择一个已登录的小红书账号")
```

**⇒ 不要用它做通用回读校验。** 抖音/快手/视频号的发布结果只能：
1. 读 `GET /api/publish` 的 `status` / `result_url` / `error`
2. 或人工到创作者后台核对

---

## 7 僵尸 `preview_render = generating`

**现象**：没有队列进程在跑，但界面显示 `preview_render=generating`。

**真值在**：`Haike_video/.backlot/production-queue.sqlite3` → 表 `production_jobs`

**恢复前检查**：先从统一队列确认是否仍有活动任务、最近心跳和最终产物；仅凭界面显示 `generating` 不能认定为僵尸任务。保留任务 ID 与诊断证据，按 Haike 当前队列的正式恢复入口处理。2026-09-22 曾通过停服务后手动改 `automation`／`preview_render` 状态恢复，但这只是历史事故做法；**不得把直接改数据库或状态字段当成通用恢复命令**。若当前版本没有受支持的恢复入口，停止自动处理并交由维护者核对。

---

## 8 WorkBuddy 本机环境曾需无沙箱 + `CODEBUDDY_SAFE_DELETE_ENABLED=0`

**适用条件**：2026-09-22 的本机 WorkBuddy 环境。工作台当时需读写工作区外的渲染／缓存路径，部分动作被沙箱拦截。其他 Agent、机器和任务应先诊断实际权限；不要把关闭安全开关写成通用前置步骤。

**⇒ 端口 4754 只允许一个实例**，多开会抢锁导致随机失败。

---

## 9 pytest 必须带特定参数

```bash
# Haike
python -m pytest ... --import-mode=importlib --basetemp=.p

# copy_skill
uv run pytest -p no:cacheprovider
```

**⇒ 不带的后果**：导入冲突 / 缓存污染。

---

## 10 响度天花板（音频）

**规则**：
```
人声 +8 / BGM −6 dB / 成片 −9 LUFS
验收：|I − target| ≤ 1.5、TP ≤ −1.0
```

**★ 抬人声抬不动**：天花板是 `I = min(target, −2.0 − 波峰因数)`。

**★ BGM 判定陷阱**：BGM 只按**说话间隙包络**判（P5/P25 ≥ +2），
**不得用整片 200–800 Hz LUFS**。

**★ 别把 finalize 默认值当项目 target**：`-14 LUFS` 可能是 finalize 的默认值，
要和项目自身 target 比对。

---

## 11 竖屏字幕底边必须 < 0.80

模板 `y=0.89` **不合规**。

**⇒ 改文字层后必须重跑**：`overlay → preview → approve → final`。

---

## 12 B-roll 与台词非一一对应时的硬要求

**必须多来源 + 每 2.2–3.5 秒换画面。**
**⇒ 别让同一素材扛整段口播。**

---

## 13 QC 必须用全片联系表

**不能只看 4 帧。** 要查：视频流 / 时长 / 字幕 / 水印 / 响度 / TP。

**★ 但「看全片」仍不等于「看得懂」（2026-09-29 升级）**：联系表是**抽样**，抽不到的问题照样出厂——该批次 7 条成片 size／元数据／解码全部正常，其中仍有一条「3.0–8.5 秒**每帧**人脸大特写」被三道定时兜底判成「全部合格」。**内容层必须走程序化密采样门禁**（≤0.5 秒步长扫中央可见带的人脸／文本／亮度）；抽样只用于发现事故，不能用于证明合格。判据与现行流程见 [agent-runbooks/模板图文视频.md](../agent-runbooks/模板图文视频.md) §7。

---

## 14 `creatorhub` 只改 `studio/` 目录内的文件

`PathBinder.allow_outside=False` 会**跳过外部 app**。
**⇒ 别跑 `--bind-only` / `/api/rebind`。**
**⇒ 改 JSON 只能外科式单值替换。**

---

## 15 改了封面代码必须重启服务

**uvicorn 启动时没有 `--reload`。**

三平台封面代码：
```
抖音    app/platforms/douyin/cover.py
快手    app/platforms/kuaishou/cover.py
视频号  app/platforms/channels/publish.py
```

---

## 16 `.backlot/` 不是缓存，但也不能住代码

**⇒ 不要删。** 它是项目数据（队列、账本、诊断证据）。
同理 `.workbuddy/` 也不是缓存。

**⇒ 反过来：生产脚本绝不能住在 `.backlot/` 里。** 该目录被 `.gitignore` 整体忽略（`Haike_video` 第 111 行），
住进去的代码**不入版本控制、跨机必然丢失、也不受上游同步保护**。2026-09-29 发现模板图文流水线的
16 个脚本全住在 `.backlot/_diag/923-batch/`，已迁入 `Haike_video/scripts/template_video/`。

**⇒ 判据：把「数据」与「代码」分开** —— 数据留在被忽略的工作目录（本就该忽略），
代码必须在 `scripts/` 等受版本控制的路径。**迁完后务必用 `git check-ignore -q <file>` 复验**（rc=0 即仍被忽略）。

---

## 17 脚本的 `items[0]` 静默回退

`scripts/_sh_open_list_entry.js` 的 `items[0]` 静默回退
**已于 2026-09-21 改为 `ok=false` 报错退出** —— **不要改回去**。

---

## 18 中央可见区内容门禁：人脸与「非中文」文本

**时间**：2026-09-29
**现象**：成片中央带（归一化后 y570–1280）出现 (a) 人物大特写、(b) 纯拉丁的源作者水印，仍被判合格出厂。

**真因**：
- (a) 旧规则只约束「cue-001 第一帧不是人物侧脸」，**中段 cue 没有同样的门禁**；中段一旦取了「博主出镜口播」类素材，3–9 秒就是连续人脸大特写。
- (b) 字幕扫描脚本**只把含 CJK 的文本判脏**，`@handle` 形式的拉丁水印被直接放过。

**⇒ 判据**：中央区按 ≤0.5 秒步长采样；`face_big`（人脸宽 ≥ 中央区宽 ×0.22）命中即不合格；文本**不限语种**（≥3 字符、置信度 ≥0.6），再由人工分流「画面本身文字 ✅／口播字幕·源水印 ❌」。
**⇒ 抽 1.5／4.5／7.5 三帧不足以保证**，必须密采样。

---

## 19 发布日志按平台分流：视频号在 stderr

`grep` `codex-publish-stdout.log` 找不到视频号的「平台核对」行——**不是没发，是日志不在那儿**。
抖音／快手发布器用 `print` → stdout；视频号发布器用 logging → `codex-publish-stderr.log`。

**⇒ 判读发布结果前先确认该平台的输出流**；任务的 `acceptance_*` 字段可能整列为空，也不能替代核对。

---

## 20 发布任务持有路径，不持有快照

`publishtask.media_json` 存的是**绝对路径**，发布时直接读盘、**不复制副本**。

- `contract_version=1` 不锁成片 SHA-256 → 成片同名覆盖后，旧任务发出去的就是新片，**无需重建**。
- `contract_version=2` 在提交时与发布前各校验一次 `file_sha256(video) == video_sha256` → 成片一变旧任务必 `failed`，**必须重建**。

**⇒ 返工替换成片后，先查 `contract_version`／`cover_policy`／`video_sha256` 再决定是否重建任务。**

---

## 21 ★ 版式的「上下留白」必须用实机截图反解，不能凭画布坐标拍脑袋

**时间**：2026-09-29
**现象**：模板图文视频（9 秒竖屏）七期成片在真机上被用户指出「最上面太靠上，会和抖音最上面的搜索等功能按键重叠」。而此前所有版本都通过了画布层面的自检。

**真因**：版式常量一路只按**画布坐标**（1080×1920）设计，从未与**手机屏幕上抖音 UI 的实际占位**对过账。画布与手机可见区之间隔着一个 **≈1.364 的缩放**加一次**横向裁切**——凭感觉留的 100px 在屏幕上只剩 73px，且位置整体错位。

**⇒ 判据（可复用套路，三步缺一不可）**：
1. 拿一张该机型抖音播放页的**原始分辨率截图**（含状态栏／头像行／频道 tab／底部 tab）；
2. 把截图里的视频区与成片画布对齐，解出线性映射。本机实测：`screen_x = -96.5 + 1.364×canvas_x`、`screen_y = +5 + 1.364×canvas_y`；
3. **用帧级 MSE 反查验证映射**——把截图可见条带反算回画布、与成片某一帧逐像素比。比例对时 MSE 降到两位数（实测 73），错时 1000–9000。**这步不能省**，否则会拿着错比例去改版式。

**⇒ 本机实测常量**：抖音横向裁切后**可见画布 x 只有 71..1008**（左右各被压掉约 71px）；顶部功能区（状态栏＋头像行＋频道 tab）下沿 ＝ 画布 **y170**；另有**浮动热搜条**底沿可到 y≈200，属动态元素，只能保证不与固定 UI 重叠。

**⇒ 版式 v2 定值**（`build_923.py`）：`TOP_SAFE=212`（首行墨迹顶，越过 y170）、`BAR_X 72/1008`、`CARD_X 78/1002`、`TOP_PLATE_BOTTOM=650`（下限）、字号 80／54。实测首行墨迹顶＝画布 211→屏幕 293，固定功能区下沿＝屏幕 237，**净留白 ≈57px**。

---

## 22 ★ OCR 的「单字命中」几乎都是噪声，判 `text_risk` 需 ≥2 个 CJK 字

**时间**：2026-09-29
**现象**：某条素材被自动字幕扫描**逐帧稳定判 DIRTY**，目视却完全干净；一条好素材差点被丢弃。另一处成片在 1.0／2.0 秒报出中文「米」字。

**真因**：**Claude 的星芒 logo「✳」被 RapidOCR 稳定误读为单字「米」**。图形类 logo、星芒／十字／放射状图标都容易落进这个陷阱。

**⇒ 判据**：自动门禁改为 **`MIN_CJK = 2`**——单帧需 OCR 到 **≥2 个 CJK 字**才判 `text_risk`（`qc_ep.py` 内置）。逐秒扫描脚本可以保留原样（用于时间线粗筛），但**最终定论必须过 ≥2 字阈值**。

**⇒ 处置顺序**：遇到「整段判脏但目视干净」，**先用原尺寸裁出可见带（1080×630）逐像素看**，再决定是不是噪声——不要因为一条 OCR 报警就丢掉可用窗口。

---

## 23 ★ 暗场要按「段」判，不是按「帧」判；选段阶段就要查整段亮度

**时间**：2026-09-29
**现象**：一版成片第三镜 6.0–8.5 秒**连续 6 帧**亮度只有 ~20，整段近黑——这是事故。但同一版成片的首帧亮度 V=31.3 也曾被报警，实际是深空底色配高对比白字，目视完全合格。

**真因**：`dark_risk` 是**逐帧**判 `V < 45`，不区分「单帧落在深底」与「整段发暗」。

**⇒ 判据**：
- **单帧**低亮（尤其首帧）：目视确认对比度足够即可放行，不是「整段暗场」。
- **连续多帧**低亮：不合格，换窗口重跑。本次事故原因是选用了一段**金色分布动效**（看着华丽、实际近黑）。
- **选段阶段就把整段亮度查出来**，**亮底图表／对比表优先于深底动效**——亮底素材天然免疫此类事故，且信息量更高。

---

## 24 ★ 同一条流水线上的解释器应当只有一种

**时间**：2026-09-29（同日两次修订）
**现象**：用系统 Python 跑字幕扫描／人脸门禁，`ImportError: DLL load failed while importing onnxruntime_pybind11_state`，连试三次全败。

**当时的真因**：三个解释器能力不同，脚本对不上就静默失败在 import 阶段；**更要命的是门禁脚本借的是
`copy_skill` 项目的 venv（跨仓寄居）** —— 那个项目一旦重建／清 venv，本流水线的内容层门禁立刻全废。

**⇒ 现行做法（2026-09-29 起，已替换旧「三种解释器分工」结论）**：本流水线的门禁依赖
（`rapidocr 3.9.2`／`opencv-python 5.0.0.93`／`onnxruntime 1.29.0`）已装进本仓 `Haike_video/.venv`，
**渲染与门禁统一用同一个解释器**；依赖清单固化为 `Haike_video/scripts/template_video/requirements.txt`。

**⇒ 通用原则**：跨仓借解释器 = 隐性单点依赖。能力缺口应当**装进本仓 venv 并写进 `requirements.txt`**，
而不是长期借别人的。**导入顺序仍敏感**：脚本里先 `import onnxruntime` 再 `import cv2`／`rapidocr`，
否则 DLL 初始化失败。跑之前先 `import onnxruntime, cv2` 打一行版本号自证。

---

## 25 ★ 迁移脚本目录后，`dirname(__file__)` 当工作目录会错位

**时间**：2026-09-29
**现象（差点踩中）**：`qc_ep.py`、`_preview_ep.py` 原先与工作数据同目录，`WORK = os.path.dirname(os.path.abspath(__file__))`
指向工作目录是**对的**；脚本一迁到 `scripts/template_video/`，这个表达式就变成**脚本目录**，
QC json 与 `_chk929/` 会默默落到错误位置——**不报错，最难查**。

**⇒ 迁脚本时必须一并审查所有 `__file__` 派生的路径**，把「工作目录」与「脚本目录」解耦
（本文用 `_paths.WORK_DIR`）。**同类信号**：`os.getcwd()`、硬编码 `./` 相对路径、`os.chdir`。

---

## 26 ★ opencv 读不了含非 ASCII 字符的路径

**时间**：2026-09-29
**现象**：`cv2.FaceDetectorYN_create(r"D:\刘宇钊\...\Haike_video\models\yunet.onnx", ...)`
报 `OpenCV(5.0.0) ... Can't read ONNX file: D:/刘宇钊/...`；**同一文件换纯 ASCII 路径即正常**。

**⇒ 解法**：模型以**项目内路径为准**（可入库、可审计、跨机自带），运行时用 `_ascii_safe()`
复制一份到 `%LOCALAPPDATA%\videohub-models\` 再交给 cv2。
**别为了绕开它把模型放去用户缓存目录** —— 那等于把「资源自持」又交回给机器环境（换机即断）。
