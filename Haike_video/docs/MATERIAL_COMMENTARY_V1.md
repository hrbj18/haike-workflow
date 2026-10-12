# 素材解说模板 V1

状态：beta，支持可选精剪 V2。最近核对：2026-10-08。

第三种通用模板的核心合同是“素材观察 → 自由叙事 → 声音与镜头编排 → 统一队列 → 待审预览”。电影解说、直播切片、产品演示和现场互动共用同一合同；题材标签不决定段落、镜头数或成片时长。理解和叙事由当前 agent 或人完成，程序不提供全自动电影理解或自动找金句的承诺。

操作入口：`/material-commentary`；[跨仓 runbook](../../Haike-Videohub/agent-runbooks/素材解说视频.md)；[导演 skill](../skills/pipelines/material-commentary/director.md)。

## 代码与数据真值

| 职责 | 权威入口 |
|---|---|
| 创建、草稿、编排、预检、冻结 | [material_commentary.py](../backlot/material_commentary.py) |
| 区间取证与人工/agent 观察 | [commentary_evidence.py](../backlot/commentary_evidence.py) |
| 音轨导入、报价、付费防重发 | [commentary_audio.py](../backlot/commentary_audio.py) |
| 事件卡、覆盖、重复区间与同源对照 | [commentary_editorial.py](../backlot/commentary_editorial.py) |
| 实际语音时间戳与字幕绑定 | [commentary_alignment.py](../backlot/commentary_alignment.py) |
| 媒体合成、缓存、技术 QA | [commentary_render.py](../backlot/commentary_render.py) |
| 素材引用、逐镜使用台账与重定位 | [commentary_library_bridge.py](../backlot/commentary_library_bridge.py) |
| HTTP 与前端 | [commentary_api.py](../backlot/commentary_api.py)、[material_commentary.html](../backlot/ui/material_commentary.html) |
| 命令行与工作流登记 | [material_commentary_cli.py](../scripts/material_commentary_cli.py)、[material-commentary.yaml](../pipeline_defs/material-commentary.yaml) |
| 共用媒体身份与来源 | [MATERIAL_LIBRARY_V1.md](MATERIAL_LIBRARY_V1.md)、[素材库管理合同](MATERIAL_LIBRARY_MANAGEMENT_V1_1.md) |

草稿及版本目录索引存于素材库 SQLite 的 `commentary_drafts`、`commentary_versions`。`create` 建立 `pipeline_type=material-commentary` 的项目，项目内保存：

- `artifacts/commentary-workflow.json`：运行时和人工审核合同。
- `artifacts/commentary/evidence/`：`evidence.json`、`review.json`、`sheet.jpg`、`source.mp4`。
- `assets/audio/commentary/`：PCM 音轨及 `audio.json`。
- `assets/audio/commentary-alignments/`：绑定音轨指纹、文案和实际语音时间戳的不可变字幕记录。
- `artifacts/commentary/tts/`：报价参数、提交状态及可恢复音轨账本。
- `artifacts/commentary/versions/`：冻结 `request.json`、`result.json`、`preview.mp4`、`subtitles.srt`。
- `artifacts/commentary/cache/`：按内容签名复用的已完成段落。

完整身份保存在 JSON/数据库；目录采用签名前缀。运行媒体、数据库和账本留在忽略目录，不进入知识库或示例。

## 制作合同

### 证据与范围

素材先登记到共享库，以 `media_id` 取证，不直接把任意媒体路径塞入镜头。一个证据身份绑定媒体指纹、起止秒数及归一化裁切 `x/y/w/h`；可选 `review_revision` 用于有意重做观察，最多 80 字，默认为空并保持相同证据复用。单次精查范围为 0.1—120 秒，长源文件先用已有概览和转写定位。证据图按真实裁切生成，播放器用于检查连续动作、台词及切口。

`review` 要求实际查看声明、审核者、画面观察、前后文、可用性；台词和未知项可单独记录。`source_subtitles`、`source_music` 分别为 `none/present/unknown`。只有 `usable=true` 的证据可用于镜头。源文件或证据文件哈希变化会拒绝预检，不能沿用旧观察。

新取证和新版本只能采用未归档素材。提交时把已审核观察绑定为素材库冻结引用 `MREF`，作用域包含本模板、实际裁切和输出画幅；每个实际镜头登记对应版本的 `MUSE` 使用记录。该确认不扩大到其他裁切或旧图文模板的中央带。归档不撤销已有冻结版本：历史任务可用同一内容指纹恢复；新选材须先按素材库管理流程恢复为可用。移动原文件后通过素材库重定位同一指纹，渲染解析新路径，不手改冻结清单。

