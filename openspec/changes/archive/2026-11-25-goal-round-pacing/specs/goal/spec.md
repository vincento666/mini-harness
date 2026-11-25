# Spec Delta: goal

## MODIFIED Requirements

### Requirement: 轮次驱动与上限

一轮结束且 `turn/end.stop_reason` 不在 `{ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED}` 之内时，系统 SHALL 检查当前目标：`phase == active`、`armed` 为真、`rounds_started < max_rounds` 三者同时成立才 SHALL 开新轮，并按顺序写 `turn/start`、goal 来源的 `user/message`、该轮首条 `step/start`、该轮首条 `context/assembled`、`goal/updated`（`rounds_started` 递增，`revision` 不变）。三者任一不成立 MUST NOT 开新轮。

`MAX_STEPS` MUST NOT 阻止续轮：它表示**本轮步数用尽**，不是任务失败；模型与工具都可能完全正常。只有 `ABORTED`、`FENCE_DENIED`、`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED` 四类收尾才 MUST NOT 自动续轮。没有可续的目标时，`MAX_STEPS` 仍按普通收尾停住（没有目标就没有下一轮）。

`rounds_started` 是**当前 goal 轮次的序号**：goal 消息被准入（`context/assembled` 落盘）之后它就是本轮的 n；人类轮的 `user/message` MUST NOT 推进它。`max_rounds` 是**单个目标**的轮次上限，不是会话的轮数上限。`max_rounds` 由 CLI 的 `minihns goal <id> edit --max-rounds` 或模型的 `update_goal edit` 改写；会话内的 `/goal edit` 只改正文。

goal 轮次以零个成功派发的工具调用收尾（模型只说话、没有动作）时，系统 SHALL 累加「连续空转轮数」；连续轮数达到 `[goal] stall_rounds` 时 SHALL 解除武装、MUST NOT 开下一轮，`phase` MUST 保持不变（完成与否不是驱动能替模型判断的事实）。`stall_rounds` 缺省为 `2`：一轮可能只是「想清楚再答」，连续两轮才判死循环；配置 `0` 表示关闭该闸门（完全对齐 DSH，只由 `complete` / `blocked` / `max_rounds` 决定）。任何有工具调用的 goal 轮次把计数清零；人类轮 MUST NOT 受这条约束，并把计数清零。判据单位是**轮**（一次准入），不是步；一轮里只要有一个成功派发的工具调用就不算空转。

轮次额度 SHALL 在**首条 `context/assembled` 落盘之后**消耗：该轮真的装进了上下文才算数；该轮在装配完成之前失败（provider 立刻失败、注入失败、折叠失败、装配内压缩失败）MUST NOT 计入 `rounds_started`——这是 DSH「进模型历史才计数」在 mini 的等价物。

`rounds_started` 已达 `max_rounds` 时，系统 SHALL 写 `goal/updated` 把 `phase` 置 `blocked`、`blocked_reason.code` 置 `round-limit`，并 MUST NOT 再起轮次。

写日志失败时 MUST NOT 静默重试：落 `error/*`、结束会话、以非零退出码收尾。

一轮以 `ABORTED` 收尾时，系统 SHALL 把 `phase` 置 `paused` 并解除武装；以其余三类失败收尾时 SHALL 只解除武装（`phase` 保持，等人 `/goal resume`）。

#### Scenario: 达标即续跑

- **WHEN** 一轮以 `MODEL_COMPLETED` 收尾，目标 `active`、已武装、`rounds_started == 1`、`max_rounds == 3`
- **THEN** 日志依次出现 `turn/start`（新 `turn_id`）、`source.round == 2` 的 `user/message`、`step/start`、`context/assembled`、`rounds_started == 2` 的 `goal/updated`

#### Scenario: 人类轮写满步数后目标轮接上

- **WHEN** 一条人类输入建了 `active` 目标，该轮在第 `max_steps` 步以 `MAX_STEPS` 收尾
- **THEN** 日志出现 goal 来源的 `user/message` 与新的 `turn/start`，`rounds_started` 从 0 变为 1；该轮不是失败收尾，武装位保持

#### Scenario: 目标轮写满步数后继续下一轮

- **WHEN** 一个 goal 轮次在第 `max_steps` 步以 `MAX_STEPS` 收尾，且 `rounds_started < max_rounds`
- **THEN** 系统开下一轮，`rounds_started` 递增；`turn/end.stop_reason` 仍记为 `MAX_STEPS`

#### Scenario: 没有目标时写满就停

- **WHEN** 会话里没有目标，或目标不是 `active`，一轮以 `MAX_STEPS` 收尾
- **THEN** 不开新轮，行为与加这个能力之前相同

#### Scenario: 一轮空转不误杀

- **WHEN** 一个 goal 轮次零工具调用，上一轮有工具调用（计数从 0 起），目标仍 `active`、已武装、还有额度
- **THEN** 驱动照常开下一轮；`turn/end.tool_calls == 0` 只作审计

#### Scenario: 连续两轮空转按默认阈值停

- **WHEN** `[goal]` 没有 `stall_rounds`（缺省 2），连续两个 goal 轮次零工具调用
- **THEN** 第二个轮次之后不再开轮、武装位解除、`phase` 仍 `active`、计数清零；下一次 `/goal resume` 从零重新计

#### Scenario: 关闭闸门就完全对齐 DSH

- **WHEN** `[goal] stall_rounds = 0`，goal 轮次连续空转
- **THEN** 驱动一路开到 `max_rounds`，最后落 `blocked{round-limit}`，不因空转提前停

#### Scenario: 上限不再开轮

- **WHEN** `rounds_started == max_rounds` 且目标仍 `active`
- **THEN** 不出现新的 `turn/start`，出现一条 `goal/updated`：`phase == "blocked"`、`blocked_reason.code == "round-limit"`

#### Scenario: 早失败不消耗轮次

- **WHEN** 第 2 轮的 `turn/start` 与 goal 消息已写，首条 `context/assembled` 落盘之前装配失败（预算超线、契约或工具目录写失败）
- **THEN** `rounds_started` 仍为 1（这一轮不算数），这一轮的 `goal/updated` 不出现；且不再自动续跑

#### Scenario: 取消把目标置暂停

- **WHEN** 第 2 轮进行中被取消，轮以 `ABORTED` 收尾
- **THEN** 日志新增 `goal/updated`：`phase == "paused"`；`get_goal()` 的 `armed == false`

#### Scenario: 失败收尾解除武装

- **WHEN** 一轮以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 不出现新的轮、不出现 goal 来源消息；`get_goal()` 的 `armed == false`

#### Scenario: 写不进日志就停

- **WHEN** 续跑要写的 `goal/updated` 落盘失败
- **THEN** 不出现新的轮，日志里留下 `error/*`，命令以非零码结束
