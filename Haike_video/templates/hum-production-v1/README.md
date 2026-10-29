# Hum / Coral 与开源动效完整口播模板

完整的前端动态场景与两套整片设计见[店长动态素材模板](dynamic/README.md)：连续素材瀑布、空间画廊、多屏重排、同卡点击展开与返回；沿用本模板的完整口播时钟、统一队列和草稿复制入口，验收范围独立记录。

项目自有实现，合同 `hum-production-v1`，Composition `HumProduction`。它复用 MotionGit 参考的卡片级联与同卡展开语法，并加入 Hallmark Hum 亲子剪纸、Coral 温暖棉纸两种视觉方向。原 `.motion` 和原20秒样片合同独立保留。

**当前阶段**：见 [video-template-spec.json](video-template-spec.json) 的独立验收维度。自动化合同和本地音频测试不代表已看过本期成片或已验收数字人口型；正式复用前由作者按实际样片证据更新阶段。

## 1. 下一条怎样复用

在 MotionGit 工作台选择“完整口播与动态素材 · Hum / Coral / Archive / Playroom”，复制对应设计的已完成草稿，换完整口播、对应字幕时码和素材。人物可以沿用逐段大框、小框安排，或者不出镜。每张卡都有素材和封面上传槽，镜头标题、卡片、音效及出镜时窗可在完整 JSON 中编辑；Archive/Playroom另有[动态场景控件与手册](dynamic/README.md)。

