# 海客多屏口播模板

这是侯总亲子宣传片的复用入口，模板 ID 为 `motiongit-native-story-v1`。当前规格与验证范围见[规格](video-template-spec.json)和[验证摘要](reference/validation-summary.json)，操作由[项目 runbook](../../../Haike-Videohub/agent-runbooks/海客多屏口播模板.md)约束。

当前为 `implementation + ready`：限定本机受控输入、本期4:5 `auto`完整产物技术/编码抽样视觉，以及新原生横版入口实际准备/预览/冻结范围。`small/hidden`已预检，首次使用仍须对应画面验证；连续听看、音素口型、真机与用户审美确认分别待验。

同一已适配包内，换完整口播、真实素材、完整同声源数字人及文案槽即可准备新片；不复制本期临时脚本，也不改动 MotionGit 保护实现。原生包、个人素材、已生成数字人、系统字体和凭据由执行环境提供，均不随公共模板分发。

## 与旧入口的区别

- 本模板固定本期已选的 S01 开场与作品墙、S04 分类与镜头、S08 归纳与行动，保持整组动作。横版由官方运行时保持原生效果；4:5由项目 `native-story` variant按目标画布重排，保留动作语法，几何与原生版分别验收。实际时长来自新口播，语义内容由 Agent 完成。
- [深色立体完整模板](../motiongit-dark-full-v1/README.md)同时记录十组完整原生对照和项目 Remotion 重建。本模板的原生内容替换与该重建分开记录身份，不沿用其几何或验收结论。
- 官方原生公开尺寸仅横版/竖版，没有任意4:5画布。旧 `portrait_companion` 是完整横画面缩小后上下留边，保留用于恢复旧作品。本模板4:5通过项目Remotion在1440×1800/60fps直接排版，独立核对人物、四卡、墙和字幕，不能宣称与横版逐像素相同。

## 每期换什么

| 输入 | 约束与缺项处理 |
|---|---|
| 完整口播 WAV | 真实时长为主时钟，原速完整保留；不按字数估时，不循环或变速填槽 |
| 同源字幕/句时码 | 来自该 WAV 的真实转录，绑定原声 SHA；换口播后旧字幕和旧人物不能混用 |
| 完整数字人口播 MP4及头像 | 与同一 WAV 对应，覆盖全片时钟；只换人物形象时先经现有数字人阶段生成，不循环几秒缓存 |
| 四卡/素材墙/镜头实拍 | 资产有稳定 ID、来源和 SHA；静帧封面明确为静帧，镜头框使用显式真实源区间，不把短素材冻帧填满 |
| 内容槽 | 主题、短标题、四类标签、邀请与地址；依据实际脚本和素材填写，不保留上一期事实或把动画数字当经营数据 |
| 配乐 | 显式来源、增益、入点和循环选择。横版原生人声/SFX合入一次再加一份BGM；4:5用完整WAV、项目cue音效和一份BGM，不重复加入人物MP4声音 |
| 目标画幅 | 按当前实现的可用画幅选择；4:5与横版分别准备、预览和冻结，不由横版 pad 冒充 |
| 真实素材看帧与同源证明 | `source_review`记录每个源SHA、实际看过的帧和采用区间；`avatar.evidence`证明同声源与完整解码；`captions.provenance`绑定完整原声，不能只填“已看过” |
| 字体与动作音效 | 4:5绑定`fonts.body/display`与`sfx.tick/whoosh/dong`实际文件和SHA；来自本机已授权资源，不随公共模板打包 |

只有脚本或人物图片时，先走项目已有音频/字幕/数字人入口，取得完整同声源产物，再进入此模板。这个模板入口不会隐式调用付费服务；每期新付费按当期授权执行，历史费用上限不成为长期预算。

`examples/input.example.json`是结构示例，资源均未附带，64位全零SHA、授权/同源布尔值都是示意，不能作为真实授权或来源证据，也不能直接提交。复制后填写真实资源路径、实际SHA与真实音频/人物证明；文案和地址也要按本期脚本替换。示例省略高级`timeline`覆盖，由CLI在支持范围内按完整口播求时钟，不沿用上一期固定帧数。

输入/证明字段的唯一结构真值是 `backlot/studio_dark_native_content.py` 的 `REQUIRED/OPTIONAL` 与 `check()`：墙选帧4–64个，四卡恰4个，动态镜头源须有连续12.3秒；字幕是原生`{t0,t1,zh,en,highlight}`数组，逐词文本与真实时码一一对应。同声源证明与实际素材看帧记录须可核对文件SHA，写布尔值不能代替真正检查。

## 执行顺序

1. 复制[输入示例](examples/input.example.json)到本期忽略目录，填入本期资源和内容。读取当前CLI帮助，以源码参数为真值；示例资源须由用户自备。
2. 核对官方包与helper版本、输入来源、完整时钟、素材区间和工程/缓存卷余量。预检通过只证明参数可执行，尚未证明画面好看。
3. 按画幅准备：横版走官方公开 check/plan/prepare/preview，4:5走项目桥接和Story组件关键状态。实际查看最后一张卡、最长标题、人物遮挡、素材墙、镜头框、接缝和结尾；4:5不要求先做横版原生工程。
4. 保存绑定预览文件和 SHA 的实际审核回执，然后冻结到统一生产队列。渲染恢复使用原请求与原任务编号；不为恢复再生成口播或数字人。
5. 核对正式产物的尺寸、帧数、20Mbps、AAC48k双声道、真峰值和完整解码，再查看最终编码关键状态。连续听看、音素口型、真机与用户确认分别记录。

