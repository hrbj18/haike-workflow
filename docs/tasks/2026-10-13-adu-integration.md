# ADu 集成验收记录

2026-10-13，Task Master #11。版本与产品合同见 [产品说明](../PRODUCT_AVATAR_MOTION.md)。

## 范围

实际工作台新增动效口播，保留原海客三个版式和图文入口。完整模板目录全部接入；轻量九组件实际执行；方法型能力展示资料及人工审阅边界。未将历史49个包或候选组宣称为49种已稳定的新模板。

## 程序验证

使用安装副本 Python3.12，源码 Haike_video 下执行：

```sh
python -m pytest -q tests/backlot/test_studio_motion.py tests/backlot/test_studio.py tests/backlot/test_production_queue.py tests/backlot/test_production_queue_worker.py tests/backlot/test_production_queue_server.py tests/backlot/test_work_catalog.py
```

最终88项通过。覆盖真实视频结束时钟、素材归属/路径/ZIP、原文完整覆盖、配乐明确选择、动作绑定、字幕不重叠、HTML普通值、兼容组语义/数量/素材身份、不可变计划和源文件指纹、确认门、空草稿恢复、队列与作品合同。

前端 `node --test tests/*.test.mjs` 最终13项；生产构建通过。根源码 `scripts/check.py` 使用Python3.12通过，Python3.9不能解析项目已有的新版f-string语法，不作为本项目检查环境。

## 真实媒体验收

技术素材为既有海客 `haike-avatar-smoke-20261012/assets/incoming/avatar/host/T001_HOST.mp4`，不调用供应商。视频真实结束6.52秒，输出网格为391帧/60fps；6.56秒容器时长不能用于延长人物尾帧。测试动作落点为明示fixture，不称为自动识别词级时间。

| 测试 | 结果与私有证据 |
|---|---|
| 完整竖屏工程 | `.backlot/studio-motion-smoke-render3/summary.json`，native父队列完成，1080×1920/391帧/音轨/完整解码 |
| 九个轻量组件 | `.backlot/studio-motion-nine-smoke/{hero,point,number,compare,steps,quote,demo-owned,checklist,outro}/summary.json`；均完成，1920×1080/391帧/音轨 |
| 配乐＋双语字幕 | `.backlot/studio-motion-audio-caption-smoke/summary.json`；完整竖屏工程完成，QA音频不是正式配乐，原口播时钟不变 |
| 实际14754操作 | 草稿studio-75dae049dd104f89；PQ-329d12d75864b7f2cf00完成，作品work-353b0776a88d4bd773b34b8a待审核 |
| 播放器 | 正确版本v-23fadc86cbec6ca7dabeaf8f，1080×1920，6.516667秒，error为空，实际播放时钟前进 |
| 工程下载 | 浏览器下载成功；452成员、CRC无错误，与原生studio-4 ZIP同一SHA；草稿更新后仍绑定已完成版本4 |

输出保留检查、规划、混音、构建日志及新attempt工程；失败尝试保留不覆盖。完整检查通过不代表候选目录逐组人工验收，也不替用户确认最终版。

## 界面与连接

同视口/状态参考比较、桌面1512×737与手机390×844、模板筛选/样片/弹窗/焦点/无溢出见前端design-qa.md。SRT fixture仅供技术表单测试，不作为自动识别结果。

本轮发现原127.0.0.1:17894未运行。用户明确确认将已保存Key发送到 https://8.138.207.71:17894/v2 做免费验证；HTTPS正常校验，账户中心导航随网关更新。已验证余额¥20、冻结¥0、商业月消费¥0、四项可用；文本/视觉及数字人仍待开通。私有配置权限0600，记录及截图不含完整Key。本轮新增收费调用0、外部发布0。

## 已知范围

ADu需要本机安装固定引擎与媒体运行依赖；本机Mac已验，未声称Windows实机已验。完整候选组需要足够时间和本期素材；机器将缺项阻断。历史版本、手绘/新模板提炼/修剪通过专业方法流程使用，没有虚构一键自动实现。发布继续遵守已有作品确认、资料、账号和日历确认门。
