# 动效模板统一复刻契约

适用：画廊内编号 2–11 与已导入的 8 套动效模板。固定模板保留原封面、原实现和现有替换路线。采用 Hypit 的对象、语义事件及验收方法，执行继续使用已验证的项目渲染器或原包。

## 真值与执行

MD 说明设计意图、操作步骤和能力边界；JSON 保存精确身份、输入合同、对象关系、语义时间线、动作绑定及验证定位。JSON 中的动作编号必须解析到实际实现；现有模板内部动作可使用 `haike.<template>.<action>`，版本精确匹配。163 项目录沿用其命名空间，不用列表下标充当稳定编号。

源码持有的几何、裁切和运动公式继续由源码持有。合同绑定文件与 SHA256，并说明实际读取的参数路径；仅登记编号或 `data-effect` 属性不能证明执行接入。保留原冻结文件，迁移通过旁路合同与适配层表达。未知版本、动作或缺失必需素材明确阻断依赖它的操作。

## 统一接口 v1

公共入口：`backlot/motion_replay.py`、`scripts/motion_replay.py`、`config/motion-replay/contract.schema.json`。注册文件位于`config/motion-replay/`，精确分组及适配器以`motion_replay.py`固定允许列表为准；现含编号2–5、6–11、导入原包、独立知识、原生全片、流程演示及公开组件各版本。知识参考`/3`登记于`imported-knowledge-reference-public-v3.json`，五套公开组件`/2`另有`imported-public-v2.json`与`imported-public-v2-bound.json`。各组绑定自己的实现、测试和说明；新增注册文件须同时进入校验、准备和发行组件闭包，不能只改目录扫描或假定组数固定。新增精确版本保留原有身份，不增加画廊样式数量。

注册文件：`schema: haike.motion-replay-registry/1`，包含 `templates` 数组。每项必需字段：

- `template_id`、`version`：精确可移植身份；`gallery_id`：本机画廊对应项，可选；`family` 为 `numbered` 或 `imported`。
- `renderer`：`kind`（`project` / `native_package`）、`entrypoint`（实际入口或协议）、`adapter`（适配器身份）、`execution`（`supported` / `inspect_only` / `needs_adaptation`）；执行入口采用代码允许列表，JSON 不授予任意命令执行权。
- `sources`：数组，每项 `path` 为仓库相对路径、`sha256` 为文件身份；私有包只保存公开身份与摘要，凭据、原包与私有素材留在本机。
- `objects`：数组，每项 `id`、`role`、`authority`；空间、层级、裁切、公式和可编辑字段可指向固定源代码位置，明确源码拥有的范围。
- `actions`：数组，每项 `id`、`version`、`implementation`（源码路径与真实符号或原生动作组）、`objects`（对象 ID）、`parameters`（真实参数路径或源码锁定说明）、`phases`（entry / active / settled / exit 的事实或不适用原因）。
- `timeline`：`mode` 为 `source_locked` / `semantic` / `native`，`clock`、`events` 数组及 `retiming` 能力说明。事件具备 `id`、`action_id`、`anchor`、`window`、`reading`；保持原时序可引用原场景/帧规则，新稿可重排必须由实际适配实现证明。关键内部事件独立登记，外层总窗口不能代替内部语义。
- `slots`：真实已开放输入的数组，每项 `id`、`kind`、`input_path`、`required`、`missing_policy`；未开放布局与动作参数锁定，不能虚构通用可调字段。
- `capabilities`：明确参考保真、换稿、语义重排、高清和音频的范围；不支持的能力说明原因。
- `validation`：按维度分别记录 `pass` / `fail` / `pending` / `not_applicable`，并保存方法、范围和证据路径；结构通过不提升视觉、听审、生产接入状态。

允许组内扩展字段，统一校验器拒绝身份重复、未知动作引用和未绑定的必需字段。公共接口扩展须同步schema、调用方、测试与所属runbook；保留既有精确版本及冻结身份。

