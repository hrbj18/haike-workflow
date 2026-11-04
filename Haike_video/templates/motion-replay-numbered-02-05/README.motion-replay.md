# 动效模板2–5旁路复刻适配

公共规范见 [MOTION_REPLAY_STANDARD](../../docs/MOTION_REPLAY_STANDARD.md)。注册文件为 `config/motion-replay/numbered-02-05.json`；接口为 `backlot.motion_replay_numbered_02_05.prepare(template, request, *, workspace)`。保留四套原release、源码、确认记录与效果，不迁移Hypit Runtime。

| 模板 | 精确版本 | 保留范围 | 执行边界 |
|---|---|---|---|
| kinetic-field-v1 / 2 | 1.0.0 | 16秒，24fps；设计540×960，原render scale=.5，编码270×480；完整声音原速、固定gain | 返回原 `kinetic_field_preview.py` 统一队列入口；高清、任意长稿未开放 |
| nana-mint-explainer-v1 / 3 | 1.0.0 | 13景薄荷横屏1920×1080/30fps；认可片89.266667秒有声 | 返回原 `nana_mint_preview.py` 队列入口；作者准备的真实scene/cue/caption时码由原TSX消费 |
| field-notes-v1 / 4 | 1.0.0 | 24秒、四场各180帧、720×1280/30fps、低清照片与连续人物小窗、静音 | 本地Player；没有完整父队列生产路由 |
| field-notes-v2 / 5 | 2.0.0 | 原24秒、6/8/5/5秒四场、低清照片、静音；实际Arrive/Compare/Connect/Converge | 本地Player；网格仍从本机私有原组件导入，不分发私有源码；没有完整父队列路由 |

准备仅接受已由原模板准备入口生成的目录。新稿先按原模板README取得完整音频、同源人物、实测ASR与合法素材并运行原prepare；此旁路不生成这些内容，不从本机私有默认自动选素材。模板3的scene时码和明确cue可变，内部固定节奏仍锁定；不支持任意13景重排、独立events覆盖或按字数均摊时码。模板4/5不会把照片改为视频或自动开启主声音。

从仓库根目录运行；Python使用本checkout虚拟环境：

```powershell
# request.json: {"data":"<已准备的独立本期目录>"}
Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_replay.py prepare --template-id field-notes-v2 --version 2.0.0 --request <本期request.json>
```

`request`只允许 `data` 和可选的 `action_ids`。`action_ids`若出现，必须等于该模板注册动作的**完整固定顺序**；子集、重复、替换和重排均明确拒绝。新版本、未知字段、未消费cue、文件SHA变动、必需资源缺失、媒体不足或时钟不符直接阻断。缺data返回blocked；不创建目录、不入队、不构建bundle、不调用供应商。

返回对象含 `renderer`、`props`、`action_bindings`、已解析的 `timeline`、`inputs`、`blockers`、`queue_route`、`execution_status` 和 `reproduction`。`inputs.episode_manifest`是来源/哈希准备清单；`inputs.renderer_input_file`才是实际读取文件：模板3为 `public/content.json`，其他三套为 `episode.json`。模板2传入原KineticField的 `content`，模板3传入 `episodeFile` 与实际content；4/5传入原场景消费的 `episode`，只补原预览相同字体族。`prepared`只表示输入准备通过；模板4/5同时返回 `preview_prepared_production_blocked`，没有视频制作授权或完整渲染路由。

模板2/3通过返回的原队列脚本生成本期关键帧，实际看帧并完成原design-review后，才沿原入口做已请求的完整导出。模板3的bundle仍由其原render.cjs的bundle阶段准备；本适配器不运行完整renderer，不绕过队列。原确认音轨保持文件不变；重新配音/混音必须按原模板执行，不继承旧听审。

模板4/5的独立预览可以消费保存下来的prepare返回JSON。输出须是全新 `.local` 目录：

```powershell
node Haike_video/templates/motion-replay-numbered-02-05/build-preview.cjs <prepare返回JSON> <新的.local预览目录>
# 启动本地只读HTTP服务后，打开其真实端口；不使用原14754安装副本。
Haike_video/.venv/Scripts/python.exe -m http.server <空闲端口> --bind 127.0.0.1 --directory <新预览目录>
```

构建前重新调用公共prepare核验props，复制已绑定的素材，生成独立Player和 `motion-replay-build.json`。4号构建只导入原RecipeStage，不要求5号私有网格。5号使用与原build相同的CSS作用域、纸白背景适配和原 `.65` 缩放；保留原Freeze202网格保持。构建不是视频渲染。

`/?capture=1&frame=640`查看原全片帧；`/?capture=1&action=haike.field-notes-v2.converge&localFrame=70`通过实际动作绑定求得原全片640帧，再调用原场景。局部动作检查没有更换任何场景组件，也没有重排节目。`MotionReplayFieldNotesAction`在宿主**原绝对帧**上验证动作范围并调用原组件，连续人物不施加Freeze或局部重启。冷加载必须等字体/图片/视频解码后核对 `video.currentTime` 与原帧，必要时重新定位；加载帧不能作为画面保真证据。该动作调用只是原场景的检查入口，不能组合163目录动作。

源几何、裁切与精确运动参数继续在原TSX/配置中。注册事件是源码读取路径及时间关系；例如模板2标题实际从305帧挂载，TextReveal的内部参数与词数决定落定点，不能把旧动作索引中的估计13.4秒当真值。修改原设计需另建原模板版本，不更新旧release掩盖差异。

检查入口：

```powershell
# 在Haike_video目录
.venv/Scripts/python.exe -m unittest tests.backlot.test_motion_replay_numbered_02_05 -v
# 仓库根
node Haike_video/templates/motion-replay-numbered-02-05/test-bindings.cjs
Haike_video/.venv/Scripts/python.exe scripts/check.py
```

`registry.py`只生成本旁路注册文件和执行绑定快照，绝不刷新原release。修改旁路适配器、包装或构建代码后，经审查运行它重新绑定本旁路源码身份；必须重验受影响范围。本轮实际证据和历史限制见根 `.local/motion-standard-unification/A/HANDOFF.md`；私有素材、原包、准备产物不随公开源码分发。没有新增付费、发布或安装副本同步。
