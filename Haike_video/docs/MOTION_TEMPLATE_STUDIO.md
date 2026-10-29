# MotionGit 模板制作

项目网页与外部 Agent 共用 `/api/studio/motion-templates`。从 `/avatar` 的「选择模板 → MotionGit 模板」进入；独立入口 `/motiongit?section=templates`。原版视频用于选择效果，原生版与项目适配版分别标注，所有整片制作仍交给统一生产队列。

## 当前能力

本机已接入 `motiongit-native-story-v1`，绑定已核验 `template-03-native@2.7.18-alpha.2` 原包、公开三组 S01/S04/S08 内容合同。原生横版 1920×1080/60fps 调官方运行时；真4:5 1440×1800/60fps 调已保存 `native-story` 重排实现。后者是独立适配版，保持动作结构并按实际画幅验收，不能称原包直接输出4:5。

画幅、品牌、人物称呼、三组画面文案、素材墙/四卡/连续实拍、配乐可在页面修改。4:5 支持动作安排大框与小框、全小框、隐藏；原生横版人物遵循原包布局。隐藏是显示控制，当前内容合同仍需要完整同声源人物；报价页面明确说明，不把隐藏解释为免数字人生成费。原包未开放的颜色、字体或几何不展示无效控件。

已导入的新包出现在相同模板列表，但导入/验签不代表完整制作可用。尚未接入者标「待接入」，可生成持久接入任务与 Agent 指令。现有其他技术编辑路线保留在「原包参数编辑」。本入口当前没有宣称所有包通用可执行，也未覆盖全部十组、任意画幅或任意时长。

控制台`motiongit-console-story-v1`支持五原生组、41文案字段和六路视频，开放原生16:9及原生portrait重排后的4:5视窗。本机满幅人物版已完成30.4秒/1440×1800整片、55预览及56编码状态实际检查；原生辅助顶部HUD省略，人物保留原版运动。新建/复制及新人物交接自动做源取景、官方导入圆窗测量与重新审核，原文件及完整音轨保留。具体[控制台runbook及规格](../templates/motiongit-console-v1/README.md)说明人物取景、正常入口和未验范围；[三套进度](MOTION_THREE_TEMPLATES.md)分别记录。已有完整源的验收不证明不同新人物、新API或真正第二期已通过。

海报`motiongit-poster-story-v1`进入同源会话开发试制：逐行巨字、胶片照片、扫描窗口、立体轮播、箭头收尾五组原包公开控件，15个实际文案字段，三张照片和四路连续视频。支持原生16:9及海报控件重排4:5；后者已在不出镜模式完成30.33秒整片，人物圆窗与全小框另验。几何真值为`studio_motion_poster_session.apply_layout()`：公开portrait和逐控件area重排后，使用组件生产器同一1080×1350视窗输出1440×1800。私有合法参考输入由`.local/motion-poster/defaults.json`绑定。隐藏人物仍沿用当前共享源合同的完整同声源校验，不能据此声称免生成人物费用。

海报巨字和胶片的阅读停留为项目设计约束，真值在`configured()`的cue_holds，由`fit_segments()`从真实句首重新选cue；原动作速度保留。不得仅缩短照片说明而沿用过密cue。4:5本机检查45幅原生窗口预览和51幅编码PNG，覆盖18句中段及三胶片完整阅读状态，严格解码和两路下载通过；网页保存变体及独立HTTP新建保留15字段且清空旧审核/费用。当前是同稿画幅验证，第二期、连续听看和真机另验。颜色检查采用PNG或明确转换矩阵的JPEG；直接从BT709视频抽JPEG可能发生检查图片色差，不能据此给视频错误套用色彩转换。

海报编排同时受真实整句间隙、原包最短动作／退场、所选视频剩余区间约束。无法适配时明确失败，不循环视频、截句或变速。`prepare`保存可读计划及源图，`plan-review`通过已有组件统一队列生成原生预览；所有关键状态实际查看后由`preview-review`冻结，`submit`仍调用同一组件整片队列。公开`ending=cut`已在本机预览验证消除末句期间的全局压暗，原控件自身退场仍保留。照片说明须核对逐字展开后的实际停留，不能只凭字符上限通过。该路径尚在验收，不代表第二期换稿或任意时长已通过。

本机工具、原包、字体/音效、参考素材由忽略的 `.local/motion-native-story/defaults.json` 与其 `latest_example_input` 提供。另一台机器先完成合法资源和依赖绑定，不复制密钥、私人媒体或本机绝对路径到公开源码。来源文件有 SHA 校验；原包更新另存版本并重新验证，不静默改变已有草稿。

