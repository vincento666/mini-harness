# Spec Delta

## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表
系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`。词表外的事实 MUST NOT 通过临时新造类型表达。`model/retry` 自 M4 起可达；`tool/cancelled` 自 M3 起可达。

#### Scenario: 一次带审批的写的事件序列
- **WHEN** 一次 run 的某回合派发一次获批的 `edit`
- **THEN** 该回合里事件类型按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的顺序成组出现

#### Scenario: 无法归类的内部故障仍走 error 命名空间
- **WHEN** 内核发生一个不属于任何既有 `namespace/method` 的故障
- **THEN** 日志写入 `error/internal` 记录，而不是新造事件类型

#### Scenario: 一次重试一条 model/retry
- **WHEN** 一次请求收到 429 并被重试
- **THEN** 日志里在配对的 `model/request` 与下一条 `model/response`（或 `error/model`）之间恰好有一条 `model/retry`，payload 含 `turn_id`、`attempt`、`status`

#### Scenario: 没有重试就没有该记录
- **WHEN** 跑完一次没有 429 与 5xx 的 run
- **THEN** 日志里没有任何 `model/retry` 记录

#### Scenario: tool/cancelled 自 M3 起在词表内
- **WHEN** 一次 `bash` 超时
- **THEN** 日志里有一条 `tool/cancelled` 记录，它不被记为 `unrecognized_type`

### Requirement: approval 事件记录问与答
系统 SHALL 在**向人提问之前**写一条 `approval/request`（含 `turn_id`、`tool_call_id`、工具名、关键参数），并在得到结论时立刻写一条 `approval/response`（含同样的 `turn_id` 与 `tool_call_id`，`decision` 取 `APPROVED`、`DENIED`、`UNAVAILABLE`）。在非 `ABORTED` 收尾的 session 里，每条 `approval/request` MUST 有且只有一条配对的 `approval/response`。以 `error/abort` 收尾的 session 里允许一条没有配对的 `approval/request`，它读成「未回答」。

#### Scenario: 获批的一对记录
- **WHEN** 一次提问得到批准
- **THEN** 日志里该 `tool_call_id` 有一条 `approval/request` 与一条 `decision: APPROVED` 的 `approval/response`

#### Scenario: 词表每个 decision 值可达
- **WHEN** 跑完 M2 的 approval 场景（批准、拒绝、不可问人）
- **THEN** 三个 `decision` 取值各至少被一条测试断言到

#### Scenario: 提问先落盘再等人
- **WHEN** 一次提问在得到结论之前进程被打断
- **THEN** 日志里已有那条 `approval/request`，它不被记为「没问过」

#### Scenario: 半对只在取消收尾的 session 里成立
- **WHEN** 一次 run 在提问期间被取消
- **THEN** 日志以 `error/abort` 收尾且允许那条 `approval/request` 没有配对；非取消收尾的 run 里不存在这种半对

### Requirement: 围栏拒绝写 error/fence
系统 SHALL 在围栏或审批拒绝终止 run 时写一条 `error/fence`，payload 含 `turn_id`、`code`、`path`、`raw_path`、`detail`：`path` 是围栏判定实际使用的解析后键，`raw_path` 是调用里写的原始路径，`detail` 只面向人。没有目标路径的调用（`bash`）两者 SHALL 是 `null`。该记录 MUST 在配对的 `tool/result` 之后、`turn/end` 之前写入。

#### Scenario: error/fence 的位置可断言
- **WHEN** 一次 run 因越界写终止
- **THEN** 日志里 `error/fence` 出现在该调用的 `tool/result` 之后、该回合的 `turn/end` 之前

#### Scenario: 两个路径字段各有取值
- **WHEN** 一次 run 因 `write` 一个写作 `../outside.md` 的路径终止
- **THEN** 那条 `error/fence` 的 `raw_path` 是 `../outside.md`，`path` 是解析后的键，判据不需要读 `detail`

#### Scenario: 没有目标路径的拒绝两个字段都是 null
- **WHEN** 一次 run 因 `--sandbox read-only` 下的 `bash` 终止
- **THEN** 那条 `error/fence` 的 `code` 是 `SANDBOX_DENIES_WRITE`，`path` 与 `raw_path` 都是 `null`

## ADDED Requirements

### Requirement: tool/cancelled 记录被打断的工具调用
系统 SHALL 为每一个被超时或被取消打断的工具调用写恰好一条 `tool/cancelled`，payload 含 `turn_id` 与 `tool_call_id`。它 MUST NOT 携带命令输出或文件内容；是超时还是取消由配对的 `tool/result.outcome` 区分。

#### Scenario: 一次超时一条记录
- **WHEN** 一个调用因超时被打断
- **THEN** 该 `tool_call_id` 有一条 `tool/cancelled` 与一条 `outcome: TOOL_TIMEOUT` 的 `tool/result`，且 `tool/cancelled` 的 payload 里没有命令输出

#### Scenario: 没有打断就没有该记录
- **WHEN** 跑完一次既没有超时也没有取消的 run
- **THEN** 日志里没有任何 `tool/cancelled` 记录