公共读取命令从仓库根执行：`Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_replay.py catalog`；`verify`核对登记来源；`prepare --template-id <ID> --version <精确版本> --request <输入JSON>`通过代码允许列表调用既有适配器。输入形态和开放字段由逐套合同与适配器定义，`action_ids`请求若不被当前模板支持须拒绝；准备结果不等于提交或已生成视频。HTTP同等入口为`GET /api/studio/motion-replay`及`POST /api/studio/motion-replay/prepare`，POST外层仅接受`template_id`、`version`、`request`。

准备结果统一使用`schema: haike.motion-replay-preparation/1`、精确身份、`status`（`prepared` / `blocked` / `inspect_only`）、来源核验、动作绑定与阻断。成功准备的`invocation`包含`transport`（`python_cli` / `component` / `http` / `project_python`）、真实`entrypoint`、原实现可消费的`input`和所需`context`；阻断时为null。原适配器细节保留，`submitted`始终为false。读取这些描述不会执行任意命令或跳过原队列、预览、许可与生产门禁。

## 验收与正式版

本期用户最新提速要求：只修影响实际使用的明显问题，优先锁定已有18条完整高清有声成片。黑屏/缺画面、应运动的主素材静止、无声或明显音画错位、重要文字错误或严重遮挡裁切、无法完整导出、必需组件缺失等才阻断相应使用；引号、微小尺寸位置、非关键曲线、署名细微时序和末端失焦差异记录即可，不再追加版本、审查或重渲。已运行任务自然收尾，成功音轨/ASR/数字人/完整片与已通过检查复用。未完成的连续听看如实披露，不冒充已验；装饰精修不再作为交付或升级前置。此执行优先级覆盖下文历史候选修订的待办，不改写既有证据。

全片通过按[验收量表](../../Haike-Videohub/agent-runbooks/视频模板验收量表.md)阶段4核对完整技术产物、覆盖性视觉及连续听看；目标设备/平台呈现属于阶段5，未验证时单列待验证，不冒充真机已通过，也不额外扩大未声明目标环境的本地视频交付门槛。运行组件复现、前端接入及发行环境升级仍按各自实际范围独立核验。

制作依赖与验收方法分开：本批制作沿原配音、真实ASR、高质量RunningHub数字人与既有渲染器执行；已成功素材按原身份复用。额外音频理解模型不是本工作流组件，不因Agent自身无法听音便把它或其Key权限加成交付前置。完整解码、响度/峰值、声道、原声时长、ASR覆盖与字幕时码采用已有本地工具检查；听感、口型及连续节奏按实际播放另记结论，不能用模型文字报告、ASR或量测冒充已听看。本批已取消额外omni音频机审，不再请求开模型权限或换模型重试；历史拒绝回执和未知费用分别保留，不阻塞原生产路线。

### 完整生产消费链

只读`prepare`与完整父视频分别留存回执。新完整生产适配通过`ProductionQueueWorker._run_investment_recompose`中的精确合同允许列表，沿用`studio_investment_recompose`暂停入队、专属领取及跨项目单道执行；JSON中的模块名或命令不能扩展执行权。所属生产模块须先核对模板/动作精确版本、源码与素材SHA、完整文案和真实ASR时钟，再冻结父请求；预览和正式导出消费同一时间线、裁切、人物窗口与字幕。

当前独立生产入口为`backlot/motion_replay_field_notes_video.py`（`haike-field-notes-video-production-v1`）、`motion_replay_chromatic_production.py`（`motion-replay-chromatic-production-v1`）及`motion_replay_imported_production.py`（`haike.motion-replay-imported-production/1`）。前两项新增候选版本，保留旧4/5照片版和6–11冻结身份；导入包装层继续委托原生组件渲染器，新增项目时钟不冒充原包的新控件。每个入口的完整能力与当前验收范围以所属说明和实际生产回执为准，登记分派本身不表示成片通过。

全量制作另增旁路`motion_replay_numbered_02_05_production.py`（`motion-replay-numbered-02-05-production-v1`，`frames|render`）和`motion_replay_chromatic_suite_production.py`（`motion-replay-chromatic-suite-production-v1`，仅`render`）。前者经新增`motion_replay_numbered_02_05_full.prepare`准备；后者仅由代码允许列表对注册组、模板ID和精确候选版本同时匹配后调用`prepare_contract`。旧06及既有已接受生产模块不改写；候选新模块存在、接口测试通过和整片验收是分别记录的状态。组件尚未准备齐全时明确报告缺件，不回退到另一套风格或任意模块。

