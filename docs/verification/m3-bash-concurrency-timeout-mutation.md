# M3 变异测试轮（task 9.1）

基线：211 passed / 2 skipped，TOTAL 95%（1103 语句 / 52 未覆盖），HEAD `c841f0b`。做法：一处改坏 → 跑全量 `pytest -q`（不带覆盖率记账，约 52 秒）→ 记下变红的测试 → `git checkout -- <被改文件>` 还原；还原前先看 `git status --short`，别把本轮未提交的测试文件一起回滚。

变异面按 tasks 9.1 点名的五块挑：执行段的异常族、并发上限数值、落盘顺序、超时数值、进程树终止；另加「内容有界」一块，因为它是 `bash` 唯一的输出契约。

| 编号 | 变异（改法） | 结果 |
|---|---|---|
| X1 | 异常族顺序：`except OSError` 排在 `except TimeoutError` 之前（`TimeoutError` 是 `OSError` 的子类，于是超时塌成 `TOOL_IO_FAILED`） | 杀 2 条：`test_a_timeout_in_the_execution_segment_is_a_result`、`test_every_tool_outcome_is_reachable`（词表判据看见 `TOOL_TIMEOUT` 跑不出来了） |
| X2 | 取消不塌成结果词：`except asyncio.CancelledError` 的 return 改成 `raise` | 杀 2 条：`test_an_interrupted_execution_segment_is_a_result`、词表判据。附带事实：seam ① 的取消判据**仍然绿**——`_race_with_cancel` 的兜底那条也产出 `TOOL_CANCELLED`，两处塌词分别被 seam ② 与 seam ① 钉住 |
| C1 | 并发上限数值：`MAX_PARALLEL_TOOLS = 8` → 9 | 杀：`test_ten_reads_in_one_turn_never_exceed_the_limit`（断言 `peak == 8`，报「同时跑到的调用数 9 超过规格上限 8」） |
| C2 | 落盘顺序护栏：删掉 `await started[index - 1].wait()` | **存活**，判定为 dud（见下） |
| C3 | 串行规则只看自己：`if mutating[index] or mutating[index - 1]` → `if mutating[index]` | 杀：`test_a_fence_denial_does_not_swallow_the_calls_already_running`（`tool/call` 变成 `['c1','c2','c3']`，该跳过的第三条被派发了） |
| W1 | `approval/request` 不在提问前落盘：`ask_logged` 直接 `return True` | 杀 4 条：`test_each_approved_write_asks_once_and_then_succeeds`、`test_the_request_is_on_disk_before_the_human_is_asked`、`test_events_jsonl_stdout_equals_the_log_line_by_line`、`test_replay_verifies_a_log_that_carries_approval_and_fence_events` |
| T1 | bash 默认超时：`DEFAULT_TIMEOUT_SECONDS = 30` → 45 | **第一轮存活**，补判据后被杀（见下） |
| T2 | 模型超时：`_TIMEOUT_S = 120.0` → 60.0 | 杀：`test_the_model_request_carries_a_120_second_timeout`（httpx 的 `request.extensions["timeout"]` 三个字段一起变） |
| P1 | 进程树终止只杀 shell：Windows 分支的 `taskkill /T /F /PID` → `process.kill()` | 杀：`test_a_timed_out_command_leaves_no_descendant_still_writing`（后代继续往 `ticking.txt` 写）。附带事实：取消那半边不是红而是**挂住**——`await process.wait()` 等一个被后代占着的管道，整条 session 再也不返回（见下） |
| P2 | bash 的 cwd 不是工作区根：`cwd=str(context.workspace)` → `context.workspace.parent` | 杀 10 条：`test_bash_tool.py` 里 7 条 + `test_a_bash_command_runs_end_to_end_in_the_cli` + `test_turn_cancel.py` 2 条（脚本落错目录，命令本身找不到） |
| O1 | 输出上限 off-by-one：`if len(encoded) <= OUTPUT_LIMIT_BYTES` → `<`（正好等于上限也算超限） | **第一轮存活**，补判据后被杀（见下） |
| K1 | 超时不配 `tool/cancelled`：`CANCELLED_OUTCOMES` 去掉 `TOOL_TIMEOUT` | 杀：`test_a_timed_out_call_does_not_stop_the_rest_of_the_batch` |

