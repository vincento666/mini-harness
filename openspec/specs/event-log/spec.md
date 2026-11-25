# event-log Specification

## Purpose

定义 mini-harness 的唯一真源：只追加的 JSONL 事件日志写什么、怎么写、写到哪里，以及每条记录必须携带哪些字段。
## Requirements
### Requirement: 事件日志只追加且是唯一真源
系统 SHALL 把一次运行的全部事实写成 JSONL 事件记录并只追加到该 session 日志尾部；已写入的记录 MUST NOT 被修改、重排或删除。任何「当前状态」都从日志派生，系统 MUST NOT 维护与日志并列的可变真源。

#### Scenario: 运行结束后日志前缀不变
- **WHEN** 一个 session 从 `session/start` 跑到 `session/end`
- **THEN** 运行过程中任意时刻已写入的字节序列仍是最终日志文件的严格前缀

#### Scenario: 重放不追加事件
- **WHEN** 对同一个 session 连续执行两次 `minihns replay`
- **THEN** 该日志文件的字节数与内容都不变

### Requirement: 每条事件记录携带公共信封字段
系统 SHALL 在每条事件记录里写入 `schema_version`（整数，M1 固定为 1）、`type`（`namespace/method` 形式）、`session_id`、`seq`（同一 session 内从 0 起严格递增）、`ts`（UTC ISO-8601 时间戳）和 `payload`（对象）。

#### Scenario: 每行可独立解析
- **WHEN** 读取日志文件的任意一行
- **THEN** 该行是单个合法 JSON 对象，且六个信封字段全部存在、类型正确

#### Scenario: seq 严格递增
- **WHEN** 同一 session 日志中任取相邻的两条记录
- **THEN** 后写入记录的 `seq` 比先写入记录的大 1

### Requirement: 每次 run 一个新 session 与确定的日志路径
系统 SHALL 为每次 `minihns run` 生成唯一 session id，并把日志写到 `<session-dir>/<session-id>.jsonl`；`<session-dir>` 默认为当前工作目录下的 `sessions/`，可由 `--session-dir` 覆盖；目录不存在时 SHALL 创建。

#### Scenario: 两次 run 不共享日志
- **WHEN** 在同一工作区连续执行两次 `minihns run`
- **THEN** 产生两个不同的 session id 与两个各自独立的日志文件

#### Scenario: session 目录不存在时自动创建
- **WHEN** `--session-dir` 指向一个尚不存在的目录
- **THEN** 该目录被创建且 run 正常写入日志

### Requirement: 日志与事件里绝不出现密钥
系统 SHALL NOT 把 API 密钥、认证头或等价凭据写入任何事件记录、payload 或 CLI 输出。

#### Scenario: 环境变量里有密钥也不泄漏
- **WHEN** 环境里存在 `DEEPSEEK_API_KEY` 且执行一次 mock run
- **THEN** 日志全文与 stdout 都不包含该密钥的值

### Requirement: 日志不可写是终止结果
当日志目录或日志文件无法创建、无法写入时，系统 SHALL 以退出码 1 结束并在 stderr 输出 `LOG_WRITE_FAILED` 与失败路径；MUST NOT 静默丢弃事件后继续运行。

#### Scenario: session 目录不可写
- **WHEN** `--session-dir` 指向一个不可写的路径
- **THEN** `minihns run` 以退出码 1 结束，stderr 含 `LOG_WRITE_FAILED`

#### Scenario: 一步中途日志变得不可写
- **WHEN** 日志文件在 session 运行途中变得不可写
- **THEN** 追加产出 `LOG_WRITE_FAILED` 失败结果而不是抛出异常，已写入的字节不变，`minihns run` 以退出码 1 结束

### Requirement: 日志读不动或读到坏行是终止结果
当 session 日志无法读取、或某一行不是合法的事件记录时，系统 SHALL 产出 `LOG_UNREADABLE` 失败结果（含路径与原因）而不是抛出未捕获异常；`minihns replay` SHALL 以退出码 1 结束并在 stderr 输出该失败码。

