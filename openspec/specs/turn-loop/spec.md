# turn-loop Specification

## Purpose

定义显式回合主循环：每个回合做哪五步、按什么顺序记账、什么条件下停止，以及工具与模型失败如何作为结果而非异常被记录。

## Requirements

### Requirement: 回合主循环按固定五步显式执行
系统 SHALL 对每个回合按固定顺序执行：写 `turn/start` → 折叠装配上下文（越线时先压缩并写 `compaction/summary`）并写 `context/assembled` → 调 Provider 并写 `model/request` 与 `model/response` → 派发工具调用并写 `tool/call` 与 `tool/result` → 写 `turn/end`。该顺序 MUST NOT 藏在回调或隐式钩子里；压缩 MUST NOT 成为第六步，它属于装配步之内。

#### Scenario: 两个回合的事件顺序可断言
- **WHEN** 一次 run 完成两个回合
- **THEN** 日志里事件类型按上述五步成组出现，且每个 `turn/end` 都在下一个 `turn/start` 之前

#### Scenario: 压缩不改变五步的顺序
- **WHEN** 某回合的装配触发了压缩
- **THEN** 该回合仍是 `turn/start` 开始、`turn/end` 收尾，`compaction/summary` 位于该回合的 `context/assembled` 之前

### Requirement: 回合内事件携带 turn_id
系统 SHALL 在 `turn/start`、`context/assembled`、`model/request`、`model/response`、`tool/call`、`tool/result`、`turn/end` 的 payload 里写入 `turn_id`；同一回合内 `turn_id` 相同，跨回合 MUST NOT 重复。

#### Scenario: turn_id 与回合序号一一对应
- **WHEN** 一次 run 跑了 3 个回合
- **THEN** 日志里恰有 3 个不同的 `turn_id`，每个 `turn_id` 恰对应一条 `turn/start` 与一条 `turn/end`

### Requirement: 停止判定写在 turn/end
系统 SHALL 在每条 `turn/end` 的 payload 里写 `stop_reason`，取值只允许 `MODEL_COMPLETED`、`TOOL_CALLS`、`MAX_TURNS`、`PROVIDER_ERROR`、`ABORTED`、`FENCE_DENIED`、`CONTEXT_WINDOW_EXCEEDED`。`TOOL_CALLS` 只用于「模型要求调工具、还要继续」的回合；`MODEL_COMPLETED` 只用于「模型不再要求继续」；`FENCE_DENIED` 只用于「本回合因围栏或审批拒绝而终止」；`CONTEXT_WINDOW_EXCEEDED` 只用于「本回合的上下文压缩之后仍然装不下」。`session/end` SHALL 记录整个 session 的最终 `stop_reason` 与回合总数。

#### Scenario: 模型不请求工具即停止
- **WHEN** Provider 返回的 `tool_calls` 为空
- **THEN** 该回合 `stop_reason` 为 `MODEL_COMPLETED`，且不再开始下一回合

#### Scenario: 模型要求调工具时回合以 TOOL_CALLS 收尾
- **WHEN** Provider 返回的 `tool_calls` 非空且回合数未达 `--max-turns`
- **THEN** 该回合 `stop_reason` 为 `TOOL_CALLS`，且紧接着开始下一回合

#### Scenario: 达到回合上限即停止
- **WHEN** 已完成的回合数达到 `--max-turns`
- **THEN** 最后一个回合的 `stop_reason` 为 `MAX_TURNS`（即使该回合也要求调工具），`session/end` 被写入，run 以退出码 0 结束

#### Scenario: 围栏拒绝的回合以 FENCE_DENIED 收尾
- **WHEN** 某回合派发工具时发生围栏或审批拒绝
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `FENCE_DENIED`，`session/end` 的最终 `stop_reason` 也是 `FENCE_DENIED`

