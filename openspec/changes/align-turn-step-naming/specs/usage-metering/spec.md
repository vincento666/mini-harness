# Spec Delta: usage-metering

## MODIFIED Requirements

### Requirement: 回合与会话的 token 四桶计量

系统 SHALL 从日志里每个 `model/response` 的 `usage` 聚合四个互不重叠的 bucket：`input_uncached`、`cache_read`、`cache_write`、`output`。`reasoning` 是 `output` 的细分，MUST NOT 再加一次。缺 `usage` 的步 SHALL 跳过，MUST NOT 用估算值代替。

会话总量 SHALL 是各步的求和；同一步的最终 assistant 消息用量 SHALL 替换该样本，MUST NOT 重复计数。

#### Scenario: 四桶求和

- **WHEN** 两个步分别报告 `input 100 / cache_read 20 / output 30` 与 `input 50 / output 10`
- **THEN** 会话总量是 `input_uncached 150 / cache_read 20 / cache_write 0 / output 40`

#### Scenario: reasoning 不加两次

- **WHEN** 某步 `output` 为 30、其中 `reasoning` 为 12
- **THEN** 总量只加 30，不是 42

#### Scenario: 缺 usage 的步跳过

- **WHEN** 某步的 `model/response` 没有 `usage`
- **THEN** 该步不出现在 `steps[]` 里，也不影响总量

### Requirement: `minihns usage` 的输出

系统 SHALL 提供 `minihns usage <session-id>`，输出 JSON：`steps[]`（每步的 `step_id` 与四桶）、`total`（四桶之和）、`cost`（可为 `null`）。命令 MUST NOT 修改日志。

`steps[]` 的单位是**步**（一次模型往返）：一轮里跑了几步就有几项，`step_id` 与日志 `model/response` 的 `step_id` 同值。旧键 `turns[]` / `turn_id` MUST NOT 再出现——它们把步的用量记在轮的层级下，会让「一轮两步」看起来像「两轮」。

#### Scenario: 输出可被 E1 消费

- **WHEN** 对一个含两步用量的会话跑 `minihns usage`
- **THEN** stdout 是合法 JSON，恰好含 `steps`、`total`、`cost` 三个顶层键，且 `steps[]` 每项带 `step_id`

#### Scenario: 一轮两步是两项

- **WHEN** 对一份 `turn/start` 一次、`step/start` 两次的会话跑 `minihns usage`
- **THEN** `steps[]` 有两项、`step_id` 分别是那两步的 id，`total` 是两者之和