知识模板的独立可分发实现使用`studio_imported_knowledge_full.py`（`haike.knowledge-full/1`），属于新增实现身份，不冒充受保护原生renderer。公共父视频入口委托其原`submit(queue,request,phase=...)`和`run(queue,job)`，默认先`preview`，正式`render`仍须原模块逐图审阅回执。原包身份、独立源码身份、风格对照及每套实际成片证据分别记录；新增分派不使原包取得再分发许可，也不代表两套已经完整交付。

原知识模板完整制作另用`studio_imported_native_knowledge.py`（`haike.native-knowledge-full/1`），经`motion_replay_imported_native_full.prepare`和`imported-native-full.json`绑定原精确包、真实原生机制与本期输入；同样保留`preview|render`及原全部图片审阅门槛，不提取保护核心。原默认参考无人物时保持无人物；只有明确选人物模式才核对全程连续人物源，不能将首尾片段当成全程覆盖。原生保真、独立组件可分发和本期成片验收是独立事实，新独立候选不能仅凭同模板ID代替原效果通过。

公开源码组件候选另有独立合同`haike.motion-public-production/1`，由`motion_public_runtime.py`委托版本化`motion_public_execution_v1.py`；原模板/原包身份不改变，不以场景源码字节相同冒充motion-kit/poster-kit控件等价。公共完整生产CLI仅对该新合同选择`motion_public_worker_v1.MotionPublicProductionWorker`，其余合同继续原worker；新类继承原领取、租约、单道与完成流程。冷启动工作台和该CLI使用`motion_public_queue_v1.MotionPublicProductionQueue`，仅对该新合同补充经原脱敏器处理的任务名称。原`production_queue.py`及`production_queue_worker.py`字节不变；这些扩展不授予任意模块执行权，不声称解决全部历史摘要漂移。该候选默认预览、完整图片审阅后才能正式导出，实际输入/全片/保真及发行闭包仍须逐项通过；当前现场服务未因此自动重启或提升画廊默认。

流程演示另有独立参考实现`studio_imported_promo_reference.py`（`haike.promo-reference-full/1`），实际公开参考为58.75秒横屏作品墙流程，旧20秒project-wall只属试验桥，Hum候选不能因完整导出便当作原样式。新实现保留橙字、四列墙、同卡选择放大、详情/指引和黑底品牌等可观察动作；原包与新源码身份分开，保真依靠实际输出对照。公共execute仅该合同选择`motion_promo_worker_v1`，冷启动工作台/CLI的`motion_promo_queue_v1`继承上述公开组件队列，只增加该合同脱敏名称，旧base及先前扩展文件均不改。与其他新组件一样须按实际preview/review/render门禁完成，登记不等于成片或保真通过。

所属适配器冻结本期请求后，从仓库根调用`Haike_video/scripts/motion_replay_production.py submit --request <冻结JSON>`暂停入队；导入包用`--phase preview|render`保留原计划/预览审阅门禁。`execute --job-id <原队列ID> --confirmed`只领取指定原任务，`status --job-id <原队列ID>`只读核对。执行标志由Agent依据当前有效授权填写，不要求重新征求已给过的制作授权。已完成任务直接复用；失败或未知不会自动恢复。明确可重试的原本地合成可加`--resume-local`，不能用于配音、识别、数字人或受理未知阶段；上游只能按原服务任务的恢复回执处理。该CLI采用代码固定允许列表，不运行JSON给出的模块或命令。

新增独立知识参考合同`haike.knowledge-reference-public/1`固定到`motion_knowledge_public_production_v1`，用`imported-knowledge-reference-public.json`登记；流程演示阶段合同`haike.promo-reference-full/2`固定到`studio_promo_phase_v2`，通过新`imported-promo-phase-v2.json`及只读wrapper准备，继承原流程演示renderer字节。新`motion_reference_public_worker_v1`固定分派这两路及此前public/1、promo/1，其他合同委托原worker；冷启动工作台使用此类。工作台/CLI的`motion_reference_public_queue_v1`继承先前queue扩展，仅补两合同脱敏名称。旧base和先前D/C扩展不改写。通用resume仍拒绝本地重合成、后台claim_next仍排除该kind，执行须沿公共CLI明确领取指定原父；没有新增HTTP自动执行。新promo /2的CLI status和execute另附实际health availability，历史completed状态、缓存健康和执行就绪分别报告。接线/隔离队列测试不表示实际预览、全片或保真通过，仍须实际沿公共入口验收。

