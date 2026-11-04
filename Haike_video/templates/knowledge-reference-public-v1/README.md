# 纸笔与粉笔：独立公开参考实现

文档类型：video-template-runbook；标准：video-template-v1。

规格：[点阵手账](paper.spec.json)、[粉笔黑板](chalk.spec.json)。两者均为`implementation + specification`，目前只完成源码、真实输入/字体宽度门槛和几何测试；实际参考保真、完整输出、听审和目标环境分别待验，不能以结构/几何测试提升视觉状态。

本实现身份`knowledge-reference-public-v1 / 5.0.0-independent.1`与原个人包身份分开。观察来源为官方公开gallery的12张纸笔、24张粉笔图，以及本次合法原生预览/正片。没有读取、提取或解密受保护实现，没有拷贝原图、原材质图片、原笔图片、图标包或私有代码。全部材质、笔、图形、镜头和绘制代码是本目录独立创作；原创代码随仓库源码许可，字体分别保留OFL，不为原个人包授予再分发许可。

前端卡片身份继承现有`motion-replay-presentation.json`及`config/motion-replay/imported-native-full.json`：纸笔`motion-package-mg-178e6870ae932019c6bf2fe9`，粉笔`motion-package-mg-5b31b7dd6e6709861dc6ac88`。`template_id`仍分别为`knowledge-explainer-sketchnote`与`knowledge-explainer-chalkboard`，不能代替`gallery_id`。只读准备、冻结父请求和实际执行回执均携带canonical卡片ID；新增版本与`haike.public-knowledge.*`动作命名空间保持独立，原登记不覆盖。

`drawing.ts`持有实际字形揭示、向量笔、荧光、胶带、便签与原创图标；`backgrounds.ts`持有确定种子的点阵/纸粒/黑板擦痕/边框/托槽。`paper.ts`持有长页中对象永久ID、镜头接力、逐项笔写、便签修订与回看弧线；`chalk.ts`持有疏排章栏、逐项粉笔正文/关系线及8种单独的几何示意。通用B6只能选择compare/process/evidence/recap/definition，不能把门店稿或任意题材硬套球体模型。科学模式须显式传入同一对象/光源/投影参数，开发示例为静音`previewOnly`，不冒称对应B6旁白或原演出。

参数真值在这些源码与`types.ts`；只开放`episode.json`中的文案、明确对象、语义事件和有限模型参数。纸笔每个对象分别消费camera/write/highlight/draw/annotation事件；修订/回看/总览单独消费事件。粉笔章标题、章栏、正文、对照答案、关系线各有独立窗口。声音决定完整主时钟；动作历时是基于可见参考独立编写的近似值，非原包参数导出。留白/阅读窗可延长，不将整段动作等比拉长。当前持续医疗边界为独立实现新增层，和原版末段note/conclusion中出现的边界不同；该差异必须随实际对照记录，不以语义等同冒充画面相同。

字体是实资源。`font-provenance.json`保存独立公开上游commit/下载地址、字重/版本/摘要、OFL全文以及与参考声明的比较。Long Cang、Fraunces、JetBrains Mono三项字节相同。霞鹜文楷采用作者公开完整Medium TTF，原参考声明较小500WOFF而无版本元数据；家族/字重一致不等于字节或字距相同，实际图片对照前不提升该维度。渲染不访问字体网络，不用Noto或系统字体回退。

## 输入、执行与恢复

1. 输入为私有`data/public/episode.json`、本期完整WAV/可选授权音乐、四份公开字体及`preparation.json`。准备清单逐SHA绑定原批准parameters、真实ASR句证据与同一完整声音。默认无人，不开放人物、照片或B-roll输入；对外来源字段拒绝内部文件/批次标签。标签/便签使用真实字体测宽，超出时拆分画面短标签而保留完整声音/字幕，不默默缩字。
2. 独立项目先按既有checkpoint入口初始化。`backlot.motion_knowledge_public_production_v1.prepare(queue,{data})`只核对现有输入与源码/运行时并给出冻结请求。公共只读适配入口为`motion_knowledge_public_execution_v1.prepare(template,request,workspace=...)`。缺失运行组件明确阻断，不安装、不换版本、不购买服务。
3. 精确生产合同`haike.knowledge-reference-public/1`，固定producer `backlot.motion_knowledge_public_production_v1`，现有kind `studio_investment_recompose`。须由公共固定允许列表登记后，使用`motion_replay_production.py submit --request <冻结JSON> --phase preview`与`execute --job-id <原编号> --confirmed`。开发关键帧亦沿全局单道，不直接调用render.cjs绕过队列。
4. `review(queue,request,evidence)`要求同身份完整关键帧清单、实际查看声明、文字观察及显式`decision: approve|reject|changes_requested`。拒绝或要求修改不能写通过。正式`--phase render`在入队前核对明确批准、原预览父、执行回执和全部PNG的字节/尺寸/可解码性，并把具体预览/图片/审核SHA冻结在render请求中；领取执行后、开始媒体调用前再核对，等待期间任何绑定变化均拒绝。输出1080×1920/60fps、视频≥20Mbps、完整原速声音、持续医疗边界和真实ASR字幕。编码帧/混音/设备听看/保真单列。`previewOnly`的科学示意禁止正式输出。
5. preview幂等键只取原请求与阶段，审核说明或时间不改变preview身份；重复提交同一已完成预览复用原父并返回`artifact_integrity`。`preview_integrity(queue,request)`独立给出完整性状态、原编号与明确修复方法；完成但缺图/缺清单时不自动覆盖。render始终复用该阶段原键，新approval不能另建旧render父。需要修订时保留旧父/冻结/产物，显式新建revision的data与project_id重新准备，或从备份恢复原预览/审核精确字节；不能靠新审核重建旧任务。源码、字体、episode或运行时变化使旧回执失效；不修改受保护原包或既有冻结版本。

当前必要门槛：公共路由接线、真实队列开发帧、逐机制实际对照及有差异项定向修复。大留白和小图文是原通用粉笔版式特征，保留其事实；手机可读性不能由本机截图推断。连续听看、真机与隔离升级复现保持待验。
