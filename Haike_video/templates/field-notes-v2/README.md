# 动效模板5 · 青珊瑚线索接力

文档类型：video-template-runbook。
标准版本：video-template-v1
模板规格：[实现规格](template.spec.json)

2026-11-03，`field-notes-v2`，v2.0.0，正式动效模板5。用户确认效果并明确要求编号纳入正式模板，登记见REGISTRATION.json，源码和依赖冻结见release.json。原正式模板4 v1.0.0完整保留。当前确认范围为本机24秒低清静音样式，换文案/素材和正式有声/高清另验。

用户已确认当前效果“这个效果是可以的”，回执见[APPROVAL.json](APPROVAL.json)；正式编号指令见[REGISTRATION.json](REGISTRATION.json)。由原候选登记为正式5只调整身份和执行门禁，画面编排保持用户确认版。

先读[总标准](../../../Haike-Videohub/agent-runbooks/视频模板编写标准.md)、[统一选型规则](../../motion-components/README.md)。[规格](template.spec.json)描述实现边界；[selection.json](selection.json)持有四场时钟、色板、人物角色与选型理由；Scene.tsx持有几何和适配行为。MD负责执行流程，JSON和源码负责稳定复刻，构建清单绑定实际素材/字体/导入图/依赖。

## 设计与复用

保留青珊瑚纸感、连续辅助人物小窗、字幕位置。时长仍24秒，章节改为6/8/5/5秒，给网格聚焦完整的建立/选中/返回过程。标题让位、线条同场交接、来源汇聚依据TalkCraft语法独立适配竖屏；网格段导入私有原组件再适配宿主运行时、背景、CSS作用域和保持期，四项全部明确为adapt。

不机械套用横屏默认字号、配色或背景持续运动。线条只承担标题到素材的同场交接，未实现跨场摄像机。网格原退出段改为回位后保持；不隐藏其余候选。替代方案与理由见selection。上游源保持私有，本目录不含其副本。

## 执行

输入为旧样板准备目录：低清素材、字体、720帧连续人物及静音episode/preparation。缺文件或哈希变更时重新绑定授权素材并准备，不自动换素材。命令从仓库根执行，使用已安装Node及Python虚拟环境：

```powershell
& Haike_video/.venv/Scripts/python.exe Haike_video/scripts/motion_catalogue.py check --plan Haike_video/templates/field-notes-v2/selection.json
node Haike_video/templates/field-notes-v2/verify-release.cjs
node Haike_video/templates/field-notes-v2/build.cjs .local/field-notes-v2-preview .local/custom-template-field-notes
& Haike_video/.venv/Scripts/python.exe Haike_video/templates/field-notes-v2/verify.py .local/field-notes-v2-preview
& Haike_video/.venv/Scripts/python.exe Haike_video/templates/chromatic-motion-lab-v1/serve.py --data .local/field-notes-v2-preview --port 14948
```

构建前验证模板5及原模板4冻结身份、当前选型与上游哈希、准备清单；成功生成episode/baseline、私有bundle和build-manifest。`http://127.0.0.1:14948/`是用户原确认的对照页，保留当时“候选”标签作为历史预览；当前正式身份读取本手册、library与release。构建后重载页面，等待字体/图片/人物解码再按[验收设计](ACCEPTANCE.md)检查；修改冻结样式须建立新版本并复验受影响区间。原预览14946保留。

输出资产留在.local，未生成新数字人、付费请求或发布。小窗新人物默认性价比的规则沿用[角色策略](../../config/avatar-generation-policy.json)；本轮复用旧素材，不触发生成。

完成条件：静态/负例检查、实际动作过程、边界与连播记录、源身份检查均有回执。验收版本见VALIDATION.json，本地逐帧和截图在`.local/field-notes-v2-review/`。本轮用户效果认可已记录；正式声音/高清、工作台/平台/异机保持待验，低清视觉通过不延伸范围。