新阶段控制的预览身份只绑定原输入、实现与阶段，不随审核人、审核时间或后来新增review变化；重复preview应返回同一原父。render入队前核对已完成同源预览、全部实际PNG及明确批准，冻结具体审核与图片身份，领取后再核对。拒绝、要求修改、缺图或摘要变化均不能授权导出。已失败、取消、受理未知或缺失产物的原任务保留原状态和恢复点，不因更改审核而变成新任务。需要重新开发预览时显式建立新revision及独立输出空间，保留旧现场并重新审核；后端revision不得改变画面或声音。缓存成片是否完整、预览是否健康、当前源码能否执行和视听是否验收分开报告。既有冻结合同保留其原行为，新规则由新版本实现，不能声称全部历史路由已修复。

公共队列结果以原脱敏规则处理新增字段，包括`availability`、`artifact_integrity`及内部reason，不能只脱敏原row而让附加绑定泄露本机绝对路径或凭据。内部冻结、审核和完整性核对继续使用真实路径与摘要；公共脱敏不修改原父、图片或证据。Agent实际看图从所属适配器的私有原预览清单读取，不用公开状态字符串代替图片，更不以ready/valid字样提升视觉或听审结论。

五套公开组件的`haike.motion-public-production/1`及其完成片保留为开发历史，不因静态或候选整片完成自动提升为正式默认。新独立`/2`候选将阶段控制与渲染执行分别固定：控制器只调用代码指定的执行模块，采用同一明确审核、领取前撤回、真实租约/取消及导出登记前后重验标准；执行修订保留原HTML与Remotion渲染器，仅修已定位的可见文字、时序和版式差异。原参考编辑器里的frame计数有叙事用途时保留，本期营销版不相干的计数可在新候选中仅隐藏文字并保持布局占位及全部动效。新合同、来源与真实验证未接齐前仍为开发候选，不能让旧冻结SHA失效后就地回填，亦不能用新增源码或媒体替身测试声称整片已复刻。

公开组件`/2`现在固定到`motion_public_production_v2`和`motion_public_execution_v2`，同走ReferenceQueue/Worker与公共execute的claim前校验；status附实际health并沿原规则脱敏。完成预览的原父result是完整见证：当前manifest SHA与全PNG清单必须精确匹配该原始结果及冻结请求，不能删减清单后通过重新审核把缺图变成完整。该检查覆盖review、render准入、preclaim、run、缓存、health及局部render修订。媒体前后使用控制器注入的内存`_phase_guard`，JSON不能提供回调；原completed状态、当前产物完整性、具体批准和视听结论分别报告。

五样式的统一只读契约保留`imported-public-v2.json`／`1.0.0-public.2`候选，另以`imported-public-v2-bound.json`／`1.0.1-public.2`绑定实际生产记录，不修改原41精确版本或已接受renderer。后者固定`motion_replay_public_v2_bound.prepare`，先核实际场景消费的control/variant或dark group；显式action_ids必须与实际消费集合一致，场景顺序与时钟仍由composition及真实ASR决定。适配结果的`invocation.input.source_receipts.motion_replay`带精确模板/版本、canonical卡片、源SHA、真实动作及事件/输出档案，必须原样交给固定producer.prepare并进入真实父请求；不能丢弃该字段后声称已按命名模板契约冻结。已有不同绑定须明确重做准备，不静默覆盖。原始输入不改，新增来源元数据不改变画面、素材或声音；低层组件独立输入仍不冒充已验收的命名模板。

