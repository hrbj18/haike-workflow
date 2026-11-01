# 动效模板库：61 个开源项目适配分析

核验日期：2026-11-01。目标是把参考片的动作语言、已有 `.motion` 工程和自己的口播素材，沉淀为海客项目里可编辑、可重排、可横竖屏制作的模板库。评分只衡量对这个目标的帮助；不按明星数、模型宣传或项目体积排名。

**不需要完整搬入 Hypit，才能做好前三条口播模板。** 更合适的办法是学习它“先看整片—看不清的局部再看—记录对象如何连续变化—回看成片”的方法，把成果接到现有 ASR、Remotion、素材、数字人和统一队列上。就像学一家餐馆的菜谱和验菜方法，不必连厨房、收银台和外卖系统都搬回来。Hypit 的生成媒体、凭据、SVML/SVS/SVRun 和 Runtime 是另一套完整系统；这不是当前模板库必须承担的前提。[Hypit制作说明](https://github.com/hypit-ai/hypit/blob/main/skills/hypit/SKILL.md)

## 证据与计数

本次在生产端 `docs` 和本任务目录的 Markdown/JSON 中做了有界查找，没有找到此前对话所述“60 个已核验、9 个受限”的逐项原报告；仅找到了制作方向中的项目引用。因此，**这份是重新补做的一手核验，不宣称恢复了旧报告，也不沿用旧的数量结论。**

下表包含 **61 个不同的开源代码仓库**，每个均实际取得 GitHub 官方仓库元数据及第一方 README，并阅读了与表中能力有关的说明。代码许可证采用仓库 SPDX 元数据；GitHub 无法自动判定的 FFmpeg、SVG.js、Tween.js、Konva、MuseTalk、SadTalker另依据第一方 README/LICENSE。部分项目的字体、示范片、模型权重和服务另有条款，代码开源不等于这些材料全部可再分发。另列 **11 个已访问但有商业条款、许可不明或仅为入口的项目**，不凑入61个开源项目计数。没有把同仓库多个 skill、多个画幅或模板变体重复计数。

这是**文档与仓库元数据核验**，不是61套运行验收、源码安全审计或同机性能比赛。所有分数、可借用方式与缺口均为结合本项目的主观工程判断。README中的效果、速度、数量属于上游声明，不能当作海客已实测。可复核的仓库身份、README Git blob SHA、SHA256、大小、采集时间及评分见[证据索引](MOTION_TEMPLATE_FIT_20261101.evidence.json)。原始互联网获取文件仅放系统临时目录，不加入仓库；索引不含凭据、私有素材或完整上游文章。

仓库更名只计一次：`redotvideo/revideo` 的 GitHub API 当前返回 `midrender/revideo`；`QwenLM/Qwen2.5-VL` 返回 `QwenLM/Qwen3-VL`；`FunAudioLLM/SenseVoice` 返回 `QwenAudio/SenseVoice`；`designcombo/react-video-editor` 返回 `openvideodev/react-video-editor`。Snapcn当前访问身份是 `shadcn-labs/snapcn`，README中还保留 `snapcndev/snapcn` 的命令，使用前应核对具体版本，不盲跟别名。

## 怎么评分

| 权重 | 只针对海客目标的问题 |
|---|---|
| 30 | 能否保留对象持续状态、动作顺序、转场接力和节奏，而非只拼静态版式？ |
| 25 | 能否沉淀为有参数、素材槽、容量限制和版本的自有模板？ |
| 15 | 能否使用自己的声音、数字人、实拍及真实语义时钟？ |
| 10 | 能否支持横竖屏重新布局，而非整体裁一刀？ |
| 15 | 与现有 Windows、Remotion、统一队列、审核及恢复的接入成本是否合理？ |
| 5 | 公开能力和许可证是否清楚，是否便于维护与交付？ |

总分100。工具只解决一小层仍可能很有价值；低分不代表它本身差。例如 ASR 不提供模板编舞，3D引擎不提供口播生产协议，所以不会因为技术强就排在最前。明星数仅用于确认冷门与热门均有覆盖：本次样本包含十万星级通用库，也包含0—30星的流程和组件项目；明星数未进入分数。

## 61 个开源项目

“可借用”不表示已集成；“缺口”指不能据此直接承诺本项目需求。每行仓库链接均是一手来源入口，精确README地址和采集摘要在证据索引。

### 模板、参考复刻与制作方法

| # | 项目／一手来源 | 适配分 | 可借用的具体能力 | 对本项目的主要缺口 | 代码许可 |
|---|---|---:|---|---|---|
| 1 | [adunext/adu-motion-video](https://github.com/adunext/adu-motion-video) | 94 | 已有口播/知识动画，强调完整镜头组、可编辑工程、横竖各自布局与 `.motion` 包内制作入口。适合原生合同接入。 | 不同包公开的控件、人物/照片槽和执行协议不同；仓库MIT不能代替个人包和素材授权。 | MIT |
| 2 | [degueba/onda](https://github.com/degueba/onda) | 93 | Remotion组件以TSX、Zod schema、说明一起落到项目，统一弹簧、时长和错峰参数。最适合扩充现有组件库。 | 组件不是完整口播模板；需要自己的叙事、中文字体、布局容量及队列封装。 | MIT |
| 3 | [lovisdotio/motion2code](https://github.com/lovisdotio/motion2code) | 91 | 参考采样、变化点补帧、单一seek时钟、逐帧并排对照与确定性检查。直接补强“没看清就回看”。 | 默认SVG/GSAP和循环短片，不是数字人口播工程；自己的文案改变后不能照搬同秒像素差结论。 | MIT |
| 4 | [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | 90 | 导演规则、技术规则、STYLE分开；支持把风格改造后保存为自己的长期风格。 | 多种Canvas/WebGL代码路线依赖生成模型的实现质量；风格卡不自动变成稳定的可填表模板。演示片另有署名/配音例外。 | MIT（代码文档） |
| 5 | [alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion) | 89 | 解说语法、参数化片段、运动热图、长文/竖屏压力检查及反PPT门禁；很适合“关系怎么动”的积累。 | 另一套Canvas/Python生产引擎；生成角色帧不等于侯总数字人。应取语法与验收思想，按现有时钟适配。 | MIT |
| 6 | [shadcn-labs/snapcn](https://github.com/shadcn-labs/snapcn) | 87 | 可复制到本项目的Remotion文字、设备窗、字幕等组件；明确帧时钟和组件时长，讨论实际文字抖动。 | 部件需要组合成中文口播；免费代码与其他付费组件边界须逐项检查。别名命令需核对。 | MIT |
| 7 | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 85 | HTML确定性视频合同、可编辑组件注册表、lint—预览—渲染工作流，能提供大量动作与布局参考。 | 整体引入将增加第二套渲染/编辑体系；先借动作实现和合同设计，避免为了组件重做现有生产线。 | Apache-2.0 |
| 8 | [Hihnala/framesmith](https://github.com/Hihnala/framesmith) | 82 | 品牌规范先行、分镜先行、真实素材口播处理与逐阶段记录；把技术工具与导演判断分开。 | 基于HyperFrames，部分语音功能依赖外部服务；自身不保证任意参考片的动作一比一重建。 | MIT |
| 9 | [Vincentwei1021/mg-styles-15](https://github.com/Vincentwei1021/mg-styles-15) | 81 | 15种风格的成片、完整画面代码、cues和音频脚本，可拆出动作与声音编排实例。 | 作者也说明同提示词不会得到同片；字体不随仓库、3D路线需Blender，不是统一schema即插即用。 | MIT |
| 10 | [openfilm/openfilm](https://github.com/openfilm/openfilm) | 78 | 开放HTML时间轴、画面页与媒体轨分离、可编辑Studio与命令行，音画可分别导出。 | 是可替代的整套生产系统；迁移当前模板、恢复和UI成本高，应优先研究格式而非换引擎。 | MIT |
| 11 | [iart-ai/motion-design-skills](https://github.com/iart-ai/motion-design-skills) | 76 | 时序、字体、色彩、构图、艺术指导与Remotion规则分模块，适合补充模板创作检查表。 | 主要是指导性skill；稳定模板代码、素材绑定、口播时钟和生产恢复仍需本项目实现。 | MIT |
| 12 | [Yari-tuber/mv-director](https://github.com/Yari-tuber/mv-director) | 74 | 将歌词意义、逐字对齐、节拍表和画面兑现关联，明确不能平均点亮歌词。 | 目标是音乐MV，新增分轨/对齐模型依赖较重；口播应由真实ASR时钟主导，不能强压到乐拍。 | MIT |
| 13 | [chrischabot/product-demo-skill](https://github.com/chrischabot/product-demo-skill) | 74 | 用真实应用取证、故事与画面对应、Remotion确定性适配；强调竖屏需要独立构图和复核。 | 产品演示强于人物讲解；引用的外部动作配方有独立再分发限制，不能全库当MIT搬入。 | MIT（本仓库） |
| 14 | [pompeii-labs/product-launch-video-workbench](https://github.com/pompeii-labs/product-launch-video-workbench) | 72 | manifest记录每拍意义/文案来源，布局探针和渲染像素验证可读性；可学习“声明必须在画面兑现”。 | Docker/既定演示环境、默认静音发布片；当前队列、声音、数字人及Windows便携流程不在其范围。 | MIT |
| 15 | [madebysaira/RemotionPlaybook](https://github.com/madebysaira/RemotionPlaybook) | 71 | 分场、宫格、场景规格、执行与评分步骤分开，适合作为参考复刻的交接材料。 | 文档有特定模型能力的强宣传，未作为事实采信；不是自动模板库，也不替代实际成片检查。 | MIT |
| 16 | [guigulaoshi/music-video-director-skill](https://github.com/guigulaoshi/music-video-director-skill) | 70 | 可编辑EDL与素材场景/节拍分析分离，重复镜头校验，改剪辑可不重做全部分析。 | 主要剪现成素材，不能提供参考口播所需的矢量编舞和统一可编辑模板。 | MIT |

### 渲染、媒体合成与编辑工程

| # | 项目／一手来源 | 适配分 | 可借用的具体能力 | 对本项目的主要缺口 | 代码许可 |
|---|---|---:|---|---|---|
| 17 | [motion-canvas/motion-canvas](https://github.com/motion-canvas/motion-canvas) | 74 | TypeScript生成器编排与编辑预览，适合学习持续对象、图解与事件顺序。 | 不是现有Remotion组件；需重做媒体、字幕、队列和发布合同，不能直接导入 `.motion`。 | MIT |
| 18 | [midrender/revideo](https://github.com/midrender/revideo) | 76 | TypeScript场景、无头渲染API和服务器入口，可参考任务与媒体层的分工。 | 属于另一引擎；本次只核验公开README，没有证明任意旧Motion Canvas/Remotion工程可无损迁移。 | MIT |
| 19 | [mifi/editly](https://github.com/mifi/editly) | 68 | 声画分层JSON剪辑规格、转场、动态Canvas叠加，适合简单素材片与声明式时间线设计。 | 复杂持续对象、文字细节、交互控件和中文布局仍要手写；并非高保真参考复刻器。 | MIT |
| 20 | [Zulko/moviepy](https://github.com/Zulko/moviepy) | 64 | Python裁切、合成、字幕和自定义像素效果，适合离线辅助预处理。 | 复杂MG排版与浏览器组件复用较弱，v1/v2有断代，不能为了辅助功能再开完整生产分支。 | MIT |
| 21 | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | 86 | 抽帧、真实PTS、音频处理、编码和完整解码，是参考取证与交付检查的基础。 | 不理解动作语义，不提供模板schema或导演判断；保留现有受测工具链即可。 | LGPL/GPL，取决于构建 |
| 22 | [OpenCut-app/OpenCut](https://github.com/OpenCut-app/OpenCut) | 63 | 开源视频编辑器及无头/批处理方向，可研究媒体和时间线的产品组织。 | 完整编辑器体量大；README状态不等于本机模板、跨平台和自动化已稳定。 | MIT |
| 23 | [OpenShot/libopenshot](https://github.com/OpenShot/libopenshot) | 53 | 跨平台时间线、关键帧、音画处理与Python绑定，适合研究本地合成职责。 | 引入C++/Qt等构建负担，难直接复用现有React模板，不是现成参考理解能力。 | LGPL-3.0-or-later |
| 24 | [mltframework/mlt](https://github.com/mltframework/mlt) | 52 | 成熟媒体生产者、过滤器和剪辑框架，适合参考时间线/效果分层。 | 底层框架不提供中文口播模板；Windows交付及与现有栈衔接成本高。 | LGPL-2.1 |
| 25 | [olive-editor/olive](https://github.com/olive-editor/olive) | 43 | 跨平台非线性编辑器，可参考参数编辑和合成组织。 | 面向通用剪辑，接入成本远大于本次模板库缺口；并无已核验的 `.motion` 生产适配。 | GPL-3.0 |
| 26 | [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | 51 | 快速无损挑选素材、保留来源时间，适合前期筛选和大文件粗剪。 | 关键帧边界与无损剪辑不能替代逐帧MG合成，不应充当模板引擎。 | GPL-2.0 |

### 可沉淀的动画、图形与交互部件

| # | 项目／一手来源 | 适配分 | 可借用的具体能力 | 对本项目的主要缺口 | 代码许可 |
|---|---|---:|---|---|---|
| 27 | [airbnb/lottie-web](https://github.com/airbnb/lottie-web) | 70 | 把已制作的矢量动画作为可seek的装饰/解释部件复用。 | AE导出特性与渲染支持有限；换长中文、换照片和全片重排不能只改播放器参数。 | MIT |
| 28 | [LottieFiles/dotlottie-web](https://github.com/LottieFiles/dotlottie-web) | 72 | 压缩动画包、主题/slots、布局、分段与状态机，可参考“可替换内容与动作封装”。 | `.lottie` 与 `.motion` 不同；复杂模板排版、声音和数字人仍需外部合同。 | MIT |
| 29 | [rive-app/rive-runtime](https://github.com/rive-app/rive-runtime) | 64 | 矢量状态机和交互对象，适合复用进度条、通关提示和游戏化状态。 | 原始设计文件及编辑工具另论；需确定性驱动，不能把交互播放时间直接当成视频帧时钟。 | MIT |
| 30 | [juliangarnier/anime](https://github.com/juliangarnier/anime) | 65 | 轻量动画与时间线，适合借用参数化错峰、路径和文字动作。 | 动画库本身没有媒体、字幕、模板资产或完整制作恢复，需要帧时钟适配。 | MIT |
| 31 | [motiondivision/motion](https://github.com/motiondivision/motion) | 63 | React布局过渡、弹簧与手势，可改善模板编辑器和借鉴对象变形。 | 默认交互/浏览器生命周期不等于可乱序渲染的纯帧函数。 | MIT |
| 32 | [pmndrs/react-spring](https://github.com/pmndrs/react-spring) | 58 | 弹簧物理和可复用动画参数，可用于编辑器预览或动作设计。 | 用实时状态推进容易与离线确定性渲染冲突；现有Remotion弹簧已覆盖不少用途。 | MIT |
| 33 | [theatre-js/theatre](https://github.com/theatre-js/theatre) | 69 | 可视化时间线与参数曲线，适合研究如何让专业动作可人工细调。 | Studio与Core许可不同；新增完整编辑器和状态恢复成本较高，不能直接替换现有队列。 | Core Apache-2.0；Studio AGPL-3.0 |
| 34 | [tweenjs/tween.js](https://github.com/tweenjs/tween.js) | 56 | 外部时间驱动的插值和缓动，适合纯时间函数封装。 | 仅底层插值，没有可交付镜头或模板参数界面。 | MIT |
| 35 | [mojs/mojs](https://github.com/mojs/mojs) | 62 | burst、形状、旋涡与错峰，可借用强调词/通关爆点设计。 | 容易只增加装饰；仍需语义事件、单一时钟及确定性渲染。 | MIT |
| 36 | [svgdotjs/svg.js](https://github.com/svgdotjs/svg.js) | 60 | 程序化矢量对象与路径，可辅助连线、标注和白板构造。 | 不是视频引擎，没有媒体、声音及模板编辑合同。 | MIT |
| 37 | [d3/d3](https://github.com/d3/d3) | 67 | 数据绑定、比例尺、图形和对象身份，适合排名、关系图与持续数据对象。 | 浏览器transition需转为帧函数；真实数据来源和排版容量要另验，不能复制参考数值。 | ISC |
| 38 | [konvajs/konva](https://github.com/konvajs/konva) | 68 | 场景图、变换、拖放与导出，适合模板可视化调位、素材窗编辑。 | 不是现成视频时间线；Polotno是另一个商业SDK，不能把其模板/能力当Konva开源附送。 | MIT |
| 39 | [fabricjs/fabric.js](https://github.com/fabricjs/fabric.js) | 66 | Canvas对象、文本、控件和序列化，有利于编辑器参数与对象模型设计。 | 文本/滤镜与现有Remotion需建立一致性；无参考片理解或全片声音生产。 | MIT |
| 40 | [pixijs/pixijs](https://github.com/pixijs/pixijs) | 58 | 高效2D场景与特效，适合复杂粒子/大量对象的局部动作。 | 是图形底座；确定性、字幕、素材时钟和编辑能力仍由本项目负责。 | MIT |
| 41 | [mrdoob/three.js](https://github.com/mrdoob/three.js) | 59 | 透视卡片、灯光、相机和3D材质，扩充少量纵深镜头。 | 不是口播模板；过量3D会增加渲染/字体/素材处理成本，需逐帧固定时间。 | MIT |
| 42 | [pmndrs/react-three-fiber](https://github.com/pmndrs/react-three-fiber) | 62 | 用React组件组织Three.js，可与现有组件思维衔接。 | 它是Three.js的React渲染层，不是独立视频生产能力；需固定React版本并控制渲染循环。 | MIT |
| 43 | [ManimCommunity/manim](https://github.com/ManimCommunity/manim) | 64 | 精确图解、对象变换、公式与关系动画，适合知识讲解的局部片段。 | Python渲染路线与React媒体模板不同；人物、素材替换、中文布局和全片队列需额外工作。 | MIT |

### 理解、真实时钟、素材与数字人辅助

| # | 项目／一手来源 | 适配分 | 可借用的具体能力 | 对本项目的主要缺口 | 代码许可 |
|---|---|---:|---|---|---|
| 44 | [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 79 | Content/Adaptive/Threshold检测、场景时段和抽图，可建议重点回看范围。 | 不能识别“同一对象在变形/重排”；变化候选必须结合ASR与视觉判断，不能当完整分镜。 | BSD-3-Clause |
| 45 | [m-bain/whisperX](https://github.com/m-bain/whisperX) | 75 | ASR、强制对齐与说话人分离的组合，清楚区分转写文本与词时间证据。 | 中文/噪声/模型依赖要实测；已有阿里ASR时不必重复整条音频，也不提供动画语义。 | BSD-2-Clause |
| 46 | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 68 | CTranslate2、量化与批处理，适合无云时的本地转写备选。 | 上游速度比较不能证明比本机阿里服务更快更准；词级语义与模板编舞仍需后处理。 | MIT |
| 47 | [openai/whisper](https://github.com/openai/whisper) | 62 | 通用多语种转写、语言识别与本地基准。 | 不宜为了复刻流程替换已工作的中文ASR；转写本身不等于可靠逐字对齐或画面理解。 | MIT |
| 48 | [QwenAudio/SenseVoice](https://github.com/QwenAudio/SenseVoice) | 72 | 中文/粤语等识别和情绪/音频事件标签，可辅助理解口播语气。 | SenseVoiceSmall自身不直接产生说话人分离；时间/说话人要由实际组合管线提供。 | MIT（代码） |
| 49 | [modelscope/FunASR](https://github.com/modelscope/FunASR) | 76 | ASR、VAD、标点与说话人模块组合，适合统一结构化转写返回合同。 | 工具包不等于当前百炼调用；本地部署成本、模型与时码精度须按具体配置验收。 | MIT（代码） |
| 50 | [jianfch/stable-ts](https://github.com/jianfch/stable-ts) | 69 | 时间戳稳定、对齐和字幕重新分组，可参考“原始证据与展示分段分开”。 | 不是凭文案自动生成真实时码；仍依赖真实音频与模型，不能平均分字替代识别。 | MIT |
| 51 | [smacke/ffsubsync](https://github.com/smacke/ffsubsync) | 61 | 将已有字幕与声音活动对齐，适合旧素材字幕整体偏移校正。 | 不能识别缺失文字，不能证明逐字动作时刻正确，也不生成模板动作。 | MIT |
| 52 | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 75 | 从参考帧识别烧录文案、文字区域，可辅助对照文案与排版边界。 | OCR文本不是原始ASR；变形、遮挡和快速运动需局部补帧复核，不理解动作因果。 | Apache-2.0 |
| 53 | [QwenLM/Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | 77 | 视频、图像及带时间信息的视觉语义理解，可作为结构化动作分析器候选。 | 多模态生成描述仍会漏对象/错时点，需同源帧证据；这不意味着DeepSeek等纯文本模型直接获得视觉能力。 | Apache-2.0（代码；权重逐项核对） |
| 54 | [OpenBMB/MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V) | 70 | 面向设备的视频/图像理解路线，适合探索本地素材粗分类与疑点定位。 | 设备性能和权重许可分别核对；未证明本机足以替代现有视觉分析，不能承诺识别全部编舞。 | Apache-2.0（代码） |
| 55 | [facebookresearch/sam2](https://github.com/facebookresearch/sam2) | 62 | 视频对象掩膜与跨帧追踪，可辅助人物/物体分层与素材窗保护。 | 分割不识别叙事角色、图形语义或版式；GPU/模型部署代价不适合所有参考分析。 | Apache-2.0 |
| 56 | [danielgatis/rembg](https://github.com/danielgatis/rembg) | 60 | 静态素材去背景，适合照片贴纸、证明卡片和自有素材分层。 | 图像抠图不是稳定的视频人物抠像；头发、手和连续边缘仍需另验，模型许可单独看。 | MIT |
| 57 | [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk) | 65 | 用真实视频和新音频生成口型，可参考音轨与人物窗口的输入输出分离。 | 不生成MG模板；画质/口型/时长须实际验收。不能因代码MIT就忽略所有依赖模型条款。 | MIT（代码） |
| 58 | [MeiGen-AI/InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk) | 70 | 音频驱动的长人物视频、头身表情联动，可为连续口播提供人物层。 | 计算与模型依赖重，不能替代场景编舞；不等于任一RunningHub工作流的价格/质量已验证。 | Apache-2.0（代码） |
| 59 | [OpenTalker/SadTalker](https://github.com/OpenTalker/SadTalker) | 52 | 单张人物图加音频的可运行开源路线，可作数字人层的参考。 | 以头像表演为主，无法提供同参考片的身体姿态/场景；依赖第三方组件许可。 | Apache-2.0及第三方例外 |
| 60 | [librosa/librosa](https://github.com/librosa/librosa) | 66 | 音频和音乐信号处理，可辅助节拍/能量与动作音效安排。 | 信号峰值不是语义重点；音乐节拍不能覆盖口播真实时钟。 | ISC |
| 61 | [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | 79 | ASR与独立ForcedAligner能力分清，适合在确有需求时补真实文本—声音时间对齐。 | 不是百炼服务能力的同义词；本地对齐精度、资源及具体语种要实测，不因“阿里”品牌就宣称更强。 | Apache-2.0 |

### 另核验的11项：不纳入开源数量

以下仍给适配分，方便比较；许可受限不代表方法不值得研究。它们没有被混入上面61项。

| 项目／一手来源 | 适配分 | 可借用与实质限制 |
|---|---:|---|
| [hypit-ai/hypit](https://github.com/hypit-ai/hypit) | 88 | 参考理解、生成媒体与可编辑视频的完整流程有价值；但[LICENSE](https://github.com/hypit-ai/hypit/blob/main/LICENSE)是Apache附加多租户、商业再分发、标识等条件，不按标准Apache计数。当前只取方法，完整接入有重复引擎、费用和许可范围问题。 |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | 96 | 是海客既有代码视频底座，最适合继续承载自有模板；[许可](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)有公司使用条件，不按无条件OSI开源计数。其本身不完成参考理解和模板沉淀，且本次无需换引擎。 |
| [larashero3-dotcom/lieflat-code-video](https://github.com/larashero3-dotcom/lieflat-code-video) | 74 | 镜头/接力/节奏词汇和独立Remotion starter有参考性；当前[说明](https://github.com/larashero3-dotcom/lieflat-code-video/blob/main/README.md)明确PolyForm Noncommercial，完整案例工程、完整动作库、自动成片检查未公开。不能把演示当成全部现成组件，更不能直接纳入商业交付。 |
| [openvideodev/react-video-editor](https://github.com/openvideodev/react-video-editor) | 61 | 原designcombo仓库，当前README介绍OpenVideo的浏览器多轨与WebCodecs/Pixi导出；有员工规模相关商业许可。不是开源免费编辑器能力可全部搬入的证据。 |
| [diffusionstudio/core](https://github.com/diffusionstudio/core) | 64 | LICENSE为MPL-2.0，公开时间线、字幕、检查点和浏览器合成值得学；README另列导出水印/去水印密钥价格。为避免把仓库代码许可等同全部产品权益，本报告保守放在此组，未凑入61项。 |
| [crafter-station/remotion-clone-video](https://github.com/crafter-station/remotion-clone-video) | 81 | 8阶段参考重建、15类动画配方与实帧对照很贴近需求；README已读，许可API未给项目LICENSE，暂不复制代码或宣称标准开源。 |
| [blixvip/MotionClone](https://github.com/blixvip/MotionClone) | 80 | 参考/重建同步拖动、分段笔记与可编辑HyperFrames交付很有价值；README明确未授予全项目开源许可。应学习比较交互，不直接搬代码。 |
| [liangdabiao/video-clone-lite](https://github.com/liangdabiao/video-clone-lite) | 68 | 轻量复刻取向与可改流程值得对照；取得README但项目许可证未明确，且不把作者“替代Hypit”的宣传视为质量证明。 |
| [transitive-bullshit/ffmpeg-concat](https://github.com/transitive-bullshit/ffmpeg-concat) | 49 | 多种GL转场拼接可借鉴；本次仓库许可API未找到许可证，且拼接不是持续对象编舞。 |
| [adunext/motiongit-skill](https://github.com/adunext/motiongit-skill) | 84 | 官方“完成工程→提炼→打包.motion”入口，可用于未来发布自有模板的流程研究；仓库主要指向官网最新校验包，未取得明确仓库许可证/完整运行实现，不当作一套已接入工具。 |
| [motiontemplates/all](https://github.com/motiontemplates/all) | 86 | 带预览、编号、画幅、素材需求和源码链接的模板目录，适合持续发现来源；当前汇总仓库无统一许可证，必须逐个模板/包核对，目录条目也不能重复当开源项目数。 |

## find-skills 与 agent-reach 实际做了什么

使用[agent-reach](https://github.com/Panniantong/Agent-Reach)的GitHub/`gh CLI`、Exa/`mcporter`与网页/Jina路由。先实际执行 `agent-reach doctor --json`：GitHub只证明命令与配置存在，后续实际非空API返回才证明本次能读；Exa亦以实际返回核验。Reddit、小红书、Twitter没有可用登录后端，本次未安装、未登录，也没有编造这些平台的意见。对开源能力和许可的结论只采用拥有该事实的第一方仓库，而非论坛好评。

按[find-skills](https://github.com/vercel-labs/skills)流程，先读取skills.sh目录，再运行已缓存CLI的 `npx --no-install skills find ...`；没有执行add/update或安装新skill。

| 实际查询 | 返回的相关结果／第一方核验 | 如何使用结果 |
|---|---|---|
| `motion video` | [heygen-com/hyperframes](https://skills.sh/heygen-com/hyperframes/hyperframes-creative)（列表显示916.8K）、[iart-ai/motion-design-skills](https://skills.sh/iart-ai/motion-design-skills/motion-art-direction)（3.9K）、[openfilm/openfilm](https://skills.sh/openfilm/openfilm/openfilm)（3.8K） | 三个仓库README和元数据均已另读。索引中的skill命名/安装量可能落后仓库，未用作评分依据。 |
| `video clone` | [crafter-station/remotion-clone-video](https://skills.sh/crafter-station/remotion-clone-video/remotion-clone-video)（32），同时出现不少翻译/配音与不相关结果 | 只列贴近参考重建的一项；另核仓库发现许可不明，所以放入比较组。搜索命中不是可集成证明。 |
| `motiongit` | 返回多项motion-sites/网页参考库结果，未返回精确的MotionGit原生接入skill | 不把近似词结果当答案；另用GitHub核实 `adunext/motiongit-skill` 与 `motiontemplates/all` 官方入口。 |

安装量仅是2026-11-01这次查询的界面快照；同一个仓库里的多个skills始终只计一个项目。末尾执行 `agent-reach check-update` 返回本机v1.5.0、可更新v1.6.1，本次没有更新环境。

## 应怎样取长补短

| 海客要稳定保存的层 | 优先借鉴 | 在本项目里的落点与边界 |
|---|---|---|
| 参考证据 | Hypit、Motion2Code、PySceneDetect、OCR/VLM | 保存整片论证、真实ASR句/词、PTS和同源帧；候选变化只负责定位。把对象ID、状态、进入/变化/退出、遮挡与声音关联记清。 |
| 语义编排 | 花叔、MV Director、Lemo | 不仅记录“蓝底大字”，还记录评论先打字再出现证明、同ID排名重排、同图白到黑接力等动作意义。新文案按声音重新编排，不能强套原片秒数。 |
| 自有动作组件 | Onda、Snapcn、mg-styles-15 | 源码、schema、示例、字体/文案容量和运动曲线一起入库；一个部件能被多个模板复用，模板有自己的整体节奏。 |
| 授权原包 | ADU、每个.motion自身协议 | 保留原包SHA/版本与已核验helper；读真实schema和制作入口，不把受保护内核抄出。未知协议先只读，新增适配另验。 |
| 单期内容 | 现有ASR/音频/数字人/素材模块 | 音频作主时钟，自己的素材有来源与稳定ID；匹配嘴型的人物只放真实对应片段，完整人物不足不能循环假装完整。 |
| 编辑与制作 | 现有Remotion、队列、工作台 | 参数控件/素材绑定→结构校验→真实计划→预览审图→统一队列→成片回执与版本恢复。画廊卡片应反映真实能力，不把“能导入”标成“已成熟”。 |
| 实际验收 | Motion2Code、Framesmith、花叔、Launch Workbench | 技术检查、语义对应帧、连续观看、听审、口型和真机分别记录。重写文案后按同语义事件对照，像素分数只辅助找异常。 |

本项目当前已采用的范围应以[原生模板协议](../NATIVE_TEMPLATE_PROTOCOLS.md)与各模板验证记录为准；本研究不是把上表全部宣布为已实现。眼下合理的主线是继续把“少量、丰富、实测过的动作模板”做深，而不是一次装入十几套完整视频框架。

## 对用户几个核心问题的回答

**直接用.motion与复刻同款内置模板并不相同。** 前者保留原包自己的动作和规则，省掉重写成本，但能改多少取决于每包合同；后者把动作抽象成海客自己的组件与容量，长期调整更自由，同时要承担还原、排版和验证成本。两条路线可以并存，MotionGit始终只是模板来源之一。[ADU原包路线](https://github.com/adunext/adu-motion-video)、[Onda源码组件路线](https://github.com/degueba/onda)

**横屏改竖屏不是导出参数改成9:16。** 人物、安全区、字幕、长句、图片方向、图谱连线和观看顺序都要重排；原模板若只有横屏合同，就应把竖屏当一个需要单独验收的布局。自动缩放无法保证保留可读性和全部动作。[原生横竖布局声明](https://github.com/adunext/adu-motion-video)、[独立竖屏审查要求](https://github.com/chrischabot/product-demo-skill)

**是否需要极强前端模型，要看让模型承担多少临时发明。** 从空白写高质量MG，仍很依赖模型的视觉/代码与导演能力；上游风格项目也承认提示词不能保证同样成片。把复杂动作提前做成受测组件，给模型清楚的schema、素材槽和容量后，常规制作主要变成选镜头、填内容、按真实声音编排和读中文错误，较弱模型也更有机会稳定使用。但本次没有做DeepSeek同机盲测，不能承诺任意国产模型都能达到同等质量。[Lemo说明](https://github.com/lemomo-ai/lemo-opuscar)、[mg-styles说明](https://github.com/Vincentwei1021/mg-styles-15)

**阿里ASR不必为模仿Hypit而更换。** 应保留原始识别结果、句/词起止、置信信息及音频SHA，既给人看带时间轴的文案，也让动作和回看工具引用同一证据。需要更细的对齐时，再针对真实缺口选对齐模块；没有数据时不能按汉字平均分配，也不能把Qwen开源模型与百炼某API的实际能力混为一谈。[Qwen3-ASR/ForcedAligner](https://github.com/QwenLM/Qwen3-ASR)、[WhisperX对齐定义](https://github.com/m-bain/whisperX)

这次的推荐不是选一个总分冠军取代所有东西，而是：**用Hypit的方法把片看明白，用原生.motion保留已有好动作，用Onda/Snapcn方式保存自己的可编辑组件，用海客既有生产线把每次制作做稳。**
