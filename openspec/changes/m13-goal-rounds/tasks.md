# Tasks

## 0. 前置

- [x] 0.1 子代理复核验证契约（五项检查：可追溯 / 可证伪 / 坏法覆盖 / 范围 / 可读），GAPS 先改契约再进 apply

## 1. 事件与折叠（seam ④）

- [x] 1.1 `goal/updated {goal|null}` 事件、快照字段校验（`blocked` 必带 `blocked_reason`、两者非空）、折叠取最后值
- [x] 1.2 `user/message.source`：缺省 `{kind:"user"}`；goal 轮次写 `{kind:"goal", goal_id, revision, round}`；旧日志缺字段按人读

## 2. 投影与任务并行（seam ②④）

- [x] 2.1 `todos` 投影清空条件保持「每段开头」（含 goal 轮，对齐 DSH）——曾改成 goal 段保留，2026-11-18 撤回
- [x] 2.2 `[goal] allow_parallel_in_progress`（默认 `true`）+ 第二个 `in_progress` → `TODO_PARALLEL_DISABLED`，整表不落盘

## 3. goal 工具（seam ②）

- [x] 3.1 `get_goal`（无目标回 `{"goal": null}`）+ `create_goal`（单目标 → `GOAL_ALREADY_ACTIVE`；子会话 → `GOAL_AUTHORITY_REQUIRED`）
- [x] 3.2 `update_goal` 的 CAS：id/revision 不符 → `GOAL_REF_STALE`；`pause` / `complete` 按 phase 翻转
- [x] 3.3 `resume`：`active` 的解除武装目标置真；`paused` → `GOAL_RESUME_BY_TOOL_DENIED`
- [x] 3.4 `blocked`：`rounds_started < blocked_after_consecutive_rounds` → `GOAL_BLOCK_TOO_EARLY`；接受时 `code == "model-reported"`

## 4. 轮次驱动（seam ①⑦）

- [x] 4.1 段后判定 + 四事件顺序（`segment/start` → goal 来源 `user/message` → 首条 `turn/start` → 首条 `context/assembled` → `goal/updated`），`rounds_started` 递增、`revision` 不变
- [x] 4.2 达上限：写 `blocked {code: "round-limit"}`，不起新段
- [x] 4.3 五类失败收尾（`ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` / `MAX_TURNS`）不续跑、不开新段；`ABORTED` 另写一条 `goal/updated` 把 `phase` 置 `paused`，其余只解除武装
- [x] 4.4 `replay` 校验 goal 轮次：轮号非正、同一 `goal_id` 内跳号、超 `max_rounds`、`revision` 落后、`phase` 已停 → 退出码非零；正常日志退出 0
- [x] 4.5 `get_todos` 读回（D8 的配套）：读 `todos` 投影、不落事件、段首为空、计划模式放行；`DispatchContext.todos` 由批首前缀折好传入

## 5. 武装与命令面（seam ⑥）

- [x] 5.1 `armed` 只活在进程内：启动与 `--resume` 后为假，`pause` / `complete` / `blocked` / 撞上限置假（`test_goal_update`、`test_chat_goal_driver::test_resume_does_not_continue_an_active_goal`）
- [x] 5.2 `/goal`、`/goal pause`、`/goal resume`、`/goal clear` 四条命令；无目标不写事件（`test_goal_commands`；host 同一条 `execute_command`，带 env）
- [x] 5.3 CLI 黑盒：`--resume` 之后第一次模型调用前没有 goal 来源消息，`/goal resume` 之后才有（`test_chat_goal_driver` 的两条 chat 用例）
- [x] 5.4 REPL 段后驱动：`chat` 里目标 `active` 且已武装时，段结束不开提示符、直接起下一轮；提示符只在驱动停下时出现（`test_chat_goal_driver::test_chat_keeps_running_rounds_without_another_line`）

## 6. 收尾

- [x] 6.1 真实端点验收（小上限两轮续跑，记录 `docs/verification/m13-goal-rounds-real-endpoint.md`；A/B 两场，complete 与 round-limit 各一）
- [ ] 6.2 UAT 验收（人跑；场次手册 `docs/verification/m13-goal-rounds-uat.md`）
- [ ] 6.3 变异测试一轮（记录 `docs/verification/m13-goal-rounds-mutation.md`）
- [ ] 6.4 Learning Gate