本次公开`/2`结构审查中，缩减preview清单的P2已按独立原反例修复并定向复验；这只关闭该阶段缺陷，不证明新五片画面通过。五套本期输入已沿`1.0.1-public.2`准备并进入真实主队列，原始输入与绑定输入只有来源元数据差异，真实冻结父的精确版本、动作及来源绑定已逐项核对，见本机批次`ROOT_PUBLIC_V2_ACTUAL_PARENT_BINDINGS.json`。五套preview均首次执行完成，共568张真实PNG；深色、纸感、浅色与控制台按完整预览具体批准后，四个完整HD有声父均首次完成，完整解码和最终编码目标实际查看另留回执。深色新片已选入当前18文件及前端封面，旧片/集合回执保留。原参考定向对照随后确认浅色缺少短语错峰清晰化、控制台缺少署名独立延迟，纸感最后主层清晰保持与原末端失焦不同；这些完整导出不能冒充相应机制已保留，当前主清单仍保留原片，修订采用独立来源。海报引用装饰字形仍有实差，原`/2`维持changes_requested且禁止full。技术、编码抽查、本期原样式对照、连续听审与最终升级环境复刻分别核验，当前不表示全18正式交付通过，新增catalog版本也不自动提升画廊默认。

海报字形修订独立使用`haike.motion-public-poster-production/3`，固定`motion_public_poster_production_v3`与`motion_public_poster_execution_v3`，仅接`observed-controls/3`、`observed-poster`及`vibrant-poster`。精确`1.0.0-public.3`在`imported-public-poster-v3-bound.json`由固定`motion_replay_public_poster_v3_bound`准备，核实际控件/运行版本/完整来源并注入生产消费的replay回执；旧51版本及冻结身份保持。ReferenceQueue/Worker、claim前校验与完整预览见证等沿`/2`修复后的阶段规则。固定接线、真实输入只读准备及反例检查通过；首次实际预览78张已逐图查看并具体批准，方折符号形式修正通过，字体墨迹度量残差按独立候选范围披露，整片与最终编码仍按本版本产物验证，不以静态检查或旧`/2`图片替代。局部时序修订按原帧证明的可见状态验证，不要求从稀疏帧恢复唯一easing或精确首现帧；也不能用整体延时替代已观察到的同帧局部清晰度差异。

浅色、控制台的引言局部修订独立使用`haike.motion-public-quote-production/3`，固定`motion_public_quote_production_v3`与`motion_public_quote_execution_v3`，仅接`observed-quote-controls/3`及各自`observed-light`/`template-01-integrated`、`observed-console`/`template-04-dark-console`组合。两条精确`1.0.0-public.3`在`imported-public-quote-v3-bound.json`由固定`motion_replay_public_quote_v3_bound`准备；回执保留实际场景props、句词事件和时钟身份。`quote.reveal_groups`只对浅色reveal开放，逐组拼接须等于全文，默认分组由已绑定实现确定，不能在准备时丢弃或伪报。新预览保留原完整动作抽样并补quote局部约束时刻，本期各83图；实际短语清晰度、署名门禁、换行和字形仍须新版本图片验证。固定接线及真实输入只读准备通过不等于这两套实际画面通过，旧版本、原完整片和画廊默认保持。

知识参考定向修订另用`haike.knowledge-reference-public/2`、精确`5.1.0-independent.1`，固定`motion_knowledge_public_execution_v2`和`motion_knowledge_public_production_v2`，通过`imported-knowledge-reference-public-v2.json`增列两个原canonical卡片；/1源码、实际图和要求修改记录保留。新reference worker/queue识别/2，公共execute与promo /3一样先调用只读validate_claim，领取后由所属run再验真实frozen、worker、attempt、租约、当前批准与取消；不放开原通用resume或后台领取。源与测试通过后才运行绑定原失败证据的定向预览，实际查看后明确决定是否允许全片。静态几何、注册成功或定向预览数量不能替代新画面/各机制保真及完整视频验收；科学示意previewOnly不允许完整导出。

