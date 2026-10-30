# GitHub Actions

工作流已启用，位于 `.github/workflows/`，main/dev提交、Pull Request 和手动运行都会触发，标签不重复运行：

- `source.yml`：Windows/Python3.12源码边界、迁移测试、PowerShell解析、固定版本Gitleaks凭据扫描。
- `components.yml`：API账户/账本/网关假供应商测试、视频工作台/队列回归、Node22前端测试与生产构建。

Actions仅有源码读取权限，没有供应商密钥、平台Key或服务器SSH凭据。检查不启动真实收费调用或发布任务，也不自动部署、复制账本或修改生产数据。

每个检查有超时；同分支的新提交取消旧检查。第三方Action固定到已核验的官方提交，依赖使用项目锁文件或声明的测试环境。新增外部部署工作流需单独明确目标和数据迁移步骤。

分支及迭代流程见 [Git管理](../docs/GIT_WORKFLOW.md)。
