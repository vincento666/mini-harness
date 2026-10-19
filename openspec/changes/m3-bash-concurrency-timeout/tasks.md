# Tasks

## 1. 词表与结果形状先行

- [x] 1.1 `tool/cancelled` 进 `events/vocabulary.py` 的具体类型表；翻转 `tests/test_event_vocabulary.py` 里「它在词表外」那条判据（改成在表内、写出去不被记为 `unrecognized_type`）。seam ④
- [x] 1.2 `ToolOutcome` 加 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`；`tests/test_vocabulary_reachability.py` 先加两条可达判据（先红）。seam ②
- [ ] 1.3 `tool/cancelled` 的 payload 形状判据：含 `turn_id` 与 `tool_call_id`、不含命令输出或文件内容。seam ④
- [ ] 1.4 `tests/test_turn_loop.py` 里「M2 场景不写 tool/cancelled」那条判据拆成两条：取消发生在回合边界时仍不写、取消打断执行中的调用时必写。seam ①
- [x] 1.5 `error/fence` 的 payload 加 `path` 与 `raw_path`（`detail` 只面向人）：越界写那条判据断言两个字段各有取值，`read-only` 下的 `bash` 那条断言两者都是 `null`。ADR-0002 第 11 条。seam ②④

## 2. 测试 helper 收口（判据①的前置）

- [x] 2.1 `tests/tool_harness.py::dispatch_call` 收 `registry` 与 `approval_gate` 参数（默认值不变），使「只注册 bash 的注册表」与「注入一个会提问的 gate」两条 seam ③ 判据写得出来。seam ②③
- [x] 2.2 四处手搓 `SessionSettings(...)`（`test_fences._context`、`test_approval_gate._run`、`test_vocabulary_reachability._dispatch_with_gate`、`test_tool_registry`）改用 helper。seam ②③
- [ ] 2.3 seam ① 的 provider 桩与 run helper 收成一份（ADR-0002 第 16 条）。seam ①
- [x] 2.4 验证：`grep` 数一遍 `SessionSettings(` 在 `tests/` 的出现次数，与收口前对比并记录进提交信息。seam ①②③

## 3. bash 工具契约

- [x] 3.1 `BashArgs` 与 `bash` 的工具定义（`mutates=True`）注册进注册表；`--sandbox read-only` 下被拒的判据（`DENIED_BY_FENCE` + `error/fence` 的 `SANDBOX_DENIES_WRITE`，命令没有副作用）。seam ③
- [x] 3.2 cwd 固定为工作区根：命令写相对路径的文件，`read` 用同一相对路径读到它。seam ③
- [x] 3.3 超时数值：默认 30 s、入参 `timeout_seconds` 上限 600、601 是 `TOOL_ARGS_INVALID` 且没有进程被启动。seam ③
- [ ] 3.4 执行段的超时塌成结果：`TOOL_TIMEOUT` 加一条配对的 `tool/cancelled`，进程没有未捕获异常（判据要用异常族里不显眼的成员，不只 `TimeoutError`）。seam ②③
- [ ] 3.5 命令退出码非 0 仍是 `OK`，content 含退出码与 stderr 内容。seam ③
- [ ] 3.6 输出上限与截断标记：超限的 content 含固定标记、长度有界、`outcome` 不变。seam ③
- [ ] 3.7 进程树终止：命令启动的后代进程在超时之后不再运行、不再继续写工作区（两端各自断言，判据不断言手段）。seam ③
- [ ] 3.8 立 ADR-0009：`bash` 经平台 shell 执行、进程树终止手段、以及它与 fences 主规格「MUST NOT 依赖 job object」的区分。验证：`docs/adr/0009-*.md` 存在且三条判据（难回退 / 无上下文会困惑 / 真实取舍）都成立。

## 4. 派发段的并发调度

- [ ] 4.1 同一回合两个 `read` 并发：第二个在第一个结束之前已经开始。seam ①
- [ ] 4.2 同一回合两个 `edit` 串行：第二个只在第一个写出 `tool/result` 之后开始。seam ①
- [ ] 4.3 并发上限 8：10 个 `read` 的回合里同时在跑的不超过 8，10 个都有配对的 `tool/result`。seam ①
- [ ] 4.4 每回合前缀取样一次、整批共用：同批的 `read` 不算「已读过」，同批的 `write` 是 `WRITE_WITHOUT_READ`。seam ①
- [ ] 4.5 `tool/result` 按声明顺序落盘（构造一个第二个先完成的场景），且同一份日志两次折叠逐字段相等。seam ①④
- [ ] 4.6 围栏拒绝时已经开始执行的并发调用不被吞：它仍有配对的 `tool/result`，日志仍以 `error/fence` 与 `session/end` 收尾、退出码 3。seam ②
- [ ] 4.7 重放判据：同一批工具调用并发跑与串行跑，每个 `outcome` 相同。seam ①

## 5. 超时与取消落进回合与 CLI

- [ ] 5.1 超时后回合继续：`TOOL_TIMEOUT` 之后同批剩余调用照常派发，`turn/end` 的 `stop_reason` 不是 `ABORTED`。seam ①
- [ ] 5.2 取消打断正在执行的调用：`tool/cancelled` + `TOOL_CANCELLED` + `error/abort` + `turn/end(ABORTED)` + 退出码 5（seam ① 注入 cancel）。seam ①
- [ ] 5.3 取消之后没有「有 `tool/call` 没 `tool/result`」的记录。seam ①
- [ ] 5.4 Linux 上 SIGINT 的 CLI 黑盒：真实子进程 + SIGINT → 退出码 5 与上述日志形状。seam ⑥
- [ ] 5.5 模型请求超时数值 120 s：seam ⑤ 断言 provider 的超时配置是 120 s，seam ⑥ 断言 `minihns run` 没有改变它的参数。seam ⑤⑥
- [ ] 5.6 `approval/request` 改成提问之前落盘：两条判据——非 `ABORTED` 收尾的 run 里每条 `approval/request` 都有配对 `approval/response`；提问被取消打断时允许半对且日志以 `error/abort` 收尾。ADR-0002 第 9 条。seam ①④

## 6. 平台适配层与两端同一套判据

- [ ] 6.1 路径大小写折叠的两端判据：Windows 上折叠、Linux 上区分（同一测试两端各有断言，复制 `tests/test_fences.py:30-40` 的形状）。seam ②⑥
- [ ] 6.2 符号链接判据在 Linux 真跑；Windows 侧换成不要求特权的 junction 形式跑。seam ②
- [ ] 6.3 tty 检测的两端判据：非 tty 且未 `--yes` 时 `UNAVAILABLE` 在两端都成立。seam ②⑥
- [ ] 6.4 bash 的两端执行形状（`cmd.exe /c` 与 `/bin/sh -c`）落地，判据只用平台中立命令。seam ③⑥

## 7. CI 矩阵

- [ ] 7.1 写 `.github/workflows/` 的 CI：`windows-latest` + `ubuntu-latest` 矩阵，跑 pytest、`coverage combine`、`coverage report --fail-under=95`、`mypy --strict src`、`ruff check`、`ruff format --diff`。验证：本地逐条跑过同样的命令序列且退出码 0。
- [ ] 7.2 推送分支与 `main`（`origin/main` 落后 52 个提交，推送与首次启用 Actions 是人要做的动作），确认两个 job 都跑绿。
- [ ] 7.3 覆盖率在两端分别报告、不合并；把两端的 `TOTAL` 记进 `docs/CURRENT.md` 的门禁实测表。
- [ ] 7.4 验证 CI 不持 API key：workflow 文件里没有 secret 引用，openai 的 seam ⑥ 判据只连本地假端点。

## 8. 人手验收（AGENTS.md 固定判据）

- [ ] 8.1 拿真实工作区办一件真事：一次 run 里让模型用 `bash` 跑一条真实检查命令、再用 `read` 读它的输出；观察并发派发与落盘顺序。记进 `docs/verification/m3-bash-concurrency-timeout-manual.md`。
- [ ] 8.2 同一份记录里观察两件打断：一条故意超时的命令（跑过 30 s）看 `tool/cancelled` 与回合继续；一次 Ctrl-C 看退出码 5 与 `error/abort`。

## 9. 收尾门禁

- [ ] 9.1 变异测试一轮，记进 `docs/verification/m3-bash-concurrency-timeout-mutation.md`。重点变异面：执行段的异常族、并发上限数值、落盘顺序、超时数值、进程树终止。判据：每个变异都被至少一条测试杀死；存活的补一条能杀死它的判据。
- [ ] 9.2 Learning Gate：扫本轮证据（红过的测试、存活的变异、返工过的规格、踩过的工具坑），可复用教训进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`。
- [ ] 9.3 改判 `docs/adr/0002-deferred-refactors.md` 的第 1 条剩一半、第 12、16 条为「已处理」，并把 `docs/CURRENT.md` 的门禁实测与缺口更新到 M3 实况。

## Workflow follow-up

- `/openspec-apply-change` 按上面的顺序 red → green，一个循环一次提交，提交信息带 task 编号，一个提交最多覆盖同一 seam 上相邻 3 个 task
- `code-review` 两轴（Standards / Spec）
- 先 `openspec-sync-specs` 再 `/openspec-archive-change`
- 归档后跑一次 `agents-md-slim`
