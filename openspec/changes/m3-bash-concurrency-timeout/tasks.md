# Tasks

## 1. 词表与结果形状先行

- [x] 1.1 `tool/cancelled` 进 `events/vocabulary.py` 的具体类型表；翻转 `tests/test_event_vocabulary.py` 里「它在词表外」那条判据（改成在表内、写出去不被记为 `unrecognized_type`）。seam ④
- [x] 1.2 `ToolOutcome` 加 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`；`tests/test_vocabulary_reachability.py` 先加两条可达判据（先红）。seam ②
- [x] 1.3 `tool/cancelled` 的 payload 形状判据：含 `turn_id` 与 `tool_call_id`、不含命令输出或文件内容。seam ④
- [x] 1.4 `tests/test_turn_loop.py` 里「M2 场景不写 tool/cancelled」那条判据拆成两条：取消发生在回合边界时仍不写、取消打断执行中的调用时必写。seam ① —— 前半拆成 `test_a_cancel_at_the_turn_boundary_writes_no_tool_cancelled`，后半是 `test_turn_cancel.py::test_a_cancel_interrupts_the_call_that_is_running`；原来那条同时判 `model/retry` 的半边拆成 `test_a_fenced_fixture_run_writes_no_model_retry`
- [x] 1.5 `error/fence` 的 payload 加 `path` 与 `raw_path`（`detail` 只面向人）：越界写那条判据断言两个字段各有取值，`read-only` 下的 `bash` 那条断言两者都是 `null`。ADR-0002 第 11 条。seam ②④

## 2. 测试 helper 收口（判据①的前置）

- [x] 2.1 `tests/tool_harness.py::dispatch_call` 收 `registry` 与 `approval_gate` 参数（默认值不变），使「只注册 bash 的注册表」与「注入一个会提问的 gate」两条 seam ③ 判据写得出来。seam ②③
- [x] 2.2 四处手搓 `SessionSettings(...)`（`test_fences._context`、`test_approval_gate._run`、`test_vocabulary_reachability._dispatch_with_gate`、`test_tool_registry`）改用 helper。seam ②③
- [x] 2.3 seam ① 的 provider 桩与 run helper 收成一份（ADR-0002 第 16 条）。seam ①
- [x] 2.4 验证：`grep` 数一遍 `SessionSettings(` 在 `tests/` 的出现次数，与收口前对比并记录进提交信息。seam ①②③

## 3. bash 工具契约

- [x] 3.1 `BashArgs` 与 `bash` 的工具定义（`mutates=True`）注册进注册表；`--sandbox read-only` 下被拒的判据（`DENIED_BY_FENCE` + `error/fence` 的 `SANDBOX_DENIES_WRITE`，命令没有副作用）。seam ③
- [x] 3.2 cwd 固定为工作区根：命令写相对路径的文件，`read` 用同一相对路径读到它。seam ③
- [x] 3.3 超时数值：默认 30 s、入参 `timeout_seconds` 上限 600、601 是 `TOOL_ARGS_INVALID` 且没有进程被启动。seam ③
- [x] 3.4 执行段的超时塌成结果：`TOOL_TIMEOUT` 加一条配对的 `tool/cancelled`，进程没有未捕获异常（判据要用异常族里不显眼的成员，不只 `TimeoutError`）。seam ②③
- [x] 3.5 命令退出码非 0 仍是 `OK`，content 含退出码与 stderr 内容。seam ③
- [x] 3.6 输出上限与截断标记：超限的 content 含固定标记、长度有界、`outcome` 不变。seam ③
- [x] 3.7 进程树终止：命令启动的后代进程在超时之后不再运行、不再继续写工作区（两端各自断言，判据不断言手段）。seam ③
- [x] 3.8 立 ADR-0009：`bash` 经平台 shell 执行、进程树终止手段、以及它与 fences 主规格「MUST NOT 依赖 job object」的区分。验证：`docs/adr/0009-*.md` 存在且三条判据（难回退 / 无上下文会困惑 / 真实取舍）都成立。

## 4. 派发段的并发调度

- [x] 4.1 同一回合两个 `read` 并发：第二个在第一个结束之前已经开始。seam ①
- [x] 4.2 同一回合两个 `edit` 串行：第二个只在第一个**执行结束**之后开始（措辞按 D3 返工记录）。seam ①
- [x] 4.3 并发上限 8：10 个 `read` 的回合里同时在跑的不超过 8，10 个都有配对的 `tool/result`。seam ①
- [x] 4.4 每回合前缀取样一次、整批共用：同批的 `read` 不算「已读过」，同批的 `write` 是 `WRITE_WITHOUT_READ`。seam ①
- [x] 4.5 `tool/result` 按声明顺序落盘（构造一个第二个先完成的场景），且同一份日志两次折叠逐字段相等。seam ①④
- [x] 4.6 围栏拒绝时已经开始执行的并发调用不被吞：它仍有配对的 `tool/result`，日志仍以 `error/fence` 与 `session/end` 收尾、退出码 3。seam ②⑥
- [x] 4.7 重放判据：同一批工具调用并发跑与串行跑，每个 `outcome` 相同。seam ①

## 5. 超时与取消落进回合与 CLI

- [x] 5.1 超时后回合继续：`TOOL_TIMEOUT` 之后同批剩余调用照常派发，`turn/end` 的 `stop_reason` 不是 `ABORTED`。seam ①
- [x] 5.2 取消打断正在执行的调用：`tool/cancelled` + `TOOL_CANCELLED` + `error/abort` + `turn/end(ABORTED)` + 退出码 5（seam ① 注入 cancel）。seam ①
- [x] 5.3 取消之后没有「有 `tool/call` 没 `tool/result`」的记录。seam ①
- [x] 5.4 Linux 上 SIGINT 的 CLI 黑盒：真实子进程 + SIGINT → 退出码 5 与上述日志形状。seam ⑥
- [x] 5.5 模型请求超时数值 120 s：seam ⑤ 断言 provider 的超时配置是 120 s，seam ⑥ 断言 `minihns run` 没有改变它的参数。seam ⑤⑥
- [x] 5.6 `approval/request` 改成提问之前落盘：两条判据——非 `ABORTED` 收尾的 run 里每条 `approval/request` 都有配对 `approval/response`；提问被取消打断时允许半对且日志以 `error/abort` 收尾。ADR-0002 第 9 条。seam ①④

## 6. 平台适配层与两端同一套判据

- [x] 6.1 路径大小写折叠的两端判据：Windows 上折叠、Linux 上区分（同一测试两端各有断言，复制 `tests/test_fences.py:30-40` 的形状）。seam ②⑥ —— 键本身那条早就在；补的是**后果**：换写法读过的文件能不能满足写前必读，两端各断言一支
- [x] 6.2 符号链接判据在 Linux 真跑；Windows 侧换成不要求特权的 junction 形式跑。seam ② —— junction 判据本机真跑，符号链接那条在这台机器上 skip、由 CI 的 Linux 跑
- [x] 6.3 tty 检测的两端判据：非 tty 且未 `--yes` 时 `UNAVAILABLE` 在两端都成立。seam ②⑥ —— 已有的 DEVNULL 黑盒 + 桩门两条照跑；补一条「管道里喂进来的 `y` 不是人」，把 stdin 换成管道仍然 `UNAVAILABLE`
- [x] 6.4 bash 的两端执行形状（`cmd.exe /c` 与 `/bin/sh -c`）落地，判据只用平台中立命令。seam ③⑥ —— 判据只用 `python <文件>` 与 `&&`：一条跑通、一条短路；再加 CLI 黑盒跑通 `bash` → `read`

## 7. CI 矩阵

- [x] 7.1 写 `.github/workflows/` 的 CI：`windows-latest` + `ubuntu-latest` 矩阵，跑 pytest、`coverage combine`、`coverage report --fail-under=95`、`mypy --strict src`、`ruff check`、`ruff format --diff`。验证：本地逐条跑过同样的命令序列且退出码 0。—— `.github/workflows/gates.yml`；本地那 8 条命令逐条退出码 0（`uv sync --frozen` 起）
- [ ] 7.2 推送分支与 `main`（`origin/main` 落后 52 个提交，推送与首次启用 Actions 是人要做的动作），确认两个 job 都跑绿。
- [ ] 7.3 覆盖率在两端分别报告、不合并；把两端的 `TOTAL` 记进 `docs/CURRENT.md` 的门禁实测表。
- [x] 7.4 验证 CI 不持 API key：workflow 文件里没有 secret 引用，openai 的 seam ⑥ 判据只连本地假端点。—— `gates.yml` 里 `secrets` / `env:` / `API_KEY` 零命中；`tests/test_cli_provider.py` 的 openai 黑盒连的是测试自己起的 `127.0.0.1` 假端点，另有一条判据钉住 `trust_env=False`（代理环境变量不生效）

## 8. 人手验收（AGENTS.md 固定判据）

- [ ] 8.1 拿真实工作区办一件真事：一次 run 里让模型用 `bash` 跑一条真实检查命令、再用 `read` 读它的输出；观察并发派发与落盘顺序。记进 `docs/verification/m3-bash-concurrency-timeout-manual.md`。
- [ ] 8.2 同一份记录里观察两件打断：一条故意超时的命令（跑过 30 s）看 `tool/cancelled` 与回合继续；一次 Ctrl-C 看退出码 5 与 `error/abort`。

## 9. 收尾门禁

- [x] 9.1 变异测试一轮，记进 `docs/verification/m3-bash-concurrency-timeout-mutation.md`。重点变异面：执行段的异常族、并发上限数值、落盘顺序、超时数值、进程树终止。判据：每个变异都被至少一条测试杀死；存活的补一条能杀死它的判据。—— 12 条：10 杀、2 存活已补判据（bash 默认 30 秒没人钉、输出上限的边界没人判）、1 条判定 dud（`started` 链在同步落盘下不可观察）
- [x] 9.2 Learning Gate：扫本轮证据（红过的测试、存活的变异、返工过的规格、踩过的工具坑），可复用教训进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`。—— 收 L-027 至 L-030 四条，关闭 L-018、补 L-019；**AGENTS.md 不晋升**（三条最值钱的信号分别已被 AGENTS.md 变异段、L-005 / L-017 同族、L-004 覆盖）
- [x] 9.3 改判 `docs/adr/0002-deferred-refactors.md` 的第 1 条剩一半、第 12、16 条为「已处理」，并把 `docs/CURRENT.md` 的门禁实测与缺口更新到 M3 实况。—— 逐条改判：已处理 1（含剩的一半，helper 收 `registry`/`gate` + run 形状收成一份）、6、9、10、11；改判为长期形态 8、12、16（桩留在各文件的理由成立）；未处理推到 M5 的 14、15；未触发的 17。`docs/CURRENT.md` 已刷新到 Windows 侧实况；两端 `TOTAL` 那一半要等 CI 首绿（7.3）。

## 10. `code-review` 修复轮（两轴审查之后）

- [x] 10.1 `_race_with_cancel` 的兜底塌词只对 `asyncio.CancelledError` 生效；从执行段逃出来的其它异常不得改名成 `TOOL_CANCELLED`，要落 `error/internal` 并作为内核失败收尾。seam ① —— 判据 `test_an_escaped_exception_is_not_renamed_to_a_cancellation`；逃出来的异常由 `one()` 接住、写 `error/internal`（含 `tool_call_id`）、置 `stop`，已跑完的调用照常落结果，run 以词表外的 `INTERNAL_ERROR` 收尾（退出码 1）
- [x] 10.2 `bash` 在两个档位下各跑一次：结果与日志形状没有可观察差别，且日志里没有 `error/fence`。seam ③ —— 判据 `test_the_two_sandbox_levels_treat_the_same_command_the_same_way`：同一条命令在 `workspace-write` 与 `danger-full-access` 下各跑一整段 session，两次的 `tool/result` 内容与 `outcome` 逐字段相同、`stop_reason` 相同，两份日志里 `error/fence` 零条
- [x] 10.3 「围栏拒绝时已在跑的并发调用不被吞」换成真实可达形状：一个还在跑的只读调用 + 一个被拒的调用。seam ① —— 结论比原判据更硬：落地规则（只读并发、会改动串行）让「拒绝时另一个调用还在跑」**在同一批里不可达**，被拒的写调用必须等前一个跑完。判据改名 `test_a_fence_denial_does_not_swallow_the_calls_dispatched_before_it`，钉配对与落盘顺序（`tool/result` 在 `error/fence` 之前）+ 档位轴先拒时 `path` 是 `null`、`raw_path` 仍是原写法；delta scenario 与 design.md 的 D1 落地修正同步改写，「还在跑就被打断」那一半由取消路径判
- [x] 10.4 event-log 的「成组出现」改成实现实际保证的东西（每个调用的四类事件按此相对顺序；不同调用的组可交错，`tool/result` 按声明顺序），并补一条判据钉住这个相对顺序。seam ④ —— scenario 改名并拆成两条；判据 `test_an_approved_call_keeps_its_relative_order_when_the_batch_interleaves`。R1（连续）/ R2（结果按声明顺序）/ R3（`tool/call` 派发时落盘）不能同时成立，证明与主流 harness 的对照记进 `design.md`
- [x] 10.5 提问可被取消打断：approval 门改成 awaitable，提问期间取消置位则这一对允许半对、这一条塌成 `TOOL_CANCELLED`。seam ① ② —— `ApprovalGate.request` 与 `StdinApprovalGate.request` 改成 awaitable，真实门的 `readline()` 放进 daemon 线程等（不是 `asyncio.to_thread`，理由记进 design.md 的 D6 重新裁决）；判据两条：`test_a_cancel_arrives_while_the_human_is_being_asked`（注入的门，半对 + `TOOL_CANCELLED` + `error/abort` + `ABORTED`）与 `test_a_cancel_interrupts_a_question_the_human_has_not_answered`（真实门，`readline()` 还挂着时 session 已经以 `ABORTED` 收尾）
- [ ] 10.6 补一条 Windows 也跑得动的 `bash` 超时 CLI 黑盒（seam ⑥），并把 `docs/CURRENT.md` 里「Windows 侧超时黑盒都有」那句改到与实况一致
- [ ] 10.7 「数值不暴露成命令行开关」补参数表判据：`bash` 的 30 / 600、并发上限 8、模型超时 120 都没有对应开关。seam ⑥
- [ ] 10.8 记账：Standards 轴的 9 条判断项进 `docs/adr/0002-deferred-refactors.md`；「结果 durability 缓冲到批次结束」这个取舍（硬杀会吞已完成的结果）记进 `design.md` 与 `docs/CURRENT.md` 的缺口

## Workflow follow-up

- `/openspec-apply-change` 按上面的顺序 red → green，一个循环一次提交，提交信息带 task 编号，一个提交最多覆盖同一 seam 上相邻 3 个 task
- `code-review` 两轴（Standards / Spec）
- 先 `openspec-sync-specs` 再 `/openspec-archive-change`
- 归档后跑一次 `agents-md-slim`
