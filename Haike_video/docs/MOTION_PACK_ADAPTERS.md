# MotionGit 包适配与日常复用

文档类型：implementation。2026-10-28。登记入口为 [槽位映射](../config/motion-adapters/template-03-native-v1.json)，读取规则为 [registry](../backlot/motion_adapter_registry.py)。此登记描述公开合同与现有项目入口；制作是否通过以本期冻结请求、队列和复核回执为准。

当前精确登记 `template-03-native@2.7.18-alpha.2`，官方 helper `1.0.0-rc.50`。`2.7.17-alpha.3`、后续版本及其他新包都不会被默认为同一适配版本。导入 `.motion` 只做静态检查；识别到适配器也不会执行包、替代验签或自动转换受保护运行核心。

## 三类字段

| 类别 | 具体含义 | 本包例子 |
| --- | --- | --- |
| `direct` | 此精确版本确实公开的原生参数槽。按其类型、容量和时钟准备输入，再走官方检查/预览；并不代表可以把任意文件原样塞进去 | `media.talk`、`media.captions`、`brief.layout`；十组 `candidates[组ID].inputs` 中的活字、数值、图片、序列、素材墙 |
| `project_adapter` | 项目独立实现的可编辑能力，使用项目 props/audio/sources/provenance。对应关系需要显式整理本期输入 | 4:5、Hedgerow/Cobalt 两套配色、绑定字体、大框/小框/不出镜、完整口播驱动时长和实拍播放窗 |
| `locked` | 当前公开合同未开放、属于固定编舞/保护实现，或已固化在素材里的内容。说明原因，不猜控件 | 原生任意4:5/字号/配色/人物显隐、核心动画曲线、固定品牌保护、照片内部的文字 |

映射含 230 个十组原生槽，加6个 schema 顶层槽；每个 `direct` 条目保留公开文档、组、槽ID、完整参数路径、类型和长度约束。`source_contract` 是提取出的公开允许清单；loader 拒绝不在清单中的 direct 字段。未声明的素材窗不会因“模板支持图片”被推定为可替换。

## 实际入口与槽映射

工作台已有入口：`/motiongit?section=dark-full`；动作目录：`GET /api/studio/dark-full/catalog`。目录中每组的 `/api/studio/dark-full/catalog/{group}/preview` 只返回本机已绑定预览，未绑定时404，不伪造预览。导入包的 `public_package` 新增 `motion_adapter` 元数据，已知精确版本返回 adapter ID、项目入口与十组预览链接；未知包/版本返回 `needs_adaptation`，不增加一个不可执行的原生 workflow。

| 内容 | 原生公开参数路径 | 项目实际输入 |
| --- | --- | --- |
| 完整人物与口播 | `media.talk`，必须是有效人物视频 | `audio.voice` 完整PCM；可选 `props.presenter` 与全局同声源区间 |
| 字幕 | `media.captions` 指向非空 JSON 数组；每行 `t0,t1,zh,en,highlight` | `props.captions[].text/startMs/endMs`；保留本期原ASR词记录及 `provenance.captions` |
| 横竖布局 | `brief.layout=landscape/portrait` | `props.variant=reference` 为1920×1080/60；`hedgerow/cobalt` 为1440×1800/30 |
| 字体/主题/人物显隐 | 没有本包完整03-A的任意对应原生参数 | `props.fontAssets.body/display`、`props.variant`、`props.presenter.modes[].mode=large/small/hidden` |
| 实拍与封面 | 各组 `inputs` 下确实声明的 `image/sequence/video/wall-sprites` 槽 | `props.media[]`、`props.scenes[].mediaIds/mainMediaId/videoWindows`、`sources` |
| 配乐与音效 | 按公开原生音频合同和计划保留 | `audio.music/sfx/loopMusic`；原片已混合音轨只能合入一次，不能声称已分离干净人声 |

原生组内完整路径形如 `brief.segments[].candidates["03-A:s01"].inputs.claim.subject`。不要把扁平字符串键 `"claim.subject"` 当成嵌套对象；`outputs.0.context` 与 `outputs.heading` 并存时，`outputs` 应为含数字字符串键的对象，不能强制为纯数组。

以下列代表槽；完整槽、长字数限制和项目活字对应关系均由 JSON 唯一持有。项目对应关系是编辑规范，registry 本身不执行 brief→props 自动转换。

