# 深色立体·完整多屏模板

文档类型：video-template-runbook。标准版本：video-template-v1。模板规格：[规格](video-template-spec.json)。

固定呼叫词：**深色立体完整模板**。本目录是项目可编辑模板；原生 `.motion` 全片对照保留在独立原生队列合同中。阶段与实际验收范围只以 [规格](video-template-spec.json) 和本期质量/复核回执为准，源码存在不代表成片已经完成。

完整原生还原和项目可编辑重建分别交付。项目版保留十组结构与受控编辑能力，装饰、几何和局部缓动存在明确差异，见[重建差异](reference/reconstruction-differences.md)及[验证摘要](reference/validation-summary.json)；不能把项目重建宣传为原版逐像素或全部动效完全等同。

当前规格为 **implementation + ready**，限定于已声明的受控输入和本机验证范围。最终原生r3、可编辑v2、两条海客片、脚本功能案例和工作台HTTP接入有分别绑定的实际证据；连续听音、音素口型、真机、用户观看及工作台UI视觉仍待验，不宣称全片连续视听或跨机通过。本机[完整对照与十组预览](http://127.0.0.1:14756/motiongit-showcase)可直接观看；迁机以实际工作台服务地址为准。

## 复用入口

工作台 MotionGit 页的“完整多屏模板”提供十组动作、两套海客主题、持久草稿和队列记录。日常先复制完成草稿，再换完整口播/真实字幕时码/实拍；品牌、短标题、素材标签和邀请卡是活字。源视频内部的字仍是源素材的一部分。

Agent 入口（仓库根）：

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_full.py --input <本期输入.json> --check
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_full.py --input <本期输入.json> --output-dir <交付目录>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_full.py --request <原工程/artifacts/dark-full-request.json>
```

第一个入口只检查，不入队、不调用云服务；后两个经现有统一生产队列执行和恢复。已有结果按SHA读回，关闭页面不会丢任务；未完成时源码改变须冻结新身份，保留旧结果和已付费上游任务。

## 输入与时长

输入顶层为 `title, props, sources, audio, provenance`，可选 `shotPlan`。精确字段和门禁由 [适配器](../../backlot/studio_dark_full.py)、[类型](types.ts) 和 [动作目录](catalog.json) 唯一持有。

- `audio.voice` 是完整本期 PCM WAV。海客帧数为 `ceil((samples/rate+tailSeconds)*30)`；默认尾部0.25秒。口播始终从0原速连续播放，不能拉伸、截断或换序。
- `props.variant` 为 `hedgerow`（深叶绿、奶油、衬线）或 `cobalt`（冷白、电蓝、硬边面板）。4:5 输出1440×1800/30fps。`reference` 为完整十组1920×1080/60fps/122.4秒，不能把30秒社会版冒称完整复刻。
- `props.media` 绑定3–24个实拍/图片及真实封面；`sources` 用安全文件名映射本地绝对源文件。冻结副本、SHA和来源留在私有工程，浏览器不能任意访问本机路径。
- 大素材的受控冻结副本在 `HAIKE_RENDER_CACHE` 指定的持久缓存中，默认本机 Documents/HaikeCache；位置和每个SHA写入冻结请求。工程内保留请求、质量回执及最终作品，不把目录联接当作托管成片。迁机时须按来源清单恢复该缓存或重新冻结，不能只复制JSON声称素材已迁移。
- `props.scenes` 精确连续覆盖全片；或省略scenes改用 `shotPlan`。每项为一整组、语义内容及 `weight`；引擎先保留完整动作阅读下限，再分配多余时间。原生最短时长和项目阅读下限分别保存，不能混用。
- `scene.content` 开放分词标题、分类、说明、邀请及签名，字段见 [A组](reference/groups-a-implementation.md) 与 `GroupsB.tsx` 字段注释。建议大标题每行≤9汉字、标签≤6字。长字数须重排/缩写并看帧，不能靠裁切塞入。
- `clipPlan:[{mediaId,at,seconds,offset}]` 的at是本场景比例入点，seconds是真实播放秒数，offset是源素材秒。预检编译为 `videoWindows`。只有对应 live 节点可见时才显示视频，其余卡使用封面；声明窗口和看帧区间必须覆盖实际长度，禁止循环、尾帧填充或变速。
- `cueTimes` 是场景局部秒，只调动作启动点；入场/位移/缓动保留原有秒数。尾部动作留出落定时间。`s02→s03` 必须相邻、同一中央主素材，源偏移连续，不在新场景从头重播。
- `captions` 必须来自同一完整口播的实际时码，以实际字体测量字宽。只换脚本时先走项目已配置音频中心/字幕阶段，得到真实WAV与时码再合成。合成CLI不会隐式生成TTS或数字人。
- 脚本＋素材的固定入口为[脚本制片契约](../../docs/DARK_FULL_SCRIPT.md)：`dark_full_script.py`沿既有音频中心执行check/quote/confirm/resume/export，导出的同一输入再交给上述`dark_full.py`和统一队列。实际12秒功能案例及原operation恢复范围在验证摘要中单列，不冒称第三条正式审美主片。
- `presenter:{src,from,frames,offset,modes}` 可选；模式为large/small/hidden。播放位置始终 `offset+(globalFrame-from)/fps`，大小窗或隐藏只改变显示，不重置口型时钟。必须绑定同一完整语音SHA和实际覆盖区间；没有人物则整个字段省略。
- `audio.music` 与 `sfx` 使用现有来源，音效按动作全局节点重排。配乐只在显式loopMusic时循环；口播与实拍不循环。实拍原声静音。独立配乐输入可输出无配乐备选；原版已混合音轨不能宣称可无损分离音乐。

## 制作与检查

输入→只读preflight→受控素材/源码冻结→统一queue→Remotion/VideoCompose→H264/yuv420p、实测≥20Mbps、AAC48k立体声→完整解码与帧数/峰值检查→实际关键状态与素材语义复核→待观看作品版本。

每次检查长标题、最后一张卡、动作落定、字幕安全区、素材实际区间和人物避让。技术检查不替代实际看帧；抽样不替代连续观看/听音或平台真机。失败只修对应槽或本地阶段，保留口播、数字人任务与旧成片。

新增生产前，执行者还须检查托管工程卷和缓存卷的实际余量；CLI的素材/时钟preflight不代替磁盘检查。按当前约20.5Mbps输出，30秒的配乐＋无配乐两版仅最终文件就约154MB，122.4秒单版约317MB，另加新上传素材与缓存。建议托管工程卷至少留1GB再加本期新素材，缓存卷另留实际渲染所需空间。当前本机空间限制见验证摘要：已完成片播放/恢复可用，余量不足时不得启动新生产；不搬走或目录联接作品库注册原作来伪装容量充足。

## 完整原生对照

受控替换本期口播/人物/素材的原生短片扩展见[原生内容替换合同](../../docs/DARK_NATIVE_CONTENT.md)。它沿官方整组动效和同一队列执行；短片、原版122.4秒对照及可编辑重建分别记录身份与验收。

原生合同 `motiongit-dark-native-v1` 使用验签包、固定官方helper、公开check/plan/prepare/preview/render命令。先实际看过本期native预览再审核，完整render仍由单一队列执行。输入manifest记录准备工程、工具链、源音轨、审核和差异；大缓存保留在本机持久缓存中，源码与公共仓库不附个人授权包或秘密字段。

```powershell
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_native.py --input <已审核原生manifest.json>
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/dark_native.py --request <原工程/artifacts/dark-native-request.json>
```

原作者内嵌实拍/录屏缺失时，用同规格本机自制图形替代并记录；不能把下载的原预览当成新渲染。原混合口播/配乐/音效只合入一次。项目可编辑重建和官方native对照有各自来源与版本，不把两者混称同一引擎。

## 下一份新包怎样接入

验签与公开contract→实际观察整片/状态/接缝→登记动作组、cue、相邻依赖与素材时钟→将公开参数映射到本项目content/media/presenter/audio槽→用真实素材有界试镜→同队列完整制作→独立记录规格就绪与验证范围。第一次适配新包可能需要新组件/排版；适配完成后，同包换口播与素材不再修改渲染源码。不是任意`.motion`零适配转换器。

新增动作需登记可编辑字段、完整状态、最短阅读时长、布局和缺项门禁，保留上游来源/许可证及原包固定品牌约束。优先复用公开实现，不移除保护或绕过官方审核。
