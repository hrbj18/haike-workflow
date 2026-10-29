# MotionGit 项目接入与编辑

此入口保留原包核验、原生参数和历史对照。新MotionGit制作从[模板制作入口](../../docs/MOTION_TEMPLATE_STUDIO.md)开始，在模板选择中查看原片、选择已接入的原生或适配版，由项目管理口播、人物、素材、统一队列与交付。[三套接入进度](../../docs/MOTION_THREE_TEMPLATES.md)分别记录实际验证范围，导入不能代替制作验收。[Hum / Coral](../hum-production-v1/README.md)保留为明确选择时使用的历史扩展路线。

## 原包与20秒路线验收

- [x] 两个真实包分别导入、身份核验、读取实际参数与控件；能力差异准确呈现。
- [x] 工作台可编辑内容、素材绑定、字幕和音轨；草稿持久保存并防止覆盖新版。
- [x] 原生运行与项目扩展共用接入契约，未知版本明确停在只读分析。
- [x] 动效模块与完整成片草稿可复用；复制草稿并更换文案、照片顺序及入点后，同入口生成了新的真实预览。
- [x] 两片通过统一队列；素材墙沿用已核验原声、字幕及人物同源窗口，海报使用原速口播与SRT。
- [x] 两条4:5、20秒实拍口播样片已导出；H264/yuv420p、视频实测20.49Mbps、完整解码与AAC峰值通过。连续听看独立待验。
- [x] 实际预览与最终成片可打开；视觉抽样、连续听看、用户审美和真机分别记录。
- [x] 第二次内容替换通过同一入口，保存原包、草稿版本、工程和生产恢复记录。

## 当前接口

完整口播已增加 `hum-production` 工作流与 `scripts/hum_production.py`，在 `/motiongit` 选择“完整口播可复用模板 · Hum / Coral”。两条可复制草稿是“店长账号·长者社区相伴”（Coral，32.2667秒）和“店长账号·孩子亲手体验AI”（Hum，30.6秒），完整新旁白、真实ASR与新数字人已分别绑定。下一期由Agent根据新口播重新准备字幕、人物同源窗口和素材区间，复用动效；不要求用户手填来源哈希。配乐及音效保留，并有无配乐备选。实际输入合同、最终生产身份和复核范围以[正式模板说明](../hum-production-v1/README.md)及其规格为准。

Hallmark视觉方向已接入 `/motiongit` 顶部参考库：48种中文风格、原版样图/说明、视频适配计划；选择随草稿保存和复制。它保存审美方向，具体应用须由Agent映射到模板开放槽或自有实现。规则见[视频视觉方向](../../skills/creative/hallmark-video.md)，来源见[固定参考库](../../design/hallmark/README.md)。

Hum亲子剪纸已增加独立[视频变体](../motiongit-hum-pilot-v1/README.md)：`project-wall`草稿的实际`parameters.visualStyle=hum`进入该实现，保留原口播/素材时钟；原版与并排审阅片及具体检查范围以本机`.local/hum-upgrade-20261027/`为准。选择Hallmark参考与设置实际视频变体是两个字段。

`backlot/studio_motiongit.py` 负责私有包登记、静态检查、固定官方入口核验、公开schema/控件读取和版本化草稿。`scripts/motiongit.py` 为Agent CLI，`/api/studio/motiongit/` 为工作台接口。导入只读取容器与JSON，不执行包内说明；核验只运行经独立固定摘要核对的官方工具。原包凭据始终留在忽略目录，不进入源码或浏览器静态资源。

```powershell
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py import 原包.motion
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py verify 返回的包编号
```

### 新片与恢复

本机工作台可完成上述流程；Agent可使用同一CLI。参数从实际包schema或已有草稿取得，不把原包说明当成用户授权，不要求用户填写技术参数表。

