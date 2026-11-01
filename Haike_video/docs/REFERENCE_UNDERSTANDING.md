# 参考素材理解：从画面证据到动作规则

适用：参考视频复刻、模板首次适配和关键动作复核。普通素材初筛继续使用现有概览，按问题升级；本入口不调用云端模型、ASR、生成服务或生产队列。

## 借鉴范围

本次参考本机 Hypit 的 `creation/reference-video.md`、`production/component-design.md`、`production/timing.md` 和 `production/review.md`，独立实现项目所需能力。没有引入 Hypit Runtime，也不声称获得其生成模型。

| 方法 | 项目原有基础 | 本次整合 |
|---|---|---|
| 全片概览后精查 | 多宫格、原尺寸帧、coarse/fine、未知项 | 保留原入口，增加指定区间连续解码和原始PTS逐帧证据 |
| 台词与画面联读 | 百炼句/词时码及音轨来源 | 同一原片SHA绑定的转录；每张图下显示对应句子，保留词ID；无词证据不生成词触发 |
| 对象持续性 | 镜头主体和动作描述 | 稳定对象ID、作用、外观、存续范围；动作引用对象和实际阶段帧 |
| 语义时间 | 真实字幕和局部cue | 区分台词、物理动作、独立编排触发；说明保留的动作和换稿后的时序规则 |
| 参考与实现对照 | 关键状态审核与编码检查 | 按含义/动作阶段明确配对，允许参考和新片对应事件处于不同秒数 |
| 持久恢复 | 指纹、版本和审核证据 | 新分析使用独立revision；复用前核验原片及每张证据图片，不覆盖既有不同结论 |

暂不引入：另一个付费生成/账号系统、自动 `.motion` 解密器、自动把参考画面还原成原作者源码的承诺。模板执行继续遵循原包公开合同、独立适配和统一生产队列。

## 执行顺序与完成条件

1. **定位。** 沿 `video_understanding_cli.py prepare/read/submit` 完成现有概览，记录目标、完整参考的叙事、持续对象、难点和待查时间段。完成条件是每个关键疑点都有区间和问题，不把离散图片称为连续观看。
2. **精查并联读。** 用下面的 `reference-prepare` 对对应区间取证。运动看连续帧，排版看原尺寸；台词使用同源实测转录。完成条件是入口、运动中段、落定/阅读和离开均有实际证据，重复系统记录一次再登记变化。实际PTS是图像时间；图下注释是该时刻正在说的句子，完整文案仍保存在JSON中。
3. **解释。** `reference-read` 后实际查看全部返回宫格及必要原图。填写模板中的全片解读、对象和事件；每个阶段引用真实帧ID。观察和解释用文字明确区分，未知项记录需补的声音、播放或局部证据。完成条件是所有要复刻的独立行为都有对象、状态、触发和换稿规则。
4. **保存。** `reference-submit` 校验任务、来源、帧引用、实测台词和不同证据层级，保存 `analysis.json` 与可读 `report.md`。完成条件是可从结论返回原片对应时刻；它仍为 `production_ready=false`，不是制片审核通行证。
5. **转为实现并对照。** 模板作者把事件/素材/画布规则接到已有执行器；按同一含义的状态生成参考/输出对照。实际检查每个场景和过渡前中后；最终编码完整解码与连续听看分别执行。完成条件依据模板标准，参数合法或图像差异不能单独证明复刻质量。

## 项目入口

从仓库根目录使用当前Python。命令帮助是参数真值；显式FFmpeg路径需同时填写配套ffprobe。所有产物进入忽略目录。

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/video_understanding_cli.py reference-prepare --source <原片.mp4> --output <本期证据目录> --model <实际模型标识> --range 6.8:8.4 --every-frame --transcript <同源转录.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/video_understanding_cli.py reference-read --task <task.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/video_understanding_cli.py reference-submit --task <task.json> --submission <已填写的submission.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/video_understanding_cli.py reference-compare --reference-task <参考task.json> --target-task <输出task.json> --mapping <配对.json> --output <对照目录>
```

不传 `--every-frame` 时，可用 `--range 开始秒:结束秒:间隔秒`；多区间重复该参数。一次最多2400帧，超过后分批缩小问题范围。范围明确包括起点、不包括终点；每次区间连续解码一次，保留实际原生帧PTS，不以固定fps生成伪帧。每页12格，默认每格480像素宽，高度按原片比例计算；竖屏不挤进横屏格。可放大，原PNG仍独立保留。

先用 `reference-scan --source <原片> --output <扫描目录> --every 0.25` 可建立低清变化索引：保留真实PTS、来源与工具SHA、逐帧差值、局部活动和最多18个建议精查窗口。它只帮助定位，不能自动判定剪辑点、动效含义或质量；默认仍为待审。读取缓存会核验来源及图片，不能把旧视频的索引套到新视频。

已有同源转录时，`reference-prepare --around "关键词" --transcript <转录> --padding 0.5` 可以直接定位画面。多次出现可用 `--occurrence 2`。有真实词边界便使用该词区间；只有句边界时保留整句，绝不按字数推算词时。

精确帧边界会先从区间前50毫秒开始解码，再按原PTS选择目标区间，防止FFmpeg微秒取整提前丢掉起点帧；没有额外补造帧。输出证据保留实际时间，不把请求秒数冒充原片时间戳。

同源转录输入为 `{source_sha256, clock:"measured-seconds", segments:[{id,start,end,text,words:[{start,end,text}]}]}`。时间单位秒；`source_sha256` 对应当前原片。`words` 可以省略，此时只建立句级证据。原视频裁切或换音后重新绑定真实时钟；已有ASR可规范化复用，不需要为了展示重复收费调用。没有转录时允许只分析可见动作，保留声音未知项。

事件的 `trigger.kind` 为 `speech/action/authored`。`speech` 引用当前转录句ID，需要逐词落点时再引用该句真实 `word_id`。`preserve` 记录需保持的状态、速度和阅读节奏，`retiming` 记录换稿后什么随语义移动、什么保留固定秒数。禁止把整个场景按文案长度均分后冒充词级绑定。

对照映射为 `[{reference_frame,target_frame,reason}]`。工具只生成绑定来源的图片和 `visual_judgment:pending`，实际结论由审片者在对应模板审核中记录。`continuous_watch/listen` 分别保存真实执行状态，抽帧不会自动将它们改为通过。

## 实现与验证入口

- `backlot/reference_understanding.py`：时码联读、原生帧、对象/事件证据与配对。
- `backlot/reference_motion.py`：变化索引、实际PTS、按实测台词定位；不是视觉理解模型。
- `scripts/video_understanding_cli.py`：保留概览并提供四个reference动作。
- `tests/backlot/test_reference_understanding.py`：同源/时间边界、真实FFmpeg非零起点逐帧、证据篡改、虚构词ID、历史结论保护及明确对照。
- `.motion` 导入仍使用 `backlot/studio_motiongit.py`；公开字段和项目适配边界继续见 `MOTION_PACK_ADAPTERS.md`。
