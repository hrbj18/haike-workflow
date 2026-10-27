# Hum / Coral 完整口播模板

项目自有实现，合同 `hum-production-v1`，Composition `HumProduction`。它复用 MotionGit 参考的卡片级联与同卡展开语法，并加入 Hallmark Hum 亲子剪纸、Coral 温暖棉纸两种视觉方向。原 `.motion` 和原20秒样片合同独立保留。

**当前阶段**：见 [video-template-spec.json](video-template-spec.json) 的独立验收维度。自动化合同和本地音频测试不代表已看过本期成片或已验收数字人口型；正式复用前由作者按实际样片证据更新阶段。

## 1. 下一条怎样复用

在 MotionGit 工作台选择“完整口播可复用模板 · Hum / Coral”，复制已完成草稿，换完整口播、对应字幕时码和素材。选 Hum 或 Coral；人物可以沿用逐段大框、小框安排，或者不出镜。每张卡都有素材和封面上传槽，镜头标题、卡片、音效及出镜时窗可在完整 JSON 中编辑。

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
- `props.brand/footer/visualStyle`：品牌、页脚及 `hum` / `coral`。4:5、1440×1800、30fps、总帧数及 `audio:'master.wav'` 自动生成。
- `props.media`：1至24项，`{id,src,thumbnail,kind?,offset,fit:'contain',objectPosition?,orientation?,label?}`。视频原声静音、原速全幅；图片可以替换，视频内部固化文字仍属于素材本身。
- `props.captions`：真实时间戳 `[{text,startMs,endMs}]`，每条最多22字且须适合实际字体字宽；不凭空估计对齐。对应口播SHA及对齐方式留在 `provenance.captions`。
- `props.fontAssets`：`{display:'display.ttf', body:'body.ttf'}`，真实字体文件随本期输入绑定。

镜头时序二选一：`props.scenes` 可完全控制每段 `from/frames` 并连续覆盖全片；`shotPlan` 使用相同场景内容但省略 `from/frames/selection`，加可选 `weight`，引擎按完整口播自动分配。场景支持 `statement`、`wall`、`focus`。素材墙默认 `motion:'cascade'`，4至6张卡；`motion:'card-stack'` 为3或5张卡。聚焦可选 `motion:'paper-reveal'`。

每个场景含 `id,module,theme,title,subtitle?`；聚焦含 `mediaId`；素材墙另含 `wallMediaIds`，自动规划时引擎生成 `cursorFrom/selectFrom/expandFrom/holdFrom`。卡片先级联/分发，再选中，**同一张卡**放大。素材墙仅选中卡从 `expandFrom` 开始播放；其他卡用封面。聚焦素材从场景第0帧播放。源视频和已看帧区间必须覆盖整个真实播放长度，长度不足时补镜头或换长素材。

人物来源为 `props.presenterClips:[{id,src,from,frames,offset}]`，安排为 `presenterModes:[{clipId,from,frames,mode:'large'|'small'|'hidden'}]`。播放位置始终是 `offset + (全局帧 - clip.from) / 30`，大小窗和隐藏只改变显示状态。人物片段必须绑定当前完整口播SHA和实际全局区间，不能在小窗出现时重新从头播放。无人物时两组字段均可省略。

`provenance` 记录真实来源：`voice:{sha256,source,authorized:true}`，`captions:{voice_sha256,method}`，非人声音轨 `audio:{文件名:{sha256,source}}`，逐素材 `media:[{id,source_sha256,thumbnail_sha256,reviewed:true,description,source_start_seconds,source_end_seconds,observed_frames}]`，可选人物 `presenterClips:[{id,source_sha256,voice_sha256,reviewed:true,globalFrom,sourceOffset,frames}]`。换音频/素材后重新核对实际内容、字幕及来源，旧记录不自动继承为新素材验收。

## 3. 输出与恢复

CLI打印本期请求、工程、队列、作品/版本及交付路径。工程内保留 `assets/hum-production-v1/` 原始文件、`artifacts/hum-production-v1-request.json` 冻结请求和 `renders/<render_id>/` 生产证据。

成片为 H264、yuv420p、1440×1800/30fps，视频实测至少20Mbps，AAC48k立体声，输出真峰值不高于−1.5dBTP；检查精确帧数、总时长和完整解码。`hum-production-nomusic.mp4` 直接复制主片视频流，仅替换为无配乐口播/音效轨。

中断后用原请求恢复：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --request <原工程/artifacts/hum-production-v1-request.json>
```

相同冻结输入幂等入队；已有完成产物按SHA恢复，不重做上游云服务。未完成任务若源码/输入变化则新建冻结身份；队列忙时等待原任务，不绕过全局生产锁。

## 4. 作者验收

测试位于 `tests/backlot/test_studio_hum_production.py`，涵盖20/35/60秒、真实FFmpeg混音、素材短缺门禁、人物大→隐藏→小全局连续时钟、冻结恢复、MotionGit绑定和API样片读取。测试PCM与假视频合同用例不是实际口播、素材审美或数字人验收。

真实成片逐项记录技术、抽帧、连续观看、完整听音、数字人口型及真机状态。抽帧和音频峰值不替代连续听看。质量记录默认 `pending`，作品以待复核版本登记；本模板不自动发布、不把历史样片结果外推到新输入。
