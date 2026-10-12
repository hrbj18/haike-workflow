# 窗口复刻（window-remake）· 操作指南 v1

> **呼叫名：`窗口复刻`**　别名：`上下换板` / `夹心板` / `留中换板` / `保留中间画面只换上下`。
> 下次要再做一期，直接说「**窗口复刻**」+ 丢掉参考片路径即可，本线已被登记进
> `skills/INDEX.md`（Workflow Call Signs）、`AGENT_GUIDE.md` §7、项目 `MEMORY.md`。
> ⚠ 别与「素材复刻」线（`haike-video-material-remake-script`）混——那条线是给素材目录写自己的脚本。
>
> 2026-09-20 从 `tech-war-remake-1`（科技与战争）这一期沉淀而来。
> 驱动脚本 `scripts/remake_window_cli.py`，**零付费**：无配音、无数字人、无 ARP、无 Pexels 下载。
> 对照物：本管线另有「素材拼接重排线」，见 `.backlot/9.14-remake-8/rebuild-SOP.md`，
> 那条线要 pick8 / curate8 / prepare_master / 重排镜头，本线**都不需要**。

---

## 0. 这条线到底在做什么

用户原话：

> 「原视频里中间的画面直接用，画面上下的标题样式不一样就好了」
> 「保留中间的画面，只调整画面上下窗口的内容」

技术前提是一个很多人没注意到的结构：

```
竖屏参考片的典型结构（720x1280）
┌──────────────────────────┐  ← 顶部：原片自己的标题带（4 层文字）
│   ← 标题带（叠在模糊带上）      │
├──────────────────────────┤  0.232
│                          │
│      中间清晰画面           │  ← 原片的真实画面，只有这一条
│   （唯一有价值的部分）        │
│                          │
├──────────────────────────┤  0.652
│   ← 字幕带（叠在模糊带上）      │
└──────────────────────────┘  ← 底部：原片自己的字幕带
```

博主为了把横屏素材垫成竖屏，上下各铺了一条**模糊填充带**，标题和字幕本来就叠在这两条带子上。

⇒ **用自己的深色板把上下两条带子整块盖掉、写自己的字，中间真实画面一点不损失。**
被盖掉的只是原片的模糊填充，不是画面内容。这就是这条线"最轻松"的根本原因。

成片画布 1080×1920（原片 720×1280 精确 ×1.5，无变形）：

| 区域 | 归一化 y | 放什么 |
|---|---|---|
| 顶部板 | `0 – plate_top_h`（默认 0.232） | N 层标题，板内垂直均分 |
| 露出画面 | `plate_top_h – plate_bot_y`（默认 0.232–0.652，占 42%） | 原片画面，**原样保留** |
| 底部板 | `plate_bot_y – 1.0`（默认 0.652–1.0） | 逐段字幕（挂在 overlay 上） |

---

## 1. 三步走

```bash
cd D:\刘宇钊\codex_work\Haike_video
PY=./.venv/Scripts/python.exe
export CODEBUDDY_SAFE_DELETE_ENABLED=0

# ① 量版式（只读，不碰任何状态；可反复跑）
$PY scripts/remake_window_cli.py measure specs/<期>.json

# ② 建项目 + 绑素材 + 写图层 + 出全片预览
$PY scripts/remake_window_cli.py prep specs/<期>.json      # ★ 必须后台跑

# ③ 人工看过全片预览，确认画面/标题/字幕都对
$PY scripts/remake_window_cli.py final specs/<期>.json     # ★ 必须后台跑
```

**每期只需要写一份 spec JSON。** 模板见 `scripts/remake_window_spec.template.json`。

`queue_preview` 默认开启：`prep` 写完时间线和图层后，通过统一生产队列生成全片预览；不要绕过队列直接调用 full-preview runner。预览人工复核后，`final` 才批准预览并开始正式渲染。

`tech-war` 那期的可复现 spec 在 `.backlot/_diag/ref920/techwar-spec.json`。

---

