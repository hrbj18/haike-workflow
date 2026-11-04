# 动效模板3

文档类型：video-template-runbook。标准版本：video-template-v1。
模板规格：[规格](video-template-spec.json)。版本：**1.0.0**。稳定ID：`nana-mint-explainer-v1`。
状态：**用户定稿，确认版完整MP4已交付**。2026-11-03用户明确“将这个动效模板固定下来，就就叫动效模板3”。验证范围见[验证记录](VALIDATION.md)和[确认记录](APPROVAL.json)；已验89.27秒16:9/1080p，其他时长新稿及真实平台逐期验收。

## 名称、版本与固定预设

呼叫“动效模板3”或“动效模板三”进入本模板，与“数字人口播模板3”和“招商视频模板3”分开。工作台入口：数字人口播→选择模板→视觉模板库→模板画廊→动画模板；可看确认样片、读手册和复制制作指令。

[template-profile.json](template-profile.json)固定薄荷色板、13景顺序、已有9组件、音频配方与输出档；TSX保留精确几何/裁切/原生动作真值。[input-contract.json](input-contract.json)规定本期可换内容。[release.json](release.json)绑定源码、依赖及规格SHA；准备和渲染前自动核对，改设计须另建版本，不覆盖旧哈希掩盖改动。

当前本机默认预设在工作区`.local/template-presets/animation-template-3/preset.json`：侯总形象、天亮猴哥音色、原生1.15速和用户《科技风》音乐。已归档人物图、音乐、确认音轨及完整基准public/；不修改账号的其他默认，不授权下期付费或发布。新文案先生成/取得新声，再用同声源生成口型，旧声音/旧口型只用于原样复现。

配乐固定为用户认可v5：原人声−1dB；科技风基准−10.5dB，侧链后先+3dB再+4dB，净−3.5dB；侧链、EQ、循环衔接、首尾淡化和限幅取profile.audio。这个+7dB只指本次科技风音源，不是任意音乐的通用增益。现有完整混音不二次叠配乐。`mix_audio.py`是该配方的本地阶段，仅在项目统一队列内调用。

复用前执行`python frozen_release.py`或项目Node的`verify-release.cjs`。新一期`content.json`、时码、字幕和媒体留在独立私有目录，完整填写13景与5个章节，不修改定稿源。真实ASR主钟可以决定本期时码，但不自动截断/加速语音，也不把原89.27秒时码硬套到新稿；每期实际看帧与听音，改变画幅或设计另验。

## 参考与实现

