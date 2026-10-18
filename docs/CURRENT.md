# 当前状态

每里程碑收尾更新一次。接手时以 `git status --short` 与 `git log --oneline -3` 为准，本文件只是快照。

更新：2026-10-18（`main` = archive 提交，M2 已合入并归档）

## 进度

- **M1 完成并已归档**：change `m1-event-log-and-turn-loop` 已合入 `main`（merge commit `141e28c`），归档在 `openspec/changes/archive/2026-10-16-m1-event-log-and-turn-loop/`，tag `m1`。
- **M2 完成并已归档**：change `m2-file-tools-and-fences` 已合入 `main`（merge commit `d89a7c2`），归档在 `openspec/changes/archive/2026-10-18-m2-file-tools-and-fences/`，tag `m2`。六份 delta 已同步进主规格：新增 29 条 Requirement、修改 9 条、移除 2 条；主规格现有 7 个能力（`openspec list --specs`：cli 6 / context-projection 8 / event-log 9 / fences 12 / file-tools 11 / provider 5 / turn-loop 9），`openspec validate --specs` 7 过 0 失败。
- 收尾门禁全跑完：变异 20 条 + 审查后抽查 4 条、Learning Gate 收 L-016 至 L-020、`code-review` 两轴修掉两条最重的发现（tasks 第 16 节）、`agents-md-slim` 已跑（AGENTS.md 110 → 100 行）。
- M2 落地的东西：五个文件工具 `read` / `write` / `edit`（CAS）/ `glob` / `grep`；三段派发管线（校验 → 围栏 → 执行）；围栏判定（档位 → 工作区边界 → 要不要问人）；`approval/request` 与 `approval/response` 事件；`error/fence` 的四种 code；`FENCE_DENIED` → 退出码 3；`SessionSettings` 同时是 `run_session` 的入参与 `session/start.payload` 的来源。

## 门禁实测

| 门禁 | 实测 |
|---|---|
| 测试 | 144 passed / 1 skipped（skip 的是符号链接判据：本机不允许创建符号链接）；全量带覆盖率记账约 25 秒 |
| 覆盖率 | `coverage erase` → `coverage run -m pytest` → `coverage combine`（合并 29 份 partial）后 TOTAL **97%**（802 语句 / 24 未覆盖）；地板 `fail_under = 95` |
| 覆盖率分布 | `tools/fences.py` 100% · `tools/dispatch.py` 100% · `events/fold.py` 100% · `cli/main.py` 99% · `tools/registry.py` 97% · `tools/file_tools.py` 96% · `loop/turn_loop.py` 91% · `events/reader.py` 85% |
| 类型 | `mypy --strict` 干净，20 个源文件 |
| 风格 | `ruff check` 干净；`ruff format --diff` 空（49 文件）；全仓没有一处 `# noqa` |

要再抬覆盖率地板，补 `events/reader.py` 与 `loop/turn_loop.py` 的判据，不要凑低价值测试。

## 待办与已知缺口

