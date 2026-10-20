# Tasks

## 1. 分支与基线

- [x] 1.1 从 `main` 建分支 `change/m8-runtime-semantics-alignment`，跑一遍四道门禁确认基线绿（`222 passed, 2 skipped`、`TOTAL` 不低于 95%、mypy / ruff / fmt 全绿），把基线数字记进提交信息
- [x] 1.2 读 `openspec/specs/turn-loop/spec.md` 的「工具调用与结果按声明顺序落盘」与 `tests/test_turn_concurrency.py::test_results_land_in_declared_order_when_the_second_finishes_first`，确认被推翻的判据就是这一条并列出它当前的断言形状（只读不改，产出写进本 change 的 design.md 附注或提交信息）

## 2. 词表两个新值（seam ②）

- [x] 2.1 先写 seam ② 判据：`tests/test_tool_registry.py::test_the_outcome_vocabulary_has_sixteen_values_and_no_not_implemented` 改成 18 个取值并含 `ABORTED_BEFORE_DISPATCH` 与 `TOOL_OUTCOME_UNKNOWN`（red），再扩 `tools/registry.py` 的结果词表让它转绿。注意：`tests/test_vocabulary_reachability.py::test_every_tool_outcome_is_reachable` 从这一步起红着，直到 5.5 把两个生产者接进观察源
- [x] 2.2 seam ② 护栏：新增 `test_the_pipeline_never_produces_the_two_kernel_only_outcomes`——工具与管线自己跑不出 `ABORTED_BEFORE_DISPATCH` 与 `TOOL_OUTCOME_UNKNOWN`（执行段逃出的异常只能塌成 `TOOL_TIMEOUT` / `TOOL_CANCELLED`）。**记录一处任务修正**：本条原写「未派发的调用不配 `tool/cancelled`、闭合码不出现在日志里」，那两半在 seam ② 上没有红切片可做（`dispatch_call` 没有取消入口、闭合不落盘），已分别落到 4.3 与 5.3；本条落地为护栏，写完即绿
- [x] 2.3 在 `GLOSSARY.md` 补这两个结果词的一句话定义（含 `_Avoid_`：不要把 `ABORTED_BEFORE_DISPATCH` 读成失败、不要把 `TOOL_OUTCOME_UNKNOWN` 读成日志损坏），并确认 `tests/test_event_vocabulary.py` 仍绿。**落点更正**：两个词写在「日志与折叠」一节紧跟「结果词」的位置（那里才是结果词在的地方），不是原写的「围栏与工具」；同节的「闭合记录」条目补一句「调用没有配对时，闭合由折叠派生，不写进日志」

## 3. 结果在产生时落盘（seam ④ 与 seam ①）

- [x] 3.1 重写 seam ④ 判据：把 `test_results_land_in_declared_order_when_the_second_finishes_first` 改成「先完成的先落盘」+ 结果集合与配对关系不断言顺序（red），确认它在当前实现下红。**同一批还拆了另一条声明顺序的残留**：`test_ten_reads_in_one_turn_never_exceed_the_limit` 原断言 `tool/result` 与 `tool/call` 同序，改成「`tool/call` 仍按声明顺序 + 结果集合配平」，被测对象（并发峰值 8）不变
- [x] 3.2 改 `loop/turn_loop.py` 的派发段：每个调用产出结果即 append 并 flush，去掉批次末的 `outcomes` 批量落盘，让 3.1 转绿（seam ④）。新增 `settle()`：`approval/response` → `tool/result` → `tool/cancelled` → `error/fence` 逐个落盘，围栏拒绝的结论改在落盘时记进 `_BatchOutcome`
- [x] 3.3 先写 seam ④ 判据：并发只读批次里第二条结果在盘上出现的时间点早于第一条结果产出（轮询日志文件，red），再确认 3.2 的实现满足它；不满足就改派发段。实测：把派发段回滚到 3.2 之前，这条在 `assert 'c1' not in ['c1', 'c2']` 上红；3.2 之后绿
- [x] 3.4 跑 seam ① 既有回归：`tests/test_turn_loop.py` 与 `tests/test_approval_gate.py::test_an_approved_call_keeps_its_relative_order_when_the_batch_interleaves` 全绿，确认「单个调用自己的记录相对顺序」没被 3.2 弄坏（`test_turn_loop.py` + `test_approval_gate.py` + `test_event_log_append.py` + `test_context_fold.py` 共 52 passed）

