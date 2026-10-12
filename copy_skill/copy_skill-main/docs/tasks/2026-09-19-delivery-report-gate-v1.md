# 交付汇报文档门禁（delivery-report-gate v1）

Updated: 2026-09-20.

上一版（`docs/tasks/2026-09-17-delivery-report-doc-v1.md`）交付了**生成器**：一个可以手工执行的
`scripts/build_report_doc.py`。它没有解决用户提出的原始问题，只是把补写从「无工具」变成「有工具」。
本任务把同一件事从**手工脚本**升级为**管线产物 + 交付门禁**。

## 触发

用户连续追问：「为什么最近几期复刻视频没有提供汇报文档来补充主题背景」。核查结论：

- `汇报文档.md` **从来不是管线产物** —— `src/` 全树对生成器**零引用**，只有人会去跑它。
- 39 期交付里只有 **3 期**有文档（9.17智元远征A3 Ultra / 9.18手机集体涨价 / 9.18日本AI篡改历史观），
  且都是**事后手工补写**。
- 9.19 五期的 `清单.json` 里 **没有 `report_doc` 块** ⇒ 那批跑的时候管线根本没接上。
  **「功能已提交 + 单测全绿」≠「功能已生效」** 再一次成立。

## 目标

1. 管线自己写骨架：任何一条发布路径落盘交付目录时，同时写下 `汇报文档.md` 的初始版本。
2. 门禁可批量判定：一条命令能告诉你「哪几期缺文档 / 缺哪一段」，退出码可被 CI 或人工采信。
3. 门禁数字必须可信：体积口径不得被硬链接放大成假超限。

## 决定

- **落点**：`scripts/build_report_doc.py` 退化为**薄包装**（把 `src/` 入 `sys.path` + 显式重导出公开名），
  真正的实现迁到 **`src/douyin_intelligence/report_doc.py`** —— 管线要 import 它，`scripts/` 不在包内。
- **五个发布点全部挂载**：`run_material_replication` 内有五条发布路径（空池早退 / dry-run 早退 /
  预筛清空早退 / `download_only` / 完整链路）。只挂主路径等于给四条早退路径留后门 —— 空池那一期
  恰恰最需要文档来解释「为什么没有素材」。
- **opt-in 范式照抄 `episode_research_pack`**：`{"enabled": bool(block.get("enabled", True))}`，
  **缺省 true**（否则「新增开关」会静默关掉门禁）。登记进 `tests/conftest.py` 的嵌套剥离列表
  `_OPT_IN_NESTED_MATERIAL_BLOCKS`。
- **不翻 `degraded`**：人工段没填是**流程状态**，不是素材质量缺陷。把它写成 degraded 会让
  「降级」这个信号失去含义，也会让 `insufficient`/`degraded` 的读者误判素材。
- **人工段 = 二 / 三 / 六**，自动段 = 一 / 四 / 五 / 七。`--check` 在人工段仍带
  `<!-- HUMAN-TODO -->` 时退 **2**；`--force` 是唯一丢弃入口。
- **生效日 = 2026-09-19**，由 `--since` 显式声明。更早的 34 期记 `legacy`。
  9.18 五期（生成于 09-18 10:22~10:58，早于机制代码落地 14:22）同属 `legacy`，**且用户决定不补**。
- **体积按 inode 去重**：`direct_delivery` 下 `04-原片` 的条目与 `02/03` 的源片是**同一 inode**
  （`nlink=2~3`），按 `st_size` 求和会**重复计入约一倍**。

## 交付物

- `src/douyin_intelligence/report_doc.py`：`SECTIONS` / `report_status` / `write_report_doc`（不动点）/
  `audit_deliveries`；CLI `--delivery` / `--check` / `--all` / `--root` / `--since` / `--force`。
- `src/douyin_intelligence/replication_pipeline.py`：`_maybe_write_report_doc`，五处挂载。
- `src/douyin_intelligence/replication_delivery.py`：`report_doc_lines(manifest)`（历史交付 readme
  逐字节不变）。
- `tests/test_report_doc.py`、`tests/test_report_doc_pipeline.py`。
- `config/content_intelligence.json`：`report_doc: {"enabled": true}`。
- `AGENTS.md` / `CODE_MAP.md` / `CURRENT_STATUS.md` 同步。

## 排除

- 不给 9.18 五期补写（用户明确只要 9.19）。
- 不改 `script_candidate_pool()` 的时效缺口（另立任务；本任务只把它写进受影响期的第六节）。
- 不动 `download_budget` 把缓存复用计入 `used.bytes` 的缺口。

## 安全边界

- 跑全量 pytest 前/后 `git ls-files --deleted` 必须为空；不并发、不用 `pytest .`；禁 `git stash`/`gc`/`repack`。
- 批处理期间 `src/` 冻结。

## 验收

1. `pytest tests` 全量通过（2026-09-20：**1133 passed / 0 failed / 0 skipped**）。
2. 9.19 五期逐期 `build_report_doc.py --delivery <目录> --check` → **EXIT=0**。
3. `build_report_doc.py --all --root output/复刻视频 --since 2026-09-19` → **EXIT=0**，
   且 `待人工填写 0`。
4. AST 结构不变量：`test_every_publish_path_writes_a_report_skeleton` 断言五处挂载点齐全（`offenders == []`）。
5. 硬链接体积：造 `os.link()` 夹具，断言 `apparent_bytes=8192 / total_bytes=4096 / hardlinked_bytes=4096`。
6. `scripts/audit_handoff.py --root .` → **EXIT=0**，且 `CURRENT_STATUS.md` 不超 3000 非空白字符。
7. **重跑保留语义（2026-09-20 补修）**：`--overwrite` 重跑不再把已填人工段重置成骨架。
   `report_doc.carry_over_report()` 按文档头部 `主题` / `业务日期` 核对身份后携带已发布报告，
   五处 `_publish` 挂载点全部传 `destination`；
   `test_every_report_call_passes_the_destination_for_the_carry_over` 以 AST 断言
   `len(calls) >= 5` 且每个调用都带 `destination`。
8. **重渲染幂等自证（人工段 + 自动段都不被误伤）**：逐期连跑两遍
   `build_report_doc.py --delivery <目录>`，`diff` 只允许出现 `汇报时间` 行
   （必要时附 `体积口径` 的差额 1 KB 变化）。五期实测通过，第二遍零 diff。

## 遗留

- 9.19 五期的 `清单.json` 仍无 `report_doc` 块（该批早于接线）—— **下一批交付必须核对它出现**，
  否则等于接线没生效。
- 脚本复刻选源无时效约束，见 `CURRENT_STATUS.md` 的 Product limitations。
