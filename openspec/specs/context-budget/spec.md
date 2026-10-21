# context-budget Specification

## Purpose

定义上下文的窗口预算：预算由哪些参数决定、触发线怎么算、预算读数从哪来、越线时压缩在什么时机发生、压缩救不了时产出哪个结果。

## Requirements

### Requirement: 窗口预算由 window 与 reserve 两个参数决定
系统 SHALL 用 `--window`（默认 128000）与 `--reserve`（默认 8192）决定一次 run 的窗口预算；两者取值 MUST 是 ≥ 1 的整数，非法取值 SHALL 在 session 开始之前以退出码 2 结束并在 stderr 输出 `INVALID_ARGUMENT`。有效值 SHALL 进 `session/start` 的 payload（`window` 与 `reserve`）。

#### Scenario: 默认预算进 payload
- **WHEN** 一次 run 不带 `--window` 与 `--reserve`
- **THEN** `session/start` 的 payload 里 `window` 为 128000、`reserve` 为 8192

#### Scenario: 非法窗口取值不产生日志
- **WHEN** 执行 `minihns run -p "x" --window 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

### Requirement: 触发线由固定公式给出
系统 SHALL 用 `floor(min(W × 0.8, W − O − 65536))` 给出压缩触发线（W 是 `window`、O 是 `reserve`）；65536 是实现常量，MUST NOT 有命令行开关。该公式算出负数时触发线 SHALL 取 0，此时每一次装配都算越线。

#### Scenario: 默认参数下的触发线是一个可断言的数
- **WHEN** `window` 为 128000、`reserve` 为 8192
- **THEN** 触发线为 54272（`W − O − 65536` 比 `W × 0.8` 小）

#### Scenario: 小窗口下每次装配都越线
- **WHEN** 一次 run 的 `--window` 小到 `W − O − 65536` 为负
- **THEN** 每一个需要装配的回合都进入压缩判定，且触发线本身是 0 而不是负数

### Requirement: 预算读数有两个来源
系统 SHALL 把一次装配的预算读数定义为两者中较大的一个：本次折叠上下文的估算 token 数（每条消息的 `content` 与 `tool_calls` 文本长度之和除以 4、向上取整后逐条相加），与该日志前缀里未被遮蔽、`purpose` 不是 `compaction` 的 `model/response` 的 `usage.input_tokens` 的最大值。读数 MUST NOT 依赖进程内缓存或该点之后的事件。

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

### Requirement: 遮蔽范围保留尾部且不拆散配对
系统 SHALL 在压缩时保留尾部：保留预算为 `floor(W × 0.16)`（W 是 `window`）。遮蔽范围是从对话体第一条可遮蔽记录起的连续 seq 区间，其选择使未被遮蔽的记录估算不超过保留预算。`session/start` 与既有的 `compaction/summary` MUST NOT 进入遮蔽范围；切点 MUST NOT 落在一条 assistant 工具请求与它的 `tool/call` 或 `tool/result` 之间，此时整组一起遮蔽。没有可遮蔽内容时 SHALL 不产生遮蔽范围。

#### Scenario: 保留预算是窗口的 16%
- **WHEN** `window` 为 128000
- **THEN** 保留预算为 20480

#### Scenario: 切点不拆散一组工具往返
- **WHEN** 尾部切点落在一组 assistant 工具请求与它的工具结果之间
- **THEN** 遮蔽范围的 `end` 在该组最后一条记录之后，整组一起被遮蔽

#### Scenario: 既有摘要不被遮蔽
- **WHEN** 一次压缩发生在已有 `compaction/summary` 之后
- **THEN** 遮蔽范围的 `start` 大于那条记录的 `seq`

#### Scenario: 没有可遮蔽内容时不产生范围
- **WHEN** 对话体里只剩一条本身就超预算的记录
- **THEN** 不产生遮蔽范围，也不写 `compaction/summary`

### Requirement: 越线时压缩发生在装配之内
当一次装配的预算读数超过触发线时，系统 SHALL 在写出该点的 `context/assembled` 之前完成一次压缩：生成摘要、写一条 `compaction/summary`、再按新的日志前缀重新折叠。一次装配 MUST NOT 压缩多于一次；未越线的装配 MUST NOT 写 `compaction/summary`。

#### Scenario: 压缩记录在装配记录之前
- **WHEN** 某回合的装配越线并完成了压缩
- **THEN** 该回合的日志里 `compaction/summary` 出现在该点的 `context/assembled` 之前

#### Scenario: 未越线就没有压缩记录
- **WHEN** 跑完一次预算充裕的 run
- **THEN** 日志里没有任何 `compaction/summary` 记录

#### Scenario: 一次装配只尝试一次
- **WHEN** 一次装配压缩之后预算读数仍超过触发线
- **THEN** 系统不尝试第二次压缩，而是产出溢出结果

### Requirement: 压缩救不了时是 CONTEXT_WINDOW_EXCEEDED 结果
当一次装配压缩之后预算读数仍超过触发线时，系统 SHALL 写一条 `error/context`（payload 含 `turn_id`、`code: CONTEXT_WINDOW_EXCEEDED`、`detail`）、写 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）与 `session/end`，并以退出码 4 结束；MUST NOT 抛出未捕获异常，也 MUST NOT 为这个溢出结果调用回合模型——带 `purpose: compaction` 的摘要调用除外。

#### Scenario: 溢出的回合不产出该回合自己的模型调用
- **WHEN** 一次装配以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 该回合没有 `context/assembled`、没有不带 `purpose: compaction` 的 `model/request`、没有 `tool/call`

#### Scenario: 单条消息本身就超线
- **WHEN** 对话体里没有任何可遮蔽的内容，而预算读数已超过触发线
- **THEN** 日志以 `error/context`、`turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）与 `session/end` 收尾，退出码为 4