后续直接呼叫“用海客多屏口播模板，换成这份口播/素材/数字人，做4:5”，由 Agent 按本手册整理本期输入。存在本机私有`.local/motion-native-story/defaults.json`时，可补入已验证的工具、字体、音效、配乐和原生依赖缓存；口播、字幕、数字人及其同源证明仍逐期绑定，不能把旧人物配到新声音。另一台机器先核对本机依赖与合法资源。

本目录的规格是作者与执行者共用的契约；ready只覆盖验证摘要声明范围。某一输入通过不自动证明任意长度、人物裁切或其他画幅通过，新输入仍执行本期预检、实际看帧和声音检查。标题/标签按实际字体测量字宽，溢出会明确阻断，由 Agent 按本期语义缩写，不能默默截字。

### 真正4:5

从仓库根目录执行。`check`只读；`build`写本期素材与公共构建，不制作整片。桥接不带`--render`只输出可检查的`portrait-input.json`；带`--render`才沿既有统一父队列渲染，没有新增云调用。

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_native_content.py check --input <本期input.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_native_content.py build --input <本期input.json> --out <本期持久构建目录>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/native_story_portrait.py --build <构建目录/content-build.json> --check
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/native_story_portrait.py --build <构建目录/content-build.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/native_story_portrait.py --build <构建目录/content-build.json> --render
```

前两步的输入`layout`须为`portrait45`。布局来自 `studio_native_story_portrait.py` 的三组语义桥接和 `motiongit-dark-full-v1` 的 `native-story`组件；桥接的`--check`不是画面审核。正式产物仍须实际查看关键状态和源素材/人物/字幕避让。原请求恢复用既有`dark_full.py --request <dark-full-request.json>`，不重新调用数字人。

人物模式使用桥接参数`--presenter-mode auto|small|hidden`：默认`auto`随动作使用大框/圆窗，`small`始终小圆窗，`hidden`不显示口播人物。三者都复用已验证完整数字人与同一原声，不产生新数字人费用。模式改变需独立输出路径；预检通过不证明该模式的视觉已验收。

两引擎各自分配完整组：横版以`profile.json`的保护窗口及348/695/793帧基准调静止间隔，官方plan最终裁决；4:5以项目完整组下限8.3/11.5/8.2秒和权重1/1/3按完整原声分配，物理缓动保持固定秒数。本期30.6秒得到530/721/585帧，仅为本输入结果，不能写成下一期固定时间。两引擎不共用横版anchors，也不宣称动作时序相同；时长不足或静止容量不足会阻断，不能靠拉伸口播补齐。

### 官方原生横版

改输入`layout`为`landscape`，用独立构建目录。执行相同check/build后，按顺序运行内容CLI的 `native-plan --build`、`native-prepare --build --review`、`native-preview --build --times`、`native-manifest --build --review`。每个命令均可从 `--help`读取当前必需参数。

计划审核须绑定本期`plan/inputs.json` SHA、`actual_plan_inspected=true`与实际素材图片；最终审核须绑定未修改的本期`preview.json` SHA和至少五张真正查看的本期关键图。审核字段与文件归属由 `native_prepare()` / `native_manifest()`验证，不自行把未看过的图记为通过。

`native-manifest`只写`native-queue-input.json`，不入队；实际制作使用 `Haike_video/scripts/dark_native.py --input <native-queue-input.json>`，旧请求恢复使用同CLI `--request <dark-native-request.json>`。这条横版路线保持官方完整组，`portrait_companion=false`，不会附带横画面留边版冒充4:5。

首次原生依赖安装可用输入可选`native_dependency_cache`明确指定已存在缓存目录。编译器核对官方`dependencies.json`及锁文件身份，官方`setup`继续验依赖；未提供时用独立新缓存。新CLI本机已实际验证至五张预览、幂等manifest和freeze-only，没有为证明准备流程再渲染一条原生全片；原生完整父片的历史生产证据在验证摘要单独列出。

Windows完整原生导出还需短实例路径。可选`native_instance_root`是父目录已存在、不超过110字符的绝对缓存路径，原包与来源文件不变；默认旧目录结构保留。新网页制作入口自动配置短实例，避免导出事务临时文件超过Windows路径长度。修改配置或编译器后生成新构建，不回填旧冻结请求；网页/HTTP/CLI完整流程见[制作入口](../../docs/MOTION_TEMPLATE_STUDIO.md)。

## 固定边界与恢复

横版轨迹、缓动、状态顺序、整组依赖和固定品牌标记由已验官方运行时持有；4:5的几何与动作实现由项目Story组件固定，保留动作语法并独立验收。公开槽以外的变化属于新适配；下一份 `.motion` 包需先核对其公开契约和布局，不能直接当成这份模板。

时长不足以承载完整动作组时，预检应明确阻断并给出实际所需时长，不能快放整组或切掉结尾。素材不够时补素材或改变已支持槽的内容，保留现有付费产物。原生公开字段仍固定的章节小标题、角标和人物外框按当期差异说明保留。

输出完成后保留本期输入、原生计划、预览审核、冻结请求、队列编号、质量与独立审查回执。正式操作契约和恢复命令见 runbook；本页不保存逐次制作日志。