同一知识样式的有限画面修订再用`haike.knowledge-reference-public/3`、精确`5.1.1-independent.1`及`imported-knowledge-reference-public-v3.json`，固定独立execution_v3/production_v3，公共ReferenceQueue/Worker和claim前门槛同/2。它只修已定位的灯泡曲线、绿板细粒/擦痕和便签Canvas阴影状态泄漏，保留/2源码、原父和全部72图审核。`targeted-revision/2`绑定原要求修改审核，除三项实现身份外episode所有正文、模型、事件、时钟及声音字节须与原冻结相同；纸笔6帧与粉笔2帧已实际复验通过，随后两套完整HD有声父均完成，完整解码及最终编码帧查看另留回执，见本机批次`A/knowledge-public-assist/FULL_DELIVERY_V3.json`。不追加泛审或要求复制私人材质像素；连续听审仍待验证，静态/接口检查不提升保真或交付状态，既有科学模型及previewOnly限制保持。

当前阶段限制：promo /2已通过一次实际公共preview/render及缓存健康核对，但随后发现review未消费明确decision，reject/changes_requested也可能写成批准绑定；它的源码、原父和成片保留作历史候选，不能据此提升为新的正式默认。修复的新合同`haike.promo-reference-full/3`固定到`studio_promo_phase_v3`，精确版本`3.0.0-reference-public.3`通过`imported-promo-phase-v3.json`与固定只读wrapper登记。新reference worker/queue增加该合同；公共execute只对/3先调用只读`validate_claim`再沿原队列领取，run再次检查真实worker、attempt、租约、当前批准与PNG，保持既有renderer和声音公式。新阶段已单独完成实际preview及完整render，41张新预览PNG与原已看图一致，14张最终编码帧实际查看，完整音画解码和撤回门禁分别留证；这些不替代连续听审或发行环境复刻，也不能用/2图片冒充新预览。知识独立参考5.0.0版本的实际开发帧存在已定位视觉差异，保持要求修改状态；结构测试或有完整旧原生片不能代替新独立实现保真验收。

已完成父任务的幂等复用只证明原产物可取回，不能证明旧冻结请求仍能重新生成。升级验收须另用合法测试输入走实际准备、校验、领取、渲染和产物核验。部分历史生产器将整个队列或共享生产模块纳入源码摘要；新增无关路由也可能触发其严格漂移校验。保留原冻结请求和对应实现版本，不以重写旧SHA、跳过校验或假生产器分派测试消除差异。后续实现版本与调度接口的解耦、精确版本兼容适配须单独落地并验证，当前登记或设计不表示此能力已完成。

同一模板可保留多个精确版本，画廊默认绑定不因新增候选而自动升级。完整生产记录至少包含本期脚本、音频、ASR、动作消费和语义事件、原素材、数字人工作流及原任务、队列父编号、费用预留与账单、最终MP4/封面和分项验收。已成功的同稿同声源音频/人物段允许按SHA与原时码复用，费用只记一次；未知受理保留敞口和原记录，不为制作另一模板自动重复购买。

人物生成或复用前，先按实际渲染器的画面可见域核对窗口，包含原生人物卡的预入场、退出和帧边界余量；语义场景起止不能直接当作人物可见起止。留存边界代表帧、原旁白切片和生成帧域的映射，切片避开实际词句并保留必要上下文，完整旁白仍原速连续使用。既有素材未覆盖可见域时，应在已有授权和本期预算内补齐匹配素材，或明确阻断；不能以黑卡、冻结画面、循环人物或移动口型时钟补足，也不能把固定秒数余量套给所有渲染器。输入变化后定向复查原缺口，再沿原预览与父队列门禁出片。

共享渲染依赖先只读核对锁文件、实际模块解析、Node/浏览器/FFmpeg和所需字体。不要用`-LiteralPath`配通配符的空结果推断文件缺失；运行中不得对共享`node_modules`执行清理安装。确有缺件时按原锁在隔离暂存目录准备、核验完整性与运行探针，保留正在使用的二进制；向共享运行树切换或替换须在原任务释放执行权后统一完成。修复留存来源、锁SHA及验证回执，不能用安装成功代替原任务恢复和真实渲染验证。

同素材、同文案、同时间输入首先保持原效果：核对冻结身份、对象与动作调用，再比较代表帧及连续动作区间。只有实际改动的行为需要新增渲染证据；优先复用原素材和产物，必要时渲染短区间。更换口播时，以新音频及语义事件重建适配器确实支持的时序；固定时长模板不得宣称任意换稿可用。

