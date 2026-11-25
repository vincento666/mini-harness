# Spec Delta: turn-loop

## ADDED Requirements

### Requirement: 三层时间词与事件名按 DSH 对齐

系统 SHALL 使用 `turn` 表示一条输入展开的那串 `step`，使用 `step` 表示一次「装配 → 调模型 → 派发」；`turn` 等价于 DSH 的 turn，`step` 等价于 DSH 的 step。目标轮（goal round）是一次 goal 来源的 `turn`，`rounds_started` 数它。

日志事件名 SHALL 为 `turn/start`、`turn/end`（轮的边界）与 `step/start`、`step/end`（步的边界）；`turn/start` 的载荷含 `turn_id`，`step/start` 与步内事件含 `step_id`。原 `segment/*` 与旧语义的 `turn/*` MUST NOT 出现在新日志里；读取 v1 日志时按 `event-log` 的版本门拒绝（`SCHEMA_UNSUPPORTED`），不尝试猜它的新名字。

实现标识符 SHALL 同步改名：`SegmentOutcome → TurnOutcome`、`run_turn_segment → run_turn`、`RunOutcome.turns → steps`、`first_turn_index → first_step_index`、`TurnDeltaSink → StepDeltaSink`。行为、事件顺序、额度与退出码 MUST NOT 因改名改变。

#### Scenario: 轮的边界与步的边界可区分

- **WHEN** 一次 run 的一条输入展开两个步
- **THEN** 日志里恰有一条 `turn/start`、两条 `step/start`、两条 `step/end`、一条 `turn/end`；`turn/end` 在最后一个 `step/end` 之后

#### Scenario: 目标轮就是一次 turn

- **WHEN** 一个上限为 2 的目标连跑两轮
- **THEN** 日志里有三条 turn（人类首轮加两个目标轮）；两条 goal 来源的 `user/message` 各自落在一条 `turn/start` 之后，`rounds_started` 为 2

#### Scenario: 旧日志被版本门拒绝

- **WHEN** 读取一份 `schema_version == 1` 的日志
- **THEN** 以 `SCHEMA_UNSUPPORTED` 失败，不产出投影、不改写文件