## C2 存活：判定为 dud，不补判据

`_append_all` 是同步函数（`def`，不是 `async def`），`begin()` 全程不让出事件循环，所以「排在它后面的调用要等它开始」这条链在当前实现下**不可观察**：删掉它，`tool/call` 的落盘顺序一条都没变。按 AGENTS.md 的变异纪律（语义等价的改法是 dud mutant，不算），这条记为 dud，不为它编判据。

顺带把事实写清楚：`started` 链防的是「落盘将来会变成 awaitable」那种实现（例如日志写入换成 `asyncio.to_thread`）。到那一天它才成为可观察的护栏；现在它是护栏，不是判据能到达的地方。

**2026-10-20 追记（M8 之后这条不再适用）**：M8 把落盘时机改成「产生即写」、落盘顺序从声明顺序改成完成顺序（ADR-0012），主规格里「工具调用与结果按声明顺序落盘」那条 Requirement 已 REMOVED。C2 守的正是那条声明顺序保证——它现在守一个规格不再要求的性质，重跑它没有意义。落盘时机这条在 M8 变异轮里有了判据：同方向的变异（结果回到批次末缓冲）被 seam ⑥ 的 `test_a_hard_kill_leaves_no_half_written_line` 杀死。`started` 链本身仍然不是判据能到达的地方。上面的原始判定保留不改。

## 存活的两条真缺口与补的判据

**T1（默认超时 30 秒没人钉）**：上限那半边早就被 `timeout_seconds: 601 → TOOL_ARGS_INVALID` 钉住了，默认值改成就没人知道——全量一条都不红。补 seam ③ `test_the_timeout_numbers_are_the_ones_the_spec_names`：默认 30、上限 600 是规格里的数值，另判「省略 `timeout_seconds` 的调用实际拿到 30」（`BashArgs(command="true").timeout_seconds == 30`）。变异下红：`assert 45 == 30` ✓ 还原后绿 ✓。

**O1（上限的边界没人判）**：已有的截断判据只断言「超限会被截」，把 `<=` 写成 `<` 它抓不到。补 seam ③ `test_the_output_limit_is_a_boundary_not_a_threshold`：先跑一条什么都不写的命令，量出「退出码 0」那行前缀占的字节数，再让脚本正好写 `OUTPUT_LIMIT_BYTES - 前缀` 字节——正好等于上限的内容原样进日志、没有截断标记；多一个字节才有。变异下红：`assert 16401 == 16384`（16384 + 17 字节的标记）✓ 还原后绿 ✓。

## P1 的附带事实：进程树终止也保证「执行段一定返回」

超时那半边 P1 是红的（后代还在写）。取消那半边它是**挂住**：`process.kill()` 只收掉 shell，后代握着 stdout/stderr 的管道句柄，`await process.wait()` 永远不返回，整条 session 卡在执行段里。全量跑因此在变异 7 下不结束。规格里「取消打断的调用塌成结果词」隐含一个前提：执行段一定会返回。这条不另立判据——`test_turn_cancel.py` 的两条判据在正确实现下会返回，挂住本身就是它们失败的形式。

## 工具坑：定向跑测试会把「被杀」误判成「存活」

X1 第一次只跑 `tests/test_bash_tool.py tests/test_turn_cancel.py`，15 条全绿，看着像存活；跑全量才红——`bash` 自己把超时塌成结果词，dispatch 的那条捕获只有 seam ② 的桩判据（`test_vocabulary_reachability.py`）经过。变异测试 MUST 跑全量，定向跑只能用来定位。

## 结论

12 条变异：10 条第一轮被杀，2 条（T1、O1）存活并已补判据、重跑确认被杀，1 条（C2）判定为 dud。判据「每个变异都被至少一条测试杀死」达成（dud 不计）。轮末基线：213 passed / 2 skipped。
