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

### Requirement: 事件类型只取自 M1 词表
系统 SHALL 只发出 M1 词表中的事件类型：`session/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`tool/call`、`tool/result`、`turn/end`、`session/end`、`error/*`。`error/*` 在 M1 用到的具体类型是 `error/model`、`error/internal`、`error/abort`。词表外的事实 MUST NOT 通过临时新造类型表达。

#### Scenario: 一轮纯文本回复的事件序列
- **WHEN** mock Provider 在一个回合返回不含工具调用的回复，run 正常结束
- **THEN** 日志的类型序列恰为 `session/start`、`turn/start`、`context/assembled`、`model/request`、`model/response`、`turn/end`、`session/end`

#### Scenario: 无法归类的内部故障走 error 命名空间
- **WHEN** 内核发生一个不属于任何既有 `namespace/method` 的故障
- **THEN** 日志写入 `error/internal` 记录，而不是新造事件类型

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

#### Scenario: 回合中途日志变得不可写
- **WHEN** 日志文件在 session 运行途中变得不可写
- **THEN** 追加产出 `LOG_WRITE_FAILED` 失败结果而不是抛出异常，已写入的字节不变，`minihns run` 以退出码 1 结束

### Requirement: 日志读不动或读到坏行是终止结果
当 session 日志无法读取、或某一行不是合法的事件记录时，系统 SHALL 产出 `LOG_UNREADABLE` 失败结果（含路径与原因）而不是抛出未捕获异常；`minihns replay` SHALL 以退出码 1 结束并在 stderr 输出该失败码。

#### Scenario: 日志里有一行不是合法的事件记录
- **WHEN** 被重放的日志里某一行不是合法的事件记录
- **THEN** `minihns replay` 以退出码 1 结束，stderr 含 `LOG_UNREADABLE`，且进程没有未捕获异常