### 自由段落与声音

草稿外层为 `{title, revision, payload}`。`payload` 主要字段：

| 字段 | 约束及用途 |
|---|---|
| `version` | `material-commentary-v1` |
| `format` | `portrait` 720×1280、`landscape` 1280×720、`square` 720×720；均 30 FPS |
| `content_kind` | 自由描述题材，不触发固定故事模板 |
| `intent`、`structure` | 观众应理解什么、依据素材如何组织；提交时均必填 |
| `segments` | 自由顺序，最多 240 段；每段 1—100 镜头 |
| `target_lufs` | −16 至 −8；新项目读取当前全局偏好后持久化 |
| `music` | `null` 或已登记音乐的 `audio_id/gain_db/allow_source_music_mix` |
| `subtitle_style` | 可选项目级字幕显示样式；省略沿用旧字号和颜色 |

每段包括唯一 `id`、`purpose`、`basis`、`mode`、`shots`。镜头为 `{evidence_id,start,end,repeat_reason?}`，时间是原媒体的绝对秒数且须落在证据窗口内。调整裁切须重新取证。

| `mode` | 时钟与声音规则 |
|---|---|
| `narration` | 必填 `text`、匹配的 `audio_id`；原声静音，实际旁白音轨决定段长 |
| `original` | 使用源区间时长与原声；`text` 为空，`audio_id` 为空 |
| `mixed` | 实际旁白音轨决定段长，同时保留原声；`source_gain_db` 默认 −18，可在 −60 至 0 范围调整 |

音频标准化为 48 kHz 双声道 PCM16，每帧 1600 个样本；旁白所需帧数向上取整，不拉伸语音。镜头依次消费，最后一个有效镜头截到音轨边界，多余镜头不进入该版本。覆盖不足返回 `needs_material` 和缺少秒数。原声段按每镜头可用整帧拼接。输出最多一小时，这不是推荐视频时长。

每段字幕可用 `estimated/timed/none/aligned`；`timed` 的 `{start,end,text}` 是相对本段的秒数，依次递增且不超过段长。`estimated` 按字数估时，始终带待听辨提示。`aligned` 读取 `alignment_id` 对应的实际语音时间戳；音轨身份、指纹及完整文案须一致。腾讯生成返回的逐字元数据自动导入；其他音轨可导入有来源说明的逐字/逐词时间戳。原声段要新增字幕时必须提供逐句时间戳。文本使用纯文本且通过实际字体宽度检查。

已有字幕存在或未知时，要么关闭新字幕，要么 `subtitle_position=top` 并填写 `source_subtitle_note`。重新裁切仍需查看，不能把旧字幕当成已自动消除。保留原声且源配乐存在或未知时，新增音乐需显式设置 `allow_source_music_mix=true`；该字段表示已核对混合策略，不能代替听辨。

`subtitle_style` 可由页面“字幕字号与颜色”或 CLI/API 配置，例如：

```json
{"font_size":64,"text_color":"#FFFFFF","highlight_color":"#FFD54A","highlight_terms":["交朋友","反应"],"outline_size":3,"shadow":1,"strip_punctuation":true}
```

字号20—96、描边0—6、阴影0—4，均为整数；颜色只接受 `#RRGGBB`，强调词最多24项且每项最多30字。配置存在时补齐上例默认值（强调词默认空，去标点默认 false），保存、冻结和段落缓存均绑定该样式。省略配置不改变历史冻结或旧渲染行为；无新增字幕的原声段仍可复用缓存。预检按实际字体检查去标点后的宽度，超出画幅84%或显示为空时拒绝提交，须精简/拆句并保留实际语音时间戳。

去标点只改变烧录字幕及 SRT 显示，不修改配音文案、音轨或对齐记录；保留小数、时间、百分比及英文词内连接符。烧录字幕给完整关键词着色并恢复正文颜色；SRT 是同文字的纯文本，不承载颜色。源视频已有的硬字幕不受此设置影响，仍需单独处理。64号适合本次竖屏短句，其他画幅和长句应按预览调整。

### 精剪 V2（可选）

在 `payload.editorial` 写入 `version=2`、`candidate_media_ids`、`coverage`、`events`，启用以下检查；原 V1 草稿保持兼容。

