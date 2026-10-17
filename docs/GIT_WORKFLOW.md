# 海客科技 · Git项目管理

2026-10-17。用户确认视频工作台和收费中转站在 [hrbj18/haike-workflow](https://github.com/hrbj18/haike-workflow) 管理，保留仓库公开可见性和原提交历史。本次只上传新版独立分支，保留旧版标签，不合并 `main`、不打包。

| 目录 | 管理对象 |
|---|---|
| `Haike_video/` | 14754视频工作台、原生队列、图文与数字人口播、动效适配 |
| `prototypes/haike-avatar-generator/` | 工作台React界面源码及前端测试 |
| `api-platform/` | 收费中转站、账户、充值、兑换码、定价、账单、云端部署模板 |
| `creatorhub/` | 发布、账号连接及调度 |
| `docs/`、`.taskmaster/tasks/` | 设计、验收、部署及迭代任务 |

本机 `origin` 指向上述仓库；已有 `reference` 是本机参考目录，保留但不作为 GitHub 上传目标。安装和新分支均从明确提交读取，运行时、账号数据与代码分离。ADu引擎仍是独立第三方依赖，固定版本见 `PRODUCT_AVATAR_MOTION.md`，不嵌套复制Git元数据。

## 分支与提交

- `main`：本次保留原旧版提交 `05183670edca40483f4d2d212282e4c05c94cc84`。
- `legacy-before-v2-20261017`：固定上述旧版源码的保留标签。
- `dev-ybw`：现有集成分支；后续 feature/fix 经 PR 审阅后再合入。
- `feat/retain-capabilities-ui`：本次新版源码与通用 Agent 教程，不因上传就宣称正式稳定版或新机验收完成。
- 后续从集成分支建立 `feat/<功能>`、`fix/<问题>`；更新 `main` 和正式版本标签另行授权。

```sh
git switch dev-ybw
git pull --ff-only origin dev-ybw
git switch -c feat/new-template
# 修改、运行所属模块检查，再暂存明确的文件
git add 路径
git diff --cached
git commit -m "Add new avatar template"
git push -u origin feat/new-template
```

通过Pull Request审阅代码和检查结果。不要用force push改写共享分支。需要回退功能时用 `git revert <提交>` 产生可追踪的反向提交；资金数据库回退必须按独立备份恢复流程执行，不能跟随代码自动回退。

## 新克隆与构建

```sh
git clone --branch feat/retain-capabilities-ui https://github.com/hrbj18/haike-workflow.git
cd haike-workflow
python scripts/check.py
python scripts/build-studio.py
```

使用Python3.12、Node22+。`build-studio.py`从锁文件安装前端依赖并将编译结果放入本checkout的工作台；生成的静态目录不进入Git。Windows完整环境继续使用 `scripts/setup.ps1`，已包含该构建步骤。Mac运行副本位于另一个安装目录，开发源码构建不会自动覆盖它；验收后按明确目标同步源码、重建静态界面并重启对应服务。

收费中转站独立进入 `api-platform` 执行 `uv sync --frozen` 和 `uv run --frozen pytest -q`。生产更新从确定的提交导出该目录，按 `api-platform/deploy/README.md` 建立新版本目录再切换；私有数据保留在 `/var/lib/haike-api-platform`。Git提交不会自动改变当前云端服务。

## Git边界

Git保存源码、测试、公开模板、依赖锁文件、品牌资源和必要的设计文档。以下内容由 `.gitignore` 排除：本地环境、供应商和用户Key、Cookie、账单数据库、加密密钥及主密钥、用户素材、成片、备份、缓存和生成目录。

忽略规则不替代提交前核验：新增源码用 `git diff --cached` 检查，运行 `scripts/check.py` 和凭据扫描。不要用 `git add -f` 绕过规则。测试只使用隔离数据和假供应商，CI不配置生产密钥。数据库、主密钥和素材另行加密备份；Git不能恢复账户余额或用户文件。

主流程检查见 `ci/README.md`。未完成的付费能力、人工审核与跨机器验收边界以产品和任务记录为准。