新正式制作默认高清、主声音开启、真实视频素材；代理、低清、静音只属于检查配置。历史模板4/5的冻结照片样式仍按原受控范围保留，开放新视频/高清有声制作须先适配并验证。既有6–11的正式配置不等于已验证完整高清有声导出，交付记录须保留这一界限。每套模板分别说明支持、待适配与本机缺依赖，画廊可见不等于生产就绪。

对外正片的可见文字不得带内部批次号、DOCX文件定位、调试或制作状态；合法事实来源与品牌说明按其真实用途保留。来源字段若由原渲染器上屏，也须按可见内容验收，不能只当后台证据。修正此类问题优先改本期已开放输入，保留旧片/冻结及成功声音素材，仅定向核验变更区域；不为此重复购买配音或数字人。

未安装私人原包时，画廊仍从`templates/motion-replay-presentation.json`列出八套原样式，标记需导入原包；该展示数据不授予执行能力。优先复用本机原封面，允许的原版公开视频可作为样式参考；没有公开参考或授权本机图片时明确显示待恢复，不猜链接、不重画或分发私人包内资源。

升级目标覆盖可识别的海客旧版本和分发家族，不局限1027。同一句Agent指令应自动识别便携包、历史布局和Git源码checkout，沿相应安全路线更新并保留私有配置、作品及未提交改动；ZIP安装事务拒绝覆盖Git时，Agent须继续采用版本管理/隔离工作区路线，不能以不支持作为最终交付。发行包需包含实际所需且可合法分发的组件、字体、依赖和固定身份，不能只展示封面或要求用户事后补缺件；不得将私人包、密钥或本批私有素材混入公开包。

闭包审计先明确分发形态，再分类实际调用图：自有源、第三方可独立分发源、仅限应用集成的依赖、安装时从固定官方来源恢复的运行时、用户私有输入分别记录来源、摘要、许可和恢复条件。独立组件归档与完整海客应用不是同一范围；独立归档排除的文件若是应用实际必需依赖，须在完整应用所需清单中明确保留其许可条件和恢复步骤，不能据其余文件校验通过而静默漏件。仅限应用集成不等于无条件MIT，也不能不核实际许可和分发形态就推断完整应用必须删除该依赖。原版权、完整许可和NOTICE按实际条件随集成保存；各模板最终关键调用和完整复刻仍须验证。

原已验证渲染链能按真实版本、官方锁定来源与文件摘要恢复时，优先在隔离树恢复并核对实际调用。依赖较大、锁文件尚未完成核对或依赖并非无条件MIT，本身都不能证明必须替换渲染器；不得以较易打包的桥接或近似实现代替原效果。确有不能恢复的必需实现时，再建立独立候选身份、保留原源并对照验证。任何此类范围/路线结论须附实际证据，不能由静态目录扫描、源码归档或实验短样推升成最终闭包通过。

按用户最新优先级，模板可用性收尾并锁定现有完整片后，继续更新器整合；不等待装饰精修或为微小差异重复导出。升级仍须保留配置、作品和未提交改动，包含或自动恢复必需组件，并验证实际模板调用。复用已成功的完整片、冻结输入与原完整模式证据，在真实升级目标做逐样式关键调用的短区间实际自检；确有使用故障时才修复并重验相关范围，不为每次升级重新导出18条长片。完整片证据、短自检、各旧版家族的升级事务、公开下载及真实物理机分别记录，范围不足时明确说明，不能互相冒充。此优先级调整不表示更新器或全部目标环境已验证完成。

编号2–5的输入及实际动作调用见[原组件旁路说明](../templates/motion-replay-numbered-02-05/README.motion-replay.md)；编号6–11见[视频组件与受控槽说明](../templates/motion-replay-numbered-06-11/README.md)；导入包逐路线输入与边界见[MOTION_REPLAY_IMPORTED.md](MOTION_REPLAY_IMPORTED.md)；一句话更新见仓库根[UPDATE_WITH_CODEX.md](../../docs/UPDATE_WITH_CODEX.md)。已有授权继续沿本次及有效历史记录核对，更新检查本身不新增素材许可确认步骤。
