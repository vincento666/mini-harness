# Spec Delta: goal

## MODIFIED Requirements

### Requirement: 轮次驱动与上限

一轮结束且 `turn/end.stop_reason` 不在 `{ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED}` 之内时，系统 SHALL 检查当前目标：`phase == active`、`armed` 为真、`rounds_started < max_rounds` 三者同时成立才 SHALL 开新轮，并按顺序写 `turn/start`、goal 来源的 `user/message`、该轮首条 `context/assembled`、`goal/updated`（`rounds_started` 递增，`revision` 不变）。三者任一不成立 MUST NOT 开新轮。

`MAX_STEPS` MUST NOT 阻止续轮：它表示**本轮步数用尽**，不是任务失败；模型与工具都可能完全正常。只有 `ABORTED`、`FENCE_DENIED`、`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED` 四类收尾才 MUST NOT 自动续轮。没有可续的目标时，`MAX_STEPS` 仍按普通收尾停住（没有目标就没有下一轮）。

`rounds_started` 是**当前 goal 轮次的序号**：goal 消息被准入（`context/assembled` 落盘）之后它就是本轮的 n；人类轮的 `user/message` MUST NOT 推进它。`max_rounds` 是**单个目标**的轮次上限，不是会话的轮数上限。`max_rounds` 由 CLI 的 `minihns goal <id> edit --max-rounds` 或模型的 `update_goal edit` 改写；会话内的 `/goal edit` 只改正文。

goal 轮次以零个成功派发的工具调用收尾（模型只说话、没有动作）时，系统 SHALL 累加「连续空转轮数」；连续轮数达到 `[goal] stall_rounds` 时 SHALL 解除武装、MUST NOT 开下一轮，`phase` MUST 保持不变（完成与否不是驱动能替模型判断的事实）。`stall_rounds` 缺省为 `2`：一轮可能只是「想清楚再答」，连续两轮才判死循环；配置 `0` 表示关闭该闸门（完全对齐 DSH，只由 `complete` / `blocked` / `max_rounds` 决定）。任何有工具调用的 goal 轮次把计数清零；人类轮 MUST NOT 受这条约束，并把计数清零。判据单位是**轮**（一次准入），不是步；一轮里只要有一个成功派发的工具调用就不算空转。

轮次额度 SHALL 在**首条 `context/assembled` 落盘之后**消耗：该轮真的装进了上下文才算数；该轮在装配完成之前失败（provider 立刻失败、注入失败、折叠失败、装配内压缩失败）MUST NOT 计入 `rounds_started`——这是 DSH「进模型历史才计数」在 mini 的等价物。

`rounds_started` 已达 `max_rounds` 时，系统 SHALL 写 `goal/updated` 把 `phase` 置 `blocked`、`blocked_reason.code` 置 `round-limit`，并 MUST NOT 再起轮次。

写日志失败时 MUST NOT 静默重试：落 `error/*`、结束会话、以非零退出码收尾。

一轮以 `ABORTED` 收尾时，系统 SHALL 把 `phase` 置 `paused` 并解除武装；以其余三类失败收尾时 SHALL 只解除武装（`phase` 保持，等人 `/goal resume`）。

#### Scenario: 人类轮写满步数后目标轮接上

- **WHEN** 一条人类输入建了 `active` 目标，该轮在第 `max_steps` 步以 `MAX_STEPS` 收尾
- **THEN** 日志出现 goal 来源的 `user/message` 与新的 `turn/start`，`rounds_started` 从 0 变为 1；该轮不是失败收尾，武装位保持

#### Scenario: 目标轮写满步数后继续下一轮

- **WHEN** 一个 goal 轮次在第 `max_steps` 步以 `MAX_STEPS` 收尾，且 `rounds_started < max_rounds`
- **THEN** 系统开下一轮，`rounds_started` 递增；`turn/end.stop_reason` 仍记为 `MAX_STEPS`

#### Scenario: 额度用尽时写满不再续

- **WHEN** `rounds_started == max_rounds`，该轮以 `MAX_STEPS` 收尾
- **THEN** 系统写 `blocked`（`round-limit`），不再开轮

#### Scenario: 没有目标时写满就停

- **WHEN** 会话里没有目标，或目标不是 `active`，一轮以 `MAX_STEPS` 收尾
- **THEN** 不开新轮，行为与加这个能力之前相同

#### Scenario: 四类失败仍不续

- **WHEN** 一轮以 `ABORTED`、`FENCE_DENIED`、`PROVIDER_ERROR` 或 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 系统不开新轮；`ABORTED` 另把 `active` 目标置 `paused`，其余三类只解除武装
