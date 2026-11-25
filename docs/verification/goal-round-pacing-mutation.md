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

## 还原

三条都用 Edit 反向改回；`git diff --stat src/mini_harness` 为空，相关三文件 `110 passed`，确认回到基线。

## 覆盖缺口

- **政策段被 append 覆盖**没有专门的变异：当前实现是「先插政策、再插 append」，要产生覆盖得删掉政策插入或改顺序；M2 已覆盖「不插」的形态，覆盖形态由 `test_the_append_prompt_comes_after_the_goal_policy` 的顺序断言兜住。
- **`MAX_STEPS` 无目标时仍停**没有独立变异：`next_round` 的第一行 `goal is None` 是既有分支，M1 只改集合不影响它；该行为由 `test_without_a_goal_max_steps_still_stops` 与真实端点场次（`eadcfdb4…`）覆盖。
- **`streamed_any` / 流式**不在本 change 范围，变异留给 `restore-chat-streaming`。
