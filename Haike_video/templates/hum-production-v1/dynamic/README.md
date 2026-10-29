# 店长动态素材模板

文档类型：video-template-runbook
标准版本：video-template-v1
模板规格：[规格](video-template-spec.json)
状态：本机4:5、不出镜范围已就绪；两条完整片已走真实统一队列，技术与实际抽帧/运动条带验收通过。连续主观听看、平台真机和用户审美确认分别待验；人物新动态布局未追加验收。

## 调用与范围

调用名：**店长动态素材**。这是`hum-production-v1`的整片扩展，Composition仍是`HumProduction`，生产继续走现有统一队列。与runbook的关系：本文件规定操作、检查和恢复；`types.ts/layout.json/Scenes.tsx/motion.ts`及后端校验负责真正执行。

两套整片设计：`archive`长者画廊用灰蓝、海军蓝、铜色和宋体标题，留白与窄边框；`playroom`亲子探索用亮黄、蓝、橙和粗黑标题、厚描边与错位几何。选择风格同时改变背景、字体输入、卡片载体、标题层级和构图节奏；只改背景色不等于切换完整设计。字体必须在本期sources中实际绑定。

当前设计为4:5、1440×1800、30fps。完整PCM口播决定总帧数，保留原速语音和真实字幕时码。主素材原速播放并保持contain；卡片展开期间仍是同一个视频节点，不重新播放。次要卡片为对应实拍的真实封面。球面画廊会重复已有封面形成空间排列，不代表额外拍摄素材。

## 四种动态场景

统一场景为`module:'dynamic'`，通过`motion`点名，不是单片转场。

| 编号 | motion | 实际行为 | 最短时长 | 推荐内容 |
| --- | --- | --- | --- | --- |
| D01 | `click-open` | 级联入场、光标移动/触碰反馈、同卡展开、停留、回原位 | 135帧 / 4.5秒 | 展示某一段重点实拍 |
| D02 | `waterfall` | 按素材比例计算瀑布排布，素材墙连续移动 | 90帧 / 3秒 | 开头呈现丰富现场、活动回顾 |
| D03 | `spatial-gallery` | 球面卡片排布、镜头转动与推进，主卡真实视频 | 120帧 / 4秒 | 社区氛围、探索主题 |
| D04 | `reflow` | 多卡入场后重排为左侧主画面和右侧辅助卡 | 105帧 / 3.5秒 | 围绕一句口播集中展示主体 |

每段明确`id,title,subtitle?,mediaId,wallMediaIds,motion`。`wallMediaIds`绑定3至9个不同素材ID，且必须包含`mediaId`。主卡在本场景从`media.offset`开始播放；连续场景之间是否沿用源区间由本期分镜决定。`statement`用于开头或结尾文字段，其余旧`wall/focus`场景不混入这两种新风格。

标题最多两行，副标题单行；后端检查真实字体字宽。动态标题88px、字幕76px；文字段标题112px。舞台`[70,470,1300,940]`、字幕`[88,1450,1264,158]`分别留区。当前门店地址为画面固定页脚；换门店/画幅/版式属于模板适配，换同账号口播和实拍属于参数复用。

## 下一条制作

1. 在`/motiongit`打开本期长者或亲子草稿，点**复制为新视频**，保留旧成片与旧版本。改视频名称，换完整配音、对应真实字幕、素材和封面；更新来源SHA与已看源区间。不能只换音频而沿用旧字幕。“选择每段的动态场景”可直接修改四种动作、主素材、标题和说明。
2. 完整JSON中可保留精确`props.scenes`，按新口播重新安排连续的`from/frames`；或删去该字段，提供`shotPlan`并使用`weight`自动分配。自动分配受动作最短时长约束，口播太短时减少场景；素材不足以覆盖原速播放时补素材或调整场景，校验不会循环视频填空。
3. `audio.sfx`使用全局`atSeconds`，音效文件可复用，但按新点击、展开、重排节点重新定位。配乐只有显式`loopMusic:true`才循环；使用已有混音的侧链和峰值门禁。配音、素材原声、音乐与音效用途分别记录。
4. 在生成前执行本期结构/来源/字体检查。工作台保存可恢复版本；Agent批量制作使用下面同一入口。没有本地TTS/ASR/数字人服务调用需求时，不新增上游任务。

