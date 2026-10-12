# 模板图文视频流水线 · 正式位置

科技资讯「9 秒模板图文条」的生产脚本集合。**本目录就是这条流水线的正式位置**：
入版本控制、跨机自带、不依赖工作区外的第三方目录。

> **迁移说明（2026-09-29）**
> 这些脚本原先寄居在 `../.backlot/_diag/923-batch/` —— 整个 `.backlot/` 被 `.gitignore`
> 第 109 行忽略，等于**不入版本控制、跨机必然丢失**；同时它们借的是 `copy_skill` 的解释器、
> 读的是工作区外另一个 Haike 副本的 BGM 曲库。本次一并收进本项目，成为自持工作流。

---

## 1. 环境：一个 venv 跑全部

渲染、OCR 门禁、人脸门禁**同用** `Haike_video/.venv`，不再跨仓借解释器：

```bash
PY=./.venv/Scripts/python.exe        # 在Haike_video根目录执行
```

该 venv 相对上游基线额外需要（见 `requirements.txt`）：

| 包 | 版本 | 用途 |
|---|---|---|
| `rapidocr` | 3.9.2 | 中央可见带**文字**门禁（有没有混进中文字幕/水印） |
| `opencv-python` | 5.0.0.93 | 人脸检测 + 亮度统计；人脸模型走 `cv2.FaceDetectorYN` |
| `onnxruntime` | 1.29.0 | 上面两者的推理后端 |

> ⚠️ **顺序敏感**：脚本里必须**先** `import onnxruntime`、**再** `import cv2`／`rapidocr`，
> 否则 cv2 先加载的 MSVC 运行库会让 `onnxruntime_pybind11_state` DLL 初始化失败（2026-09-29 实测）。

## 2. 路径：全部由 `_paths.py` 收口

**不硬编码任何盘符或工作区绝对路径**（对齐 `Haike-Videohub/contracts/layout.json` 的
「任何自动化脚本都必须按本文件解析路径，不得硬编码」）。所有路径从 `_paths.py` 取：

| 常量 | 默认值 | 环境变量覆盖 |
|---|---|---|
| `WORK_DIR` | `.backlot/_diag/923-batch` | `TEMPLATE_VIDEO_WORK` |
| `MUSIC_DIR` | `song/` | `OPENMONTAGE_MUSIC_DIR` |
| `MODELS_DIR` | `models/` | `OPENMONTAGE_MODELS_DIR` |
| `FACE_MODEL` | `models/yunet.onnx` | `VRF929_FACE_MODEL` |
| `PROJECTS_DIR` | `projects/` | `OPENMONTAGE_PROJECTS_DIR` |
| `VIDEOHUB_ROOT` | 四仓根（`Haike_video` 的父目录） | `VIDEOHUB_ROOT` |
| `COPY_SKILL_OUT` | `../copy_skill/copy_skill-main/output/复刻视频`（采集端**数据来源**） | — |
| `FFMPEG` / `FFPROBE` | `FFMPEG_BINARY` → PATH → `lib.ffmpeg_locator` | `FFMPEG_BINARY` |