Agent 批量制作使用同一入口，从仓库根运行：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --input <本期输入.json> --check
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --input <本期输入.json> --output-dir <交付目录>
```

第一条检查完整来源、音频样本时钟、真实字幕、看帧区间和字体字宽，不入队、不扣费。第二条冻结本地副本，经现有统一队列调用 VideoCompose/Remotion；关闭页面不丢失生产身份。此入口只接受已有本地配音/人物结果，TTS、ASR、数字人生成属于上游已授权任务。

## 2. 本期输入

顶层是 `title, props, sources, audio, provenance`，以及可选 `shotPlan`。权威字段、范围、校验及出错处理在 [适配器](../../backlot/studio_hum_production.py)；类型和画面参数分别由 `types.ts`、`layout.json` 与渲染源码持有。

- `sources`：安全平面文件名 → 绝对本地文件。按内容哈希冻结；`master.wav` 由引擎生成。浏览器只得到画面、字体、最终母带，来源记录留在私有工程中。
- `audio.voice`：完整 PCM WAV，16至96kHz、单/双声道、2至600秒。成片总帧数为 `ceil((原样本数 / 采样率 + tailSeconds) * 30)`；尾部默认0.25秒、允许0至2秒。语音从0开始，原速连续，无重排。
- `audio.music`、`musicGainDb`、`musicOffsetSeconds`、`loopMusic`：可选配乐及其混音。音乐须足够覆盖全片；只有显式 `loopMusic:true` 才循环配乐。
- `audio.sfx`：`[{src, atSeconds, gainDb}]`，全局口播时钟上的音效。母带有配乐侧链和峰值余量；另保存同口播/同音效的 `nomusic.wav` 与无配乐MP4。
- `props.brand/footer/visualStyle`：品牌、页脚及 `hum` / `coral` / `darkroom` / `carnival`，或独立动态场景扩展`archive` / `playroom`。4:5、1440×1800、30fps、总帧数及 `audio:'master.wav'` 自动生成。
- `props.media`：1至24项，`{id,src,thumbnail,kind?,offset,fit:'contain',objectPosition?,orientation?,label?}`。视频原声静音、原速全幅；图片可以替换，视频内部固化文字仍属于素材本身。
- `props.captions`：真实时间戳 `[{text,startMs,endMs}]`，每条最多22字且须适合实际字体字宽；不凭空估计对齐。对应口播SHA及对齐方式留在 `provenance.captions`。
- `props.fontAssets`：`{display:'display.ttf', body:'body.ttf'}`，真实字体文件随本期输入绑定。

镜头时序二选一：`props.scenes` 可完全控制每段 `from/frames` 并连续覆盖全片；`shotPlan` 使用相同场景内容但省略 `from/frames/selection`，加可选 `weight`，引擎按完整口播自动分配。场景支持 `statement`、`wall`、`focus`。素材墙默认 `motion:'cascade'`，4至6张卡；`motion:'card-stack'` 为3或5张卡。聚焦可选 `motion:'paper-reveal'`。

每个场景含 `id,module,theme,title,subtitle?`；聚焦含 `mediaId`；素材墙另含 `wallMediaIds`，自动规划时引擎生成 `cursorFrom/selectFrom/expandFrom/holdFrom`。卡片先级联/分发，再选中，**同一张卡**放大。素材墙仅选中卡从 `expandFrom` 开始播放；其他卡用封面。聚焦素材从场景第0帧播放。源视频和已看帧区间必须覆盖整个真实播放长度，长度不足时补镜头或换长素材。

标题统一最多2行、每行最多16字，仍需通过实际字体字框检查。字幕使用84px字体，独立安全区为 `layout.json` 的 `[88,1460,1264,140]`；动态卡片舞台在1440px处裁切，为字幕上沿预留20px间隔。卡堆与竖版聚焦的Coral副标题使用侧注布局，级联素材墙副标题在展开前退场。更长标题或字幕应按语义缩短/分句，不能靠裁切和覆盖实拍塞入。

人物来源为 `props.presenterClips:[{id,src,from,frames,offset}]`，安排为 `presenterModes:[{clipId,from,frames,mode:'large'|'small'|'hidden'}]`。播放位置始终是 `offset + (全局帧 - clip.from) / 30`，大小窗和隐藏只改变显示状态。非零全局入点用10帧淡入，片段末尾8帧淡出，渐变期间原速源时钟继续。人物片段必须绑定当前完整口播SHA和实际全局区间，不能在小窗出现时重新从头播放。无人物时两组字段均可省略。

`provenance` 记录真实来源：`voice:{sha256,source,authorized:true}`，`captions:{voice_sha256,method}`，非人声音轨 `audio:{文件名:{sha256,source}}`，逐素材 `media:[{id,source_sha256,thumbnail_sha256,reviewed:true,description,source_start_seconds,source_end_seconds,observed_frames}]`，可选人物 `presenterClips:[{id,source_sha256,voice_sha256,reviewed:true,globalFrom,sourceOffset,frames}]`。换音频/素材后重新核对实际内容、字幕及来源，旧记录不自动继承为新素材验收。

## 3. 输出与恢复

CLI打印本期请求、工程、队列、作品/版本及交付路径。工程内保留 `assets/hum-production-v1/` 原始文件、`artifacts/hum-production-v1-request.json` 冻结请求和 `renders/<render_id>/` 生产证据。

成片为 H264、yuv420p、1440×1800/30fps，视频实测至少20Mbps，AAC48k立体声，输出真峰值不高于−1.5dBTP；检查精确帧数、总时长和完整解码。`hum-production-nomusic.mp4` 直接复制主片视频流，仅替换为无配乐口播/音效轨。

中断后用原请求恢复：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --request <原工程/artifacts/hum-production-v1-request.json>
```

相同冻结输入幂等入队；已有完成产物按SHA恢复，不重做上游云服务。未完成任务若源码/输入变化则新建冻结身份；队列忙时等待原任务，不绕过全局生产锁。

冻结前使用真实生产队列相同的无凭据规范化：来源记录中的 `authorization_basis`、`reuse_authorization` 等保留键不进入冻结请求，必要的 `authorized:true`、来源SHA和字幕/人物同源SHA仍须完整。会改变字幕、音频计划或源文件绑定的保留字段直接阻断。旧失败请求保持原身份，修复后从原输入创建新冻结请求；不要手改原请求或跳过SHA校验。

## 4. 作者验收

测试位于 `tests/backlot/test_studio_hum_production.py`，涵盖20/35/60秒、真实FFmpeg混音、素材短缺门禁、人物大→隐藏→小全局连续时钟、冻结恢复、MotionGit绑定和API样片读取。测试PCM与假视频合同用例不是实际口播、素材审美或数字人验收。

