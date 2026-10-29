# 门店纯实拍撞色模板18–21

2026-10-23完整片扩展：执行[完整片Runbook](FULL-RUNBOOK.md)，支持配音主时钟、章节标题和20/21可选店长短段；下文是v001六秒设计来源，不能用其180帧限制覆盖完整片规则。完整片验证范围以各variant规格及本轮实际证据为准。

Creative Production用于现场故事与关键帧；frontend-design用于颜色、字阶、版面与克制动效。6秒开发样片：同一句已确认天亮猴哥配音，不含数字人画面或数字人素材槽。4:5、1440×1800、30fps，20Mbps档，原始素材不预压缩。单镜3秒，3秒切换与whoosh峰值同步。

## 设计计划

| 编号 | 配色 | 结构草图与字体 |
|---|---|---|
| 18 橙紫现场海报 | 橙#FF782E、紫#4928B8、淡杏#FFE4CB、白#FFFFFF | [巨型标题][窄侧栏/完整实拍大窗][字幕]；黑体巨标题，微软雅黑字幕；海报式实拍为主 |
| 19 冰蓝樱桃双联 | 冰蓝#C6F4FA、樱桃#BF234B、深蓝#163852、白#FFFFFF | [短标题][左机器人/右体验双联][字幕]；两条竖片平等并排，人物反应与机器同屏 |
| 20 酸橙深蓝横切 | 酸橙#D7F451、深蓝#203C69、亮蓝#5B9FE6、白#F8FCFF | [顶栏][单竖片居中][横切巨字][字幕]；素材面积集中在上部，下方夸张横向标题 |
| 21 玫粉孔雀拼接 | 玫粉#FF9DC3、孔雀#006D71、浅粉#FFE5F0、白#FFFFFF | [左竖题/右大实拍][左小实拍跨接/右短句][字幕]；错位直角拼接，实拍之间形成主次 |

复核：不是把旧数字人窗口简单换成素材；18单画面海报、19并列观察、20横切题字、21主副拼接。四者独立配色与占比，不加无意义序号、渐变和通用卡片阴影。全部只用现有实拍，无AI生图。原片contain避免截断机器人和门头；侧边色留白是设计的一部分。

## 共用参数与生产

index.tsx为像素/颜色/动画真值。输入style18–21，durationFrames180，shots两轨left/right各完整覆盖0–6秒，caption三句来自已确认音频词时钟，audio=master.wav。无avatar字段、无数字人文件。字幕x55/y1560/w1330/h140、58px微软雅黑900，整句6帧easeOutCubic移动6px后稳定；地址30px/bottom44，不盖主画面。片头主图12帧克制揭幕，3秒仅换镜不闪屏。

复用前轮已验6秒配音母带：人声−2.5dB，音乐−5dB，speech-led-v1侧链threshold0.05/ratio2.5/attack15ms/release180ms，limiter−3dBFS；dong0.68秒−15dB；whoosh3秒峰值、起播2.874秒−19dB；BGM尾0.45秒淡出。原片静音，不与母带叠加。母带与来源回执按SHA冻结。

执行适配器backlot/studio_store_footage.py，原生prepare→submit→ProductionQueueWorker.run_local_recompose。PNG/CRF1/YUV444p高保真母版，最终H264 slow20.5M CBR/2M缓冲/AAC192k，实测视频流≥20Mbps；不是数学无损编码，原片字节保持。完成后检查完整解码、尺寸时长、真实导出帧、字幕和声音峰值。

复刻CLI：scripts/store_manager_template.py --request <冻结request> --check；去掉--check复用归档，--fresh当前实现重渲染。默认根.local/store-manager/defaults.json，本轮短样放无数字人模板测试子目录。保持specification六秒开发阶段；完整片、异机、平台与设备听审分别验收。
