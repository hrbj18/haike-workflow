# 指定抖音视频下载入口与知识库

目标：用现有 MediaCrawler 客户端解析用户指定视频，并调用项目 materials.download_video 保存文件；不依赖 yt-dlp。

范围：新增 scripts/download_douyin_mediacrawler.py；默认使用工作区最上层 www.douyin.com_cookies.txt，支持 --cookies 指定 Netscape 文件。使用独立临时浏览器上下文，不操作现有登录浏览器。新增跨仓中文 runbook 和索引。

边界：不修改上游或全局媒体下载开关，不记录凭据、原始响应、带签名直链，不覆盖既有视频；限时请求和媒体大小上限。失败只输出安全阶段与异常类型。当前其他工作树改动保持原状。

验收：离线检查 Cookie 默认/显式路径、HttpOnly/过期/跨域过滤、恶意 URL 拒绝；实际下载用户提供的京东方分享链接，以独立文件和 ffprobe/解码证明成功；验证知识库链接与凭据检查，区分原有错误。记录可移植命令、失败恢复和实测范围。

不执行发布、转码、素材筛选或批量采集。

## 验证结果

- 2026-09-24：默认工作区 Cookie，MediaCrawler 获取视频 7688649786064424233，项目函数下载 4,779,611 字节。FFprobe：1080×1920 H.264/AAC，25.578005 秒；FFmpeg 全片解码退出 0。
- SHA-256：3293f4f5aed080359b8139f82ee1479630ff9e3d74655169c65d15600fb197bd。安全回执 download.json 与 MP4 同目录，产物位于用户 Downloads，本文件不保存凭据或直链。
- 显式 Cookie 路径离线检查通过，默认路径/显式路径、HttpOnly、过期和跨域过滤、非抖音 URL 拒绝的 8 项测试通过。
- 回归时发现项目已有纯 HTTP 单条下载脚本 scripts/download_douyin_video.py；已保持其原内容，新增 MediaCrawler 入口单独命名为 scripts/download_douyin_mediacrawler.py。两个入口合计 31 项测试全部通过。
- 完整离线测试：1139 passed、1 skipped、1 failed；唯一失败为 test_replication_theme.py::test_shipped_override_tables_are_effective（现有 Wi-Fi 8 主题关键词配置，本次未修改）。
- handoff 审计通过。本次 runbook 的结构、链接和凭据检查无错误；全知识库检查仍有原有“基于上下窗口的复刻优化.md”核验日期格式错误。共享工作树其他改动未纳入本次修复或提交。
- 知识库索引、根目录及 Videohub 的 AGENTS 路由已加入下载入口。Videohub 当前没有配置 Git 远端，本次集成为本地文件，不声称已推送。
