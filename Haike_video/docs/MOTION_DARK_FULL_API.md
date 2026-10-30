# 完整多屏模板工作台接口

文档类型：implementation。2026-10-28。本接口编辑 `motiongit-dark-full-v1`；运行和源素材验证仍以 `studio_dark_full.py` 为准。

页面 `/motiongit?section=dark-full` 保留原包导入标签，新增“完整可复用模板”。草稿、素材绑定、准备记录和领取反馈保存于现有 Studio 私有 SQLite；浏览器不接收源路径、密钥或冻结执行对象。原包和两份服务端配方不会被编辑页面覆盖。

## 工作顺序

| 接口（前缀 `/api/studio/dark-full`） | 行为 |
| --- | --- |
| `GET /catalog` | 十组编号、名称、主观审美分、完整动作最短时间、可用配方和已绑定预览 |
| `POST /recipes/elder/copy`、`/recipes/child/copy` | 从本机固定入口复制配方；不存在时明确404。源文件先进入托管资产，同盘优先硬链接并校验SHA，跨盘复制先查空间 |
| `GET /drafts`、`GET /drafts/{id}` | 恢复服务端持久草稿和安全素材绑定 |
| `POST /drafts` | 保存 `id/revision/title/theme/script/recipe`；revision为CAS，旧版本返回409。内容完全未变时保留原revision和时间戳，真实改动才新增版本 |
| `POST /drafts/{id}/clone` | 携带revision复制新草稿；保留独立编辑状态，复用不可变素材 |
| `POST /drafts/{id}/assets?revision=…&slot=…&kind=…&filename=…&rights_confirmed=true` | 二进制上传并绑定，成功后递增revision；使用既有Studio归属、文件类型和媒体探测规则。视频专用上限256MiB、10分钟；通用服务默认80MiB不变 |
| `POST /drafts/{id}/captions` | 绑定本期真实字幕；请求为revision及`[{text,startMs,endMs}]`。文字须对应当前稿件，绑定当前口播SHA；不会估算时码 |
| `GET /readiness` | 读取现有ASR适配器的真实状态；不识别、不配音 |
| `GET /drafts/{id}/next-stage` | 为Agent返回`needs_voice/needs_alignment/needs_review`和现有配音/字幕接口，未发起云调用 |
| `POST /drafts/{id}/preflight` | 携带revision；按真实PCM WAV时钟与adapter检查，返回实际时长、帧数和动作清单，不冻结 |
| `POST /drafts/{id}/prepare` | 携带revision，冻结adapter准备结果；返回project/render/request SHA，不返回私有路径 |
| `POST /drafts/{id}/adopt` | 携带revision和已完成CLI工程的project_id；比对实际props/audio/provenance及全部素材槽SHA，一致才登记已有结果，不重新渲染 |
| `POST /drafts/{id}/submit` | 携带revision及request_sha256，提交同一统一队列，通过既有`run_local_recompose`专属claim领取，不改变通用队列闸门 |
| `GET /drafts/{id}/productions` | 读回历次准备、原队列状态、领取反馈、作品及视频版本 |
| `POST /drafts/{id}/productions/{sha}/resume` | 让既有worker再次领取同一个可恢复任务；不会创建新job或重做已完成付费上游 |

写请求遵守现有同源与Content-Type检查。JSON接口用`application/json`，素材用`application/octet-stream`。`recipe`只接受props/audio/provenance/shotPlan；`sources`由服务端管理，不能从浏览器提交任意本地路径。素材URL按草稿及槽检索，实际文件须在托管projects根内且SHA不变；最终视频须属于该草稿登记的准备记录、已完成队列任务并通过adapter验证。

## 口播、动作与恢复

- 可选择1至10组完整动作，以实际口播时长和内容为准；约30秒推荐3至4组，不设“最多4组”的硬限制。02和03成对且相邻，中央素材身份和源时钟由原adapter检查。页面改动作时保留已有内容及真实播放窗口，不为新动作编造取段；保护时长仍由原adapter执行。
- 更换口播或稿件会标记`needs_alignment`。使用现有已配置配音/字幕流程，或上传PCM WAV与实际SRT，再做本期素材看帧和人物同步检查。缺配置不表示TTS可用；此接口不替代原报价、费用授权和供应商调用意图。
- 更换实拍后，旧看帧记录失效。新增素材先入草稿，再由Agent做内容匹配、媒体槽和播放区间。未完成时preflight明确阻止，不把上传当作审片完成。
- prepare/submit响应未知时先读productions。request SHA在原统一队列形成幂等键；重复提交读回同一job。页面关闭不会丢失记录。统一制作通道忙时，原任务保持paused，反馈明确提示稍后恢复；不将“已提交”标成“已完成”。
- 原视频、无配乐备选、work_id和version_id由完成结果返回。作品链接使用现有`/projects?work=…`入口，发布仍走现有审核与授权流程。
- 已完成的CLI视频可通过adopt关联到内容一致的工作台草稿。接口先验证冻结记录及完成队列，再按真实口播重新preflight，对比画面参数、字幕、素材入点、音轨计划、公开来源和每个槽的实际文件SHA。路径可因托管复制而不同，内容不能不同；字幕、入点或文件发生变化时拒绝登记。CAS在检查前后保护草稿版本，重复登记只保留同一条制作记录。

## 本机预览注册

总控可在忽略目录 `.local/motion-full-20261028/workbench-previews.json` 登记：

```json
{"groups":{"s04":{"path":"服务端实际预览文件路径","kind":"image","label":"实际候选静帧，未代表连续成片验收"}}}
```

预览文件仅由服务端固定注册表解析，API只返回本机安全URL。未绑定的组显示“预览待绑定”，不假装已有动态视频。原包作者资产与模板代码的许可边界仍按模板说明执行。

## 当前验收证据

16个后端API合同测试通过：持久化/CAS、无变更保存不增版本、复制、路径与凭据边界、同源、缺配方、真实上传校验、口播时钟失效与SRT绑定、脚本待配音、重复提交原job、通道busy及256MiB专用限制；adopt测试包含成功与幂等、字幕/素材入点/文件SHA变化拒绝、过期和检查期间CAS冲突、未完成任务拒绝。前端模型、原站点打包和路由共12项Node测试通过，Vite及Sites构建成功。所有测试无真实付费调用。

独立QA服务在14882，使用C盘自有测试DB，prepare/submit/resume被测试服务明确禁止。两份真实配方仅通过HTTP复制、恢复和检查安全响应，未冻结或提交生产。浏览器自动验收被Computer Use工具停止，原因是无法可靠确定Windows浏览器当前URL以执行策略；本轮未改用其他UI自动化方式，不能据构建或HTTP测试声称浏览器视觉验收通过。

正式14756源码服务已用根构建脚本部署，并经标准启动器重启；14754未操作。两条CLI成片已通过真实HTTP adopt关联到各自复制草稿。GET productions回传原completed job/work/version，整条视频GET流式SHA与已完成文件一致，Range返回206且MP4头有效；重复adopt幂等，复制草稿后修改保存不会改变原草稿或原视频。操作未新建渲染任务或调用付费服务，完整结果见忽略目录`.local/motion-full-20261028/workbench-live-result.json`。视觉验收仍待用户或获准工具实际观看。
