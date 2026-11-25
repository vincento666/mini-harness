# Spec Delta: turn-loop

## ADDED Requirements

### Requirement: 段结束后按目标条件续跑

每个 `segment/end` 之后，系统 SHALL 判定是否续跑，判定只看当前目标快照、本次段的 `stop_reason` 与本段是否产生过工具调用：`phase == "active"`、`armed` 为真、`rounds_started < max_rounds`、`stop_reason` 不在 `{ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED, MAX_TURNS}` 之内，且（人类段或本段至少有一个工具调用）时，SHALL 开新段；否则 MUST NOT 开新段。段尾仍有未决问题时 SHALL 回到入口等待人类输入，MUST NOT 开自动轮次。

开新段时，系统 SHALL 按固定顺序写：`segment/start`、goal 来源的 `user/message`（`source.round` 等于快照的 `rounds_started + 1`）、首条 `turn/start`、首条 `context/assembled`、`goal/updated`（`rounds_started` 递增，`revision` 不变）。

轮次额度在首条 `context/assembled` 落盘后消耗；装配完成之前失败 MUST NOT 计入。写日志失败 SHALL 落 `error/*` 并终止会话，MUST NOT 静默重试。

`rounds_started` 已达 `max_rounds` 时，系统 SHALL 写 `goal/updated` 把 `phase` 置 `blocked`、`blocked_reason.code` 置 `round-limit`，并 MUST NOT 开新段。

#### Scenario: 达标即续跑

- **WHEN** 段以 `MODEL_COMPLETED` 收尾，目标 `active`、已武装、`rounds_started == 1`、`max_rounds == 3`
- **THEN** 日志出现 `segment/start`（新 `segment_id`）、`source.round == 2` 的 `user/message`、`rounds_started == 2` 的 `goal/updated`，顺序与这里一致，且 `revision` 与上一轮相同

#### Scenario: 上限不再开段

- **WHEN** `rounds_started == max_rounds` 且目标仍 `active`
- **THEN** 不出现新的 `segment/start`，出现一条 `goal/updated`：`phase == "blocked"`、`blocked_reason.code == "round-limit"`

#### Scenario: 失败收尾不续跑

- **WHEN** 段以 `CONTEXT_WINDOW_EXCEEDED` 或 `MAX_TURNS` 收尾
- **THEN** 不出现新的段、不出现 goal 来源消息、不出现 `goal/updated`

#### Scenario: 重放相等

- **WHEN** 对一份含三轮续跑的日志执行 `replay`
- **THEN** 折叠结果与写入时逐点相等，轮号序列不变

### Requirement: 段后收尾只有一份实现

`run` / `chat` / `host` 三个入口 MUST 调同一个段后收尾实现（读目标 → 判下一轮 → 落额度/停滞/失败收尾），MUST NOT 各自复制一份判定。入口之间的差别只允许在「谁来提供下一条输入」：`run` 没有输入、`chat` 回到提示符、`host` 从待跑队列取。

#### Scenario: host 也自动续跑

- **WHEN** host 会话里的人类段建了一个 `active` 目标并正常收尾
- **THEN** 日志出现 goal 来源的下一段，不需要再来一条 `POST /messages`

#### Scenario: 三个入口的判定一致

- **WHEN** 同一份目标状态与同一个 `stop_reason` 分别交给三个入口
- **THEN** 是否开下一段的结论相同；差异只在下一段由谁触发

## MODIFIED Requirements

### Requirement: 一条输入开一个段，段的边界在日志里

系统 SHALL 把一条输入（一次性 `run` 与 `serve` 的 prompt、REPL 的一条输入）展开成一个**段**，并把段的边界 durable 写进日志：段开始时写 `segment/start`（payload 含 `segment_id`），段结束时写 `segment/end`（payload 含 `segment_id`、该段最后一个回合的 `stop_reason`、该段实际跑掉的回合数 `turns`、该段真正派发过的工具调用数 `tool_calls`）。`tool_calls` 是驱动的停滞判据（零调用 = 空转），MUST 在收尾时落盘，方便审计与回放读。`segment_id` 在会话内连续编号（`s1`、`s2`…）且 MUST NOT 重复。`segment/*` MUST NOT 产出上下文里的消息。照 DSH：段的边界对应 DSH 的 `turn` 边界（`turn = phase.turn + 1` 后 `session.append("turn/start", {turn})`，编号单调且落日志），本项目的「回合」仍是 DSH 的 `step`（GLOSSARY）。

一次性入口（`run` / `serve`）的段数 SHALL 由目标轮次决定：没有目标续跑时恰有一个段；有目标续跑时每轮一段，段数等于「一加起的轮次数」。REPL 的每个段仍由一条输入或一轮目标驱动。

#### Scenario: 一次 run 恰一个段

- **WHEN** 一次 run 跑了一个回合就正常结束，且会话里没有可续跑的目标
- **THEN** 日志的类型序列是 `session/start`、`segment/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`segment/end`、`session/end`，`segment/end` 的 `stop_reason` 是 `MODEL_COMPLETED`、`turns` 为 1

#### Scenario: 有目标续跑时 run 有多个段

- **WHEN** 一次 run 里目标续了两轮，随后撞上轮次上限
- **THEN** 日志里有三个段（`s1`、`s2`、`s3`），每个段各有配对的 `segment/start` 与 `segment/end`，最后一段的 `stop_reason` 是 `MODEL_COMPLETED`

#### Scenario: 段编号在会话内连续

- **WHEN** 一次 chat 跑两个段
- **THEN** 日志里恰有 `s1` 与 `s2` 各一条 `segment/start` 与一条 `segment/end`，没有第三个段编号

#### Scenario: 段级取消段的边界也写

- **WHEN** 一个段进行中收到取消信号
- **THEN** 日志里有 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `segment/end`（`stop_reason: ABORTED`），没有 `session/end`

### Requirement: 回合数上限由 --max-turns 决定

系统 SHALL 用 `--max-turns` 限制**一个段**的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。会话级 MUST NOT 设回合数上限：会话的段数由目标轮次决定（没有目标续跑时恰一个段；有则每轮一段），`minihns chat` 里每条输入或每一轮是一个段，段用完上限 MUST NOT 结束会话（见 `chat-repl`）。目标的轮数上限是 `max_rounds`，与这里的 `max_turns` 是两个量，MUST NOT 混名。

#### Scenario: 非法 max-turns 不产生日志

- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 上限判的是段不是会话

- **WHEN** 一次 chat 的第一条输入用完 `max_turns = 2`
- **THEN** 该段的 `segment/end` 的 `stop_reason` 是 `MAX_TURNS`、`turns` 为 2，日志里没有 `session/end`，下一条输入开一个新的段并照样有 2 个回合的额度

#### Scenario: 段额度不随目标轮次累计

- **WHEN** 目标连跑三轮，`max_turns = 2`
- **THEN** 每个段各自最多两个回合，第三段的 `turns` 不从前面累加