#### Scenario: 日志里有一行不是合法的事件记录
- **WHEN** 被重放的日志里某一行不是合法的事件记录
- **THEN** `minihns replay` 以退出码 1 结束，stderr 含 `LOG_UNREADABLE`，且进程没有未捕获异常

### Requirement: 事件类型只取自当前事件词表

系统 SHALL 只发出当前词表（v2）中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`step/start`、`step/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`user/message`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`compaction/summary`、`command/run`、`command/done`、`plan/mode`、`goal/updated`、`todo/updated`、`question/asked`、`question/answered`、`present/artifact`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`、`error/context`。词表外的事实 MUST NOT 通过临时新造类型表达。

旧名 MUST NOT 被新写入使用。`schema_version == 1` 的记录 MUST 以 `SchemaUnsupported` 拒绝：v1 上迁只在改造期充当验证工具，合入前随兼容层一起删除（design D4，tasks 5.3）。

#### Scenario: 一次带审批的写的事件序列

- **WHEN** 一次 run 的某步派发一次获批的 `edit`
- **THEN** 该 `tool_call_id` 的记录按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的相对顺序出现

#### Scenario: goal 事件可写入词表

- **WHEN** 会话写入一条 `goal/updated`
- **THEN** 该行通过事件校验，重放时不被记为词表外类型

#### Scenario: v1 日志被拒

- **WHEN** 读取一条 `schema_version == 1`、类型为 `segment/start` 的记录
- **THEN** 读取以 `SCHEMA_UNSUPPORTED` 失败，不尝试猜它的新名字

#### Scenario: 新日志不写旧名

- **WHEN** 检查一次新会话的日志
- **THEN** 不存在 `segment/start`、`segment/end`，也不存在 v1 语义的 `turn/start`（它只能是 turn 的开始，不是 step 的开始）

### Requirement: approval 事件记录问与答
系统 SHALL 在**向人提问之前**写一条 `approval/request`（含 `step_id`、`tool_call_id`、工具名、关键参数），并在得到结论时立刻写一条 `approval/response`（含同样的 `step_id` 与 `tool_call_id`，`decision` 取 `APPROVED`、`DENIED`、`UNAVAILABLE`）。在非 `ABORTED` 收尾的 session 里，每条 `approval/request` MUST 有且只有一条配对的 `approval/response`。以 `error/abort` 收尾的 session 里允许一条没有配对的 `approval/request`，它读成「未回答」。

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
系统 SHALL 在围栏或审批拒绝终止 run 时写一条 `error/fence`，payload 含 `step_id`、`code`、`path`、`raw_path`、`detail`：`path` 是围栏判定实际使用的解析后键（档位轴先拒、或调用没有目标路径时是 `null`），`raw_path` 是调用里写的原始路径，`detail` 只面向人。没有目标路径的调用（`bash`）两者 SHALL 是 `null`。该记录 MUST 在配对的 `tool/result` 之后、`step/end` 之前写入。

#### Scenario: error/fence 的位置可断言
- **WHEN** 一次 run 因越界写终止
- **THEN** 日志里 `error/fence` 出现在该调用的 `tool/result` 之后、该步的 `step/end` 之前

#### Scenario: 两个路径字段各有取值
- **WHEN** 一次 run 因 `write` 一个写作 `../outside.md` 的路径终止
- **THEN** 那条 `error/fence` 的 `raw_path` 是 `../outside.md`，`path` 是解析后的键，判据不需要读 `detail`

#### Scenario: 没有目标路径的拒绝两个字段都是 null
- **WHEN** 一次 run 因 `--sandbox read-only` 下的 `bash` 终止
- **THEN** 那条 `error/fence` 的 `code` 是 `SANDBOX_DENIES_WRITE`，`path` 与 `raw_path` 都是 `null`

