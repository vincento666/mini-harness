# M8 变异测试轮（`m8-runtime-semantics-alignment`）

跑法：改坏一处实现 → 跑全量测试（`uv run pytest -q -x`，被杀即停；存活的那条跑全量确认）→ 记录 → `git checkout -- <改过的文件>` 还原并确认回到基线。施加变异前先看 `git status --short`：本轮工作树里有与 M8 无关的未提交改动（`docs/tools/`、`repowiki/`、`.gitignore`），还原只针对本轮改过的 `src/` 文件。

轮末基线：**233 passed / 2 skipped**，`TOTAL 1162 53 95%`，`mypy --strict` 22 个源文件干净，`ruff check` 干净，`ruff format --diff` 空。

## 变异与结果

| 编号 | 改法 | 结果 |
|---|---|---|
| A | 取消时未派发的调用不落结果：删掉 `abandoned()` 里的 `settle(...)`，只留 `tool/call` | 杀：`test_no_call_has_a_tool_call_without_a_result_after_a_cancel`（seam ①，`tool/result` 变成 `['c1','c2']`，第三条没有配对） |
| B | 取消时未派发的调用连 `tool/call` 也不落：删掉 `abandoned()` 里的 `if not begin(index, call): return` | 杀：同一条判据（`tool/call` 变成 `['c1','c2']`，声明过的调用在日志里没有交代） |
| C | 折叠不闭合末尾的未配对调用：删掉 `fold()` 循环之后那句 `body.extend(_closer(...) for call_id in pending)` | 杀：`test_replay_of_a_half_log_derives_the_closer_without_touching_the_log`（seam ⑥，replay 的 `final_context` 里没有 `TOOL_OUTCOME_UNKNOWN`） |
| D | 闭合派生掺入进程内残留：`fold()` 的 `pending` 从局部列表换成模块级 `_PENDING`，折叠结束不清 | **第一轮存活** → 补判据后被杀（见下） |
| E | `tool/cancelled` 给每条落盘结果都配一条：`settle()` 里 `if outcome in CANCELLED_OUTCOMES` → `if outcome is not None` | 杀：`test_a_bash_timeout_in_the_cli_is_a_result_word_and_the_run_continues`（seam ⑥，`tool/cancelled` 多出一条 `c2`） |
| F | 结果回到批次末缓冲落盘：`settle()` 只把记录攒进 `deferred`，`asyncio.gather` 之后一次 `_append_all` | 杀：`test_a_hard_kill_leaves_no_half_written_line`（seam ⑥，硬杀时 `results` 是空列表——批次末的缓冲跟着进程一起没了） |
| G | 内核替未配对的调用在日志里编一条结果：`escaped()` 在 `error/internal` 之前多写一条 `tool/result`，`outcome: TOOL_OUTCOME_UNKNOWN` | 杀：`test_an_escaped_exception_leaves_the_call_unpaired_and_fold_closes_it`（seam ①，本轮新增；见下） |
| H | 未派发的调用复用旧词：`abandoned()` 的 `"ABORTED_BEFORE_DISPATCH"` → `"TOOL_CANCELLED"` | 杀：`test_no_call_has_a_tool_call_without_a_result_after_a_cancel`（seam ①，结果词集合里 `('c3','ABORTED_BEFORE_DISPATCH')` 不见了） |

八条变异：七条第一轮被杀，一条（D）存活并已补判据、重跑确认被杀。判据「每个变异都被至少一条测试杀死」达成。

## D 存活：折叠的确定性只判了一种形状

`test_the_derived_closer_is_deterministic` 原来只喂一份半截日志，而那份日志的未配对调用后面还跟着一条会产出消息的事件（`model/response`）。折叠在中途就把 pending 冲掉并 `clear()`，模块级残留因此没有机会显形——两次折叠照样逐字段相等，全量跑 **232 passed / 0 failed**。

补法：同一条判据判两份形状，`_half_log_events()` 与 `_half_log_events()[:-1]`（后者以未配对的 `tool/call` 加一条不产出消息的 `turn/end` 结尾，pending 只能靠折叠收尾清掉）。变异下红：`assert ['tool','assistant'] == ['assistant','tool','assistant']`（第二次折叠多出一条闭合）；顺带 `test_fold_puts_the_system_prompt_first_and_keeps_the_body_in_order` 也红——残留串到了下一个测试。还原后两条都绿 ✓。

教训的形状：**「确定性」判据要判到状态被清掉的那条路径**。只喂「中途被冲掉」的那一份，等于只测了清理的一半。

## G 的落点：「闭合不落盘」这条约束此前没有可观察的判据

施加变异 G 之前先补判据，理由记清楚：run 正常跑完的批次里不存在未配对的 `tool/call`——取消路径下未派发的调用有配对结果（M8 的 A 组改动），围栏与写日志失败的路径下 `tool/call` 根本没写。唯一在 run 里留下未配对调用的形状是**执行段逃出来的异常**（`escaped()` 只写 `error/internal`），而既有那条判据（`test_an_escaped_exception_is_not_renamed_to_a_cancellation`）只判它不被改名成 `TOOL_CANCELLED`，没有判「它没有配对结果」，也没有判折叠把这条闭合派生出来。硬杀那个形状归 seam ⑥，判的是「已落盘的行完整」，同样不判有没有人替它编结果。

证据：变异 G 下全量跑到第 208 条才红，**前 207 条全绿**——这条约束在旧判据集里确实没有落点。

补的判据：seam ① `test_an_escaped_exception_leaves_the_call_unpaired_and_fold_closes_it`——`c1` 有 `tool/call`、没有 `tool/result`、日志里没有任何 `TOOL_OUTCOME_UNKNOWN` 结果词，而 `fold(records)` 里 `role` 为 `tool` 的消息恰好一条、`tool_call_id` 是 `c1`、`content` 是 `TOOL_OUTCOME_UNKNOWN`。基线下绿 ✓，变异 G 下红（`assert 'c1' not in ['c1']`）✓，还原后绿 ✓。

## 与 M3 变异记录的关系

M3 的 C2（删掉 `await started[index - 1].wait()`）判定为 dud：它守的是「`tool/call` 按声明顺序落盘」，而那条保证在 M8 已被 REMOVED。已在 `docs/verification/m3-bash-concurrency-timeout-mutation.md` 的 C2 一节追加追记（原始判定不改写）：C2 现在守一个规格不再要求的性质，重跑它没有意义；落盘时机这条在 M8 有了判据（本轮变异 F）。
