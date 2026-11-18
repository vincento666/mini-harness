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

- [ ] 3.1 `get_goal`（无目标回 `{"goal": null}`）+ `create_goal`（单目标 → `GOAL_ALREADY_ACTIVE`；子会话 → `GOAL_AUTHORITY_REQUIRED`）
- [ ] 3.2 `update_goal` 的 CAS：id/revision 不符 → `GOAL_REF_STALE`；`pause` / `complete` 按 phase 翻转
- [ ] 3.3 `resume`：`active` 的解除武装目标置真；`paused` → `GOAL_RESUME_BY_TOOL_DENIED`
- [ ] 3.4 `blocked`：`rounds_started < blocked_after_consecutive_rounds` → `GOAL_BLOCK_TOO_EARLY`；接受时 `code == "model-reported"`

## 4. 轮次驱动（seam ①⑦）

- [ ] 4.1 段后判定 + 三事件顺序（`segment/start` → goal 来源 `user/message` → `goal/updated`），`rounds_started` 与 `revision` 各递增
- [ ] 4.2 达上限：写 `blocked {code: "round-limit"}`，不起新段
- [ ] 4.3 四类失败收尾（`ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED`）不续跑、不写 `goal/updated`

## 5. 武装与命令面（seam ⑥）

- [ ] 5.1 `armed` 只活在进程内：启动与 `--resume` 后为假，`pause` / `complete` / `blocked` / 撞上限置假
- [ ] 5.2 `/goal`、`/goal pause`、`/goal resume`、`/goal clear` 四条命令；无目标不写事件
- [ ] 5.3 CLI 黑盒：`--resume` 之后第一次模型调用前没有 goal 来源消息，`/goal resume` 之后才有

## 6. 收尾

- [ ] 6.1 真实端点验收（小上限两轮续跑，记录 `docs/verification/m13-goal-rounds-real-endpoint.md`）
- [ ] 6.2 UAT 验收（人跑；场次手册 `docs/verification/m13-goal-rounds-uat.md`）
- [ ] 6.3 变异测试一轮（记录 `docs/verification/m13-goal-rounds-mutation.md`）
- [ ] 6.4 Learning Gate