用户指定[nana娜娜呀的参考片](https://www.douyin.com/video/7701714985299498725)，并明确使用项目已有53种动效。原片1280×720/30fps、2236帧，五段章节：插件接入、描述需求、官方案例、人的价值、方法教程。已实际查看全片概览及75张原生PTS动作阶段帧，原片和分析留在本期忽略目录。

本模板重建章节导航、浅薄荷背景、短标题、素材窗/人物窗、对比箭头、观点卡、三步教程和结尾关键词，使用实际安装的九个Snapcn组件：TextBuild、TextReveal、TextHighlight、TextSwap、ScreenRecording、PromptSend、AgentSteps、CaptureReveal、WordCaptions。它们是同一53项库中的选择，不额外安装动画库，不修改上游源码。

参考示例的人物、声音和软件画面是本地下载参考的派生素材，不是本项目生成的人物或新验证的软件功能。内嵌软件文字不能作为活字替换；外层标题、章节、标签、字幕、人物和素材文件分别开放。原作者准确曲线未知，实际使用Snapcn公开行为近似动作，不能声称找回原作者工程。

## 参数真值与替换槽

- `types.ts`描述本期输入，`prepare.validate_episode()`执行连续场景、cue顺序、字幕/音频时钟、文件路径与来源时长检查。
- 私有`public/content.json`是文案/场景/字幕/配色真值，`episode.json`保存来源、派生参数和文件SHA；TSX持有具体几何与原生动画参数。规格只描述这些入口。
- 声音是完整原速音轨。字幕用Caption JSON的`startMs/endMs`，场景`start/end`为全局秒，动作`cues`为场景局部秒；原生组件内部按当前帧执行。不能按文案字数均分时间。
- 13个稳定场景：integration、terms、brief、result、workflow、compare、question、value、difference、course、examples、logic、closing。新稿由作者设置真实语义时码，当前没有任意脚本自动分镜功能。
- 人物与素材每窗独立绑定`file/width/height/kind`，同一期准备后的媒体从该场景开始原速消费；brief人物在场景内2.1秒后显示。新人物先校准源取景再用固定外框，缺帧直接阻断，不循环补齐。
- 输出1920×1080/30fps，设计坐标1280×720等比放大1.5。原参考播放源清晰度不因此提高。其他比例尚未适配。
- 换配音时先取得本期真实ASR，再重写全部场景/cue/字幕时钟；人物保持本期同声源原速，不能沿用旧口型。可选`referenceClock.duration/anchors`仅让`NanaComparison`的无声原片按实测语义锚点对齐；`NanaReference`仍按原始时长/原速播放，侯总的新声音与人物不受此映射影响。

## 当前操作

从单仓库根目录操作。运行时位置由明确的安装副本提供；源码和运行数据分开。本机最终参考样例数据位于忽略的`.local/nana-template-20261102/v4/`；原片、转录和参考理解证据在其父目录。

1. **准备本期。** 输入→当前参考原片/实际转录/字体，或新一期完整JSON与本地资产→执行`prepare.py`→私有`public/`和`episode.json`。gate：原片SHA或本期文件真实存在，语音/字幕/场景时钟相同，每个视频足够覆盖原速可见区间。恢复：先读已有清单，冻结目录不覆盖。

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/templates/nana-mint-explainer-v1/prepare.py --episode <新一期JSON> --assets <本地资产目录> --output <新一期目录> --ffmpeg <现有ffmpeg> --ffprobe <同套ffprobe>
```

本地资产目录同时保留Snapcn已有字体缓存`assets/fontsource/@fontsource-variable/dm-sans@5.3.0/files/dm-sans-latin-opsz-normal.woff2`，可从本期`public/`复制；缺失时会阻断，不能依赖导出时的远程字体。

2. **交互预览。** 在`Haike_video/remotion-composer`内使用现有Node启动，不升级依赖：

```powershell
<现有Node> node_modules/@remotion/cli/remotion-cli.js studio ../templates/nana-mint-explainer-v1/index.tsx --config=../templates/nana-mint-explainer-v1/remotion.config.cjs --public-dir=<本期绝对目录>/public --port=59610 --no-open
```

打开实际打印的地址。`NanaTemplate`是完整可编辑内容；`NanaReference`播放本地参考；`NanaComparison`同钟左右对照，只有一条新模板音轨。三者共用本期内容。gate：实际预览可显示/播放，全部媒体来自本机。恢复：保留Studio和本期输入，检查错误对应的场景或文件。

3. **实际状态检查。** 在单仓库根目录以现有Node执行`render.cjs bundle <本期绝对目录>`，再运行队列检查入口。Python需要`Haike_video`在模块路径，命令环境与既有模板相同。

```powershell
$env:PYTHONPATH = (Resolve-Path Haike_video).Path
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/nana_mint_preview.py --install-root <本期工作区根> --runtime-root <现有运行时所属根> --data <本期目录> --mode frames
```

输入→冻结实现/本期媒体/检查包/运行时→统一队列精确暂停任务→PNG和frame-proofs.json。队列和projects始终属于install-root，runtime-root只选择运行时，不转移队列；运行时同根可省略。默认按本期13景和cue派生检查点；人物原生续接等额外关键点用`--frames`明确加入。gate：所有场景、主要入场/落定/边界实际看图，审核声明绑定本期图片SHA；不以文件生成成功代替视觉检查。恢复：`jobs.json`保留原job和日志，失败不丢已完成帧；变化后另冻请求，不绕过队列。

4. **明确要求导出后。** 用同一入口`--mode render`；前置`design-review.json`须包含真实图片身份及当前实现/媒体/bundle identity。统一队列生成MP4，验证完整解码、帧数、1920×1080及实测视频流≥20Mbps，作品登记保留待最终视觉/听看状态。现有原声只混入一次。恢复：保留来源、原任务及完整静音视频，不重新生成声音/人物。

## 验证与交接

先执行`build_spec.py --episode <本期episode.json>`生成描述规格；需要保留每期快照时增加`--output <本期目录>/video-template-spec.json`，会重定位源码/证据链接，保留公共参考规格。再执行Videohub的单规格检查、相关输入校验测试和根`scripts/check.py`。本模板交付可编辑本地预览；技术帧、连续听看、用户审美、完整MP4、真机和前端一键生产各有独立范围，详见VALIDATION。

共享源码没有第三方人像/原声/录屏或密钥；私有示例不随公开模板分发。9:16、4:5、新声源、新人物和另一台物理机需要分别验收。已接工作台模板画廊，普通口播表单不接受本视觉库ID作为一键生产模板。

## 侯总替换试片（2026-11-03）

本次用户明确“猴哥就是侯总”，并授权当期相关生成总计最多15元。新声采用已核可用的天亮猴哥、百炼`qwen-audio-3.1-tts-flash`原生1.15速；人物采用现有侯总图及V5.3.1 Plus。先生成完整新声，再以同源实测ASR重排29句字幕、13景和动作；只为10个出镜窗生成52.12秒原生25fps母片，主片仍30fps，不重放旧口型或拉伸声音。

本期目录为根`.local/nana-houzong-20261103/`；`SESSION.md`保存恢复点，`REPORT.md`和各版审核记录实际验收。当前输入为`preview-v5-techbgmplus4/episode.json`及其`public/content.json`，独立规格同目录，不覆盖原参考样例。v3按用户提供的《科技风》替换配乐，v4将音乐提高3dB，v5按用户明确要求再提高4dB，累计7dB；保留原人声轨增益、侧链和淡化，字幕、画面与时序沿用v2。`music-provenance.json`证明仅mix.wav改变，旧44张实际视觉帧只用于完全相同的视觉输入，不宣称重新全片听审。素材窗原速播放后停留干净UI帧，人物原速消费真实母片；仅无声语义对照允许参考画面变速。完整预览89.266667秒；连续听看、用户审美与完整MP4分别验收。v1的四个软件素材尾部问题已在v2修正，换乐及音量调整未增加付费调用。

本地准备/构建/检查入口的`paid_calls:0`只表示该本地阶段没有供应商调用；本期配音、两段人物任务的上游实际回执与费用独立保存在上述本期目录，不能解读为全流程零费用。不改变其他模板、账号或长期工作流默认；本期授权不包含发布。

用户已认可v5并明确要求导出。本期独立的`export_confirmed_v5.py`将当前实现/运行时/媒体/bundle、相同视觉输入的44张已审帧和用户接受记录绑定为`nana-houzong-confirmed-v5-full-export-v1`合同，经源码checkout统一队列执行原`render.cjs`，直接复制已认可AAC音轨。导出后17张实际编码帧、完整解码、2678帧及22.02Mbps视频流通过；文件身份、作品登记和交付路径见`preview-v5-techbgmplus4/delivery.json`。其他期次仍须使用与其输入、检查及执行合同匹配的入口，不能移用本期审核。
