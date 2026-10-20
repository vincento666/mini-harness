# Spec Delta

## MODIFIED Requirements

### Requirement: 用户取消是 ABORTED 结果
当运行期间收到取消信号时，系统 SHALL 终止**当前回合**而不是整批派发：已开始执行的调用被打断并塌成 `TOOL_CANCELLED`（配一条 `tool/cancelled`），尚未派发的每一个声明调用 SHALL 写一条 `tool/call` 与配对的 `tool/result`（`outcome: ABORTED_BEFORE_DISPATCH`）；随后写 `error/abort`（含 `turn_id` 与 `code: ABORTED`）与 `turn/end`（`stop_reason: ABORTED`）。内核 MUST NOT 把「会话是否结束」写进回合语义：`session/end` 仍由内核在回合闭合后写出，一次性 `minihns run` 的入口据此以退出码 5 结束；会话是否继续由**入口策略**决定，REPL 与端点里会话继续归 M6 / M7（ADR-0011）。取消与围栏拒绝同时在场时取消优先到底——收尾理由是 `ABORTED`，围栏拒绝的事实留在 `error/fence` 与 `RunOutcome.failure_code` 里。

#### Scenario: 回合进行中取消
- **WHEN** 某回合尚未写 `turn/end` 时收到取消信号
- **THEN** 日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `session/end` 收尾，退出码为 5

#### Scenario: 取消打断正在执行的调用
- **WHEN** 一条 `bash` 正在执行时收到取消信号
- **THEN** 该 `tool_call_id` 有一条 `tool/cancelled` 与一条 `outcome: TOOL_CANCELLED` 的 `tool/result`，随后是 `error/abort`，退出码为 5

#### Scenario: 取消后没有无结果的 tool/call
- **WHEN** 取消发生在一批并发只读调用正在执行时，该批还有尚未派发的调用
- **THEN** 每一个已写出的 `tool/call` 都有一条配对的 `tool/result`，未派发的调用也各有一条 `tool/call` 与一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`

#### Scenario: 卡在并发额度上的调用不算被打断
- **WHEN** 一批只读调用超过并发额度、靠后的调用已写 `tool/call` 但还排在额度后面，此时取消
- **THEN** 这些调用的 `tool/result` 是 `ABORTED_BEFORE_DISPATCH`，日志里没有为它们写 `tool/cancelled`；真的在跑的那些仍是 `TOOL_CANCELLED` 加一条 `tool/cancelled`

#### Scenario: 取消与围栏拒绝同时在场
- **WHEN** 同一批次里一条调用被围栏拒绝、取消也在场
- **THEN** 未派发的调用各落一对 `tool/call` 与 `tool/result(ABORTED_BEFORE_DISPATCH)`，`error/fence` 与 `error/abort` 都在盘上，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: 取消收尾的日志前缀是完整的
- **WHEN** 对一次以 `ABORTED` 收尾的 run 的日志折叠
- **THEN** 折叠结果里每个 assistant 工具请求消息都有配平的工具结果消息，且该日志可被逐点重放而不出现在读方闭合

#### Scenario: M2 不写 tool/cancelled
- **WHEN** 跑完 M2 的既有场景（围栏拒绝、参数不合法、审批拒绝，且取消发生在回合边界而不是工具执行中）
- **THEN** 日志里没有任何 `tool/cancelled` 记录

## REMOVED Requirements

### Requirement: 工具调用与结果按声明顺序落盘
**Reason**: ADR-0012 裁决「结果在产生时立刻落盘」优先于落盘顺序。缓冲到批次结束换声明顺序，是 `docs/CURRENT.md` 里唯一带「缺口」标签、没有判据的一条：硬杀落在批次中间会留下半截前缀。
**Migration**: 新 Requirement「工具结果在产生时落盘」。判据从「`tool/result` 的序列等于声明顺序」改成「同一批次的结果集合相同、每个 `tool/call` 都有配对结果、且顺序等于完成顺序」。

## ADDED Requirements

### Requirement: 工具结果在产生时落盘
系统 SHALL 在一个工具调用产出结果时立刻落盘它的 `tool/result`，MUST NOT 等同一批其他调用结束后再批量落盘。落盘顺序因此是该批次的完成顺序；调用的配对关系与「每个 `tool/call` 都有配对的 `tool/result`」MUST NOT 依赖完成顺序。

#### Scenario: 先完成的先落盘
- **WHEN** 一批并发只读调用里第二个先完成
- **THEN** 日志里第二个的 `tool/result` 出现在第一个的 `tool/result` 之前

#### Scenario: 硬杀后已产出的结果都在盘上
- **WHEN** 一批调用执行途中该 run 的子进程被硬杀
- **THEN** 已经产出过的每一条 `tool/result` 都在日志里且可独立解析，没有任何一条被部分写入

#### Scenario: 顺序变了折叠仍确定
- **WHEN** 对同一份日志连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

### Requirement: 取消与未知是两个工具结果词
系统 SHALL 把 `ABORTED_BEFORE_DISPATCH` 与 `TOOL_OUTCOME_UNKNOWN` 收进工具结果词表。`ABORTED_BEFORE_DISPATCH` SHALL 出现在未派发调用的 `tool/result.outcome` 里。`TOOL_OUTCOME_UNKNOWN` MUST NOT 出现在任何日志记录里——它只出现在折叠派生的工具结果消息里（见 `context-projection`）。两者 MUST NOT 配一条 `tool/cancelled`。词表外的值 MUST NOT 被写出。

#### Scenario: 两个新取值各从自己的生产者可达
- **WHEN** 跑完 M8 的可达性判据：`ABORTED_BEFORE_DISPATCH` 从 seam ① 的取消批次观察，`TOOL_OUTCOME_UNKNOWN` 从 seam ④ 的折叠观察
- **THEN** 观察到的取值集合等于工具结果词表，没有取值跑不到，也没有词表外的值被写出

#### Scenario: 闭合码不落盘
- **WHEN** 一次 run 正常收尾，其日志被折叠
- **THEN** 日志里没有任何一条记录的 `outcome` 是 `TOOL_OUTCOME_UNKNOWN`

#### Scenario: 未派发的调用不算被打断
- **WHEN** 一次取消让同一批里三个声明调用中的两个未被派发
- **THEN** 这两条 `tool/result` 的 `outcome` 是 `ABORTED_BEFORE_DISPATCH`，且日志里没有为它们写任何 `tool/cancelled`
