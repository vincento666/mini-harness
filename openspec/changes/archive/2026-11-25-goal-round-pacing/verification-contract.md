# 验证契约

**日期**：2026-11-25（第三版：按两轴 code review 修 F1–F7——政策升 `v2` 补停滞条件与条件句、早失败场景改成可达形态并补判据、补「不可由配置/flag 覆盖」判据）。

## 目标

让「一轮把步数写满」只结束这一轮、不杀死长任务；同时让模型从会话开头就知道轮/步与目标轮的存在，且这条政策不能被调用方关掉。

## 可观察行为

1. **人类轮写满，目标轮接上**：一条人类输入建了目标后，在同轮第 `max_steps` 步收尾 → 日志出现 goal 消息与新 `turn/start`，`rounds_started` 从 0 变 1（seam：驱动判定 → 入口续轮）。
2. **目标轮写满，继续下一轮**：goal 轮以 `MAX_STEPS` 收尾且还有额度 → 开下一轮，`stop_reason` 仍记 `MAX_STEPS`（seam：驱动判定）。
3. **没有目标就照旧停**：无目标或非 `active` 时 `MAX_STEPS` 不开新轮（seam：驱动判定）。
4. **四类失败仍不续**：`ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` 都不自动续；`ABORTED` 另把目标置 `paused`（seam：失败收尾）。
5. **政策段不可覆盖**：新会话 `session/start.goal_policy == "v2"`，首条 `context/assembled` 头部含政策（含停滞条件与条件句）；`--append-system-prompt` 只追加在政策之后；配置键与 flag 都改不了它；旧版本按原文本重算（seam：系统提示装配）。
6. **装配前失败不扣轮次**：目标轮的 `turn/start` 与 goal 消息已写，但首条 `context/assembled` 没写成（预算超线等）→ 该轮不写 `goal/updated`，`rounds_started` 不变（seam：轮次推进）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | 驱动单测：`next_round(goal=active, armed=True, stop_reason="MAX_STEPS")` 返回 `continue`（`test_the_round_decision_only_looks_at_the_snapshot_the_arm_and_the_stop_reason`） |
| 1 | 黑盒：人类轮 `max_steps=2` 写满、目标 active → 日志有 goal 来源 `user/message`，`rounds_started` 递增，后续 `turn/start` 存在（`test_max_steps_is_a_round_boundary_and_the_cap_still_stops`） |
| 2 | 黑盒：目标轮 `max_steps=2` 写满、`max_rounds=2` → 共三轮；三条 `turn/end` 的 `stop_reason` 都是 `MAX_STEPS`（同上） |
| 3 | 单测：`next_round(goal=None, armed=True, stop_reason="MAX_STEPS")` 返回 `stop`；`goal` 为 `paused` 同样 `stop`（`test_without_a_goal_max_steps_still_stops`） |
| 4 | 单测（纯函数）：`next_round` 对四个失败理由各一次 → 全部 `stop`（`test_the_round_decision_only_looks_at_the_snapshot_the_arm_and_the_stop_reason`） |
| 4 | 单测（经 `settle_turn`）：`ABORTED` → `phase == "paused"` 且 `armed == false`（`test_a_cancelled_round_pauses_the_goal_and_disarms_it`）；`PROVIDER_ERROR` → `phase` 不变且 `armed == false`（`test_a_provider_error_keeps_the_goal_active_but_disarmed`）；`FENCE_DENIED` / `CONTEXT_WINDOW_EXCEEDED` 同样只解武装（`test_fence_and_overflow_disarm_without_pausing`） |
| 4 | 单测（经 `settle_turn`）：`MAX_STEPS` → 结论 `continue`、武装位保持、`rounds_started` 不变（`test_max_steps_keeps_the_goal_armed_through_settle_turn`） |
| 5 | 端到端：新会话 → `session/start.goal_policy == GOAL_POLICY_VERSION`；首条 `context/assembled.messages[0].content` 以 `SYSTEM_PROMPT` 开头、含「写满」与「若你有 update_goal 工具」（`test_a_new_session_carries_the_goal_policy`） |
| 5 | 单测：`--append-system-prompt "额外规则"` → 头部顺序是 `SYSTEM_PROMPT` → 政策段 → `额外规则`；政策段仍在（`test_the_append_prompt_comes_after_the_goal_policy`） |
| 5 | 单测：`GOAL_POLICY_VERSION` 必须命中 `GOAL_POLICY_VERSIONS`（`test_the_current_policy_version_has_a_text`） |
| 5 | 单测：`v1` 日志仍注入 `v1` 原文、不含 `v2` 才有的条件句（`test_an_old_v1_log_still_injects_the_old_text`）；`v1` 生成的会话 `replay` 退 0、无 `REPLAY_MISMATCH`（`test_replay_of_a_log_with_the_goal_policy_still_verifies`） |
| 5 | 单测：改 `GOAL_POLICY_VERSIONS["v1"]` 的文本但不升版本 → 同一份合成日志重算与记录不一致（`test_changing_the_policy_text_without_a_new_version_breaks_replay`） |
| 5 | 黑盒：配置文件写 `goal_policy = "off"` → `INVALID_ARGUMENT`、无日志文件（`test_the_goal_policy_is_not_a_config_key`）；`--goal-policy off` → `unrecognized arguments`、无日志文件（`test_the_goal_policy_is_not_a_cli_flag`） |
| 5 | 单测：政策文本提到停滞闸门（`test_the_goal_policy_mentions_the_stall_gate`）；目标轮正文不写死「连续两轮」而说「停滞阈值」（`test_the_goal_round_text_does_not_hardcode_the_stall_threshold`） |
| 6 | 黑盒：极小窗口下首步装配前超线 → `CONTEXT_WINDOW_EXCEEDED`、本轮无 `context/assembled`、`rounds_started` 仍为 0（`test_an_assembly_overflow_before_context_assembled_keeps_the_round_count`） |

