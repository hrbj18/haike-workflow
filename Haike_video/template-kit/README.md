# 海客全模板 · Mac 复刻包

本包用于同事之间的本地模板复刻：包括当前模板源码、视觉Runbook、已冻结的可运行实例、原画质实例素材、配音混音母带和参考成片。它不是Windows工作台便携安装包，不含账号密钥、Cookie、数据库或云端付费任务。

先双击 `index.html` 浏览模板。模板的当前源码在 `source/Haike_video/templates/`，共享手册在 `source/Haike-Videohub/agent-runbooks/`。`KIT.json`列出可直接运行的实例；没有实例的条目保留源码/说明，不能当作完整片已验收。

## Mac 首次使用

1. 将整个文件夹放在本机可写目录；不要在压缩包内运行。Apple Silicon与Intel均使用目标机自己的运行时，本包不带Windows exe/DLL或Windows node_modules。
2. 准备 Python 3.12、Node.js 22、FFmpeg。已有Homebrew时可用`brew install python@3.12 node@22 ffmpeg`；确认`python3`、`node`、`npm`、`ffmpeg`、`ffprobe`能运行。包不自动安装Homebrew，也不修改系统安全设置。
3. 在终端进入本文件夹，执行`bash setup.command`。首次npm依赖与Remotion浏览器下载需要联网。Node/浏览器会按当前Mac架构下载；原Windows环境不能复制来替代。
4. 执行`python3 tools/kit.py list`查看实例编号；先用下面的六帧检查确认本机能渲染，再导出完整片。

```bash
python3 tools/kit.py verify
python3 tools/kit.py doctor
python3 tools/kit.py render store-footage-20 --smoke
python3 tools/kit.py render store-footage-20
```

输出在`exports/`，中间文件和技术回执在`.work/<实例编号>/`。重复运行不会覆盖已存在的成片。失败保留输入与中间文件，不产生云端调用；解决报错后恢复本地步骤。首次安装和最终验收必须在同事的Mac上执行；本包在Windows准备与隔离测试，不能冒称已在Mac真机通过。

`--smoke`仅检查六帧的依赖、素材加载和编码，不检验完整片平均码率、完整字幕或声音效果。完整导出才执行20Mbps门槛。

## 字体及画质

原版使用微软雅黑、黑体、宋体。Windows系统字体不随包转发。本包随附带OFL许可证的Noto Sans SC/Noto Serif SC，由网页FontFace加载，不要求先装进系统；sans和serif角色分别映射，保持色板、坐标、字号和动效结构。字体轮廓、字宽及抗锯齿会有差异，**不是像素级一致复刻**。需要严格一致时应由同事自行取得同款字体的合法使用权，并在`tools/font-loader.ts`改为自己的字体；重新验收最长字幕和标题换行。

素材、数字人原片、声音母带按SHA256保存原始字节，没有为了压缩包预降画质。共享素材按哈希去重；运行时复制到实例public目录，以避免编辑某条片时改坏其他实例。

本地导出采用PNG帧/CRF1/YUV444p中间母版，再H264 slow、20.5Mbps CBR、AAC192kbps/48kHz立体声；交付实测视频流不低于20Mbps，完整解码及帧数必须通过。20.5用于达到20Mbps交付门槛，不代表增加原始素材不存在的细节。参考成片保留当时原编码，有些历史样片低于当前20Mbps门槛，不能将它们标为新标准导出。

## 旧片复现与新片制作

`examples/`为已冻结的历史输入和当时源码，适合验证迁移链路；`source/`为当前模板源码与手册。两者版本刻意区分：旧样片可能保留后来取消的页脚或旧版细节。制作新片必须以当前源码和对应Runbook为准，不能把历史实例默认值当作新片文案。

新片先复制一份实例目录，阅读对应Runbook，换已批准配音、实际ASR字幕、章节和原素材；相应新增KIT实例和资产哈希。素材不足或文案变化时重新编排，不能只换一段音频继续用旧嘴型。混音母带供精确复现；新一期应按Runbook用包内原创BGM/SFX重混，不能拿旧母带冒充新配音。原项目适配器源码一并保留作契约参考，但其中Windows字体路径、项目ID和历史队列请求不可直接在Mac执行。

20、21只在“我是店长”等自我介绍的一句加入高质量数字人：按本期配音ASR重算，含少量前后静音，以0.2秒网格对齐25/30fps；只替换主素材窗，整条配音和字幕连续，21副窗仍播放实拍。18、19保持无数字人。具体坐标、最长8秒限制、旧片对照时间见各自完整Runbook。

本包的`offline-template-reproduction-v1`是离线开发复刻入口：不接管原工作台生产队列、不发布、不调用TTS/ASR/数字人服务。使用新音色或生成新数字人需配置同事自己的服务和费用授权；原机私人音色ID不证明同事账号可用。正式制作仍按原项目生产契约接入并验收。

## 交给新Agent的提示词

> 这是海客模板Mac复刻包。先读根README.md、KIT.json和所选模板Runbook。先verify和doctor，再复现所选实例；保持配音主时钟、原素材画质、4:5或模板明确比例和20Mbps门槛。用当前source模板做新片，examples仅用于迁移核对。20/21仅在店长介绍句替换主窗，副实拍和整条音频连续。核验字幕、BGM、音效和数字人出入点，输出技术回执与关键帧；没有Mac真机证据不得声称迁移已验收。不得调用旧云任务、搬入密钥或自行发布。

本包含用户授权供同事内部复刻使用的门店、人物和声音实例；不代表其中私人媒体可公开二次分发。源码与字体继续遵循各自许可证，见`LICENSES/`及字体目录。Remotion使用许可沿用其依赖包声明，同事应按自己的团队使用情况核对。
