# Design

## Context

动机见 `proposal.md` – Why。这里是分流跑出来的**实测现状**，它们决定了可走的路：

- `src/` 里没有 `asyncio.gather` / `wait_for` / `create_task`：并发与超时都是新机械，不是改造旧的。
- `dispatch_tool_call` 是单个 async 函数、三段塌缩在一个函数体里（ADR-0003 第 3 条：插新段改的是函数体，`DispatchOutcome` 会跟着长）。执行段现在只 `except OSError`。
- `ApprovalGate.request` 是**同步阻塞** `readline()`。串行派发时无害；并发派发一出现就是事件循环里的阻塞点。
- 每个调用派发前 `read_events(log.path)` 重读全日志前缀（`turn_loop.py:215`）。串行时只是浪费，并发时它变成语义问题。
- 覆盖率实测 96%（950 stmts / 37 miss），地板 95%；全仓只有一处平台守卫（`tests/test_fences.py:30-40`）。
- 没有 `.github/`，`origin/main` 落后 52 个提交。
- 已裁决、不再 grill：ADR-0007（Ctrl-C 取消整个 session）、ADR-0008（bash 只受档位轴）、模型超时 120 s。

## Goals / Non-Goals

**Goals:**

- 派发段成为「可被打断的段」，且打断的两种形状（超时 / 取消）各有确定的日志形状。
- 并发**不改变任何单条判定的结论**：同一批调用并发跑与串行跑，每个 `outcome` 相同。
- 同一套判据在 Windows 与 Linux 给出同一结论，门禁由 CI 跑。

**Non-Goals:**

- 不做窗口预算与 `CONTEXT_WINDOW_EXCEEDED`（M5）、不做 OS 级沙箱、不做流式、不做 REPL 的「打断但不退出」（M6）。
- 不动 provider 的 13–17 号欠账（`generate` 两段同形、三条 `str | None`、「是 openai」四处判断、`model/request` 的 `attempt`）——M3 的并发是**工具**并发，不是请求并发。
- 不引入并发上限或超时的命令行开关（编码四规第 2 条）。

## Decisions

**D1 并发放在回合循环的派发段，不放进 `dispatch_tool_call`。** `dispatch_tool_call` 保持「一次派发一个调用」的签名，`turn_loop` 用信号量 + `gather` 决定谁并发。替代：把并发塞进 dispatch——否，seam ② 的判据本身就是「一次派发的三段判定」，并发是回合级调度事实，混进去会让 seam ② 的每条判据都要带并发上下文。

**D2 只读与会改动的划分只用已有的 `ToolDefinition.mutates`。** 不新造 `read_only` 标记或第二套分类。替代：按工具名硬编码白名单——否，`mutates` 已经是围栏的判定依据，两套分类迟早分叉。

**D3 `tool/result` 缓冲后按声明顺序落盘。** 并发完成顺序不定，落盘顺序必须是 `tool_calls` 的声明顺序。替代：按完成顺序落盘——否，折叠与 `replay` 的判据依赖日志顺序（context-projection 的「折叠是确定性纯函数」），而两端的完成顺序天然不同，判据「两端同一套判据全绿」会直接为假。

**D4 每回合取样一次前缀，整批共用。** 替代：保持每调用重读——否，并发时先完成的结果会进入后派发者的前缀，「同一份日志前缀得到同一判定」这条 Scenario 字面不成立。副带好处：消掉 O(n²) 重读。