### Requirement: tool/cancelled 记录被打断的工具调用
系统 SHALL 为每一个被超时或被取消**打断**的工具调用写恰好一条 `tool/cancelled`，payload 含 `step_id` 与 `tool_call_id`。它 MUST NOT 携带命令输出或文件内容；是超时还是取消由配对的 `tool/result.outcome` 区分。尚未派发的调用不算被打断：`outcome: ABORTED_BEFORE_DISPATCH` 的调用 MUST NOT 有 `tool/cancelled`。

#### Scenario: 一次超时一条记录
- **WHEN** 一个调用因超时被打断
- **THEN** 该 `tool_call_id` 有一条 `tool/cancelled` 与一条 `outcome: TOOL_TIMEOUT` 的 `tool/result`，且 `tool/cancelled` 的 payload 里没有命令输出

#### Scenario: 没有打断就没有该记录
- **WHEN** 跑完一次既没有超时也没有取消的 run
- **THEN** 日志里没有任何 `tool/cancelled` 记录

#### Scenario: 未派发的调用没有 tool/cancelled
- **WHEN** 一次取消让同一批里声明的调用有未被派发的那些
- **THEN** 这些 `tool_call_id` 各有一条 `tool/call` 与一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`，且没有 `tool/cancelled`

### Requirement: compaction/summary 记录一次遮蔽式压缩
系统 SHALL 为每一次压缩写恰好一条 `compaction/summary`，payload 含 `step_id`、`shadowed_range`（对象，字段 `start` 与 `end` 是同一 session 内的 `seq`，含两端）、`summary`（摘要文本）、`tokens_before` 与 `tokens_after`（压缩前后该次装配的预算读数）。该记录 MUST NOT 携带被遮蔽记录的原文副本，也 MUST NOT 改写或删除被遮蔽的记录。

#### Scenario: 字段齐全且原文还在盘上
- **WHEN** 一次压缩落进日志
- **THEN** 那条 `compaction/summary` 的五个 payload 字段都在，且被 `shadowed_range` 覆盖的那些记录仍逐条存在于日志里、内容不变

#### Scenario: 一次装配最多一条
- **WHEN** 一次 run 里发生了两次压缩（分属两步）
- **THEN** 日志里恰有两条 `compaction/summary`，各自 `step_id` 不同

### Requirement: error/context 记录预算溢出
系统 SHALL 在预算溢出终止 run 时写一条 `error/context`，payload 含 `step_id`、`code`（取值 `CONTEXT_WINDOW_EXCEEDED`）、`detail`。该记录 MUST 在该步的 `step/end` 之前、该步的 `context/assembled` 之后写入（若该点有装配记录）。

#### Scenario: error/context 的位置可断言
- **WHEN** 一次 run 以预算溢出结束
- **THEN** 日志里 `error/context` 出现在该步的 `step/end` 之前，且 `session/end` 的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED`

#### Scenario: 词表每个新值可达
- **WHEN** 跑完 M5 的 seam ① 与 seam ⑥ 判据
- **THEN** `compaction/summary`、`error/context` 与 `StopReason` 里的 `CONTEXT_WINDOW_EXCEEDED` 各至少被一条测试断言到

### Requirement: 日志 schema 版本

每条记录的信封 SHALL 携带 `schema_version`；当前版本是 `2`。写入 MUST 用当前版本。读取 MUST 只接受 `2`；其它版本 MUST 以 `SchemaUnsupported` 拒绝，MUST NOT 尝试迁移或猜测。上迁 MUST NOT 改写磁盘上的原始行（这条对任何将来版本同样成立）。

#### Scenario: 不认识的版本被拒

- **WHEN** 读取一份 `schema_version == 1` 的日志
- **THEN** 以 `SCHEMA_UNSUPPORTED` 失败，且文件字节与读取前完全相同

