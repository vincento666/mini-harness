# 验证契约

**日期**：2026-11-25。这是人审的那一页；通过后进入 apply。

## 目标

让「一轮把步数写满」只结束这一轮、不杀死长任务；同时让模型从会话开头就知道轮/步与目标轮的存在。

## 可观察行为

1. **人类轮写满，目标轮接上**：一条人类输入建了目标后，在同轮第 `max_steps` 步收尾 → 日志出现 goal 消息与新 `turn/start`，`rounds_started` 从 0 变 1（seam：驱动判定 → 入口续轮）。
2. **目标轮写满，继续下一轮**：goal 轮以 `MAX_STEPS` 收尾且还有额度 → 开下一轮，`stop_reason` 仍记 `MAX_STEPS`（seam：驱动判定）。
3. **没有目标就照旧停**：无目标或非 `active` 时 `MAX_STEPS` 不开新轮（seam：驱动判定）。
4. **四类失败仍不续**：`ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` 都不自动续；`ABORTED` 另把目标置 `paused`（seam：失败收尾）。
5. **政策段在会话开头可见**：新会话的 `session/start.append_system_prompt` 非空、含轮与目标；显式 `--append-system-prompt` 覆盖它；旧日志（空串）replay 逐字段不变（seam：系统提示装配）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | 驱动单测：`next_round(goal=active, armed=True, stop_reason="MAX_STEPS")` 返回 `continue`（`test_max_steps_is_a_round_boundary_when_a_goal_is_active`） |
| 1 | 黑盒：人类轮 `max_steps=2` 写满、目标 active → 日志有 goal 来源 `user/message`，`rounds_started == 1`，第二条 `turn/start` 存在（`test_a_human_turn_that_hits_max_steps_starts_the_first_goal_round`） |
| 2 | 黑盒：目标轮 `max_steps=2` 写满、`max_rounds=3` → 出现第三轮；两条 `turn/end` 的 `stop_reason` 都是 `MAX_STEPS`（`test_a_goal_round_that_hits_max_steps_opens_the_next_round`） |
| 3 | 单测：`next_round(goal=None, armed=True, stop_reason="MAX_STEPS")` 返回 `stop`；`goal` 为 `paused` 同样 `stop`（`test_without_a_goal_max_steps_still_stops`） |
| 4 | 单测参数化：四个失败理由各一次 → 全部 `stop`；`ABORTED` 的 `phase` 变 `paused`，其余相位不变（`test_other_failure_reasons_still_stop`） |
| 5 | 单测：默认 settings 下 `append_system_prompt` 含「轮」「目标」，且 `SYSTEM_PROMPT` 常量原文不含这些政策句（`test_the_default_append_prompt_carries_the_goal_policy`） |
| 5 | 单测：`--append-system-prompt "额外规则"` → 折叠头部只有「额外规则」，不含默认政策（`test_an_explicit_append_prompt_overrides_the_default`） |
| 5 | 金样本：一份 `append_system_prompt` 为空串的旧日志 `replay` 退 0，逐点无 `REPLAY_MISMATCH`（`test_old_logs_without_the_policy_replay_unchanged`） |

## 坏法清单（变异种子）

1. **只改文档不改集合**：`NO_CONTINUE_REASONS` 里留着 `MAX_STEPS` → 行为 1、2 的判据红。
2. **顺手删多了**：把 `ABORTED` 也从集合里删掉 → 行为 4 的取消判据红（取消后自动续轮）。
3. **无目标也续**：`next_round` 不看 `goal is None` → 行为 3 红。
4. **政策段写进 `SYSTEM_PROMPT`**：旧日志 replay 红（行为 5 第 3 条），且违反「常量最前、只能追加」。
5. **两段来源**：默认政策与用户文本拼接而不是覆盖 → 行为 5 第 2 条红（头部出现两段）。
6. **政策段只在 `create_goal` 之后注入**：新会话开头的 `session/start.append_system_prompt` 为空 → 行为 5 第 1 条红。

## 不验什么

- 不验模型是否真的「按轮写」：模型策略不是运行时能保证的；本 change 只保证「写满不会死」与「模型看得到规则」。
- 不做 L1（工具描述条件句）与 L2（`create_goal` 后硬停）——DSH 无对照，按对齐纪律不做。
- 不做 L4（轮内工作量预算）：另开 `goal-round-budget`。
- 不实测 token 成本，只记录上限从 `max_steps` 变为 `max_steps × max_rounds`。
- 不评政策段文案的优劣，只断言关键词与位置；文案可迭代。
- 不改 `turn/end` 词表、`max_steps`、`max_rounds` 的默认值。

## 待裁决

- 默认政策段被 `--append-system-prompt` 覆盖时，政策消失：已定「用户自担」，不强行拼接。
- 总步数上限 8×32=256 是否可接受：已定「部署可配」，本 change 不改默认值。
- 政策段是否也进子代理会话：已定「进」——文本用条件句「若你有 `create_goal` 工具」，避免误导。