#### Scenario: 预算溢出的回合以 CONTEXT_WINDOW_EXCEEDED 收尾
- **WHEN** 某回合的装配压缩之后预算读数仍超过触发线
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `CONTEXT_WINDOW_EXCEEDED`，`session/end` 的最终 `stop_reason` 也是它

### Requirement: 未注册工具是 UNKNOWN_TOOL 结果
系统 SHALL 把模型请求的每个工具调用派发到工具注册表；注册表里内置五个文件工具，未注册的工具名 SHALL 产生一条 `tool/result` 且 `outcome` 为 `UNKNOWN_TOOL`，回合 MUST NOT 因此中断。

#### Scenario: UNKNOWN_TOOL 不打断回合
- **WHEN** Provider 返回一个调用未注册工具名的回复
- **THEN** 该调用有配对的 `tool/call` 与 `tool/result`，`outcome` 为 `UNKNOWN_TOOL`，且该回合正常写 `turn/end`

#### Scenario: 工具结果喂回下一回合
- **WHEN** 某回合产生了 `tool/result` 记录
- **THEN** 下一回合的 `context/assembled` 里包含对应的工具结果消息

### Requirement: Provider 失败是回合终止结果
当 Provider 无法产出合法回复时，系统 SHALL 写一条 `error/model` 记录（含 `code`）、写 `turn/end`（`stop_reason: PROVIDER_ERROR`）、写 `session/end`，并以退出码 1 结束；MUST NOT 抛出未捕获异常打断进程。`code` 取值：`PROVIDER_EXHAUSTED`、`PROVIDER_SCHEMA_INVALID`、`PROVIDER_HTTP_STATUS`、`PROVIDER_TIMEOUT`、`PROVIDER_TRANSPORT`、`PROVIDER_ABORTED`。前两个来自 mock 路径，后四个来自真实 provider 路径（HTTP 状态码不可接受且重试后仍失败 / 请求超时 / 连接层失败 / 取消信号已置位）。`PROVIDER_ABORTED` 与既有的取消路径不冲突：内核置位取消时走的仍是 `error/abort` 与退出码 5，这条只在 provider 侧兜住「信号已置位却仍被调用」。

#### Scenario: fixture 条目耗尽
- **WHEN** 需要的回合数超过 fixture 里的回复条目数
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1

#### Scenario: HTTP 状态码不可接受
- **WHEN** 真实 provider 的请求重试一次后仍收到 5xx
- **THEN** 日志写 `error/model`（`code: PROVIDER_HTTP_STATUS`）、`turn/end`（`stop_reason: PROVIDER_ERROR`）与 `session/end`，退出码为 1

#### Scenario: 请求超时
- **WHEN** 真实 provider 的请求超时
- **THEN** 日志写 `error/model`（`code: PROVIDER_TIMEOUT`）与 `session/end`，退出码为 1，进程没有未捕获异常

#### Scenario: 连接层失败
- **WHEN** 真实 provider 的请求无法建立连接（端点没在监听）
- **THEN** 日志写 `error/model`（`code: PROVIDER_TRANSPORT`）与 `session/end`，退出码为 1，且没有 `model/retry`

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

### Requirement: 回合数上限由 --max-turns 决定
系统 SHALL 用 `--max-turns` 限制单次 run 的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。

#### Scenario: 非法 max-turns 不产生日志
- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

### Requirement: 工具派发按校验、围栏、执行的固定顺序判定
系统 SHALL 对每个工具调用按固定顺序判定：先校验入参，再做围栏与 approval 判定，最后执行；执行段 SHALL 包含该调用的超时判定。任一段的失败 SHALL 产出该调用的 `tool/result` 而不是异常；入参校验失败时 MUST NOT 做围栏判定，围栏判定拒绝时 MUST NOT 执行该工具。超时与取消 MUST NOT 以异常形式逃出执行段。

#### Scenario: 参数不合法时不碰文件
- **WHEN** 一个 `write` 调用缺 `content` 参数
- **THEN** 结果是 `TOOL_ARGS_INVALID`，且日志里没有 `approval/request`，目标文件也不存在