## 2. spec 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `project_id` | ✔ | 项目 id，同 id 重复 prep 是幂等的（素材按 name 跳过） |
| `meta.title` | | 项目标题（同时作为音轨标题） |
| `meta.brief` | | 不填则用默认说明 |
| `source.video` | ✔ | **原片路径**（绝对路径） |
| `source.clip_seconds` | ✔ | 成片总时长；原片结尾若是灰噪点/黑场，取到噪点之前 |
| `source.start_seconds` | | 从原片第几秒开始用（默认 0） |
| `source.segments` | | 分几段（默认 = 字幕条数），每段 = clip/N |
| `source.asset_label` | | 素材在项目里的显示名，默认「复刻原片」 |
| `layout.plate_top_h` | ✔ | 顶板下沿。**用 measure 的建议值** |
| `layout.plate_bot_y` | ✔ | 底板上沿。**用 measure 的建议值** |
| `layout.plate_color` | | 板底色，默认 `#0E1218`（近黑） |
| `layout.title_gap` | | 标题行距，默认 0.004 |
| `titles[]` | ✔ | 每层 `{text, size, weight, color}`；位置自动算，**不用填坐标** |
| `subtitles.items[]` | ✔ | 每段 `{text}` 或 `{text, start_seconds, end_seconds}`；不给时序就按时长均分 |
| `subtitles.style` | | `{y, size, weight, color, stroke_color, stroke_width}`，默认 y=0.755 |
| `assets.bgm` | | BGM，相对仓库根或绝对路径（本期用 `song/压迫感.mp3`） |
| `queue_preview` | | 默认 `true`；全片预览通过统一生产队列运行 |

### 横屏源片改成竖屏

当源片是 16:9 横屏、用户要求原画面完整居中时，先用本地 FFmpeg 生成 1080×1920 竖屏**中间素材**：横屏画面等比缩到 1080×608 左右，垂直居中，上下以纯色或简洁底纹补齐，不裁切、不拉伸。把这个母版登记为 `source.video`；再用 `plate_top_h` / `plate_bot_y` 只覆盖上下补齐区，由 OpenMontage 绘制标题与底部文字，正式成片仍经 OpenMontage manifest 和工作台渲染。

板位按实际像素边界计算，不依赖文字带自动识别：1080×608 画面居中时约为 `plate_top_h=0.342`、`plate_bot_y=0.658`。先看代表帧并跑 `measure` 留档；自动测量可能把原横屏内容中的贴纸文字误判为版式标题，此时保留手工边界，不要让板覆盖中央画面。若需保留原声，单独无损抽取源音轨并登记为本项目 source audio；不额外叠加 BGM。

若正式渲染因原声的响度天花板未达到默认目标而失败，先查预览报告中的实际 LUFS 与 True Peak。保持 True Peak ≤ −1 dBTP，在项目级将目标设到可达响度附近，重新生成并复核预览，再批准正式渲染；不要只忽略验收失败。

标题排版是复刻参考片的结构，**自动垂直均分**，不需要手算：

```
H_i     = size_i × 1.15 / 1920
TOTAL_H = Σ H_i + gap × (n-1)
Y_1     = (plate_top_h − TOTAL_H) / 2
Y_{i+1} = Y_i + H_i + gap
```

---

## 3. measure 的输出怎么读

`measure` 是**只读**的，随便跑。它做两件事：

**主判据 —— 找原片自带的文字带，反推板位**

```
plate_top_h = 原片上半区最低那条文字带的下沿 + 0.006
plate_bot_y = 原片下半区最高那条文字带的上沿 − 0.006
```

只要求盖住原片的标题带和字幕带，中间也就干净了。

实测校准（`tech-war` 期）：算法给出 **0.232 / 0.653**，当初人眼看片定的是 **0.232 / 0.652** —— 自动复现，误差 0.001。

**判据为什么不能只看颜色**（两个都是踩出来的坑）：

| 误判来源 | 表现 | 加什么判据才滤掉 |
|---|---|---|
| 画面里的大片同色区域（落日荒原的黄土地） | 被颜色掩码整段判成「黄色文字」 | **行段高度 ≤ 0.045**（文字行只有 0.02–0.035） |
| 画面里的白色高光（士兵的枪、背包反光、无人机准星） | 行高够矮，骗过上一刀，把 plate_top_h 顶到 **0.388** | **水平跨度 ≥ 0.30**（文字是成行笔画、横跨画面宽；物体高光只占一小段） |

