# turn-loop Specification

## Purpose

定义显式回合主循环：每个回合做哪五步、按什么顺序记账、什么条件下停止，以及工具与模型失败如何作为结果而非异常被记录。

## Requirements

### Requirement: 回合主循环按固定五步显式执行
系统 SHALL 对每个回合按固定顺序执行：写 `turn/start` → 折叠装配上下文并写 `context/assembled` → 调 Provider 并写 `model/request` 与 `model/response` → 派发工具调用并写 `tool/call` 与 `tool/result` → 写 `turn/end`。该顺序 MUST NOT 藏在回调或隐式钩子里。

#### Scenario: 两个回合的事件顺序可断言
- **WHEN** 一次 run 完成两个回合
- **THEN** 日志里事件类型按上述五步成组出现，且每个 `turn/end` 都在下一个 `turn/start` 之前

### Requirement: 回合内事件携带 turn_id
系统 SHALL 在 `turn/start`、`context/assembled`、`model/request`、`model/response`、`tool/call`、`tool/result`、`turn/end` 的 payload 里写入 `turn_id`；同一回合内 `turn_id` 相同，跨回合 MUST NOT 重复。

#### Scenario: turn_id 与回合序号一一对应
- **WHEN** 一次 run 跑了 3 个回合
- **THEN** 日志里恰有 3 个不同的 `turn_id`，每个 `turn_id` 恰对应一条 `turn/start` 与一条 `turn/end`

### Requirement: 停止判定写在 turn/end
系统 SHALL 在每条 `turn/end` 的 payload 里写 `stop_reason`，取值只允许 `MODEL_COMPLETED`、`TOOL_CALLS`、`MAX_TURNS`、`PROVIDER_ERROR`、`ABORTED`、`FENCE_DENIED`。`TOOL_CALLS` 只用于「模型要求调工具、还要继续」的回合；`MODEL_COMPLETED` 只用于「模型不再要求继续」；`FENCE_DENIED` 只用于「本回合因围栏或审批拒绝而终止」。`session/end` SHALL 记录整个 session 的最终 `stop_reason` 与回合总数。

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

### Requirement: 未注册工具是 UNKNOWN_TOOL 结果
系统 SHALL 把模型请求的每个工具调用派发到工具注册表；注册表里内置五个文件工具，未注册的工具名 SHALL 产生一条 `tool/result` 且 `outcome` 为 `UNKNOWN_TOOL`，回合 MUST NOT 因此中断。

#### Scenario: UNKNOWN_TOOL 不打断回合
- **WHEN** Provider 返回一个调用未注册工具名的回复
- **THEN** 该调用有配对的 `tool/call` 与 `tool/result`，`outcome` 为 `UNKNOWN_TOOL`，且该回合正常写 `turn/end`

#### Scenario: 工具结果喂回下一回合
- **WHEN** 某回合产生了 `tool/result` 记录
- **THEN** 下一回合的 `context/assembled` 里包含对应的工具结果消息

### Requirement: Provider 失败是回合终止结果
当 Provider 无法产出合法回复时，系统 SHALL 写一条 `error/model` 记录（含 `code`）、写 `turn/end`（`stop_reason: PROVIDER_ERROR`）、写 `session/end`，并以退出码 1 结束；MUST NOT 抛出未捕获异常打断进程。M1 的 `code` 取值：`PROVIDER_EXHAUSTED`、`PROVIDER_SCHEMA_INVALID`。

#### Scenario: fixture 条目耗尽
- **WHEN** 需要的回合数超过 fixture 里的回复条目数
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1

### Requirement: 用户取消是 ABORTED 结果
当运行期间收到取消信号时，系统 SHALL 写一条 `error/abort`（含 `turn_id` 与 `code: ABORTED`）、写 `turn/end`（`stop_reason: ABORTED`）与 `session/end`，并以退出码 5 结束。M2 派发真实工具但不实现工具级超时与取消，因此仍 MUST NOT 写 `tool/cancelled`；该类型属 M3。

#### Scenario: 回合进行中取消
- **WHEN** 某回合尚未写 `turn/end` 时收到取消信号
- **THEN** 日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `session/end` 收尾，退出码为 5

#### Scenario: M2 不写 tool/cancelled
- **WHEN** 跑完 M2 的全部场景（含围栏拒绝与取消）
- **THEN** 日志里没有任何 `tool/cancelled` 记录

### Requirement: 回合数上限由 --max-turns 决定
系统 SHALL 用 `--max-turns` 限制单次 run 的回合数，默认 8，取值 MUST 是 ≥ 1 的整数；非法取值 SHALL 以退出码 2 结束且在 session 开始之前失败。

#### Scenario: 非法 max-turns 不产生日志
- **WHEN** 执行 `minihns run -p "x" --max-turns 0`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

### Requirement: 工具派发按校验、围栏、执行的固定顺序判定
系统 SHALL 对每个工具调用按固定顺序判定：先校验入参，再做围栏与 approval 判定，最后执行。任一段的失败 SHALL 产出该调用的 `tool/result` 而不是异常；入参校验失败时 MUST NOT 做围栏判定，围栏判定拒绝时 MUST NOT 执行该工具。

#### Scenario: 参数不合法时不碰文件
- **WHEN** 一个 `write` 调用缺 `content` 参数
- **THEN** 结果是 `TOOL_ARGS_INVALID`，且日志里没有 `approval/request`，目标文件也不存在

#### Scenario: 围栏拒绝时不执行
- **WHEN** 一个 `write` 的目标解析后在工作区之外
- **THEN** 结果是 `DENIED_BY_FENCE`，且该路径上没有被创建的文件

### Requirement: 派发使用本次运行的围栏上下文
系统 SHALL 在派发每次工具调用时提供本次运行的工作区根、`--sandbox` 档位、approval 策略，以及从该派发点之前的日志前缀派生的「已读过」判定。这些事实 MUST NOT 来自与日志并列的进程内真源。

#### Scenario: 同一份日志前缀得到同一判定
- **WHEN** 对同一份日志的同一前缀分别派发同一个 `write` 调用两次
- **THEN** 两次得到相同的 `outcome`
