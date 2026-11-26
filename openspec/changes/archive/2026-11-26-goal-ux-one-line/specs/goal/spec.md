# goal Delta

## MODIFIED Requirements

### Requirement: goal 工具及其权威

系统 SHALL 提供 `get_goal()`、`create_goal(objective, max_rounds?)`、`update_goal(goal_id, revision, action, objective?, max_rounds?, blocked_reason?)` 三个工具，`action` 取 `edit` / `pause` / `resume` / `complete` / `blocked`。所有工具结果 SHALL 是同一份紧凑 JSON：无目标时 `{"goal": null}`，否则含快照与 `armed`。

`create_goal` 的**工具描述** MUST 写成条件句并说明分轮边界：任务要写文件、改代码、跑命令验证或查多处资料时（哪怕用户只给一句话）使用它、`objective` 复述用户目标；建完 MUST 结束本轮、只做计划，正式内容从目标轮 1 开始；纯问答或寒暄不该用它；建完若发现一步能收尾，当轮标 complete。描述 MUST NOT 承诺「创建后自动把任务做完」。

`create`、`edit`、`pause`、`resume` MUST 只在本轮由人类来源的 `user/message` 开启时成立；`entry == "subagent"` 的会话 MUST NOT 具备该权威，返回 `GOAL_AUTHORITY_REQUIRED`。

`create` 在存在非 `complete` 目标时 MUST 返回 `GOAL_ALREADY_ACTIVE`；上一个目标已 `complete` 时 SHALL 允许创建**新**目标（新 `id`、`revision == 1`、`rounds_started == 0`）。

`update_goal` 的 `goal_id` 或 `revision` 与当前值不符时 MUST 返回 `GOAL_REF_STALE` 且不落事件。

`edit` SHALL 是部分替换：至少一个有效字段（`objective` 非空串、`max_rounds` 为正整数），空串与 `0` 视为省略；其它 `action` MUST 忽略这两个字段。`create_goal` 与 `edit` 的 `max_rounds` SHALL 以部署策略的 `max_rounds` 为**硬顶**：请求值大于它时按它落，MUST NOT 让模型用一个大数字绕开预算；要跑更多轮只能改部署配置。

`resume` SHALL：对 `active` 且未武装的目标置真；对 `blocked` 的目标置 `active`、清空 `blocked_reason`、置真；对 `paused` 的目标 MUST 返回 `GOAL_RESUME_BY_TOOL_DENIED`（该转换只由 `/goal resume` 完成）。

`complete` SHALL 把非 `complete` 目标置 `complete` 并解除武装；`blocked` SHALL 按「阻塞需要轮数门槛」Requirement 判定。

相位不允许该动作时 MUST 返回 `GOAL_INVALID_TRANSITION` 且不落事件：`pause` 只在 `active`，`complete` 只在非 `complete`，`blocked` 只在 `active`，`resume` 在 `complete` 或轮次已用尽时拒绝（`paused` 归人，见 `GOAL_RESUME_BY_TOOL_DENIED`）。

#### Scenario: 工具描述说明建完就停

- **WHEN** 读取 `create_goal` 的工具描述
- **THEN** 描述含「要写文件」这一使用条件、含「结束本轮」与「只做计划」的分轮边界，且不含「一次做完」这类承诺
