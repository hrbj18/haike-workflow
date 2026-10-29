# 轻量素材库与分级选材 V1

文件继续放在原来的本地/CopySkill文件夹。共享SQLite登记完整内容SHA256、多位置、来源、授权状态；秒段另存主体、标签、裁切、证据和确认结果。登记不等于画面可采用。

## 入口

- 工作台 `/material-library`：登记、检索、原片跳转、裁切证据、主题候选和选材版本。
- `.venv/Scripts/python.exe scripts/material_library_cli.py`：供生产agent使用的单一离线JSON入口。
- 默认数据 `.backlot/material-library/`；`OPENMONTAGE_MATERIAL_LIBRARY_DIR` 可切换整个库；CLI `--db` 可使用独立SQLite。
- CopySkill工作台项目导入会同步登记。支持 `00-素材目录.json` 和 download_only `清单.json`；整批通过路径、大小和视频解码检查才登记。
- `sync-published` 只把已有成片事件接入为候选，须重新确认裁切；不会改旧二剪索引、转写或草稿。

## 生产端固定步骤

在Haike_video目录运行，全局参数 `--output`、`--db` 放在子命令前。

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python scripts/material_library_cli.py ingest '<标准交付清单绝对路径>'
& $python scripts/material_library_cli.py query '昇腾950'
& $python scripts/material_library_cli.py --output plan.json plan '昇腾950'
& $python scripts/material_library_cli.py --output candidates.json candidates plan.json
# 未确认素材：先用已有概览找候选时段，再准备有限区间的原片/裁切图。
& $python scripts/material_library_cli.py --output task.json prepare windows.json
# 实际查看所有图片，填task返回的submission_template；不能只看标题。
& $python scripts/material_library_cli.py submit review.json
& $python scripts/material_library_cli.py --output selection.json select plan.json --template-key t25
```

`windows.json` 示例；`media_id` 来自查询，时间来自原片，坐标归一化0—1。

```json
{"model":"实际读图执行者","windows":[{"media_id":"MAT-完整SHA256","start":25,"end":28,"crop":{"x":0,"y":0,"w":1,"h":0.6}}]}
```

一次1—12个区间，每个0.4—12秒，3fps密集裁切图加原片上下文图。不要默认分析整部电影或整场直播：先走已有概览/转写定位，再精查这些区间。同模型、同源、同裁切可缓存；任何源或证据图像变化会阻断采用。

确认字段包含 `observation/brands/entities/series/domains/tags/quality/visible_text` 和三个可用性布尔值。空身份列表表示未知，型号/品牌需要实际画面依据。`usable=true` 必须保留主要主体、无残留烧录字幕遮挡；产品展板、机柜标识允许保留。分数是执行者的质量判断，不是机器自动识别置信度。

可选 `product_text_regions` 解决实体标识的OCR误读：坐标相对于**最终1080×630中央带**，时间相对于该秒段起点；例如 `{"x":0.70,"y":0.58,"w":0.12,"h":0.15,"start":0,"end":0.32,"reason":"已查看的实体横梁标签"}`。最多8个，单个面积不超过40%，OCR框必须全部位于区域内且时间命中才能放行。不得用来覆盖烧录字幕。区域进入冻结选段表，随意改动会被拒绝。

已确认任务不可覆盖。更改候选区间/裁切/执行模型会创建新任务；同图重新复核可显式传 `review_revision`（最多80字）创建新确认版本，旧版本仍可读取。

## 分级、覆盖与补采

| 等级 | 依据 | 使用边界 |
|---|---|---|
| A | 已确认的目标实体/显式别名 | 目标相关画面；展示页、转录发布会与实拍须按观察说明区分，不自动证明新闻事实 |
| B | 同系列其他型号 | 明确系列参考，不冒充具体型号 |
| C | 同品牌同领域，或实体品牌标识 | 品牌补充 |
| D | 同行业的通用画面 | 不说明是目标产品 |
| unknown/conflict | 未确认、不确定或品牌冲突 | 可查询、禁止自动采用 |

等级优先，同级看质量；同一秒段不同裁切版本仅推荐最优候选，同分用最近确认，历史证据不删除。默认最多返回12个候选。选择固定三个不重叠的3秒片段，至少3秒达到A/B/C；默认同一原片，确需跨原片时显式配置 `single_source:false`。

需求中实体别名、系列、品牌、领域均由短JSON明示。950有启动词族，其余主题默认只用准确主题实体，生产agent须补充已确认的上位系列、品牌、领域；程序不凭空推断。

缺口返回 `needs_material` 和具体原因，不写“全网找不到”。

```powershell
& $python scripts/material_library_cli.py --output acquire.json acquire plan.json
& $python scripts/material_library_cli.py finish-acquisition '<ACQ-id>' acquire-result.json
```

默认最多两轮：第一轮实体真机/展台/机柜，第二轮同系列及同品牌logo/芯片/机房；每轮最多10搜索词、180MiB、600秒。程序只产出请求，**不自动调用网络或付费服务**；采集agent应遵守限额，写实际搜索词，区分搜索无结果、下载限制、裁切不可用、身份不确定和失败。`imported` 必须附本地标准清单路径；导入后重新做区间确认和选片。重入不消耗新轮次，预算耗尽后调整需求或人工处理。

CLI缺口/预算耗尽退出2，输入/文件错误退出1；否则0。禁止忽略退出码继续渲染。

## 模板接线与兼容

`auto_pick_0930.py t25 昇腾950` 默认登记交付、查共享库、生成冻结分级spec；`--library-plan plan.json` 指定需求，`--topic` 保留原主题。多目录配置须明确 `topic`，不能拿“华为logo”目录替换原主题。缺口写 `material_gap_t25.json`，不替换旧spec；成功写 `material-selection-versions/` 保存旧版和新版。

旧OCR/亮度选材只在显式 `--legacy-pick` 下运行，其 `jobs/strict_noface/face_ratio` 属历史扫描参数。新默认入口用已确认的区间证据，成片仍须跑原有OCR、人脸和亮度QC；不得绕过成片检查。

`select_cut_923.py preview/cut` 对新spec校验冻结ID和源指纹，共用源裁切→等比缩放/留边→中央带变换。历史spec继续使用旧变换。`qc_ep.py` 对新spec允许经过确认的实体文字/时空区域，其余中文字仍给出风险；不要直接关闭文字门禁。

本轮只完成登记、确认、选材、补采合同和模板接线。通用电影/直播解说的脚本导演、TTS和自动长片精剪仍是后续能力；已有成片二剪工作台保持独立。未实测ds4.1的成功率/成本，结构合同通过不等于该模型生产验收。
