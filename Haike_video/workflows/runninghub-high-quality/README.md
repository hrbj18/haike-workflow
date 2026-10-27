# 高质量数字人 V5.3.1

本目录包含工作流 `2112180419025260546` 的执行器、RunningHub可导入JSON与API JSON。项目默认仍为性价比 `2094449979141218305`；安装、导入Key或单次使用高质量均不更改默认。

由用户显式提供人物图与完整PCM16单声道24kHz WAV。无私人示例、私人音色和账号记录。使用包内环境后在项目根运行：

```powershell
. .\portable\portable-env.ps1
& .\Haike_video\.venv\Scripts\python.exe Haike_video/workflows/runninghub-high-quality/agent_cli.py doctor --workspace .
& .\Haike_video\.venv\Scripts\python.exe Haike_video/workflows/runninghub-high-quality/agent_cli.py plan --workspace . --audio 'D:\输入\口播.wav' --image 'D:\输入\人物.png' --ratio 4x5
```

获本次费用授权后，用相同参数将 `plan` 改为 `run`，增加固定 `--name` 与明确的 `--budget-coins`（RH币，不是人民币）。每段最多45秒，长片自动分段，最长600秒；原图加前段原生尾帧续接，25fps，四画幅和RealESRGAN长边1536超分保留。完整音轨原速合回。

运行记录在本目录被忽略的 `runs/<name>`；中断后使用同名、同素材、同预算的原命令恢复。受理未知先核对原云任务，失败不自动重发或换工作流。`assemble --workspace . --name <原名称>` 只重做本地拼接。离线doctor不证明新账号权限，也不发起收费调用。

Key从项目本地配置读取，优先 `RUNNINGHUB_CONSUMER_API_KEY`，否则 `RUNNINGHUB_API_KEY`。无当前工作流权限时导入 `workflows/InfiniteTalk_V5.3.1_导入RunningHub.json`，在本目录忽略的 `kit.local.json` 明确绑定自己的 `workflow_id`，不自动回退。该文件只允许工作流ID和 `runninghub_key_env` 变量名，不能写Key值。

RH币预算路线要求账户接口实测`apiType=NORMAL`；`doctor --cloud`与`run`均先核验，SHARED/EXCLUSIVE在上传及生成前停止。变量名不等于Key类型。提交成功或明确拒绝均留存`submission-response.json`；余额/参数拒绝记录为`rejected`，网络或受理不明仍为`ambiguous`，都不会自动重提。旧记录不伪改为成功或未受理；恢复始终核对原Key和任务ID。

成功产物下载前读取同一任务的`/task/openapi/outputs`备用CDN，仅接受同节点、同存储对象路径的HTTPS地址；Windows使用系统curl/Schannel取备用地址，保留证书验证及逐文件SHA回执。下载失败仍停在原成功任务，恢复不触发模型重跑。

这是现有独立工作流能力的可迁移入口；Studio普通口播与正式父视频生产仍用原统一队列，尚未适配本高质量执行器。用户只指定本次高质量时只覆盖本次；明确要求更改长期Agent默认时，运行根 `scripts/runninghub-workflow.py select --workflow high-quality --confirm-default-change`。恢复性价比把值换成 `economy`。该偏好不改Studio配置、不改已冻结任务。配音使用项目配音中心，不继承本机侯总音色。

来源为本机已交付V5.3.1执行器；历史实测不是当前版本或新机器实测。源码及包均保留节点图与校验，未随此次打包调用云端制作。