- 候选集合最多1000条稳定素材身份。覆盖记录为 `{media_id,status,reason,evidence_ids}`；状态 `reviewed/excluded/pending`。采用素材须有匹配的已确认证据；未处理候选阻断提交，已排除素材不能进入成片。范围排除与质量淘汰分别如实说明。
- 事件卡最多500条，包含 `id/evidence_ids/summary/context/setup/action/result/tone/original_reason`，可用 `duplicate_group` 标记同类事件。段落 `event_id` 绑定该卡，视觉和独立原声证据均须属于事件。口吻和叙事顺序由观察决定。
- 旁白使用 `aligned`；`sentence_links` 每项为 `{cue_index,shot_indexes,basis}`，每句恰好一项，关联镜头须与该句实际时间相交。按真实首尾语音时间修剪两端空白，保留前60毫秒、后120毫秒，再对齐整数帧，不变速。
- 冻结后检查实际采用的源窗口。重叠超过100毫秒须写 `repeat_reason` 解释回调或对照；超过8秒的镜头只提示核对价值，完整问答或情绪段可以保留。

段落可另设 `source_audio`，每项为 `{evidence_id,start,end,offset,gain_db,fade_in,fade_out}`。源秒数独立于视觉；`offset` 相对本段开始，可提前最多2秒、延续至本段后最多2秒，必须落在成片时域及已确认源证据内。淡入/出以秒指定。显式空列表关闭该段旧原声；省略此字段沿用 V1 原声规则。最终在全片 PCM 上混合独立原声，按样本延时；其来源也冻结并登记 `audio-001` 等使用台账。

`editorial` 返回候选处置、事件、同类组、重复窗口及长镜头诊断；`compare` 读取冻结版本，比较实际时长、切点、镜头长度、原声时间并集占比、字幕方法与源 SHA 集合。这些指标用于定位变化，主观流畅度仍须审片。

### 版本与费用

保存采用 `revision` 比较更新；无改动保存不增加版本，过期版本返回冲突，不覆盖他人修改。提交将完整时间线、素材库引用及字幕字体指纹冻结成内容签名，幂等键为 `material_commentary:<project_id>:<signature>`。重复提交已冻结的同一 `revision` 恢复原签名，即使素材已归档或重定位。正式合成只走统一队列 `kind=material_commentary`；正常编辑不直接调用 renderer。

跨机恢复须能解析同一内容的源文件、音轨与字体。字体内容变化时，恢复原字体可继续原版本；有意采用新字体时，先保存包含本次修改说明的草稿（如更新 `structure` 的版式说明），获得新 `revision`，预检后再提交。仅替换字体文件后重提旧 `revision` 仍恢复旧版本；无改动保存也不会创建新版本。

导入音轨按源文件指纹、文案及用途复用。TTS 从配音中心已有 `profile_id` 报价，冻结供应商、模型、音色和语速等参数；生成必须匹配 `quote_signature`，并携带已授权的字数及费用上限。零估算不代表免费。相同成功请求返回已有音轨；`generated` 从已生成文件继续导入；`submitting/ambiguous` 停止自动重发，等待核对供应商原任务或导入已取得音轨。更换镜头、顺序不触发 TTS。

## CLI 与 HTTP

以下命令在 `Haike_video` 根目录使用项目 Python。JSON 使用 UTF-8；`<...>` 替换为读回的真实值。命令的 `--output` 等全局选项放在子命令前。开发隔离时可显式提供 `--projects-root`、`--db`、`--queue-db`；三者须指向同一测试环境，不能把测试队列连到生产项目。

```powershell
python scripts/material_commentary_cli.py list
python scripts/material_commentary_cli.py create "本次素材解说"
python scripts/material_commentary_cli.py --output "<brief.json>" brief "<project_id>"
python scripts/material_commentary_cli.py evidence "<project_id>" "<evidence-request.json>"
python scripts/material_commentary_cli.py review "<project_id>" "<evidence_id>" "<review.json>"
python scripts/material_commentary_cli.py audio-import "<project_id>" "<audio-import.json>"
python scripts/material_commentary_cli.py alignment-import "<project_id>" "<alignment-request.json>"
python scripts/material_commentary_cli.py editorial "<project_id>"
python scripts/material_commentary_cli.py compare "<project_id>" "<comparison-request.json>"
python scripts/material_commentary_cli.py save "<project_id>" "<draft.json>"
python scripts/material_commentary_cli.py preflight "<project_id>" <revision>
python scripts/material_commentary_cli.py submit "<project_id>" <revision>
python scripts/material_commentary_cli.py versions "<project_id>"
```