> ⚠️ **cv2 读不了含中文的路径**（实测：`Can't read ONNX file: ...刘宇钊...`）。
> 模型以项目内 `models/yunet.onnx` 为准（可入库、可审计），`_paths._ascii_safe()` 会在运行时
> 自动镜像一份到 `%LOCALAPPDATA%\videohub-models\` 再交给 cv2。

## 3. 脚本清单

| 脚本 | 职责 |
|---|---|
| `dense_sheet_928.py` | 密集抽帧联系表（粗筛：整片长什么样） |
| `contact_sheet_923.py` | 候选联系表（每候选 4 帧 + 元数据 json） |
| `_mk_cand_t23.py` | 采集交付 `00-素材目录.json` → 候选 json |
| `_make_spec.py` | 候选 json + 选点 → `spec_<t_key>.json` |
| `select_cut_923.py` | **选段／裁条／预览**（`preview` / `cut` 两个子命令） |
| `_frame_check.py` | 成片视角检查图（上下字板压暗，只留中央可见带高亮） |
| `_band_crop.py` | 原尺寸裁出中央可见带（逐像素核对字幕/水印） |
| `scan_subs_929.py` | 逐秒 OCR 扫描源片带内字幕时间线 |
| `probe_face_final.py` | 成片人脸门禁 + 亮度（不依赖 rapidocr） |
| `build_923.py` | **渲染器**（版式 v2 常量 + `SPECS` 文案表） |
| `make_cover.py` | **AI 封面合成**（AI 原图 → 3:4 竖封面 + 契约可校验 proof JSON） |
| `_preview_ep.py` | 版式图 + 实机预览图（安全区目视） |
| `qc_ep.py` | 中央画面QC（中文OCR + 人脸 + 暗帧）；元数据/解码/音频和英文人工复核另做 |
| `verify_spec_929.py` | spec 核验 |
| `batch_finish_929.py` | 批次总控（轮询 state → 裁段 → 渲染 → 归档） |
| `rewrite_923_projects.py` | 项目库回写；新批次--manifest提供项目映射/事实状态/当前QC，保留稳定素材ID |
| `_paths.py` | 路径收口点（上面所有脚本共用） |

## 4. 典型调用

新自动选材默认经过共享库的裁切证据与A/B/C/D分级；缺口返回2，不用亮度/中文过滤直接兜底。
见 [素材库V1](../../docs/MATERIAL_LIBRARY_V1.md)。旧扫描只在 `--legacy-pick` 下运行。

在Haike_video根目录运行；先准备并确认秒段证据。新批次设置独立工作目录，避免覆盖历史产物。

```powershell
$python = '.\.venv\Scripts\python.exe'
$env:TEMPLATE_VIDEO_WORK = '<本批次工作目录绝对路径>'
& $python scripts/template_video/auto_pick_0930.py t30 'GPT6.1Sol发布' --library-plan plan.json
& $python scripts/template_video/select_cut_923.py preview t30 spec_t30.json
& $python scripts/template_video/select_cut_923.py cut t30 '<project_id>' spec_t30.json
& $python scripts/template_video/build_923.py t30
& $python scripts/template_video/qc_ep.py '<成片绝对路径>' t30_9s 0.3333333333
# L1/音频/L3及事实核验完成后；新批次不依赖历史THEMES。
& $python scripts/template_video/rewrite_923_projects.py --manifest writeback.json t30
```

spec路径以实际工作目录为准。QC失败退出2，禁止继续完成归档；待核验事实须标fact_pending，视频正常不能替代新闻事实核验。新增回归：`tests/test_template_project_writeback.py`。

封面可复用已有底图，记录真实来源/生成模型；未知保持unknown。本轮没有新生图。若另行生成，应读当前图片生成skill并使用已配置入口，不照抄旧机器工具路径或“零积分”结论。合成入口`make_cover.py`的默认proof假定新AI图，复用旧图时必须准确记录复用来源与时间，不能冒称本轮生成。

## 5. 自持化剩余缺口（本机已就位；跨机分发前需处理）

「脚本 / 解释器 / 资源」三线的**依赖**已收干净 —— 本机跑这条流水线不需要工作区外的任何东西。
下面四条是**分发层面**的残留，按需处理：

### 5.1 `WORK_DIR` 名字还带 `_diag`

`WORK_DIR` 目前指向 `.backlot/_diag/923-batch`（沿用既有数据，便于平滑迁移）。
它只是**工作数据**（中间产物，本就该被 gitignore），不影响自持性，但名字有误导。
下一步改名为 `.backlot/template-video/`：设 `TEMPLATE_VIDEO_WORK` 即可先行切换，**不必改代码**。

### 5.2 BGM 曲库不入版本控制（版权）

`song/` 被上游 `.gitignore` 第 123 行 `/song/` **整体忽略** ⇒ 9 首 BGM 不会随仓库分发。
这是上游约定（音乐属本地资产），也避免了把网络现成音乐推入远端的版权风险，故**未加例外**。

- **本机不受影响**：9 首已就位，`build_923.py` 的 `SPECS` 引用到的 8 首全部覆盖。
- 跨机复刻三选一：① 手动同步 `Haike_video/song/`；② 设 `OPENMONTAGE_MUSIC_DIR` 指向机器上已有曲库；
  ③ 换无版权曲库并同步改各主题的 `bgm` 字段。
- 缺失时的表现：渲染在取 BGM 阶段失败（ffmpeg 报找不到输入文件）。

### 5.3 `ffmpeg` 经 PATH 解析到了别的项目目录

`_paths.ffmpeg()` 的顺序是 `FFMPEG_BINARY` → `PATH` → 本仓 `lib.ffmpeg_locator`。
本机 `PATH` 里的 ffmpeg 位于 `D:\刘宇钊\codex_work\视频下载dy\.tools\ffmpeg\...`（另一项目的便携副本），
该目录若被移走或改名，`PATH` 这一跳就会落空。要彻底自持：设 `FFMPEG_BINARY` 指向固定路径，
或把 ffmpeg 放进 `Haike_video/.tools/` 并让 `lib.ffmpeg_locator` 优先命中。

### 5.4 未迁入的一次性脚本（23 个）

`.backlot/_diag/923-batch/` 根下仍有 23 个 `.py`（`dl_broll_923.py`、`ingest_*/`、`sheet_batch_929.py`、
`watch_sheets_929.py`、`compose_dh.py`、`dh_923.py`、`enrich_923_projects.py`、`_t_ort.py` 等）。
它们**未被操作手册引用**，属一次性／实验脚本；按知识库收录规则
（「临时脚本要先进入其所属项目的正式位置，才可成为长期依赖」）**本轮不迁**。
某个若要长期用：先迁入本目录 ＋ 补一次实跑验证，再在手册里登记。

> 已废弃的 15 个旧副本在 `.backlot/_diag/923-batch/_legacy_scripts/`（见其 README），**勿执行**。

## 6. 配套文档

- 操作手册：`../../Haike-Videohub/agent-runbooks/模板图文视频.md`
- 布局硬约束：`../../Haike-Videohub/contracts/layout.json`
- 坑记录：`../../Haike-Videohub/docs/pitfalls.md`
