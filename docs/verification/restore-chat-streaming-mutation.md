# 变异测试：restore-chat-streaming

**日期**：2026-11-25。
**基线**：`tests/test_cli_chat.py` + `tests/test_turn_loop.py` 共 78 passed / 4 skipped。
**方法**：逐条改坏实现 → 跑相关测试 → 记录哪些变红 → 用 Edit 反向改回 → 确认回到基线（`git diff --stat src/` 只剩本 change 的预期改动）。

## 变异

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | 流式改成攒批 | `_ChatStreamRenderer.text` 只把文本塞进 `_buffer`，`finish_turn` 一次性 `write(join(buffer))` | **杀死 1 条**：`test_the_first_delta_is_visible_before_the_turn_ends`（子进程写完首帧后停 3 秒，父进程 0.5 秒内读不到 `你`） |
| M2 | 取消不看「是否流过增量」 | 内核的 `if cancel.is_set() and env.on_delta is not None and delta_state.streamed_any:` 去掉最后一个条件 | **杀死 1 条**：`test_a_cancel_without_deltas_keeps_the_full_response`（`model/response` 从 1 条变 0 条——整段回复被吞） |
| M3 | 不调步末回退钩子 | 删掉 `_run_steps` 里的 `_notify_step_end(...)` 调用 | **杀死 1 条**：`test_a_mixed_turn_does_not_reverse_the_order`（stdout 变成 `> 乙乙\n甲甲\n> `，顺序倒成 2→1，正是 proposal 里 blocker B1 描述的症状）。**关键观察**：`test_a_step_without_deltas_falls_back_at_step_end_once` **没红**——单步轮里轮末投影会把正文补回来，看不出差别；只有「同轮前一步无增量、后一步流式」才暴露顺序 |
| M4 | 轮末投影不跳过已显示步 | 删掉 `_print_new_replies` 里的 `if step_id in shown: continue` | **杀死 2 条**：`test_streaming_is_the_default_and_writes_deltas_in_order`、`test_a_mixed_turn_does_not_reverse_the_order`（stdout 变成 `> 甲甲乙乙\n甲甲\n乙乙\n> `，同一段正文打了两遍） |

| M5 | 默认写反 | `--stream` 的 `default=True` 改成 `False` | **杀死 1 条**：`test_streaming_is_the_default_and_writes_deltas_in_order`（stdout 变成 `> 你好\n> `，没有增量） |
| M6 | 写但不 flush | `text()` 里的 `sys.stdout.flush()` 删掉 | **杀死 1 条**：`test_the_first_delta_is_visible_before_the_turn_ends`（管道 0.5 秒内读不到） |
| M7 | 空 content 也回退 | `on_step_end` 里去掉 `not content.strip()` 判断 | **杀死 1 条**：既有的 `test_tool_only_turns_leave_no_blank_lines`（多出空行）。我新加的 `test_a_tool_only_step_does_not_emit_a_blank_line` 没红——两者断言的形态不同，既有那条才是这条坏法的判据 |
| M8 | 空 delta 算流式 | `text()` 里 `if not text:` 时把 `step_id` 记进 `already_shown` | **杀死 1 条**：`test_empty_deltas_do_not_trigger_the_marker`（stdout 变成 `> > `，整段正文消失） |

## 还原

四条都用 Edit 反向改回；`git diff --stat src/` 只剩本 change 的预期改动（`cli/main.py` + `loop/turn_loop.py`），两文件 `78 passed`，确认回到基线。

## 覆盖缺口

- **`--resume` 的 `printed` 口径**没有变异：它只影响「恢复会话后第一条新回复打不打」，需要造一份「有压缩摘要 + 恢复」的日志才能观测；当前由 `_print_new_replies` 与初始化两处同口径的代码审查兜住（`--resume` 场景的判据列入未做项，见契约「不验什么」之外的一条待补）。
- **钩子异常转 `error/internal`** 没有变异：要模拟渲染器抛异常需注入坏 sink；当前实现只在该分支写一条记录，不影响正常路径。
- **pty 的 `0x03` 投递**不在本轮变异范围：它是信号投递的事实，不随实现改动而变，由既有 `_cli_console_process` 路径覆盖（Windows 控制台场次），macOS 上留给 UAT 的人工 Ctrl-C。
- **坏法 #12「按输入收尾」没实跑**：它要把 `finish_turn()` 从「每轮之后」挪到「输入循环之外」，属于结构性改法（改的是缩进层级而不是一行）。行为由 `test_goal_rounds_each_get_their_own_line` 覆盖——目标两轮若共用一次收行，正文会粘成一行。
- **坏法 #5「回退后再打一次」与 #4 同族**：两者都表现为「同一段正文出现两遍」，M4 已用一个变异覆盖这一族；`already_shown` 同时服务流式步与回退步，删掉它的判断会同时踩中两条。
- **坏法 #9「取消只看 sink」与 #10 同族**：M2 去掉 `streamed_any` 就是这个变异。
