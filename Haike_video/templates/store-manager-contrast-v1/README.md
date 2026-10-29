# 店长账号：风格13与风格11

跨窗口复刻入口：[13独立Runbook](../../../Haike-Videohub/agent-runbooks/店长账号模板13-橙绿双实拍.md)、[11独立Runbook](../../../Haike-Videohub/agent-runbooks/店长账号模板11-紫柠圆场.md)。包含完整坐标、素材规则、字幕、混音与精确CLI命令。正式成片默认路径读取仓库根.local/store-manager/defaults.json，当前为用户指定的成片10-23/店长账号目录。新风格14–17六秒开发样片见[独立实验模板](../store-manager-lab-v1/README.md)。

本次由招商撞色5秒样片扩展到完整店长账号视频，固定4:5、1440×1800、30fps；不改旧11–13样片。源码index.tsx为视觉参数真值。现阶段implementation/ready，仅本期冻结输入、本机合成与技术/抽帧范围；设备听审、用户确认和平台投放待验，详见[验收范围](TEST-REVIEW.md)。

13沿用森林绿#164B34、橙#FF8B35、米纸#F9EACB。人物在左上440×550相框，右上双行主题。下方630×730和620×840错位窗口全片只放原片实拍，不用文字卡替换。11沿用紫#5426C8、柠黄#E6FF59、淡紫#F4F0FF：开头3.6秒及26.5秒至结尾为大圆人物，期间为左侧650×1010实拍胶囊、右下490×490人物圆和短主题。人物始终使用全局时钟，不因换框重播。

微软雅黑；字幕62px、单行最多17字，底板x65/y1570/w1310/h132，5帧位移8→0px与scale .99→1，不做逐字闪烁；地址30px位于底部35px。标题按章节切换，13为136px或116px，11为112px，最多2行。所有视频静音，仅一个48kHz母带；原配音不变速。实拍Sequence使用源入点、原速、contain，保留整个主体；每个镜头最多4秒，不生成低清代理。

原画质原片与高质量数字人按SHA复制进项目，渲染PNG帧至CRF1/YUV444高保真中间片，再以H26420.2Mbps CBR交付（20Mbps档留余量），最终实测视频流≥20Mbps。当前Remotion拒绝H264 CRF0，因此中间片并非数学无损，不把它描述为无损。原素材不被改写或预压缩。已授权BGM按独立音轨测量并匹配外放参考，保留侧链与首尾淡化；轻dong/whoosh对齐开头及章节切换。最终AAC真峰值≤−1.5dBTP。

执行合同store-manager-contrast-v1：backlot/studio_store_manager.py prepare冻结props及原片→submit paused→ProductionQueueWorker.run_local_recompose。仅本地合成；高质量云人物按现有独立附件记录任务ID恢复。统一队列有其他任务时等待，不中断。源码变化创建新请求；已有产物校验SHA后复用。

本期输入及字幕词时钟、选段证据、来源文件、费用回执存于.local/codex-runs/store-manager-production-20261023。不可将具体健康终端画面推定为医疗功效；文案由本次用户确认，仅制作不发布。

风格11的人物圆采用cover、objectPosition=50% 42%，去掉圆内侧边留白；实拍仍contain。每期需核对新人物脸部与头顶安全范围。[13视觉规格](variants/13/video-template-spec.json)与[11视觉规格](variants/11/video-template-spec.json)分别绑定输入与验收。