## 4. 取消是回合级事件（seam ①）

- [x] 4.1 扩 seam ① 判据：`tests/test_turn_cancel.py::test_no_call_has_a_tool_call_without_a_result_after_a_cancel` 改成「未派发的声明调用也各有一条 `tool/call` 与一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`」（red），并加一条「结果词说它没开始，文件就必须没被写过」的反向断言。实测在旧实现下红在 `['c1','c2'] == ['c1','c2','c3']`
- [x] 4.2 改派发段的取消分支：新增 `abandoned()`——未派发的调用落 `tool/call` + `ABORTED_BEFORE_DISPATCH`（走同一个 `begin` 与 `settle`），已开始执行的仍塌 `TOOL_CANCELLED` 并配 `tool/cancelled`，让 4.1 转绿（seam ①）。取消与围栏拒绝同时在场时取消优先：未派发的调用落一对记录，run 仍以 `FENCE_DENIED` 收尾
- [x] 4.3 先写 seam ① 判据：取消收尾的回合里 `error/abort` → `turn/end`（`stop_reason: ABORTED`）的相对顺序不变、且未派发的调用不配 `tool/cancelled`（seam ①）。**记录**：新增 `test_the_undispatched_call_gets_no_tool_cancelled`；「不配 `tool/cancelled`」这半在 4.2 之后即绿（`settle` 只对 `CANCELLED_OUTCOMES` 写该记录），新形状下真正新增的是「本批每条 `tool/result` 都在 `error/abort` 之前落盘」这条前缀完整性
- [x] 4.4 先写 seam ① 判据：一次以 `ABORTED` 收尾的 run 的日志折叠后，每个 assistant 工具请求消息都有配平的工具结果消息，再确认 4.2 之后它转绿（seam ① 与 seam ④）。新增 `test_an_aborted_run_folds_into_balanced_tool_messages`，形状与 4.1 不同：慢的那条被打断、后两条没开始
- [x] 4.5 确认 `cli/main.py` 侧的会话终止形状：内核返回 `ABORTED` 后入口写 `session/end` 并以退出码 5 结束（`EXIT_ABORTED = 5` 与 `STOP_REASONS_TO_EXIT_CODES` 未改）；`tests/test_turn_cancel.py` 六条与 `tests/test_cli_run.py::test_sigint_handler_sets_the_cancel_event` 全绿（seam ⑥）

## 5. 读方闭合（seam ④）

- [x] 5.1 先写 seam ④ 判据：构造一份以「有 `tool/call` 没 `tool/result`」结尾的日志，折叠结果里该 `tool_call_id` 有一条 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息、且该消息出现在该调用的 assistant 请求之后、该点之后的既有消息之前（red）。新增 `test_an_unpaired_tool_call_folds_into_a_derived_closer`，实测红在 `['assistant','tool','assistant'] == ['assistant','tool','tool','assistant']`；构造日志抽成 `_half_log_events()` 供 5.3 复用
- [x] 5.2 改 `events/fold.py`：未配对的 `tool/call` 派生闭合消息，让 5.1 转绿；派生不落盘、不新造事件类型、不自动重试（seam ④）。规则是「未配对的先闭合，再轮到它之后的那条消息」：`fold` 边扫边记 pending，遇到下一条会产出消息的事件就把 pending 闭合掉，末尾再闭合剩下的
- [x] 5.3 先写 seam ④ 判据：完整日志不派生任何 `TOOL_OUTCOME_UNKNOWN`（负判据）、同一份半截日志折叠两次结果逐字段相等、`minihns replay` 对半截日志不追加任何记录，再确认 5.2 满足（seam ④）。三条都绿：`test_a_complete_log_derives_no_closer`、`test_the_derived_closer_is_deterministic`、`test_replay_of_a_half_log_derives_the_closer_without_touching_the_log`。**踩坑记录**：replay 要求日志里至少有一条 `context/assembled`（否则 `REPLAY_MISMATCH`），所以半截日志要手搓成「回合一开始装配过一次、之后另起一个回合又装配过一次」的形状；判据是「日志字节不变 + 日志里没有一条 `tool/result` 配这个调用 + 折叠结果里有闭合」，不是「日志里搜不到那个词」——装配记录本身就把折叠结果记进去了
- [x] 5.4 跑 seam ④ 既有回归：`tests/test_context_fold.py` 全部判据与「冷启动逐点重建」判据全绿，确认闭合没有弄坏前缀折叠的确定性（24 passed，含 `test_cli_replay.py`）
- [x] 5.5 按 design D6 扩 `tests/test_vocabulary_reachability.py::test_every_tool_outcome_is_reachable` 的观察源：`ABORTED_BEFORE_DISPATCH` 从 seam ① 的取消批次观察、`TOOL_OUTCOME_UNKNOWN` 从 seam ④ 的折叠观察，让这条从 2.1 起红着的判据转绿（seam ② 与 seam ① 与 seam ④）。观察源：取消在派发前置位的 fixture 会话（日志里的 `tool/result`）+ 把那份日志唯一一条结果抹掉后的 `fold`；折叠侧只收词表内的取值，因为工具结果消息的 `content` 通常是正文不是结果词

## 6. 硬杀与入口（seam ⑥）

- [ ] 6.1 新增 seam ⑥ 判据：用 `Popen` 起真实 `minihns run` 子进程，轮询日志到出现 `tool/call` 后 `kill()`，断言「已产出的每条 `tool/result` 完整可独立解析、没有半行 JSON」这条与杀点无关的性质（red → green；Windows 用 `Popen.kill()`，Linux CI 用 `SIGKILL`）
- [ ] 6.2 确认硬杀后的日志可被折叠与 replay：新增 seam ⑥ 判据跑 `minihns replay` 读那份被硬杀的日志，断言它不追加记录、逐点重放不失败（seam ⑥）
- [ ] 6.3 确认退出码形状没变：取消收尾仍是 5、围栏仍是 3、模型错误仍是 1、4 仍是保留码不被产生（seam ⑥ 既有判据回归）

## 7. 集成检查

- [ ] 7.1 跑四道门禁全绿（`uv run coverage erase` → `coverage run -m pytest -q` → `coverage combine` → `coverage report --fail-under=95 --show-missing`，再 mypy / ruff check / ruff format --diff），把 `TOTAL` 数字记进提交信息
- [ ] 7.2 跑 `openspec validate --all --strict` 确认 0 failed，并跑 `openspec show m8-runtime-semantics-alignment --type change` 确认三条 delta 都被识别
- [ ] 7.3 更新 `docs/CURRENT.md`：关闭「工具结果缓冲到批次结束落盘」那条缺口、写清 M8 的门禁实测与「协作式取消只做了一半，M10 补完」这条已知边界

## 8. 收尾

- [ ] 8.1 人手验收：拿真实工作区办一件真事（一次 run 里故意并发多个 `read`，中途 Ctrl-C，再读那份日志），观察记进 `docs/verification/m8-runtime-semantics-alignment-manual.md`，不进 CI
- [ ] 8.2 变异测试一轮并记进 `docs/verification/m8-runtime-semantics-alignment-mutation.md`：至少变异「取消时未派发的调用不落结果」「闭合不落盘」「闭合派生不确定（掺入进程内残留）」「`tool/cancelled` 给未派发的调用也配一条」各一处，判据是每个变异都被至少一条测试杀死；并在 `docs/verification/m3-bash-concurrency-timeout-mutation.md` 加一条注记说明 C2 那条落盘顺序护栏在 M8 之后不再适用（不改写历史）
- [ ] 8.3 Learning Gate：扫本轮证据（红过的判据、存活的变异、返工过的规格、硬杀判据的工具坑），可复用教训写进 `docs/lessons.md` 收件箱，没有可复用信号就写 `NO-PROMOTION`

## Workflow follow-up

- 人工审阅 proposal / specs / design / tasks 后再跑 apply 工作流。
- apply 之后跑 `code-review`（Standards 与 Spec 两轴）。
- 满足审阅要求后 `/openspec-archive-change` 归档，归档提交里三条 delta 合进主规格（`turn-loop` 的 REMOVED + ADDED、`event-log` 的两条 MODIFIED、`context-projection` 的 ADDED）。
- 归档后跑一次 `agents-md-slim`。
