## ADDED Requirements

### Requirement: 一条输入开一个段，段的边界在日志里
系统 SHALL 把一条输入（一次性 run 的 prompt、REPL 的一条输入）展开成一个**段**，并把段的边界 durable 写进日志：段开始时写 `segment/start`（payload 含 `segment_id`），段结束时写 `segment/end`（payload 含 `segment_id`、该段最后一个回合的 `stop_reason`、该段实际跑掉的回合数 `turns`）。`segment_id` 在会话内连续编号（`s1`、`s2`…）且 MUST NOT 重复。一次性 `minihns run` 恰有一个段。`segment/*` MUST NOT 产出上下文里的消息。照 DSH：段的边界对应 DSH 的 `turn` 边界（`turn = phase.turn + 1` 后 `session.append("turn/start", {turn})`，编号单调且落日志），本项目的「回合」仍是 DSH 的 `step`（GLOSSARY）。

#### Scenario: 一次 run 恰一个段
- **WHEN** 一次 run 跑了一个回合就正常结束
- **THEN** 日志的类型序列是 `session/start`、`segment/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`segment/end`、`session/end`，`segment/end` 的 `stop_reason` 是 `MODEL_COMPLETED`、`turns` 为 1

#### Scenario: 段编号在会话内连续
- **WHEN** 一次 chat 跑两个段
- **THEN** 日志里恰有 `s1` 与 `s2` 各一条 `segment/start` 与一条 `segment/end`，没有第三个段编号

#### Scenario: 段级取消段的边界也写
- **WHEN** 一个段进行中收到取消信号
- **THEN** 日志里有 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `segment/end`（`stop_reason: ABORTED`），没有 `session/end`

### Requirement: 预算溢出是回合终止结果，会话是否继续由入口决定
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束**该回合**：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具。内核 MUST NOT 把「会话是否结束」写进回合语义——`session/end` 与退出码由入口决定：一次性 `minihns run` 据此结束 session 并以退出码 4 收尾，`minihns chat` 里会话 SHALL 回到提示符等下一条输入（ADR-0019）。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: REPL 里溢出之后会话继续
- **WHEN** 一次 chat 的某个段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该段有 `error/context`、`turn/end` 与 `segment/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）、没有 `session/end`，下一条输入开启新的段

## MODIFIED Requirements

### Requirement: 回合数上限由 --max-turns 决定
系统 SHALL 用 `--max-turns` 限制**一个段**的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。会话级 MUST NOT 设回合数上限：一次性 `minihns run` 恰一个段，`minihns chat` 里每条输入是一个段，段用完上限 MUST NOT 结束会话（见 `chat-repl`）。照 DSH：DSH 的交互循环对 `turn` 与 `step` 都不设轮数上限（`dsh-agent-loop` 的全部数值配置只有 `maxParallelToolCalls` 默认 10 与每 agent 的 `maxTokens`），带轮数上限的只有委派工具的 `maxRounds`（默认 256，用完返回 `budget-limited`）——那对应本项目的 seam ⑦ / M15 的「目标轮次与 `blocked`」，MUST NOT 与这里的 `max_turns` 混名。

#### Scenario: 非法 max-turns 不产生日志
- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 上限判的是段不是会话
- **WHEN** 一次 chat 的第一条输入用完 `max_turns = 2`
- **THEN** 该段的 `segment/end` 的 `stop_reason` 是 `MAX_TURNS`、`turns` 为 2，日志里没有 `session/end`，下一条输入开一个新的段并照样有 2 个回合的额度

### Requirement: 停止判定写在 turn/end
系统 SHALL 在每条 `turn/end` 的 payload 里写 `stop_reason`，取值只允许 `MODEL_COMPLETED`、`TOOL_CALLS`、`MAX_TURNS`、`PROVIDER_ERROR`、`ABORTED`、`FENCE_DENIED`、`CONTEXT_WINDOW_EXCEEDED`。`TOOL_CALLS` 只用于「模型要求调工具、还要继续」的回合；`MODEL_COMPLETED` 只用于「模型不再要求继续」；`FENCE_DENIED` 只用于「本回合因围栏或审批拒绝而终止」；`CONTEXT_WINDOW_EXCEEDED` 只用于「本回合的上下文压缩之后仍然装不下」。`session/end` SHALL 记录整个 session 的最终 `stop_reason` 与回合总数；段级收尾不写 `session/end`，所以下面三条 scenario 里的 `session/end` 只成立于一次性 `minihns run`（接替见「预算溢出是回合终止结果，会话是否继续由入口决定」）。