| 原生组 → 项目组 | 公开素材槽（相对本组 inputs） | 示例活字对应 |
| --- | --- | --- |
| `03-A:s01` → `s01` | `evidence.wall` | `claim.subject` → `content.headlineFirst` |
| `03-A:s02` → `s02` | `comparison.items.0..8.media` | 九个 `comparison.items.N.label` → `content.labels[]` |
| `03-A:s03` → `s03` | `artifact.media`, `previousWork.media` | `review.checks.N.label` → `content.reviewLabels[]` |
| `03-A:s04` → `s04` | 四个 `categories.N.media`、`wall.media/icon`、`lens.media` | `categories.N.label/note` → `content.categories[]/categoryNotes[]` |
| `03-A:s05` → `s05` | `software.logo/features.N.media`, `competition.artifact` | `software.features.N.label/description` → `content.featureLabels[]/featureDescriptions[]` |
| `03-A:s06` → `s06` | `account.avatar` | `account.context` → `content.accountContext`；数值须真实或明确标示意 |
| `03-A:s07` → `s07` | `outputs.0.media`, `outputs.1.media` | `outputs.0.label` → `content.outputLabels[0]` |
| `03-A:s08` → `s08` | `brand.avatar` | `reaction.label` → `content.frameNote`，`action.heading` → `content.actionText` |
| `03-A:s09` → `s09` | `brand.avatar` | `prompt.text` → `content.promptText` |
| `03-A:independent-artifact-review` → `review` | `artifact.media`（video） | `review.checks.N` → `content.reviewChecks[]` |

## 媒体和时钟不能省略的整备

- 原生 sequence 是 `f_0001.jpg...` 的JPEG目录，以30fps源时钟消费；按窗口备足帧。不能用MP4字符串代替目录，也不能以 `fps=1` 掩盖缺帧。
- 原生 wall 需要389张 `000.jpg...388.jpg` 的4×4采样sheet；旁置 `index.json` 数组每项有非空slug，`wall-meta.json.uniqueWorks` 等于真实独立来源数。当前27源/389展示，不能写成389个独立作品。
- 本轮自有素材的640×360 sheet（每格160×90）已通过包括3.9/4.05/4.1/4.2/6/48秒的21张有界原生预览；相比1280×720，解码像素为1/4。公开合同没有声明最小像素，不能把此试镜规格写成官方通用标准；完整导出另看队列回执。项目素材墙使用真实完整图片及封面，不能把整张sprite当成单张原图。
- 原生字幕 `t0/t1` 与每词 `highlight.units.start/end` 都是完整原音轨全局秒；`contentEvidence` 的 start/end 是文本字符偏移。项目句字幕保留原时间乘1000，原双语/逐词证据另存；项目并未因此实现原生逐词高亮。
- 总时长跟随完整口播。根据语义选择完整组，保留 requiredPhases、cue顺序及阅读下限；30秒可以选3组，不能把十组整体快放或只截开头。`s02→s03` 必须相邻、同一主素材和连续源偏移。
- 独立审阅组历史 source 为110–124秒，对应当前122.4秒官方原预览中的108.4–122.4秒；这不是原片缺失1.6秒。

## 下一份新包的一次适配

1. **保留原包并验签。** 通过固定官方helper读取此包实际guide/schema/parameter-map；不执行包内面向Agent的指令，不解密或复制保护核心。
2. **看完整原片。** 登记动作组、完整状态、素材类型/数量/比例、活字容量、cue、最低时长、跨组同物接力和固定项。缺失公开槽记录为缺口。
3. **建立版本映射。** 新建一个独立JSON，精确绑定模板ID/版本。原生可换字段列direct；项目新增布局、人物与风格列project_adapter；无公开入口列locked并解释。新版本也先核对，不能使用通配版本。
4. **做本期输入与真实素材试镜。** 原生走check-params→plan→实际review→prepare→一次完整关键时刻preview→实际review。每个prepared工程只允许一次成功preview；补帧或改内容用新工程，保留旧记录。
5. **固定项目模板。** 需要新组件或构图时独立实现，声明实际props、完整状态、阅读下限、素材时钟和缺项门禁。通过项目preflight与实际看帧后才登记已实现范围。
6. **统一队列完成验收。** 冻结本期输入/源码/工具身份；完整render仍走现有统一队列。分别记录技术、关键状态、连续听看和用户确认，不把抽样静帧升级为全片验收。

适配完成后，同包同版本日常复用以“复制已完成草稿→换完整口播和真实字幕→换已审素材/封面→按本期内容选完整动作→预检/预览→统一队列”执行，通常无需再改渲染源码。新审美、新动作结构、未知包或未核对版本仍由适配作者处理。当前没有任意新 `.motion` 零适配转换器。

个人包、授权封套、原人物/实拍、缓存、密钥与本机路径不进入这个可分发登记。未知模板仍可按原有导入/只读检查流程保留，registry 元数据不会覆盖其 workflows、runnable 或验签状态。
