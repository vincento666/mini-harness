## MODIFIED Requirements

### Requirement: 预算读数有两个来源
系统 SHALL 把一次装配的预算读数定义为两者中较大的一个：本次折叠上下文的估算 token 数（每条消息的 `content` 与 `tool_calls` 文本长度之和除以 4、向上取整后逐条相加），与该日志前缀里**未被遮蔽**、`purpose` 不是 `compaction`、且 `seq` 大于该点之前最后一条 `compaction/summary` 的 `seq` 的 `model/response` 的 `usage.input_tokens` 的最大值；该点之前没有任何 `compaction/summary` 时不设这条 `seq` 界。一条回报描述的是产生它的那次请求：一次压缩之后，压缩之前那次请求的回报 MUST NOT 继续充当压缩之后的表层读数。读数 MUST NOT 依赖进程内缓存或该点之后的事件。

#### Scenario: provider 回报的读数比估算大时用它
- **WHEN** 某回合之前的 `model/response` 里 `usage.input_tokens` 大于同一份上下文的估算值
- **THEN** 该回合的预算读数是那个回报值，判定用它

#### Scenario: 被遮蔽的读数不参与校准
- **WHEN** 一条回报过 `input_tokens` 的 `model/response` 落在遮蔽范围里
- **THEN** 之后每一次装配的预算读数都不用它

#### Scenario: 摘要调用的读数不参与校准
- **WHEN** 一次压缩的 `model/response`（`purpose` 为 `compaction`）回报的 `input_tokens` 远大于压缩后的上下文
- **THEN** 之后每一次装配的预算读数都不用它，只用回合级回复的回报值与当前估算

#### Scenario: 没有回报时只有估算
- **WHEN** 一次 mock run 的日志里没有任何 `usage.input_tokens` 大于 0 的记录
- **THEN** 预算读数等于估算值，判定用它

#### Scenario: 同一份前缀两次读数相同
- **WHEN** 对同一份日志前缀连续计算两次预算读数
- **THEN** 两次读数完全相等

#### Scenario: 压缩之前的回报不充当压缩之后的读数
- **WHEN** 一条 `model/response` 的 `usage.input_tokens` 大于压缩之后折叠上下文的估算，而它的 `seq` 小于该装配点之前最后一条 `compaction/summary` 的 `seq`
- **THEN** 该装配点的预算读数是那个估算值，不用那条回报——即使那条记录没有被遮蔽、留在保留尾部里

#### Scenario: 压缩之后新的回报重新参与校准
- **WHEN** 一次压缩之后写出的回合级 `model/response` 回报的 `input_tokens` 大于当时的估算
- **THEN** 之后每一次装配的预算读数用这个新回报，它不受上面那条界影响（它的 `seq` 在那条 `compaction/summary` 之后）

#### Scenario: 遮蔽之后的读数低于遮蔽之前
- **WHEN** 一次压缩遮蔽掉的那段折出的消息估算大于那条摘要自身的估算
- **THEN** 那条 `compaction/summary` 的 `tokens_after` 小于 `tokens_before`
