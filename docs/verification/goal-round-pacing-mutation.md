# 变异测试：goal-round-pacing

**日期**：2026-11-25
**基线**：`890 passed / 7 skipped`（`scripts/gates.sh`，提交 `835ca3d`）
**方法**：逐条改坏实现 → 跑相关测试 → 记录哪些变红 → 用 Edit 反向改回 → 确认回到基线。

## 变异

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | `MAX_STEPS` 仍按失败收尾 | `NO_CONTINUE_REASONS` 加回 `"MAX_STEPS"` | **杀死 2 条**：`test_max_steps_is_a_round_boundary_and_the_cap_still_stops`、`test_the_round_decision_only_looks_at_the_snapshot_the_arm_and_the_stop_reason`。前者断言轮数 3 条，后者断言 `continue` |
| M2 | 政策段不注入 | `protected_header` 里 `policy = GOAL_POLICY_VERSIONS.get(...)` 改成 `policy = None` | **杀死 2 条**：`test_the_goal_policy_is_injected_when_the_session_carries_it`、`test_the_append_prompt_comes_after_the_goal_policy` |
| M3 | `session/start` 不记版本 | 删 `start_session` 里的 `"goal_policy": GOAL_POLICY_VERSION` | **杀死 1 条**：`test_the_three_entries_still_write_the_same_payload`（键集合少一项）。**关键观察**：同一次跑里 `test_context_fold.py` 45 条全绿——折叠层单独构造带 `goal_policy` 的日志仍能注入，只有端到端判据能发现「会话没写字段」 |
| M4 | 轮次提前扣 | 在 `_run_steps` 的步循环之前插 `advance_round` + 写 `goal/updated`（`context/assembled` 尚未落盘） | **杀死 1 条**：`test_an_assembly_overflow_before_context_assembled_keeps_the_round_count`（`rounds_started` 由 0 变 1）。**关键观察**：端到端的三轮用例**不受影响**——提前扣和开轮时扣是同一个值，只有「装配前失败」这条路径能看见差别。这正是两轴 review F2 要求补判据的理由 |
| M5 | 政策漏掉停滞条件 | `v2` 文本删掉「且没有连续零动作触发停滞时」 | **杀死 1 条**：`test_the_goal_policy_mentions_the_stall_gate`。`test_a_new_session_carries_the_goal_policy` 不断言停滞，所以只靠它抓不到 |
| M6 | 配置给政策开口子 | `config/load.py` 的键白名单加 `"goal_policy": (str,)` | **杀死 1 条**：`test_the_goal_policy_is_not_a_config_key`（配置被接受，`run` 退 0）。说明「不可由配置覆盖」这条 MUST 现在真有判据 |

## 还原

六条都用 Edit 反向改回；`git diff --stat src/mini_harness` 只剩政策 `v2` 与目标轮正文两处预期改动，相关三文件 `91 passed`，确认回到基线。

## 覆盖缺口

- **政策段被 append 覆盖**没有专门的变异：当前实现是「先插政策、再插 append」，要产生覆盖得删掉政策插入或改顺序；M2 已覆盖「不插」的形态，覆盖形态由 `test_the_append_prompt_comes_after_the_goal_policy` 的顺序断言兜住。
- **`MAX_STEPS` 无目标时仍停**没有独立变异：`next_round` 的第一行 `goal is None` 是既有分支，M1 只改集合不影响它；该行为由 `test_without_a_goal_max_steps_still_stops` 与真实端点场次（`eadcfdb4…`）覆盖。
- **`streamed_any` / 流式**不在本 change 范围，变异留给 `restore-chat-streaming`。
