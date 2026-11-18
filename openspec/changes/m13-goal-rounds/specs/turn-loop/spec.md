# Spec Delta: turn-loop

## ADDED Requirements

### Requirement: 段结束后按目标条件续跑

每个 `segment/end` 之后，系统 SHALL 判定是否续跑，判定只看当前目标快照与本次段的 `stop_reason`：`phase == "active"`、`armed` 为真、`rounds_started < max_rounds`、且 `stop_reason` 不在 `{ABORTED, FENCE_DENIED, PROVIDER_ERROR, CONTEXT_WINDOW_EXCEEDED, MAX_TURNS}` 之内时，SHALL 开新段；否则 MUST NOT 开新段。

开新段时，系统 SHALL 按固定顺序写：`segment/start`、goal 来源的 `user/message`（`source.round` 等于快照的 `rounds_started + 1`）、首条 `turn/start`、`goal/updated`（`rounds_started` 递增，`revision` 不变）。

轮次额度在首条 `turn/start` 落盘后消耗；该段在此之前失败 MUST NOT 计入。写日志失败 SHALL 落 `error/*` 并终止会话，MUST NOT 静默重试。

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

## MODIFIED Requirements

### Requirement: 一条输入开一个段，段的边界在日志里

系统 SHALL 把一条输入（一次性 `run` 与 `serve` 的 prompt、REPL 的一条输入）展开成一个**段**，并把段的边界 durable 写进日志：段开始时写 `segment/start`（payload 含 `segment_id`），段结束时写 `segment/end`（payload 含 `segment_id`、该段最后一个回合的 `stop_reason`、该段实际跑掉的回合数 `turns`）。`segment_id` 在会话内连续编号（`s1`、`s2`…）且 MUST NOT 重复。`segment/*` MUST NOT 产出上下文里的消息。照 DSH：段的边界对应 DSH 的 `turn` 边界（`turn = phase.turn + 1` 后 `session.append("turn/start", {turn})`，编号单调且落日志），本项目的「回合」仍是 DSH 的 `step`（GLOSSARY）。

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