`evidence-request.json` 形如：

```json
{"media_id":"<素材库返回的编号>","start":120,"end":135,"crop":{"x":0,"y":0,"w":1,"h":1}}
```

`review.json` 形如以下字段集合。示例的观察、未知项和布尔值必须按实际查验改写，不能原样作为已看声明：

```json
{
  "reviewer":"<本次审核者>","viewed":true,"usable":true,
  "observation":"<实际可见内容>","context":"<已核对的前后文>",
  "transcript":"<实际听辨台词，未听辨留空>","unknowns":"<尚未确认的内容>",
  "audio_reviewed":false,"source_subtitles":"unknown","source_music":"unknown"
}
```

`audio-import.json` 为 `{path,text,kind,provenance}`；`kind` 为 `narration` 或 `music`，音乐允许空 `text`。`draft.json` 使用 `brief` 返回的 `draft` 对象或页面“导出当前编辑清单”，修改其 `payload` 并保留读回的 `revision`；不能将整个 `brief` 响应当作保存请求。

`alignment-request.json` 为 `{audio_id,words:[{text,start,end}],provenance}`，时间相对完整导入音轨；或 `{audio_id,tencent_metadata_path}`，读取现有腾讯逐字元数据，不调用供应商。`comparison-request.json` 为 `{baseline_project_id,baseline_signature?,target_signature?}`；省略签名时取项目最新冻结版本，不要求同源，但返回 `same_source_pool` 供判断是否可比。

需新配音时先执行 `quote <project_id> <quote-request.json>`，输入 `{text,profile_id}`。核对返回参数及本次授权，再执行 `tts <project_id> <tts-request.json>`；后者包含相同文本和音色，以及 `quote_signature`、`confirmed=true`、`max_characters`、`max_estimated_cost_usd`。程序仅做单次上限校验，操作者仍须核对项目及当日总预算。

CLI 退出码：`0` 成功；`2` 素材覆盖不足；`3` 草稿/冻结记录/TTS 确认冲突；`1` 其余校验或文件错误。`evidence` 写本地取证文件，`audio-import` 转换并登记音轨，`submit` 冻结并入队；`quote` 不调用生成，`preflight` 不渲染或入队。它们没有统一的 `--dry-run` 选项。

HTTP 根路径为 `/api/material-commentaries`：

| 操作 | 方法与相对路径 |
|---|---|
| 列表、创建 | `GET /`、`POST /`，创建体 `{title}` |
| 读取全部制作上下文、保存草稿 | `GET /{id}`、`PUT /{id}` |
| 取证、提交观察 | `POST /{id}/evidence`、`POST /{id}/evidence/{evidence_id}/review` |
| 读证据图/片段 | `GET /{id}/evidence/{evidence_id}/sheet.jpg` 或 `source.mp4` |
| 导入、报价、生成配音 | `POST /{id}/audio/import`、`audio/quote`、`audio/generate` |
| 字幕对齐、事件审计、冻结版本比较 | `POST /{id}/audio/alignment`、`GET /{id}/editorial`、`POST /{id}/compare` |
| 播放已登记音轨 | `GET /{id}/audio/{audio_id}/media` |
| 预检、提交统一队列 | `POST /{id}/preflight`、`POST /{id}/render`，请求体 `{revision}` |
| 读取待审成片/字幕 | `GET /{id}/versions/{signature}/preview.mp4` 或 `subtitles.srt` |

`GET /{id}` 返回草稿、观察、音轨、版本及关联队列状态；素材不足需读取响应中的 `status`，不能只看 HTTP 200。过期草稿/确认冲突为 409，其余受控校验错误为 422。

## 验收与已知范围

技术完成需通过：源与音轨指纹、帧数、帧率、画幅、H.264/AAC、yuv420p、48 kHz 双声道、时长、音画差、全片解码及现有响度验收。结果为 `status=completed`、`qa.status=passed`、`review_status=pending_review`；没有自动发布或自动人工认可步骤。