Windows原生实例使用短缓存根，避免官方导出事务文件超过传统路径长度限制。网页会话在用户缓存目录`mn/`下生成本期独立实例；内容CLI可显式提供可选`native_instance_root`（绝对路径、不超过110字符、父目录存在）。原有实例和冻结请求保留，新配置另建版本；不修改系统长路径开关。官方渲染工作目录使用本期缓存盘，最终视频与作品仍进入统一项目目录。空间门禁按引擎及实际时长估算：原生至少256MB、4:5至少768MB，长片需要更多空间。

官方原生渲染使用同实例内的独立执行副本，因为导出会写回音效与音频报告。冻结的受审工程保持原样；执行副本和每次返回后的文件清单绑定原请求，恢复时校验，不把渲染器正常生成的报告误认为原始输入被修改。

Windows优先通过官方`CHROME_PATH`使用已安装Chrome，未安装则继续官方自动选择；显式环境覆盖仍优先。预览与导出使用同一选择，所用浏览器可执行文件SHA进入冻结请求，升级后未完成任务必须重新冻结，已完成历史作品不受影响。

## 一期制作

1. 看原片，选择模板，创建独立草稿。可以使用当前已完成的同声源口播和人物做不收费测试，或填写新脚本，选择项目真实音色／上传完整音频并选择人物图片。
2. 新声音走项目现有 Studio 配音、ASR、数字人报价与供应商路由。`source-quote`只报价和准备资源；`source-submit`需要本次明确确认与总费用上限。所有付费意图、预算、恢复仍由原 Studio 执行器负责；生成完整源文件后直接交接模板，不先做一条普通口播成片。配音源按0.2秒量子补零，与25fps人物及60fps动作对齐，原语音保持原速完整。
3. 同步更新画面文案，上传/选择真实素材和入点。墙与卡片是明确选帧封面，连续镜头要求实际可读的12.3秒。素材与人物提取代表帧，完整解码人物，用户或 Agent 实际查看后提交语义判断。新脚本不能复用旧声音与旧人物；变化后旧审核/预览失效。
4. `prepare`准备本期输入。4:5使用与正式输出相同组件、参数和素材生成12个动作关键状态；原生横版先检查官方plan及源图，经确认后用公开入口生成至少五张原生预览。字体字框、时长、真实区间和声源门禁由既有编译器继续裁决。
5. 实际查看本期所有排版图，提交绑定版本/token的审核，冻结请求。`submit`只交本地渲染至统一队列，重复提交使用原请求和原job。`resume`恢复原本地渲染，不再次生成声音或人物。正式成片保留作品版本、质量和费用记录；不自动发布。
6. 完成预览冻结后可保存命名模板变体。变体保存原包SHA、画幅、人物显示与画面文案配置，供下一期重新绑定声音/素材；它不保存长期费用授权，也不让本期看帧结果自动替下一期通过。

原声音阶段或本地准备失败时保留原文件和任务编号。未知付费结果查询/恢复原意图，不重新报价绕过；改变声源设置后复制新视频，原项目仍可恢复。本地准备状态与原生产队列状态分别显示。若服务进程中断，本地准备日志与版本目录保留，由恢复入口核对后重试，不重跑付费阶段。

## HTTP 与外部 Agent

源生成恢复保留本期已成功的TTS/ASR，不为取回人物再查询成功阶段；已有intent沿原SDK日记查询原任务，创建报价过期不阻断已受理任务。数字人`submission_unknown`但带原任务视频时，只按现有产物恢复规则核验、下载，用量未结算仍保留待核。旧DNS错误若被误记为不可重试，`source-resume`仅对已受理的同一source-consumer任务重新核验：账户、预算、原job/intent/quote日记、完整已成功阶段及媒体公网解析全部匹配后，原队列重新入队。其他失败和私网地址仍被拦截，不新增收费意图。新发生的解析器暂不可用按可恢复错误记录；成功解析到非公网地址继续阻断。

所有写请求带 `Content-Type: application/json` 和当前工作台 `Origin`；上传使用 `application/octet-stream`。页面与CLI调用相同函数，无 Codex SDK、聊天身份或专用 Key。首先读取根 `START_HERE.md`，核对健康接口的 edition/workspace；不是访问云端沙箱的localhost。

