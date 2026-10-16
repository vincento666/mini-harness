# Spec Delta

## Purpose

定义 M1 的命令行外部行为：`minihns run` 与 `minihns replay` 接受什么参数、产出什么可观察输出、失败时返回哪个退出码。

## ADDED Requirements

### Requirement: minihns run 一次性完成一个 session
系统 SHALL 提供 `minihns run -p "任务"`：一次调用跑完一个 session 并返回退出码；参数为 `-p/--prompt`（必填、非空）、`--workspace`（默认当前目录）、`--session-dir`、`--provider`、`--fixture`、`--max-turns`、`--append-system-prompt`、`--events jsonl`。`--provider mock` 时 `--fixture` MUST 同时给出。成功时 stdout SHALL 打印 session id。

#### Scenario: 缺少 prompt
- **WHEN** 执行 `minihns run` 且不带 `-p`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 空 prompt
- **WHEN** 执行 `minihns run -p ""`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`

#### Scenario: mock 缺 fixture
- **WHEN** 执行 `minihns run -p "任务" --provider mock` 且不带 `--fixture`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 成功 run 打印 session id
- **WHEN** 用合法 fixture 执行 `minihns run -p "任务" --provider mock --fixture <f>`
- **THEN** 退出码为 0，stdout 含该 session id，且 `sessions/<session-id>.jsonl` 存在

### Requirement: run 参数记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的有效参数：`workspace`（绝对路径）、`provider`、`max_turns`、`append_system_prompt`，以及用户 prompt 原文。payload MUST NOT 重复携带 `schema_version`——版本事实只存在于每条记录的信封字段。M1 MUST NOT 依据 `--workspace` 做任何权限判定（围栏属后续里程碑）。

#### Scenario: payload 与命令行一致
- **WHEN** 执行 `minihns run -p "x" --max-turns 3 --workspace <dir>`
- **THEN** `session/start` 的 payload 里 `max_turns` 为 3、`workspace` 为 `<dir>` 的绝对路径、`prompt` 为 `x`

#### Scenario: 版本事实只在信封里
- **WHEN** 读取任一 session 日志的 `session/start` 记录
- **THEN** 该记录的信封 `schema_version` 为 1，且 payload 里没有 `schema_version` 键

### Requirement: --events jsonl 输出与日志逐行相同的事件流
系统 SHALL 在 `--events jsonl` 时把与日志文件内容逐行相同的事件 JSON 写到 stdout，使 CLI 输出本身可被重放；此时 stdout MUST NOT 额外打印 session id 行或其它非事件行（session id 由每条事件记录的 `session_id` 携带）。

#### Scenario: stdout 与日志逐行相等
- **WHEN** 一次成功的 run 带 `--events jsonl`
- **THEN** stdout 的行数与日志行数相同，且逐行解析后的对象相等

### Requirement: minihns replay 逐点重算折叠并断言相等
系统 SHALL 提供 `minihns replay <session-id>`：定位该 session 的日志，对日志里每一条 `context/assembled` 用它之前的日志前缀重算折叠结果，并与该记录的 payload 逐字段比对；重算的入参 MUST NOT 取自该点之后的事件。replay SHALL 打印逐回合序列与最后一次装配的上下文。replay MUST NOT 调用 Provider，MUST NOT 修改被重放的日志。重放失败是「重放不追加事件」的例外：`error/replay` 只写到 stderr，MUST NOT 被追加进被重放的日志（理由见 `docs/adr/0001-m1-simplifications.md`）。

#### Scenario: 每个装配点都重算相等
- **WHEN** 先跑一次 run，再对同一 session id 执行 replay
- **THEN** 日志里每条 `context/assembled` 都与其前缀重算结果逐字段相等，replay 以退出码 0 结束

#### Scenario: 装配点不一致是失败结果
- **WHEN** 被重放的日志里某条 `context/assembled` 与其前缀的重算结果不一致
- **THEN** replay 产出一条 `error/replay`（`code: REPLAY_MISMATCH`，含该记录的 `seq`）并以退出码 1 结束；被重放的日志本身不被改写

#### Scenario: replay 不重新调用模型
- **WHEN** 对一个用 mock fixture 跑出的 session 执行 replay
- **THEN** 过程中没有任何 Provider 调用发生

### Requirement: 未知 session id 是参数错误
当 `minihns replay` 的 session id 在 session 目录里没有对应日志文件时，系统 SHALL 以退出码 2 结束并在 stderr 输出 `SESSION_NOT_FOUND` 与所查找的路径。

#### Scenario: session id 不存在
- **WHEN** 执行 `minihns replay does-not-exist`
- **THEN** 退出码为 2，stderr 含 `SESSION_NOT_FOUND`

### Requirement: 退出码只取自固定表
系统 SHALL 只用固定退出码：0 成功、1 模型或内部错误、2 参数错误、3 围栏拒绝或审批被拒、4 上下文预算溢出、5 用户取消。除参数错误（发生在 session 开始之前）与日志不可写这两种情况外，每个非零退出 SHALL 有对应的 `error/*` 事件。M1 中 3 与 4 是保留码，MUST NOT 被产生。

#### Scenario: 每个失败都落在表内
- **WHEN** M1 的任一失败场景发生
- **THEN** 退出码属于 {1,2,3,4,5}，且退出码非 2 时日志里有 `error/*` 记录

#### Scenario: 日志不可写时只有 stderr
- **WHEN** session 目录不可写导致日志无法创建
- **THEN** `minihns run` 以退出码 1 结束、stderr 含 `LOG_WRITE_FAILED` 与失败路径，且不要求存在 `error/*` 事件

#### Scenario: Ctrl-C 是取消结果
- **WHEN** `minihns run` 运行期间收到 Ctrl-C（SIGINT）
- **THEN** 取消信号被置位，日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `session/end` 收尾，进程以退出码 5 结束且没有未捕获异常

#### Scenario: M1 不产生保留码
- **WHEN** 跑通 M1 的全部 mock 场景与失败场景
- **THEN** 没有任何 run 以 3 或 4 退出