本轮模板专项共 41 项通过：[核心 25 项](../tests/backlot/test_material_commentary.py)、[素材库桥接 15 项](../tests/backlot/test_commentary_library_bridge.py)、[贯穿流程 1 项](../tests/backlot/test_commentary_library_integration.py)。连同统一队列和 server 的测试组合共 94 项通过，另有素材引用/管理 56 项回归通过。覆盖自由编排、CAS、证据篡改、配音时钟、素材缺口、旧字幕、CLI/API、TTS 防重发、归档/重定位、真实 FFmpeg/统一队列渲染、局部缓存复用、失败恢复和 HTTP 视频 Range。电影式倒叙、直播问答、多镜头演示的媒体是程序生成的移动图案/音频夹具；它们验证编排与媒体合同，不是现实电影和直播内容的语义验收。

10-03真实现场 V1 基线保留41.7秒冻结版本，技术、代表帧及浏览器完整播放已验，估时字幕和听感待人工；详细结果见 [V1测试记录](development/2026-10-03-素材解说模板V1-开发与测试.md)。10-08增加精剪 V2，并以同源现场互动切片与《世界纪录》动漫短片验收；结果见 [八项优化与双题材验收](development/2026-10-08-素材解说八项优化与双题材验收.md)。随后直播 V3 放大/去标点/强调字幕并减少两处跳切，65项相关回归及实片技术、代表帧、播放通过；见[直播V3验收](development/2026-10-08-直播二剪V3字幕与连续镜头验收.md)，听辨仍待人工。

证据观察为不可变记录，相同素材/区间/裁切及复核版本会复用同一证据。需要纠错时，在取证请求中指定新的 `review_revision`，重新查看并登记观察，再将草稿镜头改为新证据 ID。旧证据和已冻结版本保留；不用手工改 JSON、删除旧记录或微调时间码绕过冻结。

首版采用等比缩放留边与硬切；提供三种画幅，不含自动追焦、自动动画或特效场景。修改渲染器、队列、音频冻结、证据身份、字幕规则或来源解析后，应重跑相关测试并重新验收受影响实片。

## 段落级可选数字人

素材解说仍是第三种通用模板。数字人是可选出镜层，不规定开头长度、段落数量或故事结构。原片保留主画面；旁白或混合段可出镜，原声段不绑定出镜。每个出镜资产绑定实际 `audio_id`、音频 SHA 和文案 SHA；文案或配音更换后不能沿用不匹配的嘴型。

`presenter-import` 输入 `{path,audio_id,name,provenance}`，登记已有 MP4。`presenter-quote` 输入 `{audio_id,role_id,budget_limit_cny,prior_cost_cny,max_runtime_seconds?}`；`prior_cost_cny` 是本轮累计已用或预留的配音费用，其他出镜任务的已用或预留费用由程序叠加。当前短片生成上限 5 元，默认 900 秒等待上限，按 Plus 48GB 6 元/小时预留并加 120 秒查询/取消余量；全账户当天其他流程的开销仍须操作者核对。`presenter-submit` 增加 `quote_signature` 与 `confirmed=true`，冻结后进入统一队列 `commentary_presenter`。`presenter-status <project> <generation_id>` 读取状态，不发起新任务。上述导入、报价、生成、状态对应 HTTP `POST /{id}/presenters/import|quote|generate`、`GET /{id}/presenters/jobs/{generation_id}`。

生成使用现有角色库正面图、RunningHub 工作流 `2094449979141218305`、配置档 `infinitetalk_448x560_exact_clock_v2`、Plus 48GB。最终 PCM16 单声道 48 kHz 驱动按 25FPS 对齐并提交整数帧；一份配音只生成一次对应嘴型。身份不含预算字段，更改预算不会重复生成同一输入。提交失联或取消结果未确认标为 `ambiguous`；查询/下载/本地导入恢复使用原任务，已完成资产保留。预算入场以项目 SQLite 短事务跨进程序列化。供应商少尾帧时，仅允许不超过 5 帧且对应驱动 PCM 全部为数字零；登记实际原视频并记录差异，不补帧。缺失语音、错误帧率、超出实际出镜覆盖的段落均阻止使用。

段落可增加 `presenter: {asset_id,x,y,diameter,layout_review,crop?}`。`x/y` 为圆形左上角占画面宽/高比例，`diameter` 为画面宽度比例；`crop` 为 `{x,y,w,h}` 的归一化素材裁切。位置、裁切、素材指纹和实际语音窗口全部冻结并进入本段缓存键；出镜自身音轨不混入成片。未启用下述自动布局时，`layout_review` 说明人物和主体避让，预检仅检查边界与字幕重叠。