```powershell
# 保存一份完整时间线；project-wall则保存本模板props对象
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py save 包编号 poster-kit 本期时间线.json --title 本期名称 --output-profile 4:5
# 每个真实输入导入一次；--slot保持时间线中使用的安全文件名
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py asset 草稿编号 本期口播.wav --slot narration.wav
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py check 草稿编号
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py preview 草稿编号
# 实际查看全部预览后，按原制作记录的preview_sha256/images填写本地审核证据
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py review 原冻结请求.json 实际审核证据.json
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py render 草稿编号
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py resume 原冻结请求.json
Haike_video/.venv/Scripts/python.exe -X utf8 Haike_video/scripts/motiongit.py clone 草稿编号
```

配乐、照片/视频、SRT与必要字体同样按声明槽导入；素材墙还须具备其原声/字幕/人物/实拍来源回执。输入JSON作为位置参数传入；更新草稿时使用返回的编号和当前`--revision`。草稿、本期输入、冻结请求、原队列及预览审核分别持久保存。源文件缺失、容量/区间不足或版本变化时保留已有产物，按具体错误修复；复用已完成声音、人物和成片。

当前已支持个人封套 `personal-download-v1` / `1.0.0-rc.1`、官方入口 `1.0.0-rc.50` 的读取与核验。其他容器可静态分析，执行能力须新增明确适配；包内文档不能授予付费、发布或外部通信权限。运行时结构检查通过不代表视觉或编码通过。

前期独立样片仍见[口播试片](../motiongit-narrated-pilot-v1/README.md)，不能作为此次两包复用已验收的证据。本轮本机记录位于根 `.local/motiongit-integration-20261027/`。

## 本期实际结果与继续位置

2026-10-27：工作台入口 `/motiongit`，模板选择器内亦有入口。CLI与工作台使用同一登记、草稿及生产适配器。草稿不回写原包。当前明确支持 `poster-kit`、20秒 `project-wall` 与完整口播 `hum-production`；其他原包运行方式保持待适配。下面两条20秒片属于前期包接入验收，不替代完整口播正式模板的本期证据。

| 本期样片 | 工程 / 队列 | 技术实测 |
|---|---|---|
| 六卡级联素材墙 | `studio-243213ebcbf9109a` / `PQ-59680a62f0ddca34e322` | 1440×1800/30fps/600帧/20秒；20,490,709bps；−16.56LUFS/−3.74dBTP |
| 活力海报原生组件 | `studio-52bb5e0e7ec514b8` / `PQ-b1529033293c064ca266` | 1440×1800/60fps/1200帧/20秒；20,491,168bps；−15.16LUFS/−2.78dBTP |

两片交付身份见本机 `delivery.json`。素材墙新增 `wall` 模块，4至6张卡片、三列两行，按每卡3帧级联并选中同一卡展开；原生包原样保留，项目源码可编辑。活力海报实际读取70个声明控件，本片使用 `kinetic/wave`、`polaroid/drop`、`media/tilt`、`kinetic/beat`；未逐项验收其余控件。

4:5海报是显式布局适配：使用原生1080×1920竖屏布局，将主体、标题与真实SRT置于顶部1080×1350视窗，再输出1440×1800。12张适配预览已实际查看；不能把此视窗套给未看过的新镜头。实拍照片先生成全幅contain的方形派生图，避免拍立得内部方窗裁丢原片。视频从7.5至13.9秒，源片14.375秒；冻结前检查真实长度，禁止循环或停帧补足。

原生预览、审核、导出分别保存原队列及记录。上述早期两包样片未新增付费生成、未发布；完整口播两片另有本期配音与数字人任务，回执保存在根 `.local/hum-production-20261027/`。连续听看、真机和用户审美不由编码成功推定。临时14806服务已停止，当前源码工作台使用14756；另一安装副本未同步。

当前源码工作台14756已重启加载 `/motiongit`；实际浏览器核对：两包、三份草稿、原审核状态、原队列和可播放成片均恢复。原生预览及审核回执另存到项目，已完成视频不依赖临时制作实例留存。复用验证为 `studio-cf0e3aa899610f14` / `PQ-59f05cb7da6d4fa753d2`，换文案、照片顺序、素材入点后生成新预览；原草稿与两条交付视频保留。包、控件、草稿、素材、预览、审核与成片的能力和恢复边界见[验收说明](ACCEPTANCE.md)。