仓库根目录执行：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --input <本期输入.json> --check
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --input <本期输入.json> --output-dir <交付目录>
```

输入沿用父模板的`title,props,sources,audio,provenance,shotPlan?`，完整字段见[父模板手册](../README.md)。第一步只读预检，输出完整语音样本时钟、源文件数和总帧数。第二步冻结sources、渲染源码、依赖和本期参数，经统一队列输出有配乐/无配乐MP4、质量和交付回执。队列忙时保留原请求等待，不绕过全局执行权。

人物仍使用继承的`presenterClips/presenterModes`和全局口播时钟，支持`large/small/hidden`。**本次两片均不出镜**；这次动态版未新增数字人口型、与各卡片相互遮挡或真机验收结论。大框会覆盖主素材区域，必须按台词安排，不能一键套满全片。

## 检查与恢复

冻结前：核实脚本含义与所用实拍相符；逐主素材的`source_start_seconds/source_end_seconds`来自实际看帧，不把旧素材验收复制为新素材结论。缺文件、未知动作、重复卡片、源区间不足、字体溢出、最短动作时长不足时停止并指出字段。

渲染后：H264/yuv420p、1440×1800/30fps、视频实测≥20Mbps、全帧解码、真实字幕边界、完整语音样本与AAC真峰值≤−1.5dBTP。看每种动作的入场/运动中/稳定/返回帧，并检查重点实拍和字幕；连续听看和平台真机单独记录，静态检查不能替代它们。

中断后读回原队列任务，再恢复**原冻结请求**：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/hum_production.py --request <原工程/artifacts/hum-production-v1-request.json> --output-dir <交付目录>
```

完成任务再次执行按原SHA恢复；源码或输入已变则生成新版本，不能手改冻结请求或覆盖旧片。具体本机任务根`.local/dynamic-scenes-20261027/`保存两份完整输入、工作台草稿映射、队列等待/恢复记录及开发短样；私人文件不进入可分发资源。

磁盘不足时保留已完成任务与输出，先迁移本任务可再生缓存再恢复原请求。本机缓存数据已放在`C:/Users/Administrator/Documents/HaikeCache/dynamic-scenes-20261027/`，原路径通过junction保留；映射与兼容入口恢复见任务根`storage-offload.json`，不用重做原素材或声音。

## 本机验收实例

| 实例 | 口播 / 输出 | 工程 / 渲染 | 可复制草稿 |
| --- | --- | --- | --- |
| 长者空间画廊 | 完整32秒 / 32.2667秒，968帧 | `studio-adc5501f4bcdc1f8` / `hum-production-v1-69d083ae7460505f436d` | `mgd-08d751524c6b4ec1a5c42955d0243142` |
| 亲子探索素材流 | 完整30.3304秒 / 30.6秒，918帧 | `studio-7c46a7af06eee83d` / `hum-production-v1-18122e5b6aecc838bbfc` | `mgd-5095e54075f9474784c97ce5c93913af` |

两片分别为20,494,412和20,494,086bps视频，AAC真峰值−3.11/−4.04dBTP，完整解码通过。有配乐和无配乐版本均保留。作者查看全部16个场景抽帧、12个点击过程帧及12个其它动作过程帧；工作台恢复和对比页真实播放已检查，不把抽样当作完整连续听看。

复用验证：实际复制亲子草稿，在Playroom风格内换完整口播和三份素材，时长从30.6变32.2667秒，全部preflight通过，渲染器、原草稿和原素材绑定保持不变；该第三稿标注“未渲染”。上述两主片则均由同一渲染器实际生产。再次执行已完成长者原请求，输出SHA和原任务一次执行计数不变。准确SHA、质量与作者记录绑定在本规格，以及任务根`acceptance.json`、`reuse-check.json`、`qa/FINAL_REVIEW.md`。

对比页包含两条完整片与四段5秒开发试镜；页面选项保存在当前浏览器，并可导出动作JSON，选择本身不提交生产。服务重启：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/templates/motion-audition-v1/serve_gallery.py --directory .local/dynamic-scenes-20261027/delivery --port 14879
```

以后下载新MotionGit包，先核验身份、读取它实际开放的参数和控件，再用本期真实素材验证一个完整3至5秒场景。已支持的四动作换内容走参数复用；新排布、新交互、新画幅或新固定门店信息走模板适配，再补真实输出证据后入库。新包不会因导入成功就自动拥有本模板的媒体槽或就绪结论。

## 来源与维护

MotionGit dark2.7.17-alpha.3官方`setup --workflow motion-kit`在本机报`Frozen component library changed`，没有绕过校验。当前改用React Bits固定提交的Masonry排布和DomeGallery投影算法，以及固定GSAP3.13.0暂停时间轴；应用适配负责视频载体、4:5构图、主卡选择、动作编排及`frame/30`采样，不宣称原组件未修改。来源见[source-manifest.json](source-manifest.json)、[NOTICE](vendor/NOTICE.md)及[完整许可](vendor/REACT-BITS-LICENSE.md)。React Bits为MIT加Commons Clause；当前作为应用功能集成，不单独转售/分发组件库。

维护检验：`node Haike_video/scripts/verify_dynamic_motion.cjs`覆盖24种素材数量/风格/动作组合的非顺序拖帧、同卡返回、瀑布移动、卡片几何与画廊镜头。后端测试位于`tests/backlot/test_studio_hum_production.py`；使用隔离basetemp。模板规格用Videohub标准检查器验证。新增动作需扩展类型、校验白名单、最短时长、真实试镜和操作说明，不能填一个未知动效名假装支持。