需要避让时设置 `subtitle_layout: {x,y,max_width}`，表示字幕中心横坐标、基线纵坐标和最大宽度比例。保持字号，重叠或越界时返回校验错误，不静默缩字。字幕对齐请求可附 `cue_word_ends`（递增单元终点，覆盖所有逐字/逐词），按实际语音时间戳组成短意群。旧项目未启用这些字段时保留原行为与缓存规则。

实片与测试证据见 [开头 A/B 验收](development/2026-10-08-直播开头对照与可选雅雅出镜验收.md)。部署新增队列类型前须使执行器加载当前代码；共享同一队列的旧服务会抢到新类型并因没有注册执行器失败，不应据此重复云端付费。

## 素材空间判断与自动布局

2026-10-09 增加 `backlot/commentary_layout.py`。制作助手依据本地图片理解素材，程序自动编排数字人与新增字幕；当前没有独立的人脸/动作/OCR 语义检测器，也不自动调用付费视觉模型。启用 `presenter_layout: {mode:"auto",protection_ids:[LP-…],locks:[]}` 后，先尝试右上或左上并保持原直径（已认可样式为画面宽35%）；两侧占用、判断不确定、时间未完整覆盖或大字与出镜无法共同避让时隐藏出镜、保留声音并给出待审原因。边界检查保守使用圆框外接矩形。

空间任务与保护记录都不可变。CLI `layout-prepare <project> request.json` 请求 `{evidence_id,start,end,model?,revision?}`；单次最多30秒，按约4FPS采样整个采用窗口，保存带时间码原图及多宫格。`layout-task <project> LT-…` 读回任务和校验后的本地图片。实际查看全部帧后，`layout-protection <project> submission.json` 提交 `task_id/task_fingerprint`、完整 `reviewed_frame_ids`、`coverage=complete|uncertain`、`regions`、`cuts` 与判断依据。每个区域为 `{kind:person|action|subject|source_subtitle,label,box:{x,y,w,h},start,end}`；坐标归一到已裁切源图，不包含成片补边。保护相关脸部、关键手部动作、核心物体及原字幕，记录整个时间窗中的移动范围；只把确认的实际换镜时间写入 `cuts`。未检查、看不清、切点不确定时保留不确定性。

`layout-apply <project> request.json` 输入当前 `{revision}`，自动选择最新匹配的保护记录，保留锁定并保存。返回 `draft/layouts/warnings/pending_tasks`。缺少记录时准备本地任务并隐藏出镜；制作助手完成理解后再应用。仅有不完整或不确定记录时，依据返回原因重新准备需补查的窗口。源 SHA、裁切、实际采用时间窗、任务指纹和图片字节均参与核对。相同参数复用任务；更正空间判断提交新记录，旧记录及成片保留。

编译器把保护区域映射到实际缩放和居中补边后的输出坐标，并加4px余量。同一个连续镜头综合人物移动区域选位，位置保持稳定；同一源文件、裁切与连续时间的编辑条目也合并空间判断，不把拆条目当作换镜。`cuts` 才能把连续源拆成可换位窗口，切点对齐30FPS帧网格。新增字幕以真实字体宽度和原字号共同避让，不缩字。找不到完全安全字幕位置时保留可读位置并明确提示人工检查，长度无法容纳时要求按真实语音拆短。源烧录字幕仅作为避让区域，保持原像素。渲染层字幕可在确认切点拆分，导出SRT保留原语音意群与时钟。

锁定项为 `{shot_index,cut_index?,position:left|right|hidden}`，保存时绑定镜头指纹；省略 `cut_index` 作用于整个源镜头，并沿用到其连续编辑条目。自动应用尊重锁定，有遮挡或判断不足时警告；连续条目存在不同手动锁定时保留选择并提示统一。锁定素材/源区间改动或目标换镜窗口失效时要求解除并重新检查。编辑页展示各镜头选位理由、实际字幕位置和锁定选项，修改后重新预检。

公开HTTP入口为 `POST /{id}/layout/prepare|protection|apply`、`GET /{id}/layout/tasks/{LT}`、`GET /{id}/layout/tasks/{LT}/media/{name}` 和 `GET /{id}/layout/plan`，均在 `/api/material-commentaries` 下。冻结版本包含 `layout_plan/render_cues`，仅启用的段落增加缓存字段；旧项目不启用时行为与缓存不变。正式合成仍经统一队列。相关回归及当前直播开头D版的实片边界见[自动避让验收](development/2026-10-09-素材解说出镜自动避让验收.md)。