真实成片逐项记录技术、抽帧、连续观看、完整听音、数字人口型及真机状态。抽帧和音频峰值不替代连续听看。质量记录默认 `pending`，作品以待复核版本登记；本模板不自动发布、不把历史样片结果外推到新输入。

## 5. 开源动效扩展（v002）

新增 `visualStyle: darkroom | carnival`，走同一个完整口播主钟、素材来源门禁和生产队列。新风格使用 `focus` / `statement` 镜头，不使用旧 `wall` 的鼠标点击逻辑。换口播后按真实字幕重新分配镜头，已有音效也应对齐新节点；时长跟随 PCM 样本，不拉伸口播或循环短素材。

| motion | 上游现成效果 | 用法 |
| --- | --- | --- |
| `cloth` | Remocn ClothReveal | 一次布幕揭示，约1.2秒揭开后保持画面 |
| `parallax` | Remocn ParallaxDepth | 分层缓慢横移；速度跟随本镜头时长 |
| `mondrian` | Remocn MondrianSplit | 几何分割、重排与展开；约2.4秒后进入稳定画面 |
| `gl-film` | GL Transitions FilmBurn | 实拍入场前24帧胶片转场 |
| `gl-circle` | GL Transitions CircleOpen | 实拍入场前24帧圆形揭示 |
| `pixi-shock` | PixiJS Filters ShockwaveFilter | 第12帧起扩散一次局部波纹 |

Darkroom采用深绿/暖金、右侧实拍与左侧标题；Carnival采用红黄蓝几何块、左侧实拍与右侧标题，横屏素材使用宽幅构图。人物沿用全局口播时钟，支持 `large` / `small` / `hidden`，字幕与门店信息保持安全区域。

`OpenEffects.tsx` 只负责解码帧、纹理与帧时钟对接，不重写上游效果。Pixi ticker关闭，GL进度来自Remotion帧；渲染等待纹理和滤镜就绪，缺失WebGL直接报错。来源版本、锁定依赖、许可证见 `open-effects-manifest.json` / `THIRD_PARTY_NOTICES.md`。本机 Remocn skill 单独安装；不依赖它才能执行冻结渲染。新增效果需扩展白名单、来源/最短时长门禁与真实看帧，不能仅改任意效果名。

两条新样片与复核证据存放根 `.local/open-motion-remake-20261027/`，与以下v001样片分别保留。新依赖不自动扩大其它模板的已验收范围。

## 6. v001验收样片身份

新增五款无数字人实拍动效选择页、源码与本地恢复方法见[实拍动效试镜库](../motion-audition-v1/README.md)。每款4.5秒，甩镜、穿越推进、撕纸、立体方块波、人工轨迹冲击波；属于独立开发试镜，不改变本模板生产验收范围。

本机正式复用范围已就绪：两条最终成片完成真实队列生产、技术测量及独立关键帧/连续运动条带复核，原文字碰撞已销项。规格为限定范围的 `ready`；连续听看、完整听音、逐音节口型、平台真机和用户审美仍独立待验，不把抽样结论外推为全项通过。

| 样片 | 完整口播 / 输出 | 最终工程 | 可复制草稿 |
| --- | --- | --- | --- |
| 长者 · Coral温暖棉纸 | 32秒 / 968帧，32.2667秒 | `studio-6aec7c4a704a03fb` / `hum-production-v1-283efc09ec091a5f86bd` | `mgd-a0296fa325c6480a86a4ca62ddb4c51e` |
| 儿童 · Hum亲子剪纸 | 30.3304秒 / 918帧，30.6秒 | `studio-e56a64dcfb2513b7` / `hum-production-v1-7d8ffd312e8d5c5cae44` | `mgd-1c0c38a49af94419bf6bdb936e1c099a` |

精确请求SHA、PCM样本时钟、场景与出镜时窗见规格的 `extensions.custom.production_cases`。最终输出、质量记录及独立复核报告SHA已经绑定；较早试片不代替这两条最终身份。复核报告位于根 `.local/hum-production-20261027/qa/final-independent-review.md`，完整交付及测量见同目录任务根的 `delivery.json` / `acceptance.json`。
