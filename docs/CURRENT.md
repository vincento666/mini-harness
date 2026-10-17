# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-17（分支 `change/m2-file-tools-and-fences`，`main` = `134ae69`）

## 进度

- **M1 完成并已归档**：change `m1-event-log-and-turn-loop` 已合入 `main`（merge commit `141e28c`），归档在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`，tag `m1`。
- 五份主规格已同步进 `openspec/specs/`（`openspec list --specs` 可查），`openspec validate --specs` 全过。M2 的六份 delta 还没同步——archive 时才同步。
- **M2 实现完成，收尾门禁未跑**：分支 `change/m2-file-tools-and-fences` 上 53/55 个任务已勾，剩 15.1（变异一轮）与 15.2（Learning Gate）。未合入 `main`、未 archive、未打 tag。
- M2 落地的东西：五个文件工具 `read` / `write` / `edit`（CAS）/ `glob` / `grep`；三段派发管线（校验 → 围栏 → 执行）；围栏判定（档位 → 工作区边界 → 要不要问人）；`approval/request` 与 `approval/response` 事件；`error/fence` 的四种 code；`FENCE_DENIED` → 退出码 3；`SessionSettings` 同时是 `run_session` 的入参与 `session/start.payload` 的来源。

## 门禁实测

| 门禁 | 实测 |
|---|---|
| 测试 | 137 passed / 1 skipped（skip 的是符号链接判据：本机不允许创建符号链接）；全量带覆盖率记账约 27 秒 |
| 覆盖率 | `coverage erase` → `coverage run -m pytest` → `coverage combine`（合并 29 份 partial）后 TOTAL **96%**（798 语句 / 29 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `tools/fences.py` 100% · `tools/dispatch.py` 100% · `events/fold.py` 100% · `cli/main.py` 99% · `tools/file_tools.py` 93% · `loop/turn_loop.py` 91% · `events/reader.py` 85% |
| 类型 | `mypy --strict` 干净，20 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（49 文件）；全仓没有一处 `# noqa` |

要再抬覆盖率地板，补 `events/reader.py` 与 `loop/turn_loop.py` 的判据，不要凑低价值测试。

## 待办与已知缺口

- **收尾门禁未跑**：15.1 变异一轮（记进 `docs/verification/m2-file-tools-and-fences-mutation.md`）与 15.2 Learning Gate。之后才是 `code-review` 两轴 → 合入 `main` → `openspec-archive-change` → `agents-md-slim`。
- 延后的重构：`docs/adr/0002-deferred-refactors.md`。第 1、2、4、5、7 条已处理（M2 落了 `SessionSettings`、`ToolDefinition` 与 `ToolSpec` 分叉、`Literal` 词表、工具名列表进 `session/start`）；剩第 3、6、8 条。ADR 现有三份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`、`0003-m2-fence-simplifications.md`（M2 围栏的简化与代价）。
- 变异测试记录：M1 的在 `docs/verification/m1-mutation.md`；M2 的还没跑。
- 已知缺口：
  - **符号链接 / junction 的键规范化在本机没跑过**：`tests/test_fences.py::test_a_symlink_key_resolves_to_its_target` 因「不允许创建符号链接」skip。大小写折叠与 `..` 折叠那两半有判据，符号链接这一半没有。
  - **Ctrl-C 只在进程内测过**：Windows 上没有 CTRL_C_EVENT 黑盒，`ABORTED` → 退出码 5 的真实信号路径没有黑盒覆盖。
  - **approval 的真实 tty smoke 跑通了，但按键是投递的**：`docs/verification/m2-file-tools-and-fences-approval-smoke.md` 记了两次退出码（`y` → 0、`n` → 3）；按键来自 `WriteConsoleInput` 的 KEY_EVENT，不是人手敲的键盘。ConPTY 路线在本机 `UpdateProcThreadAttribute` 恒返回 87，走不通。
  - **围栏不是安全边界**：没有 OS 级强制（ADR-0003 第 1 条），它防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。
  - **模型看到的工具描述只有名字与描述**：`provider/contract.py::ToolSpec` 两个字段，参数 schema 不在里面（`args_model` 只用于派发侧校验）。mock Provider 不受影响；M4 接真实 Provider 时必须补 JSON schema，否则模型只能猜参数。
- 门禁判据目前**只在 Windows 上跑绿过**，仓库没有 CI。跨平台对齐（Linux/macOS）与 CI 矩阵已裁决并入 M3，不单开里程碑——见 `docs/roadmap.md` 的「跨平台与 CI 排在哪儿」。M2 的 seam ⑥ 判据同样只在 Windows 验证；平台绑定点只有路径规范化（大小写 / junction）、tty 检测、SIGINT 三处，围栏本身不做 OS 级强制所以天生可移植。
