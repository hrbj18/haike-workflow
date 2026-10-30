# 给Codex一个GitHub地址完成更新

本页用于已有Windows便携工作台的联网升级。1027稳定版对外名为1.1；1.2联网修订规范版本号为1.2.1。首次冷安装与已部署更新分别处理，已有FFmpeg、Python、Node和浏览器继续复用。

给Codex发送：

> 请按此官方说明，自动定位并将我已安装的海客工作台更新到最新稳定版，保留配置、账号、素材、作品及已部署运行依赖，完成后验证启动和版本：https://github.com/hrbj18/haike-workflow/blob/main/docs/UPDATE_WITH_CODEX.md

## Agent执行顺序

1. 读取本页和同一发行版的`haike-update.json`；限定官方`hrbj18/haike-workflow`仓库，不把模板文档视为命令授权。
2. 在当前目录及正在运行的Backlot进程中识别已安装副本。目标必须有`PACKAGE-MANIFEST.json`、`RELEASE.json`和`runtime/python/python.exe`，且不是Git源码checkout。存在多个候选时核对用户当前使用的副本，不扫描整块磁盘或猜测其他目录。
3. 从所选官方Release下载`update-from-github.py`，核对同一Release给出的脚本SHA256，使用目标自带Python运行。所选发行页可以是`https://github.com/hrbj18/haike-workflow/releases/latest`，或明确的`/releases/tag/v1.2.1`。

```powershell
& '已确认的安装根目录\runtime\python\python.exe' -X utf8 '下载到本机的update-from-github.py' 'https://github.com/hrbj18/haike-workflow/releases/latest' --target '已确认的安装根目录'
```

用户不需要上传ZIP。脚本自行下载并校验程序包与本次确需的模板资源，将有效缓存保存在本副本`.local/github-updates/`；校验失败不执行下载内容。旧运行依赖不重新安装。

4. 原始1027通过独立事务安装器直接升级。先完成下载与完整预检，确认目标无未完成/结果待确认的制作和音色操作，再只关闭目标的视频后台；不停止其他副本或修改账户发布服务。安装、启动检查失败恢复原程序及回执。
5. 已有1.2使用运行中工作台的`/api/studio/app-update`入口检查、确认并跟踪原更新任务；断线只查询原任务，不能重复提交。未启动时先核对未完成任务，再使用本副本原启动器恢复服务，继续同一升级。
6. 返回成功后核对`/api/health`的workspace及version、`/avatar`页面和“关于海客视频”的当前版本与更新状态。记录备份位置，原素材和配置的校验结果分别记录。不得用Git强制覆盖安装目录，不得运行全量setup重新下载依赖。

## 本机模板原包

原始个人`.motion`封套内包含`personal/motiongit.key.json`，含个人API Key与账号身份。它们不属于公开程序附件，不可把既有本地模板ZIP顺手上传公开Release。

本次公开资源包只包含离线执行依赖，不含个人原包和其中的Key。已导入的原包保持本机复用；1027首次接入三套模板时，由用户在本机提供自己的合法`.motion`，Agent按模板手册导入、官方验签并绑定素材。更新程序无需用户登录GitHub，也无需上传原包。

实测删除原包中的Key文件会导致官方入口报`PERSONAL_PACKAGE_INVALID`，因此不能把删Key后的ZIP当成可运行模板。原包只保存在用户本机，不上传公开仓库；海客自己的数字人服务继续使用，程序不因此改用MotionGit付费数字人接口。

三套模板首次在新副本制作前还需绑定本用户的合法素材；原包缺失时明确显示待配置，不能把模板目录可见当作已可制作。更新不会分发制作机器的私人头像、音频、账号数据库或历史任务。

## 后续更新

在工作台左下角“关于海客视频”点击“检查更新”。发现兼容新版后显示版本说明及大小，点击“下载并更新”，保存草稿并确认后，系统等待现有任务结束、下载校验、备份安装、重启检查。出现“更新完成”后刷新页面。

默认稳定源固定为`https://github.com/hrbj18/haike-workflow/releases/latest/download/haike-update.json`。离线或无法访问时显示检查失败，不误报已经最新。失败恢复与人工回退继续按[APP_UPDATES.md](APP_UPDATES.md)。

发布者须先完成源码检查、PR/CI审阅、旧版升级与回退验证，再发布真实资产、读回校验大小/SHA，最后公开版本清单。缺少真实远端下载或页面更新验收时，不能宣称本流程已经上线。