#### Scenario: 溢出收尾的日志可被重放
- **WHEN** 对一次以 `CONTEXT_WINDOW_EXCEEDED` 收尾的 run 的日志执行 `minihns replay`
- **THEN** 每条 `context/assembled` 都与其前缀的重算结果逐字段相等，replay 以退出码 0 结束；溢出发生在第一次装配之前时，日志里没有装配点，replay 照样以退出码 0 结束并说明这一点

### Requirement: 摘要调用失败沿用 provider 失败结果
生成摘要的那次模型调用失败时，系统 SHALL 沿用既有的 provider 失败形状：写 `error/model`（含 `code`）、写 `turn/end`（`stop_reason: PROVIDER_ERROR`）与 `session/end`，退出码为 1。此时 MUST NOT 写 `compaction/summary`，也 MUST NOT 产出 `CONTEXT_WINDOW_EXCEEDED`。

#### Scenario: fixture 里没有摘要回复
- **WHEN** 装配越线但 fixture 的回复条目已耗尽
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1，且日志里没有任何 `compaction/summary`

### Requirement: provider 报出的上下文超限塌成同一个溢出结果
当 Provider 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果时，系统 SHALL 产出与估算兜底同一个溢出结果：写 `error/context`（`code: CONTEXT_WINDOW_EXCEEDED`）、写 `turn/end`（`stop_reason: CONTEXT_WINDOW_EXCEEDED`）与 `session/end`，退出码为 4。此时 MUST NOT 写 `error/model`，也 MUST NOT 写 `compaction/summary`。

#### Scenario: 真实超限不走 provider 失败那条路
- **WHEN** 某回合的模型调用得到 `PROVIDER_CONTEXT_OVERFLOW` 的失败结果
- **THEN** 该回合的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED`、退出码为 4，日志里没有 `error/model`

#### Scenario: 两条触发路径产出同一个停止理由
- **WHEN** 一次 run 由估算兜底溢出、另一次由 provider 报出溢出
- **THEN** 两份日志的 `turn/end` 与 `session/end` 的 `stop_reason` 相同，退出码都是 4
