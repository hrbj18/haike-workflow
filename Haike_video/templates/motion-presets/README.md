# 正式定稿动效预设

1.2.2仅交付用户已认可的蓝白任务口播、点阵手账两款正式预设。ID、版本、执行协议、原包条件和参数SHA以[manifest.json](manifest.json)为准。配方保存动作结构、素材槽和编排要求；每期声音、字幕、素材、时序和审核独立绑定。它不包含开发机草稿或本期私人输入。纸感及其他新模板继续本地优化，后续单独验收发行。

当前后续开发分支已在上述公开主线基础上加入纸感1.1.0及[通用素材规则](PAPER-EVIDENCE.md)，不改变两款已发行配方SHA。两份不同口播的实际整片已验证；用户反馈效果改善并询问是否同一模板，二者确实复用同一六段动作和支持层。开发分支的三款清单不代表公开1.2.2含纸感。

蓝白是项目自有源码；点阵需`knowledge-explainer-sketchnote@2.7.3`，使用已核验rc.54。先通过原有导入/验签入口接入自己的合法原包，不修改或公开个人封套。已有原包本机复用；没有原包的新用户仍须提供自己的合法原包。未知版本不自动执行。

## 网页与Agent

工作台`/motiongit`的“定稿动效与原包”显示正式预设。点击“用此模板制作”创建独立草稿；缺原包时按钮禁用并指明所需版本。初稿无旧时码和审核，尚不能直接渲染。Agent按真实口播和字幕填写每镜时点、可换文案和素材绑定，保存并检查后走原预览/审核/统一队列。

HTTP入口以本机实际工作台为根：

| 动作 | 接口与结果 |
|---|---|
| 查询正式预设 | GET `/api/studio/motiongit/presets`，返回身份、绑定要求和本用户原包可用性 |
| 新建 | POST `/api/studio/motiongit/presets/{id}/drafts`，JSON可为空对象；也可传`title`和`parameters`本期参数覆盖，数组整体替换；可用`package_id`明确指定本用户已验签的匹配原包 |
| 后续操作 | 沿用`/drafts/{id}`、素材上传、参数检查、预览与制作接口；写请求携带本机Origin |
| 程序能力身份 | GET `/api/studio/motiongit/preset-capability`；文件身份与原包可用性分别记录，不表示已完成整片或听看 |

在安装根使用本副本Python调用：

```powershell
python Haike_video/scripts/motiongit.py presets
python Haike_video/scripts/motiongit.py create-preset quest-approved-portrait-v1 --title 本期视频
python Haike_video/scripts/motiongit.py create-preset quest-approved-portrait-v1 --input 本期参数.json
```

CLI和HTTP调用同一创建逻辑。参数结构沿原工作流：蓝白`props/audio/provenance`，纸感`workflow/timeline`，点阵`creationProfile/captions/sentenceEvidence/segments`。完整绑定规则在各配方`binding`。新建要保留所命名预设的关键机制；后续修改通过原草稿编辑保存，不自动修改公开预设。

蓝白每镜`from/frames`和局部`cues`需明确填写，提问输入完再出现证据，榜单用原编号完整换位，两个路径镜头保留同ID/节点且不重置。纸感按原包最短动作时间填写`t0/t1/cues`及连续`narrationMap`；点阵句级证据与本期真实音频SHA一致。不同声长不得整体缩放旧时码；素材不足、字框溢出或声源不一致由原预检拒绝。

纸感的`narrationMap.beats`与组件`cues`职责不同：前者逐句绑定真实字幕，`timing: sentence`须保留该字幕单元完整文字及起止时间；后者只选择该控件需要的动作节点。不能把所有字幕起点塞入手机或引用控件的`cues`，否则会推迟实际内容揭示。真实词边界可按语义组合字幕；保留原词时码，不均分汉字，短尾字并回相邻完整短语后重验阅读。一个文件的`mediaPolicies`会作用于重复引用；要不同源入点可使用独立素材槽，并以实际计划中的窗口为准。

人声和人物不得拉伸或循环填时长。配乐如按既有授权明确循环，须先保存原音乐SHA、授权来源、准备命令与新文件SHA，再把完整配乐绑定本期；不能暗中补长。不同声音默认不添加旧人物，只有同源证据及真实可用区间完整时才启用人物槽。

绑定与生产门禁是两件事：保存初稿不表示参数已通过，更不继承旧片审核。完整口播、配乐、字体、原片入点和可选同源人物按原生产契约审核；换输入后重新预览。点阵当前没有局部人物/实拍槽。

## 版本与更新

草稿持久保存`preset_source`中的ID、版本、配方SHA和创建时清单SHA；复制与编辑保留其来源。旧`quest/params.example.json`和原包SHA保持，预设升级不自动迁移历史草稿。旧作品可继续恢复。

打包器生成`delivery.json`，绑定正式清单、配方、公共代码及编译前端。发行清单/RELEASE同时记录其SHA和精确预设身份，事务更新重启时校验；同版本缺文件也不能报告完整成功。此文件由已验收发行构建生成，不从开发机私人运行目录复制。本轮实施与升级/渲染验收状态见[开发指导](../../docs/SINGLE_DEVELOPMENT_GUIDE_TEMPLATE_UPGRADE_20261102.md)。
