# 店长账号·Hum亲子剪纸

文档类型：video-template-runbook。标准：video-template-v1。规格：[本变体规格](video-template-spec.json)。范围：20秒、1440×1800、30fps；已有素材墙口播的 Hum 视觉升级。技术、视觉、连续听看与用户确认按本变体实际证据分别记录。

本机已完成原素材20秒变体：统一队列 `PQ-ade62e819dc7739cf58f`；成片视频流20,490,695bps、600帧、完整解码，音频−16.56LUFS/−3.74dBTP。原版、新版和同步对比片解码音频完全一致；26个编码时间点及3张原尺寸帧实际查看，工作台播放器0→20秒通过。规格ready限上述受控范围；连续听看、设备与用户审美保持待验。原草稿与原片保留。

## 入口与真值

父执行契约沿用 [口播素材墙](../motiongit-narrated-pilot-v1/README.md)。设置 `props.visualStyle="hum"`；省略或设为 `original` 保留原版视觉。当前Hum支持 `wall`、`focus`、`statement` 与原全局人物窗口；两卡 `select` 明确不在本变体范围。工作台 `/motiongit` 可保存、复制和预览本期草稿；Hallmark参考选择与实际 `visualStyle` 字段分别保存。

视觉实现和参数真值为 [hum.tsx](../motiongit-narrated-pilot-v1/hum.tsx) 内的 `HUM`、`tornEdge`、`Sheet`、`Backdrop`、`HumWall`、`HumFocus`、`HumPresenter` 与 `HumContent`；通用几何沿用父 `layout.json`。Hum颜色与纸张材质由该文件控制，父 `props.palette` 在Hum变体中仅为兼容输入，改变它不改变Hum颜色。正文和标题使用本期已绑定中文字体，不将英文Chillax误写成已加载中文字体。

素材、封面、媒体入点、字幕、人物来源及出镜时窗和唯一 `master.wav` 均来自本期冻结输入。原版与新版沿用同一母带，因此口播、BGM和SFX不重混、不重生、不变速。纸边是固定种子多边形，纤维为固定种子 `feTurbulence`；帧钟之外没有随机状态或CSS动画。

## 设计与原参考差异

参考为 [Hallmark Hum](../../design/hallmark/themes/hum.md) 与同名实际看过的网页样图：奶油纤维纸、分工明确的黄/蓝/珊瑚/薄荷色、撕边及右下投影。网页布局、示例文字和照片没有进入成片。

按用户要求保留原级联与点击展开机制：卡片每3帧错峰、18帧入场；每个场景实际 `selection` 决定光标、选中、展开和稳定时点，所选卡片的同一媒体ID持续存在；人物大小变化沿用同一原声时钟。Hum网页的 `never scale()` 与照片数量限制不覆盖本次已明确要求保留的原视频动画及素材墙。

新增纸框略缩小素材内窗，全部使用 `contain`；裁去的是纸框边缘，实拍和人物保持全幅。卡片起始旋转交替−1.1°/1.2°，选中卡旋转随展开回到0；纸托用黄色突出所选对象。字幕在原区域新增奶油纸条，未改变任何文字或时钟。

## 制作与恢复

1. `input`：父草稿和全部既有来源回执。`action`：复制为新草稿，设置 `visualStyle=hum` 和 Hallmark `theme_slug=hum`，核对其余参数与输入SHA全部相同。`output`：独立新草稿和本期冻结请求。`gate`：除视觉风格外的内容、时钟和声音保持一致。`recovery`：读取原编号继续；保留原片。
2. `input`：本期完整来源与参数。`action`：先看开头、展开和人物状态，再用根目录 `Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py preview <草稿编号>` 进入父合同的统一队列；此路线preview会生成完整测试片。`output`：完整本地4:5样片与技术QA。`gate`：本期来源、规格阶段的开发样片范围及父合同检查通过。`recovery`：按同一请求/队列恢复，不新增配音或人物调用；实现变化则另冻结版本。
3. `input`：实际编码视频、原片和母带。`action`：检查级联/点击/展开/稳定状态、竖横素材、人物大小边界与字幕；比对两片音频，制作同一时钟的并排审阅片。`output`：真实比较文件、抽样帧和分项验收。`gate`：正式新版为4:5；并排片仅是审阅衍生物，单独标明尺寸；音频来自原片单轨，避免双重人声。`recovery`：定位受影响视觉后新冻结，保留原素材、母带及上一版。

## 本期位置

2026-10-27恢复根为仓库 `.local/hum-upgrade-20261027/`，其中 `draft.json`、`request.json`、`preflight.json` 保存实际草稿、请求与范围；最终验收另记 `REVIEW.json`。本期使用已有录音、素材、人物和混音，零新云调用，不发布。连续听看、真机外放和用户审美须按实际执行记录，不能由渲染成功推定。
