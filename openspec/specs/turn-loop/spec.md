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
系统 SHALL 在每条 `turn/end` 的 payload 里写 `stop_reason`，取值只允许 `MODEL_COMPLETED`、`TOOL_CALLS`、`MAX_TURNS`、`PROVIDER_ERROR`、`ABORTED`、`FENCE_DENIED`、`CONTEXT_WINDOW_EXCEEDED` 七个词表值，每个值只用于它对应的那一类收尾（见各 scenario）。`session/end` SHALL 记录整个 session 的最终 `stop_reason` 与回合总数；段级收尾不写 `session/end`。

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
- **WHEN** 某回合的装配预算读数超过压力预算，压缩之后仍超过它
- **THEN** 该回合写一条 `turn/end` 且 `stop_reason` 为 `CONTEXT_WINDOW_EXCEEDED`，`session/end` 的最终 `stop_reason` 也是它

### Requirement: 未注册工具是 UNKNOWN_TOOL 结果
系统 SHALL 把模型请求的每个工具调用派发到本次运行装配出的工具注册表；注册表的内容由装配决定（见 `config-layering`），未注册的工具名 SHALL 产生一条 `tool/result` 且 `outcome` 为 `UNKNOWN_TOOL`，回合 MUST NOT 因此中断。

#### Scenario: UNKNOWN_TOOL 不打断回合
- **WHEN** Provider 返回一个调用未注册工具名的回复
- **THEN** 该调用有配对的 `tool/call` 与 `tool/result`，`outcome` 为 `UNKNOWN_TOOL`，且该回合正常写 `turn/end`

#### Scenario: 工具结果喂回下一回合
- **WHEN** 某回合产生了 `tool/result` 记录
- **THEN** 下一回合的装配里这些结果作为工具消息出现

#### Scenario: 空白名单下任何工具调用都是 UNKNOWN_TOOL
- **WHEN** 配置文件写 `tools = []`，Provider 仍返回一个工具调用
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合正常写 `turn/end`

### Requirement: Provider 失败是回合终止结果
当 Provider 无法产出合法回复时，系统 SHALL 写一条 `error/model` 记录（含 `code`）与 `turn/end`（`stop_reason: PROVIDER_ERROR`）。`session/end` 与退出码由入口决定：一次性入口（`run` / `serve`）写 `session/end` 并以退出码 1 结束，`minihns chat` 里这是段级收尾、会话回到提示符（ADR-0011 与 ADR-0019）。MUST NOT 抛出未捕获异常打断进程。`code` 取值：`PROVIDER_EXHAUSTED`、`PROVIDER_SCHEMA_INVALID`、`PROVIDER_HTTP_STATUS`、`PROVIDER_TIMEOUT`、`PROVIDER_TRANSPORT`、`PROVIDER_ABORTED`；前两个来自 mock 路径，后四个来自真实 provider 路径。`PROVIDER_ABORTED` 只在 provider 侧兜住「取消信号已置位却仍被调用」；内核取消仍走 `error/abort` 与退出码 5。

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
当运行期间收到取消信号时，系统 SHALL 终止**当前回合**而不是整批派发：已开始执行的调用被打断并塌成 `TOOL_CANCELLED`（配一条 `tool/cancelled`），尚未派发的每个声明调用 SHALL 落一对 `tool/call` 与 `tool/result(ABORTED_BEFORE_DISPATCH)`；随后写 `error/abort`（含 `turn_id` 与 `code: ABORTED`）与 `turn/end`（`stop_reason: ABORTED`）。内核 MUST NOT 把「会话是否结束」写进回合语义：一次性入口（`run` / `serve`）据此写 `session/end` 并以退出码 5 结束；`minihns chat` 里段中取消只写 `segment/end`、会话回到提示符（ADR-0011，见 `chat-repl`）。取消与围栏拒绝同时在场时取消优先到底：收尾是 `ABORTED`，围栏拒绝的事实留在 `error/fence` 与 `RunOutcome.failure_code`。

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

### Requirement: 预算溢出是回合终止结果，会话是否继续由入口决定
当某回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 结束**该回合**：MUST NOT 开始下一回合，MUST NOT 为该回合调用模型或派发任何工具。内核 MUST NOT 把「会话是否结束」写进回合语义——`session/end` 与退出码由入口决定：一次性入口（`run` / `serve`）据此结束 session 并以退出码 4 收尾，`minihns chat` 里会话 SHALL 回到提示符等下一条输入（ADR-0019）。该结果与取消、围栏拒绝、provider 失败互不遮蔽：同时在场时按「取消优先到底、其余按发生的先后」判定，事实各自留在自己的 `error/*` 记录里。

#### Scenario: 溢出回合没有 model/request
- **WHEN** 某回合因预算溢出收尾
- **THEN** 该 `turn_id` 有 `turn/start` 与 `turn/end`，没有任何 `model/request`、`model/response`、`tool/call`，也没有下一回合

#### Scenario: 取消在场时不为压缩调用模型
- **WHEN** 装配越线的同时取消信号已置位
- **THEN** 系统不生成摘要、不写 `compaction/summary`、不写 `error/context`，`turn/end` 与 `session/end` 的 `stop_reason` 是 `ABORTED`，退出码为 5

#### Scenario: REPL 里溢出之后会话继续
- **WHEN** 一次 chat 的某个段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该段有 `error/context`、`turn/end` 与 `segment/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）、没有 `session/end`，下一条输入开启新的段

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

