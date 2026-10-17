# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-17（`main` = `134ae69`）

## 进度

- **M1 完成并已归档**：change `m1-event-log-and-turn-loop` 已合入 `main`（merge commit `141e28c`），归档在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`，tag `m1`。
- 五份主规格已同步进 `openspec/specs/`（`openspec list --specs` 可查），`openspec validate --specs` 全过。
- **M2 的规划工件已写完**：change `m2-file-tools-and-fences`（proposal + 六份 spec delta + design + 55 个任务），`openspec validate --strict` 通过，未开始实现、未建分支。下一步是 `/openspec-apply-change`。

## 门禁实测

| 门禁 | 实测 |
|---|---|
| 测试 | 62 个全绿；全量带覆盖率记账约 15 秒 |
| 覆盖率 | `coverage combine` 后 TOTAL **95.62%**（457 语句 / 20 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `cli/main.py` 96% · `provider/mock.py` 98% · `events/fold.py` 98% · `loop/turn_loop.py` 90% · `events/reader.py` 85% |
| 类型 | `mypy --strict` 干净，17 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（27 文件） |

要再抬覆盖率地板，补 `events/reader.py` 与 `loop/turn_loop.py` 的判据，不要凑低价值测试。

## 待办与已知缺口

- 延后的重构：`docs/adr/0002-deferred-refactors.md`（7 条，第 4 条已处理）。现有两份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`；新增按 `domain-modeling` 的 `ADR-FORMAT` 扫最大号 +1 → `0003-slug.md`。
- 变异测试记录与剩余缺口：`docs/verification/m1-mutation.md`。
- `_run` 的内核失败 stderr 分支没有黑盒覆盖；Ctrl-C 只在进程内测过（Windows 上没有 CTRL_C_EVENT 黑盒）。
- replay 把工具描述当成空：M2 注册真实工具后必须改成从事件前缀推导（ADR-0002 第 7 条）。
- 门禁判据目前**只在 Windows 上跑绿过**，仓库没有 CI。跨平台对齐（Linux/macOS）与 CI 矩阵已裁决并入 M3，不单开里程碑——见 `docs/roadmap.md` 的「跨平台与 CI 排在哪儿」。M2 的 seam ⑥ 判据同样只在 Windows 验证；平台绑定点只有路径规范化（大小写 / junction）、tty 检测、SIGINT 三处，围栏本身不做 OS 级强制所以天生可移植。