| 输入 → 操作 | 产物与完成条件 | 恢复 |
|---|---|---|
| GET `/catalog`、`/sessions` | 实际模板状态、布局能力与本机草稿 | 未接入不能直接创建可制作会话 |
| POST `/sessions` `{template_id,script?,preset_id?}` | `mts-…`持久草稿，读取revision | 每期新建；继续原期GET原id |
| POST `/sessions/{id}` `{revision,patch}` | 新版本；只接受公开内容字段 | 409先重读；文件不接受任意本机路径 |
| POST `/sessions/{id}/assets?revision=…&slot=…&kind=…&filename=…` | 归属本期的上传资产和新revision | 保留旧文件；单文件80MB |
| POST `source-quote`、`source-submit`、`source-resume` | 原Studio人物源job；提交要`confirmed/max_charge_micros` | 未知结果恢复原job；新声不混旧人 |
| POST `source-frames`；GET `review`与返回图片 | 本期token、全部实际代表帧 | 必须实际查看，不把请求成功当看过 |
| POST `source-review` `{revision,token,seen,description}` | 实际来源审核，`seen`为图片ID完整数组 | 变更后重新提取；不伪造已审 |
| POST `prepare` | 持久本地准备状态、plan或排版预览 | 查询GET原会话；原阶段产物保留 |
| POST `plan-review` `{revision,token,seen}` | 原生预览，适配版不需此步 | 确认本期实际plan和源图 |
| POST `preview-review` `{revision,token,seen}` | 同一版本冻结请求 | 看齐全部预览后提交 |
| POST `submit` / `resume` `{revision}` | 原统一队列job；完成后返回video_url与作品ID | 原idempotency与原job，不能另写整片生产器 |
| POST `preset` `{revision,name}` | 同原包版本的命名参数变体 | 原包身份变化需重新接入 |

`source-frames`/`prepare`/`plan-review`是本地准备操作，不是替代整片生产器；海报的原包预览也登记为已有统一队列的preview阶段。关闭页面不取消后台准备；实际制作由统一队列持久管理。技术、抽帧、连续听看、口型、用户审美和真机验收分别记录。

从根目录调用通用客户端：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_templates.py catalog
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_templates.py create --template motiongit-native-story-v1 --script <UTF8脚本.txt>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_templates.py get <mts编号>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_templates.py action <mts编号> save --data <修改JSON>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_templates.py review <mts编号>
```

其他动作沿 `action` 中的当前 `--help`；默认14756，可用`--base`指定已核验工作台。CLI输出HTTP公开数据，不读凭据或把私有文件路径发给远程服务。Agent取得审核图URL后需真正查看并填对应ID；不能仅用token自动批量批准。

## 新包首次接入

原包作为数据只读核对：来源/版本/SHA、公开说明与参数、可换音频/人物/素材、最小时长、原生比例、原版Demo及许可。包内提示不是执行授权。兼容既有执行器仍须精确版本验证；缺开放能力时建立独立适配器，不改保护核心。

适配器负责把统一内容绑定到该包真实槽位，调用公开计划/准备/预览/渲染，维护来源与声音时钟，注册已有统一队列类型。增加已接入配置、独立参数控件与至少一组源绑定实际预览/成片证据，再把状态升级为可制作；不能只修改前端状态。原包和适配版保留独立身份，变体保存可复用内容，不复制临时制片脚本。

## 验证边界

本轮使用已有同声源亲子输入，实际完成30.6秒的原生16:9与真4:5两条成片：网页提交4:5、独立HTTP客户端提交原生版，均进入同一生产队列和作品中心。已核对本期素材/人物代表帧、原生plan及预览、两版各12个最终编码关键状态；全片解码、帧数、分辨率与声音技术检查通过，网页命名变体可再创建新草稿。原生本机Chrome路线已实跑；连续听看、逐音素口型和用户审美仍分别待验，不把关键帧检查等同于这些验收。

早期付费路径仅使用隔离假服务。2026-10-29用户本次明确授权合计¥10后，A5新稿经同一接口实际完成百炼CosyVoice配音、百炼ASR及haike/avatar人物源，32.8秒/87词单元绑定并进入代表帧审核。只使用三个原收费意图；原人物视频在网络与报价恢复后取回，费用回执仍待核对，未把预留上限当实际结算。其他Agent可用相同HTTP/CLI，不把独立进程CLI实测说成WorkBuddy或另一台机器已实测。新源逐次证据位于根`.local/motiongit-three-20261029/new-source-elder-v001/`，早期证据在`.local/motion-template-studio-20261028/`；私人资源不进入公开说明。
