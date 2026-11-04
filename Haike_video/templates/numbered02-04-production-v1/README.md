# 编号2/3/4完整正片旁路2.0.0

三套分别保留活力现场、Nana薄荷十三景、青珊瑚现场笔记四布局。旧精确版本、旧registry、原renderer和已交付模板5均不改；本目录通过`build_sources.py`从冻结源码派生，`derivation.json`保留原SHA与可审查转换。所有新增源码由`numbered-02-05-production.json`绑定，适配器`motion_replay_numbered_02_05_full`，生产合同`motion-replay-numbered-02-05-production-v1`。

- **2**：倾斜双窗/分割线、虹膜、同源放大镜与箭头、叠卡、门店定位与楼层条、爆炸贴与邀请扇卡。每个动作读自己的语义窗口，保留原曲线/空间值和物理历时，扩展真实视频与阅读区间；声音不拉伸。1080×1920/24fps，原540×960设计等比放入上方90%，底部增加完整字幕/法律说明。原照片卡变连续实拍卡，末段人物按实际生成域采样。
- **3**：保留原十三场16:9几何、原生TextBuild/TextReveal/PromptSend/AgentSteps/TextHighlight/TextSwap/CaptureReveal等真实组件。原截图槽变完整时长实拍视频；原辅助矩形明确区分“门店实拍”和“侯总AI数字人”，首尾人物仅消费同声源原窗口。每个场景/内部cue独立按真实ASR编排，1920×1080/30fps。
- **4**：保留原RecipeStage的hero/duet/cards/summary布局，直接复用原ParallaxDepth与buildMotion的几何、曲线和66帧动作。Freeze只决定几何姿态，`VideoImage`将媒体局部帧映射回全片真实时钟，不冻视频。720×1280设计完整映射1080×1920；摘要、完整字幕、非医疗说明和同源首尾人物分别占区。

同稿/音轨可复用，但每套必须实际核对各自原参考关系与新状态，不能以同一母版换色替代。来源图和旧静音/低清预览不升级为本轮成片结论。

准备目录包含`public/episode.json`、完整48k双声道PCM16`master.wav`、`font.ttf`、实际MP4；`preparation.json`绑定这些文件和`reuse-source.json`/`materials.json`，后者绑定原声音/真实ASR/HQ窗口及原片。本入口只复用既有付费成果，不提供购买或自动重发。媒体槽必须有真实视频时长，未覆盖时阻断，不循环、冻结或变声补足。Nana静态输入、错误动作版本、未绑定素材、场景空白、人物口型时钟移动和来源变化都会阻断。

公共`motion_replay.prepare`读取模板精确2.0.0和`{data,action_ids?}`；动作只接受完整固定顺序。所属producer的`admit(workspace,data,phase='frames'|'render')`产生冻结请求，先初始化本期项目。由公共`scripts/motion_replay_production.py submit --request <JSON>`暂停入队，再`execute --job-id <原ID> --confirmed`领取；所有父视频沿已有单道。不能直接运行render.cjs或用JSON指定任意模块。

预览和导出读取同一episode与bundle，源/资源/运行时/图片SHA随审查绑定。实际关键帧通过后写`design-review.json`，只对同身份执行`render`。最终输出实测视频≥20Mbps、完整音轨、全解码，并登记作品；编码代表帧、声音技术、连续听看、设备外放与发布分别记录。新生效项目数据和实际交付保持私有，不打包原片、人物、账号或供应商回执。