- **下一个里程碑是 M4（换序）**：执行顺序定为 M1 → M2 → **M4** → M3 → M5 → M6 → M7，编号不变、顺序换了；理由与代价见 `docs/adr/0005-m4-before-m3.md`。M4 开工前的阻塞项：`provider/contract.py::ToolSpec` 只有 `name` 与 `description`，参数 schema 不在里面——不补上，真实模型只能猜参数。CI 不持 API key，真实 Provider 的 smoke 走人手验收（`docs/roadmap.md`）。
- **`code-review` 两轴已跑**（fixed point `main` = `134ae69`，22 提交）。两条最重的发现已在 tasks 第 16 节修掉：执行段的文件 I/O 失败塌成 `TOOL_IO_FAILED`（此前 `FileExistsError` 逃出管线，违反不变量 B）、`glob` / `grep` 搜索根是文件时改报 `NOT_A_DIRECTORY`（此前是标签与语义相反的 `IS_A_DIRECTORY`）。词表因此 14 值。已合入 `main`（merge commit `d89a7c2`）并归档在 `openspec/changes/archive/2026-10-18-m2-file-tools-and-fences/`；`agents-md-slim` 也已跑（AGENTS.md 110 → 100 行）。
- 延后的重构与记账：`docs/adr/0002-deferred-refactors.md`。第 1、2、4、5、7 条已处理（M2 落了 `SessionSettings`、`ToolDefinition` 与 `ToolSpec` 分叉、`Literal` 词表、工具名列表进 `session/start`）；第 1 条只剩「seam ②③ 里四处手搓 `SessionSettings`」这一半，连同第 3、6、8 条与 M2 审查新增的第 9 至 12 条（`approval/*` 晚落盘、取消只在回合边界被看到、`error/fence` 的路径只在自由文本 `detail` 里、seam ②③ 的桩各留一份）留给 M3。ADR 现有五份：`0001-m1-simplifications.md`、`0002-deferred-refactors.md`、`0003-m2-fence-simplifications.md`（M2 围栏的简化与代价）、`0004-cas-compares-the-read-window.md`（CAS 比的是读到的窗口）、`0005-m4-before-m3.md`（M4 换到 M3 之前：理由、代价、被否掉的三个选项）。
- 变异测试记录：M1 的在 `docs/verification/m1-mutation.md`（两轮共 18 条：16 条被杀，存活的 G 与 P 各换回一条判据）；M2 的在 `docs/verification/m2-file-tools-and-fences-mutation.md`（收尾轮 20 条 A 至 S，含 J 的跟进 J′：15 条被既有测试杀死，G / I / J′ 是 dud mutant，M 与 N 存活并已各补一条判据；审查修复后又跑 4 条抽查 T / U / V / W，全被杀死。同文档注 6 记了一条事实：`ToolResult` 是 dataclass，词表外的值在运行期不会被挡，靠 `mypy --strict` 与可达性判据守）。
- 手测清单：`docs/verification/m1-m2-manual-smoke.md`。11 个 CLI 黑盒场景一键跑完（实测 `mismatches=0`：退出码 0/1/2/3 各有场景）、`replay` 两条、外加只有真终端能做的 approval 按键与 Ctrl-C 两条。M4 与 M3 的手测沿用它的形状（场景表 + 一键脚本 + `mismatches=0`）；M4 的那条还要含真实 Provider 的 smoke，它不进 CI。
- 已知缺口：
  - **符号链接 / junction 的键规范化在本机没跑过**：`tests/test_fences.py::test_a_symlink_key_resolves_to_its_target` 因「不允许创建符号链接」skip。大小写折叠与 `..` 折叠那两半有判据，符号链接这一半没有。
  - **Ctrl-C 只在进程内测过**：Windows 上没有 CTRL_C_EVENT 黑盒，`ABORTED` → 退出码 5 的真实信号路径没有黑盒覆盖。
  - **approval 的真实 tty smoke 跑通了，但按键是投递的**：`docs/verification/m2-file-tools-and-fences-approval-smoke.md` 记了两次退出码（`y` → 0、`n` → 3）；按键来自 `WriteConsoleInput` 的 KEY_EVENT，不是人手敲的键盘。ConPTY 路线在本机 `UpdateProcThreadAttribute` 恒返回 87，走不通。
  - **围栏不是安全边界**：没有 OS 级强制（ADR-0003 第 1 条），它防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。
  - **模型看到的工具描述只有名字与描述**：`provider/contract.py::ToolSpec` 两个字段，参数 schema 不在里面（`args_model` 只用于派发侧校验）。mock Provider 不受影响；M4 接真实 Provider 时必须补 JSON schema，否则模型只能猜参数。
  - **CAS 只比「读到的窗口」**：窗口之外的改动不触发 `STALE_EDIT`——实测 `read` 用 `offset=1 limit=1` 读过第 1 行后把第 3 行改掉，`edit` 仍 `OK` 并改写文件。这一半既没有判据、也没有测试钉住现状行为；取舍与收紧办法记在 `docs/adr/0004-cas-compares-the-read-window.md`。
  - **`approval/*` 这一对在问完人之后才落盘**：人已回答而执行段抛异常或进程被杀时，日志里没有这一对事件。ADR-0002 第 9 条。
  - **取消信号只在回合边界被看到**：同一批 `tool_calls` 里第一个调用置位 cancel 后，第二个 `write` 仍被派发（`turn_loop` 只在 267 / 279 / 293 三处查 `cancel.is_set()`）。ADR-0002 第 10 条。
  - **`error/fence` 里被拒的路径只在自由文本 `detail` 里**：判据只能断言 `code`；形态还不统一——`OUTSIDE_WORKSPACE` 放解析后的键，`SANDBOX_DENIES_WRITE` 放未解析的 `raw_path`。ADR-0002 第 11 条。
- 门禁判据目前**只在 Windows 上跑绿过**，仓库没有 CI。跨平台对齐（Linux/macOS）与 CI 矩阵已裁决并入 M3，不单开里程碑——见 `docs/roadmap.md` 的「跨平台与 CI 排在哪儿」；换序之后（ADR-0005）它整体后移一个里程碑，且 CI 不持 API key：门禁只跑 mock 判据，真实 Provider 的 smoke 归人手验收。M2 的 seam ⑥ 判据同样只在 Windows 验证；平台绑定点只有路径规范化（大小写 / junction）、tty 检测、SIGINT 三处，围栏本身不做 OS 级强制所以天生可移植。