#### Scenario: 模型不请求工具即停止
- **WHEN** Provider 返回的 `tool_calls` 为空
- **THEN** 该回合 `stop_reason` 为 `MODEL_COMPLETED`，且不再开始下一回合

#### Scenario: 模型要求调工具时回合以 TOOL_CALLS 收尾
- **WHEN** Provider 返回的 `tool_calls` 非空且回合数未达 `--max-turns`
- **THEN** 该回合 `stop_reason` 为 `TOOL_CALLS`，且紧接着开始下一回合

#### Scenario: 达到回合上限即停止
- **WHEN** 一次性 `minihns run` 里已完成的回合数达到 `--max-turns`
- **THEN** 最后一个回合的 `stop_reason` 为 `MAX_TURNS`（即使该回合也要求调工具），`session/end` 被写入，run 以退出码 0 结束

#### Scenario: 围栏拒绝的回合以 FENCE_DENIED 收尾
- **WHEN** 一次性 `minihns run` 的某回合派发工具时发生围栏或审批拒绝
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `FENCE_DENIED`，`session/end` 的最终 `stop_reason` 也是 `FENCE_DENIED`

#### Scenario: 预算溢出的回合以 CONTEXT_WINDOW_EXCEEDED 收尾
- **WHEN** 一次性 `minihns run` 的某回合装配压缩之后预算读数仍超过触发线
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `CONTEXT_WINDOW_EXCEEDED`，`session/end` 的最终 `stop_reason` 也是它

### Requirement: Provider 失败是回合终止结果
当 Provider 无法产出合法回复时，系统 SHALL 写一条 `error/model` 记录（含 `code`）与 `turn/end`（`stop_reason: PROVIDER_ERROR`）。`session/end` 与退出码由入口决定：一次性 `minihns run` 写 `session/end` 并以退出码 1 结束，`minihns chat` 里这是段级收尾、会话回到提示符（ADR-0011 与 ADR-0019）。MUST NOT 抛出未捕获异常打断进程。`code` 取值：`PROVIDER_EXHAUSTED`、`PROVIDER_SCHEMA_INVALID`、`PROVIDER_HTTP_STATUS`、`PROVIDER_TIMEOUT`、`PROVIDER_TRANSPORT`、`PROVIDER_ABORTED`。前两个来自 mock 路径，后四个来自真实 provider 路径（HTTP 状态码不可接受且重试后仍失败 / 请求超时 / 连接层失败 / 取消信号已置位）。`PROVIDER_ABORTED` 与既有的取消路径不冲突：内核置位取消时走的仍是 `error/abort` 与退出码 5，这条只在 provider 侧兜住「信号已置位却仍被调用」。

#### Scenario: fixture 条目耗尽
- **WHEN** 一次性 run 里需要的回合数超过 fixture 里的回复条目数
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1

#### Scenario: HTTP 状态码不可接受
- **WHEN** 一次性 run 的真实 provider 请求重试一次后仍收到 5xx
- **THEN** 日志写 `error/model`（`code: PROVIDER_HTTP_STATUS`）、`turn/end`（`stop_reason: PROVIDER_ERROR`）与 `session/end`，退出码为 1

#### Scenario: 请求超时
- **WHEN** 一次性 run 的真实 provider 请求超时
- **THEN** 日志写 `error/model`（`code: PROVIDER_TIMEOUT`）与 `session/end`，退出码为 1，进程没有未捕获异常

#### Scenario: 连接层失败
- **WHEN** 一次性 run 的真实 provider 请求无法建立连接（端点没在监听）
- **THEN** 日志写 `error/model`（`code: PROVIDER_TRANSPORT`）与 `session/end`，退出码为 1，且没有 `model/retry`

