# 统一下载凭据接入

目标：采集器及单条抖音下载消费工作台已验证的下载账号快照，避免复制 Cookie、占用发布浏览器或用布尔标记伪装授权。

范围：项目自有 MediaCrawler runner/命令构造、单条下载脚本、Haike Studio crawler_config 与离线测试。共享快照存储由 CreatorHub 提供；不改第三方 MediaCrawler、后台 API、前端、真实账号与 Cookie。

决策：仅传账号 ID，子进程通过纯标准库存储读取已验证 douyin_download scope；实际注入采集专用 context。凭据不进入命令行、报告或普通配置文件。显式 --cookies 兼容优先；没有选择账号时保留旧默认文件。选中但缺失/失效应明确失败，不静默换账号或继续使用发布 profile。

验收：离线 fixture 验证凭据到达 context.add_cookies、MC cookie 登录配置和单条 resolve；测试跨域/无效 scope 拒绝，命令与报告不含值，正常及异常路径无临时凭据残留；保留原采集与脚本测试。所有 subprocess/browser 操作继续有限时；不做网络下载或扫码。

交付：适配代码、离线测试、最小 handoff 更新及追加过程记录。真实平台下载成功须另行在线验证，本次不声称完成。

实现补充：账号 profile/lease/state/runs/CDP 端口隔离；端口为 10000+ID，越界明确拒绝；UA 在运行时继承。非空 proxy 在浏览器启动前阻断，不静默直连。每个 Studio 输出目录保留原项目边界。未选择账号保留旧模式。该副本原过程记录文件缺失，因此新建只含本次事实的记录，未读取或恢复旧历史。

验证：相关采集 30 项、Studio 29 项通过；独立进程全套 1143 通过/7 原有配置与环境失败/1 跳过。真实 MC 安装、授权、下载仍待验证。

后续授权范围：将旧 Studio 抖音 login/login-confirmed 入口及 AiMaterials/DouyinRecovery 转向统一下载账号服务。confirmed 必须重新检查实际下载作用域和共享快照，不写人工确认布尔；不改统一账号服务、NetworkMaterials 组件，不启动服务。增加路由与前端恢复顺序离线测试。

旧入口验收：统一检查及实际采集预检均通过才允许恢复原任务，MC/授权未就绪不伪装成功。后端相关 71 项、前端模型 16 项通过；构建/复制/服务状态由根代理统一处理。
