# 模板Mac复刻包维护

契约：`offline-template-reproduction-v1`，仅本地开发复刻与迁移验证，不是原生工作台队列/账号/发布环境的替代品。用户2026-10-25明确要求将全部模板私下交付同事Mac；本包可以包含用于该目的的原始实例媒体，禁止混入密钥、会话和账本。公共源码分发仍遵循根docs/DISTRIBUTION.md，不上传私人交付包。

构建器为根`scripts/package-template-kit.py`。输入是已审核的本机media-map（catalog ID→sample、SHA、poster、冻结render目录），输出必须为新目录。模板源码/共享手册和原生适配器参考保留目录关系；实例只取TS/TSX/CSS/layout与props，public仅取指定媒体后缀，不取请求、回执、账户配置。素材按SHA去重，预览与原媒体不重新编码。

Mac使用Python/Node/FFmpeg原生命令；模板字体通过React生命周期中的delayRender/useEffect等待OFL字体加载，不能在模块顶层创建未清理计时器。导出使用固定依赖锁、完整音频主时钟及高保真中间片，再执行20Mbps交付检查；六帧smoke不验证长片码率。输入/输出保持独立，不覆盖已有成片。

发布包前：检查全量本地依赖和媒体引用、凭据模式扫描、SHA完整性、至少一条完整实例及代表家族smoke、代表画面；记录实际平台。只按交付文件清单ZIP_DEFLATED level9归档，写SHA256；node_modules、.work、exports、系统二进制、日志和原账号数据不进包。压缩后完整CRC并逐项流式SHA读回；保留解压文件夹和ZIP。Mac真机待同事执行，不以Windows测试冒称通过。

本次版本清单以交付根KIT.json、SHA256-MANIFEST.json、验收说明.md为准。新源码和历史examples的区别须保留，不能把旧样片上的已删除页脚当当前模板规则。
