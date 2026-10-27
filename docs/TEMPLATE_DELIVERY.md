# 模板封面与版本交付

## 安装旧版模板更新

1. 完整解压模板更新ZIP到新文件夹，关闭目标副本的工作台服务。
2. 双击包内`更新模板.cmd`，输入旧版项目根目录（包含`Haike_video`等模块目录）。脚本先核对依赖锁与包内SHA256；不兼容或文件损坏时在写入前停止，改用完整新版ZIP。
3. 读取成功回执和自动备份位置，重新启动目标副本。浏览器按Ctrl+F5，在数字人口播“选择模板→视觉模板库”核对40张封面。目录仍42条，图文与访谈两条保留原手册入口。

更新包只携带模板及配套前端、API和原生执行依赖；其他模块不更新。`PACKAGE-MANIFEST.json`按更新文件合并，`RELEASE.json`保留原整包版本并追加模板更新标识。不搬Key、登录状态、数据库、原片、人物、音频或历史作品。本机有效样片绑定优先，缺失时自动读`Haike_video/templates/library-covers/<id>.jpg`，不依赖制作机器的路径。截图是版式预览，不能用作生产低清代理。

先只检查：`powershell -ExecutionPolicy Bypass -File .\install-template-update.ps1 -Target "旧根目录" -Check`。

回退前关闭目标服务。用目标包的`runtime/python/python.exe`运行`install-template-update.py --target "旧根目录" --rollback "成功回执中的备份路径"`。脚本核对备份与更新后哈希；若用户后来编辑过文件则停止，防止覆盖后续改动。备份和回执在目标`.local/template-updates/`，不删除用户目录。

## 制作交付包

完整便携包仍用`scripts/package-portable.py`，源码必须来自干净提交。需要保留当前未提交工作时，先以根`scripts/check.py`的源码边界导出至独立本地Git快照，记录原HEAD、逐文件哈希和快照提交；不替用户提交或推送当前工作区。`--dependency-root`只从另一份已审安装读取依赖，应用代码始终从快照HEAD导出。默认运行时、许可、浏览器、采集依赖及排除边界沿用`DISTRIBUTION.md`，不包含私人配置。

40张截图经用户授权只随本地ZIP交付，不纳入公开Git。打包时从明确审核的本机封面绑定复制到stage的`Haike_video/templates/library-covers/`，写无绝对路径的`index.json`记录ID、来源截图哈希、尺寸与交付哈希，再重新生成完整包清单。不得扫描其他私有目录补素材。

完整stage通过检查后，运行`scripts/package-template-update.py --stage <完整stage> --baseline <旧版完整ZIP> --destination <新更新目录>`。更新器要求Python与Remotion依赖锁保持兼容；包括完整模板目录、已编译前端和所需源码差异。两个ZIP分别写SHA256，解压验CRC及清单哈希。

验收：隔离旧版副本执行预检、更新、重复更新与回退，确认配置和用户数据字节不变；新目录不配置私有绑定时API应返回40个可读封面、42份手册。浏览器实际打开模板选择弹窗，核对全部封面加载、分类、搜索、详情和手册。完整新版分别检查初始化、诊断、服务身份及所有模块源码。另一台物理机、云端付费与账号发布单独记录。