**D5 超时塌成结果词，异常不逃逸出执行段。** `TimeoutError` → `TOOL_TIMEOUT`，`CancelledError` → `TOOL_CANCELLED`，两条都在 `dispatch_tool_call` 的执行段内塌（任务 1.2 已落）。超时的**数值**由工具自己执行：`bash` 用 `asyncio.wait_for` 包住自己的执行段，因为只有它知道入参里的 `timeout_seconds`。替代：给每个工具传 deadline 参数、或在 `ToolDefinition` 上加超时字段——否，那是把超时散进六个工具契约里，且 M3 只有 `bash` 需要它。事实更正（实现时核实）：`TimeoutError` **是** `OSError` 的子类，所以 `except TimeoutError` MUST 排在 `except OSError` 之前，否则超时读成 `TOOL_IO_FAILED`；`CancelledError` 是 `BaseException`。按 AGENTS.md 的变异纪律，执行段的判据要用族里不显眼的成员，不能只用 `TimeoutError`。

**D6 approval 门保持同步，靠「会改动的工具串行」保证它不卡事件循环。** 决策 14 的写串行从性能优化升格为正确性前提，因此写进规格（turn-loop 的并发那条）。替代：把 `ApprovalGate` 改成 async——否，不加没被要求过的复杂度，且提问本来就该是唯一串行段。

**D7 `bash` 经平台 shell 执行：Windows `cmd.exe /c`、POSIX `/bin/sh -c`，cwd 固定工作区根。** 替代：不经 shell 的 `create_subprocess_exec` + `shlex.split`——否，模型写的命令带管道与重定向，不经 shell 就不可用；而 `shlex` 的 POSIX 语义在 Windows 上不对。代价：两端 shell 语义不同，因此**每条 bash 判据只用平台中立命令**（`python -c "..."` 一类），ADR 里写明「模型在 Windows 上写 POSIX 语法会得到命令失败，那是内容不是 harness 失败」。

**D8 超时之后终止进程树：POSIX 用 `start_new_session=True` + 终止整个进程组，Windows 用 `taskkill /T /PID`。** 判据断言「后代进程不再运行」，不断言手段。与 fences 主规格「MUST NOT 依赖 job object」的关系要写清：那条禁止的是**用 OS 机制实施围栏**，不是终止自己启动的进程——这个区分要立 ADR（下一号 0009），因为字面读起来像冲突。

**D9 覆盖率地板保持 95%，两端分别报告、不合并。** 平台分支在任一 runner 上都覆盖不到另一半，靠两个手段收：把平台差异收进「同一测试在两个平台各有断言」的形状（复制 `tests/test_fences.py:30-40` 的现有形状），以及把平台实现收在少数几个函数里而不是散在分支里。替代：降地板到 92%——否，那是用降低门禁换取平台差异；替代：抽一个平台抽象层——否，M3 只有两个实现，抽象是空的。

**D10 测试 helper 收口排在判据之前。** `tests/tool_harness.py` 现在硬编码 `file_tool_definitions()` 与 `_ApprovingGate()`，写不出「只注册 bash 的注册表」或「注入一个会提问的 gate」的 seam ③ 判据。这是 ADR-0002 第 1 条剩的一半与第 12、16 条的兑现，不是可选项。

**D11 CI 是 GitHub Actions 矩阵 `windows-latest` + `ubuntu-latest`，不持 API key。** 跑 pytest + coverage + `mypy --strict` + ruff；真实 Provider 的 smoke 不进 CI（ADR-0005 第 3 条），走人手验收。seam ⑥ 的子进程 partial 记账沿用 `pyproject.toml` 里已有的 rcfile 与 `COVERAGE_FILE` 形状。

**D12 `approval/request` 在提问之前落盘，半对只在 `ABORTED` 收尾的 session 里成立。** 替代：加一个 `UNANSWERED` 取值——否，词表已经有 `UNAVAILABLE`，再加一个会让「没问到」与「问到没答」在折叠里要分别处理；替代：保持问完才写——否，M3 之后 Ctrl-C 可以打断正在等人回答的提问，那时日志里连「问过」这条事实都没有。代价：日志里第一次可能出现半对，折叠与 `replay` 必须容忍它。

