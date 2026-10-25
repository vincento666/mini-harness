# Spec Delta

## ADDED Requirements

### Requirement: 摘要请求只装本次要遮蔽的那一段
生成摘要的那次模型调用 SHALL 只携带三类消息：折叠派生的系统消息、本次遮蔽范围（`shadowed_range` 给出的 seq 闭区间）折出的消息、以及作为最后一条的摘要指令。该调用 MUST NOT 携带落在遮蔽范围之外的对话消息，也 MUST NOT 携带保留尾部。该调用携带的全部消息按既有的估算 SHALL NOT 超过「窗口减保留额」这份预算：超过时系统 SHALL 从该范围的头部按工具往返整对丢弃直到装得下——带调用的那条 assistant 与回答它的 tool 消息 MUST NOT 被拆散。一条都装不下时 SHALL NOT 发出该调用。

#### Scenario: 保留尾部不进摘要请求
- **WHEN** 一次装配越线并发出了摘要调用
- **THEN** 该调用收到的消息里，除系统消息与最后一条摘要指令外，每一条都来自本次 `compaction/summary.payload.shadowed_range` 之内；保留尾部的那段消息不在其中

#### Scenario: 摘要请求本身不越线
- **WHEN** 一次装配越线并发出了摘要调用
- **THEN** 该调用携带的全部消息按既有的估算不超过「窗口减保留额」

#### Scenario: 裁剪不拆散工具往返
- **WHEN** 遮蔽范围折出的消息超过「窗口减保留额」，裁剪从该范围头部丢掉一组工具往返
- **THEN** 该调用收到的消息里每一条 tool 消息之前都有一条带对应 `tool_call_id` 的 assistant 请求

#### Scenario: 一段都装不下时不发请求
- **WHEN** 遮蔽范围折出的消息加摘要指令即使裁到只剩一条也超过「窗口减保留额」
- **THEN** 日志里没有带 `purpose: compaction` 的 `model/request`，该回合以 `error/context`（`code: CONTEXT_WINDOW_EXCEEDED`）与 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）收尾

## MODIFIED Requirements

### Requirement: 摘要调用失败沿用 provider 失败结果
生成摘要的那次模型调用失败时，系统 SHALL 沿用既有的 provider 失败形状：写 `error/model`（含 `code`）与 `turn/end`（`stop_reason: PROVIDER_ERROR`）。`session/end` 与退出码由入口决定：一次性 `minihns run` 写 `session/end` 并以退出码 1 结束，`minihns chat` 里这是段级收尾（见 `turn-loop` 的「Provider 失败是回合终止结果」）。此时 MUST NOT 写 `compaction/summary`，也 MUST NOT 产出 `CONTEXT_WINDOW_EXCEEDED`。摘要调用**没有发出**时不是 provider 失败：那条路通向 `CONTEXT_WINDOW_EXCEEDED`（见「摘要请求只装本次要遮蔽的那一段」），此时 MUST NOT 写 `error/model`。

#### Scenario: fixture 里没有摘要回复
- **WHEN** 一次性 run 里装配越线但 fixture 的回复条目已耗尽
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1，且日志里没有任何 `compaction/summary`

#### Scenario: 没发出的摘要调用不产生 provider 失败
- **WHEN** 装配越线但遮蔽范围裁到最小仍装不下
- **THEN** 日志里没有 `error/model`、没有带 `purpose: compaction` 的 `model/request`，该回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED`