#### Scenario: 围栏拒绝时不执行
- **WHEN** 一个 `write` 的目标解析后在工作区之外
- **THEN** 结果是 `DENIED_BY_FENCE`，且该路径上没有被创建的文件

#### Scenario: 超时不逃出执行段
- **WHEN** 一个调用的执行因超时被打断
- **THEN** 该调用产出 `outcome: TOOL_TIMEOUT` 的 `tool/result`，进程没有未捕获异常，回合继续

### Requirement: 派发使用本次运行的围栏上下文
系统 SHALL 在派发每次工具调用时提供本次运行的工作区根、`--sandbox` 档位、approval 策略，以及从该派发点之前的日志前缀派生的「已读过」判定。这些事实 MUST NOT 来自与日志并列的进程内真源。

#### Scenario: 同一份日志前缀得到同一判定
- **WHEN** 对同一份日志的同一前缀分别派发同一个 `write` 调用两次
- **THEN** 两次得到相同的 `outcome`

### Requirement: 只读工具并发、会改动的工具串行
系统 SHALL 在同一回合内并发派发只读工具（`read`、`glob`、`grep`），同时在跑的只读调用数量 MUST NOT 超过 8；会改动的工具（`write`、`edit`、`bash`）SHALL 串行派发。上限是实现常量，MUST NOT 有命令行开关。

#### Scenario: 同一回合两个 read 并发
- **WHEN** 一个回合的模型回复包含两个 `read` 调用
- **THEN** 两个调用的执行时间区间重叠（第二个在第一个结束之前已经开始）

#### Scenario: 同一回合两个 edit 串行
- **WHEN** 一个回合的模型回复包含两个 `edit` 调用
- **THEN** 第二个只在第一个执行结束之后才开始执行

#### Scenario: 并发不超过上限
- **WHEN** 一个回合包含 10 个 `read` 调用
- **THEN** 同时在跑的只读调用数量始终不超过 8，且 10 个调用都有配对的 `tool/result`

### Requirement: 一批并发派发共享同一份日志前缀
系统 SHALL 在一个回合开始派发时取样一次该回合之前的日志前缀，并用同一份前缀判定该批次里的每一个调用。一个并发调用的结果 MUST NOT 影响同批另一个调用的围栏判定或写前必读判定。

#### Scenario: 同批的 read 不算已读过
- **WHEN** 同一回合里模型先请求 `read` 某文件、再请求 `write` 同一文件
- **THEN** 该 `write` 的结果是 `WRITE_WITHOUT_READ`

#### Scenario: 同一批次重放得到同一判定
- **WHEN** 对同一份日志前缀重放同一批工具调用
- **THEN** 每个调用的 `outcome` 与串行派发时相同

### Requirement: 超时与取消是工具结果词
`tool/result.outcome` SHALL 包含 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`：前者是执行段超时，后者是被取消信号打断。两者 SHALL 各配一条 `tool/cancelled`。超时之后同一回合剩余的调用 SHALL 照常派发，`turn/end` 的 `stop_reason` MUST NOT 因此变成 `ABORTED`。词表外的值 MUST NOT 被写出。

#### Scenario: 超时后回合继续
- **WHEN** 一批调用里第一个 `bash` 超时、后面还有一个 `read`
- **THEN** 第一个是 `TOOL_TIMEOUT` 加一条 `tool/cancelled`，第二个照常派发，`turn/end` 的 `stop_reason` 不是 `ABORTED`

#### Scenario: 两个新取值各有可达判据
- **WHEN** 跑完 M3 的 seam ① 与 seam ② 测试
- **THEN** `TOOL_TIMEOUT` 与 `TOOL_CANCELLED` 各至少被一条测试断言到

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

### Requirement: 预算溢出终止整个 session
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束整个 session：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具，且 `session/end` MUST 被写出。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5