输出里会打印 `—— 已忽略（不是文字，别手动拿去算板位）——` 段，把被滤掉的候选和理由都列出来，可人工复核。

**辅助判据 —— 清晰带**（原片上下是否真是模糊垫底）

如果原片上下**没有**模糊垫底（比如竖屏实拍原片），板子会真的吃掉画面，这时会明确警告。
辅助判据测不出来是正常的（本期就测不出来，因为上下是「模糊但有内容」），**不影响主判据**。

同时会在 spec 同级目录留 `_measure/*.png` 代表帧，**板位定案前人眼看一遍**。
（`cv2.imwrite` 对中文路径**静默失败**，脚本内部已改用 `imencode + write_bytes`，别改回去。）

---

## 4. 完成判定（缺一项不算完）

- [ ] `measure` 的板位建议与 spec 现值**一致**（输出里有 `[一致]` 标记），或差异已人工确认；
- [ ] `_measure/*.png` 人眼看：**板子盖住了原片全部自带的标题/字幕**，没有露字；
- [ ] `prep` 全步骤 200，overlay 写入后打印出的 layer 列表 y/h/fs 都对；
- [ ] 全片预览里：中间画面完整、上板 N 层标题不裁字、下板字幕不压出安全窗（**底边 < 0.80**）；
- [ ] `final` 渲染 `status=completed`，`output_path` 有值；
- [ ] 成片抽帧复核：无原片烧入文字残留、无黑场、时长 = `clip_seconds`。

---

## 5. 已知坑

1. **板层的 `text` 不能为空** —— 写全角空格会被服务端 strip 掉并报 422「文案不能为空」。
   脚本用 `"·"` 且 `color` 与底色相同，视觉不可见。别"优化"成空串。
2. **字幕必须走 overlay 层，不能用字幕系统** —— 字幕系统默认 `y=0.89`，底边超安全窗（规范要求 < 0.80）。
   所以 `prep` 会把字幕系统的 `enabled` 置 False，字幕由 overlay 的 `sub-*` 图层承担（默认 0.755）。
3. **改过 overlay ⇒ 各段 `review_status` 被打回 `needs_adjustment`**，所以链路只能是
   `overlay → full-preview → approve → video-render`，**不能跳过预览直接 final**，服务端会拒。
4. **`track_id` 必须从 `music_library` 回读，绝不能手打 hash** —— 尾字符打错会得到**无提示的 422**。
   脚本已内置回读。
5. **同一个 asset 可以被多个 cue 复用**，靠 visual-timeline 的 `source_in/out` 取不同区间。
   ⇒ 不必把原片切成 4 个文件（少一步、少占磁盘）。
6. **`prep` / `final` 必须后台跑** —— 前台 120s 会被 SIGTERM 杀掉，批次半途而废。
7. **服务必须在 4754 运行且无沙箱**（`CODEBUDDY_SAFE_DELETE_ENABLED=0`），否则删除守卫会让服务静默崩。
8. ★ **原片水印／烧入字如果在「中间清晰画面」里，板子盖不掉。**
   `tech-war` 期的「网络资料」水印就落在 y≈0.27 的画面区，最终成片里仍在。
   要么接受、要么裁掉右侧、要么进 overlay 前先做打码 —— **这条只能人判断，脚本不代劳**。

---

## 6. 批量做

spec 之间没有共享的单例资源（`windows.json` 之类只在素材拼接线上），可以放心循环：

```bash
for s in specs/*.json; do
  $PY scripts/remake_window_cli.py measure "$s"
  $PY scripts/remake_window_cli.py prep    "$s"   # 后台
  # 全部 prep 完 → 人一次性看完所有预览 → 逐个 final
  $PY scripts/remake_window_cli.py final   "$s"   # 后台
done
```

效率点：`measure` 和写 spec 是**唯一的脑力活**（量板位 + 写 N 层标题 + N 段字幕），
其余全是固定的 API 序列。一期的实际工作量 ≈ 读一遍原片 + 填一个 JSON。

---

## 7. 与原片的关系（合规，别跳过）

这条线**直接复用原片的画面**。技术上是"版式复刻"，但画面本身来自他人作品，
平台侧可能判重、原作者侧可能主张权利。发布前自行确认素材来源与授权状态。
水印残留（见坑 8）会让复用关系更明显。