## 坏法清单（变异种子）

1. **只改文档不改集合**：`NO_CONTINUE_REASONS` 里留着 `MAX_STEPS` → 行为 1、2 的判据红。
2. **顺手删多了**：把 `ABORTED` 也从集合里删掉 → 行为 4 的取消判据红（取消后自动续轮）。
3. **无目标也续**：`next_round` 不看 `goal is None` → 行为 3 红。
4. **政策段只在 `create_goal` 之后拼**：`session/start` 没有 `goal_policy` → 行为 5 第 1 条红。
5. **政策段写进 `SYSTEM_PROMPT` 常量**：合成旧日志 replay 红（行为 5 第 3 条）。
6. **政策段可被 append 覆盖**：实现成「有 append 就不加政策」→ 行为 5 第 2 条红。
7. **文本与版本没绑定**：改文本不升版本 → 行为 5 第 4 条红。
8. **轮次提前扣**：把 `advance_round` 的写入挪到 `context/assembled` 之前（或装配前单独写）→ 行为 6 红。
9. **政策漏掉停滞**：文本只列四条续跑条件 → 行为 5 最后的政策文案判据红。
10. **给配置开口子**：把 `goal_policy` 加进配置白名单 → 行为 5 的配置判据红。

## 不验什么

- 不验模型是否真的「按轮写」：模型策略不是运行时能保证的；本 change 只保证「写满不会死」与「模型看得到规则」。
- 不做 L1（工具描述条件句）与 L2（`create_goal` 后硬停）——DSH 无对照，按对齐纪律不做。
- 不做 L4（轮内工作量预算）：另开 `goal-round-budget`。
- 不实测 token 成本，只记录上限从 `max_steps` 变为 `max_steps × max_rounds`。
- 不评政策段文案的优劣，只断言关键词、条件句与位置；文案可迭代，改文案必须升版本。
- 不改 `turn/end` 词表、`max_steps`、`max_rounds` 的默认值。
- 不验政策段对子代理的适用性：所有会话都注入，文本用「若你有 `create_goal` / `update_goal` 工具」的条件句；不单独做子代理继承判据。

## 待裁决

- 总步数上限：目标轮最多 `8×32=256` 步，另加人类首轮的 8 步，共 264 步；已定「部署可配」，本 change 不改默认值。
- 政策段没有关闭面（配置与 flag 都不能关）：已定，这是「不可覆盖」的代价。
- 政策段也进子代理会话：已定，文本用条件句避免误导。
- UAT 由人授权代跑（2026-11-25），场次 4 降级为单测覆盖：已记在 `goal-round-pacing-uat.md`，归档时确认。