#### Scenario: REPL 里 provider 失败是段级收尾
- **WHEN** 一次 chat 的某个段因 fixture 条目耗尽拿到 `PROVIDER_EXHAUSTED`
- **THEN** 该段有 `error/model`、`turn/end` 与 `segment/end`（`stop_reason: PROVIDER_ERROR`）、没有 `session/end`，下一条输入开启新的段，进程退出码为 0

### Requirement: 用户取消是 ABORTED 结果
当运行期间收到取消信号时，系统 SHALL 终止**当前回合**而不是整批派发：已开始执行的调用被打断并塌成 `TOOL_CANCELLED`（配一条 `tool/cancelled`），尚未派发的每一个声明调用 SHALL 写一条 `tool/call` 与配对的 `tool/result`（`outcome: ABORTED_BEFORE_DISPATCH`）；随后写 `error/abort`（含 `turn_id` 与 `code: ABORTED`）与 `turn/end`（`stop_reason: ABORTED`）。内核 MUST NOT 把「会话是否结束」写进回合语义：一次性 `minihns run` 的入口据此写 `session/end` 并以退出码 5 结束；`minihns chat` 里段中取消只写 `segment/end`、会话回到提示符（ADR-0011，见 `chat-repl`）。取消与围栏拒绝同时在场时取消优先到底——收尾理由是 `ABORTED`，围栏拒绝的事实留在 `error/fence` 与 `RunOutcome.failure_code` 里。

#### Scenario: 回合进行中取消
- **WHEN** 一次性 `minihns run` 的某回合尚未写 `turn/end` 时收到取消信号
- **THEN** 日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `session/end` 收尾，退出码为 5

#### Scenario: 取消打断正在执行的调用
- **WHEN** 一次性 run 里一条 `bash` 正在执行时收到取消信号
- **THEN** 该 `tool_call_id` 有一条 `tool/cancelled` 与一条 `outcome: TOOL_CANCELLED` 的 `tool/result`，随后是 `error/abort`，退出码为 5

#### Scenario: 取消后没有无结果的 tool/call
- **WHEN** 取消发生在一批并发只读调用正在执行时，该批还有尚未派发的调用
- **THEN** 每一个已写出的 `tool/call` 都有一条配对的 `tool/result`，未派发的调用也各有一条 `tool/call` 与一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`

#### Scenario: 卡在并发额度上的调用不算被打断
- **WHEN** 一批只读调用超过并发额度、靠后的调用已写 `tool/call` 但还排在额度后面，此时取消
- **THEN** 这些调用的 `tool/result` 是 `ABORTED_BEFORE_DISPATCH`，日志里没有为它们写 `tool/cancelled`；真的在跑的那些仍是 `TOOL_CANCELLED` 加一条 `tool/cancelled`

#### Scenario: 取消与围栏拒绝同时在场
- **WHEN** 一次性 run 的同一批次里一条调用被围栏拒绝、取消也在场
- **THEN** 未派发的调用各落一对 `tool/call` 与 `tool/result(ABORTED_BEFORE_DISPATCH)`，`error/fence` 与 `error/abort` 都在盘上，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: 取消收尾的日志前缀是完整的
- **WHEN** 对一次以 `ABORTED` 收尾的 run 的日志折叠
- **THEN** 折叠结果里每个 assistant 工具请求消息都有配平的工具结果消息，且该日志可被逐点重放而不出现在读方闭合

#### Scenario: M2 不写 tool/cancelled
- **WHEN** 跑完 M2 的既有场景（围栏拒绝、参数不合法、审批拒绝，且取消发生在回合边界而不是工具执行中）
- **THEN** 日志里没有任何 `tool/cancelled` 记录

## REMOVED Requirements

### Requirement: 预算溢出终止整个 session
**Reason**: 「终止整个 session」把入口策略写进了回合语义，与 ADR-0011 已确立的边界（内核 MUST NOT 决定会话是否结束）冲突；在 REPL 里它会让一次溢出杀掉整个会话，而 DSH 的溢出是请求级失败、会话不死（`dsh-compaction-basic/lib/index.js:861-887`）。
**Migration**: 由本 change 新增的「预算溢出是回合终止结果，会话是否继续由入口决定」接替；它的两条 scenario（「溢出回合没有 model/request」「取消在场时不为压缩调用模型」）原样搬进那条需求，一次性 run 的退出码 4 留在 `cli` 的「退出码只取自固定表」里。