**D13 `error/fence` 的 payload 加 `path` 与 `raw_path`，`detail` 只面向人。** `path` 是围栏判定实际使用的解析后键，`raw_path` 是调用里写的原始写法，没有目标路径的调用（`bash`）两者都是 `null`。替代：只加一个 `target` 对象——否，两个平台的解析结果与模型写的写法本来就不同，合成一个字段就又回到自由文本。这条同时统一 M2 留下的形态不一致（`OUTSIDE_WORKSPACE` 放解析后键、`SANDBOX_DENIES_WRITE` 放 `raw_path`）。

## Seam 边界与测试策略

- **seam ①（回合循环）**：并发调度、前缀快照、落盘顺序、超时后回合继续、取消打断的落盘形状。桩沿用现有的 `_scripted_provider` / `_run_with_provider`，D10 之后只留一份。
- **seam ②（注册表与管线）**：`TOOL_TIMEOUT` / `TOOL_CANCELLED` 的可达判据、执行段异常族不逃逸、围栏拒绝时已在跑的并发调用不被吞。
- **seam ③（工具契约）**：bash 的 cwd、超时数值边界（30 默认 / 601 拒绝）、退出码非 0 是 `OK`、输出截断标记、进程树终止。判据只用平台中立命令。
- **seam ④（日志与折叠）**：`tool/cancelled` 进词表后折叠仍确定性；同一批并发派发两次折叠逐字段相等。
- **seam ⑤（provider）**：只改超时数值常量与它的断言，不加新行为。
- **seam ⑥（CLI 黑盒）**：SIGINT 在 Linux 上的黑盒判据；Windows 侧的 Ctrl-C 用 seam ① 的注入 cancel 判据 + 人手验收观察（`CTRL_C_EVENT` 的黑盒列为 Open Question，不挡判据）。

## Risks / Trade-offs

- [并发让「同一前缀同一判定」变脆弱] → D4 快照 + D3 声明顺序落盘 + 判据「重放同一批得到同一判定」。
- [`bash` 经 shell ⇒ 两端语义不同] → 判据只用平台中立命令；ADR 记代价；命令失败是内容不是 harness 失败。
- [Windows 没有 POSIX 进程组，孙进程可能留在跑] → `taskkill /T`；判据断言可观察后果（后代进程不再运行、不再继续写文件），不断言手段。
- [覆盖率地板余量只有 1 个点] → D9；CI 上两端分别报告，先补判据再动地板。
- [Ctrl-C 的 Windows 黑盒难做] → 上面 seam ⑥ 那行的分工；缺口记进 `docs/CURRENT.md` 而不是假装补上了。
- [bash 输出无界会打爆日志] → 上限常量 + 截断标记；不变量 D 的预算仍归 M5，M3 不顺手做。
- [判据「两端全绿」依赖人先推送与选 runner] → tasks 组 0 显式列出人做的动作，不把它算成代码任务。

## Migration Plan

没有数据迁移。词表是**向后兼容**的追加：既有日志不含 `tool/cancelled`，`replay` 与折叠判据不受影响；`TOOL_TIMEOUT` / `TOOL_CANCELLED` 只出现在新 run。唯一的 BREAKING 是 Ctrl-C 的语义（ADR-0007），没有需要迁移的既有产物。回滚 = 不合并 `change/m3-bash-concurrency-timeout`。

## Open Questions

两条都在 2026-10-19 由人裁决，不再是开放项：

- **bash 输出上限：单一上限 16384 字节，stdout 与 stderr 合起来算**，截断标记固定一行。替代（分别限额 16 KiB / 8 KiB）否：多一个数值、多一套判据，而 M3 的判据只断言「有上限、有标记」。
- **Windows 的 Ctrl-C 黑盒不在 M3 做**：seam ① 用注入 cancel 事件判「取消打断执行中的调用」，seam ⑥ 在 Linux 上跑真实 SIGINT 黑盒、Windows 上跑超时黑盒；Windows 侧 `CTRL_C_EVENT` 的缺口记进 `docs/verification/<change-id>-manual.md` 与 `docs/CURRENT.md`，不假装补上。
