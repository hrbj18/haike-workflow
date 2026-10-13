# 海客科技 · Git项目管理

2026-10-13。视频工作台和收费中转站统一在私有仓库 [vincent841218449/haike-workflow](https://github.com/vincent841218449/haike-workflow) 管理，原上游导入提交保留。

| 目录 | 管理对象 |
|---|---|
| `Haike_video/` | 14754视频工作台、原生队列、图文与数字人口播、动效适配 |
| `prototypes/haike-avatar-generator/` | 工作台React界面源码及前端测试 |
| `api-platform/` | 收费中转站、账户、充值、兑换码、定价、账单、云端部署模板 |
| `creatorhub/` | 发布、账号连接及调度 |
| `docs/`、`.taskmaster/tasks/` | 设计、验收、部署及迭代任务 |

`origin` 是自己的私有仓库；`upstream` 是原 `hrbj18/haike-workflow`。只在明确需要同步时读取上游，不把自己的中转站代码推送到上游。ADu引擎仍是独立第三方依赖，固定版本见 `PRODUCT_AVATAR_MOTION.md`，不嵌套复制Git元数据。

## 分支与提交

- `main`：经过检查的交付基线。
- `dev`：后续功能集成。
- `feat/<功能>`、`fix/<问题>`：从dev创建，每个独立修改单独提交，Pull Request合回dev；检查通过、人工验收后将dev合回main并打版本标签。
- 本次基线标签 `baseline-2026-10-13` 代表已记录的功能及验收范围，不表示所有候选模板和未开通API已商用验收。

```sh
git switch dev
git pull --ff-only origin dev
git switch -c feat/new-template
# 修改、运行所属模块检查，再暂存明确的文件
git add 路径
git diff --cached
git commit -m "Add new avatar template"
git push -u origin feat/new-template
```

通过Pull Request审阅代码和检查结果。不要用force push改写共享main/dev，不把更新上游等同于覆盖本地定制。需要回退功能时用 `git revert <提交>` 产生可追踪的反向提交；资金数据库回退必须按独立备份恢复流程执行，不能跟随代码自动回退。

## 新克隆与构建

```sh
git clone https://github.com/vincent841218449/haike-workflow.git
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
