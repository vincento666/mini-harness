# Spec Delta

## MODIFIED Requirements

### Requirement: minihns run 一次性完成一个 session
系统 SHALL 提供 `minihns run -p "任务"`：一次调用跑完一个 session；参数：`-p/--prompt`（必填、非空）、`--workspace`（默认当前目录）、`--session-dir`、`--provider`（默认 `mock`）、`--fixture`、`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、`--api-key-env`（默认 `DEEPSEEK_API_KEY`）、`--max-turns`、`--window`（默认 128000）、`--reserve`（默认 8192）、`--append-system-prompt`、`--events jsonl`、`--sandbox`（默认 `workspace-write`）、`--yes`。`--provider mock` 时 `--fixture` MUST 同时给出，`openai` 时 MUST NOT 被使用。成功时 stdout 打印 session id。

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
- **WHEN** 用合法 fixture 执行 `minihns run -p "任务" --provider mock --fixture <f> --yes`
- **THEN** 退出码为 0，stdout 含该 session id，且 `sessions/<session-id>.jsonl` 存在

#### Scenario: openai 带 fixture 是参数错误
- **WHEN** 执行 `minihns run -p "任务" --provider openai --fixture <f>`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

### Requirement: run 参数记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的有效参数：`workspace`（绝对路径）、`provider`、`max_turns`、`window`、`reserve`、`append_system_prompt`、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（本次注册并送给模型的工具名列表），以及用户 prompt 原文；`provider` 为 `openai` 时还 SHALL 记录 `base_url`、`model` 与 `api_key_env`（**环境变量的名字**，不是它的值）。payload MUST NOT 记录密钥的值或任何 Authorization 内容。payload MUST NOT 重复携带 `schema_version`——版本事实只存在于每条记录的信封字段。

#### Scenario: payload 与命令行一致
- **WHEN** 执行 `minihns run -p "x" --max-turns 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `max_turns` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`

#### Scenario: 工具名列表进 payload
- **WHEN** 执行一次 run
- **THEN** `session/start` 的 payload 里 `tools` 含 `read`、`write`、`edit`、`glob`、`grep` 五个名字

#### Scenario: 版本事实只在信封里
- **WHEN** 读取任一 session 日志的 `session/start` 记录
- **THEN** 该记录的信封 `schema_version` 为 1，且 payload 里没有 `schema_version` 键

#### Scenario: openai 的端点、模型与密钥变量名进 payload
- **WHEN** 执行 `minihns run -p "x" --provider openai --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_KEY`，且 `MINIHNS_KEY` 已设
- **THEN** `session/start` 的 payload 里 `provider` 为 `openai`、`base_url` 为所给地址、`model` 为 `qwen3.8-flash-next-iq3_xxs`、`api_key_env` 为 `MINIHNS_KEY`，且整份日志里找不到 `MINIHNS_KEY` 的值

#### Scenario: 窗口与预留进 payload
- **WHEN** 执行 `minihns run -p "x" --window 4000 --reserve 500`
- **THEN** `session/start` 的 payload 里 `window` 为 4000、`reserve` 为 500

### Requirement: 退出码只取自固定表
系统 SHALL 只用固定退出码：0 成功、1 模型或内部错误、2 参数错误、3 围栏拒绝或审批被拒、4 上下文预算溢出、5 用户取消。除参数错误（发生在 session 开始之前）、日志不可写、以及 replay 不一致这三种情况外，每个非零退出 SHALL 有对应的 `error/*` 事件。3 与 4 都是可达码：`stop_reason: FENCE_DENIED` 映射到 3，`stop_reason: CONTEXT_WINDOW_EXCEEDED` 映射到 4。

#### Scenario: 每个失败都落在表内
- **WHEN** M2 的任一失败场景发生
- **THEN** 退出码属于 {1,2,3,4,5}，且退出码非 2 时日志里有 `error/*` 记录

#### Scenario: 围栏拒绝映射到退出码 3
- **WHEN** 一次 run 以 `stop_reason: FENCE_DENIED` 结束
- **THEN** 退出码为 3，且日志里有 `error/fence` 记录

#### Scenario: 日志不可写时只有 stderr
- **WHEN** session 目录不可写导致日志无法创建
- **THEN** `minihns run` 以退出码 1 结束、stderr 含 `LOG_WRITE_FAILED` 与失败路径，且不要求存在 `error/*` 事件

#### Scenario: Ctrl-C 是取消结果
- **WHEN** `minihns run` 运行期间收到 Ctrl-C（SIGINT）
- **THEN** 取消信号被置位，日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `session/end` 收尾，进程以退出码 5 结束且没有未捕获异常

#### Scenario: M1 不产生保留码
- **WHEN** 跑通 M1 的既有 mock 场景（不含会改动的工具）与既有失败场景
- **THEN** 没有任何 run 以 3 或 4 退出

#### Scenario: M2 不产生保留码 4
- **WHEN** 跑完 M2 新增的全部成功与失败场景
- **THEN** 只有围栏或审批被拒的场景以 3 退出，没有任何 run 以 4 退出

#### Scenario: 预算溢出映射到退出码 4
- **WHEN** 一次 run 以 `stop_reason: CONTEXT_WINDOW_EXCEEDED` 结束
- **THEN** 退出码为 4，且日志里有 `error/context` 记录

### Requirement: minihns replay 逐点重算折叠并断言相等
系统 SHALL 提供 `minihns replay <session-id>`：定位该 session 的日志，对日志里每一条 `context/assembled` 用它之前的日志前缀重算折叠结果，并与该记录的 payload 逐字段比对；重算的入参 MUST NOT 取自该点之后的事件，且 MUST 全部可从该前缀派生（含当时的工具名列表）。replay SHALL 打印逐回合序列与最后一次装配的上下文；没有任何装配点时 SHALL 打印一行说明并以退出码 0 结束。replay MUST NOT 调用 Provider，MUST NOT 修改被重放的日志，也 MUST NOT 执行任何工具。重放不一致时 MUST NOT 往被重放的日志追加任何事件（含 `error/*`）：只往 stderr 写一行 `REPLAY_MISMATCH: <detail>` 并以退出码 1 结束。`error/replay` 不在事件词表里、从不进日志，是「每个非零退出都有 `error/*`」的例外之一（见 ADR-0001）。

#### Scenario: 每个装配点都重算相等
- **WHEN** 先跑一次带工具调用与审批记录的 run，再对同一 session id 执行 replay
- **THEN** 日志里每条 `context/assembled` 都与其前缀的重算结果逐字段相等，replay 以退出码 0 结束

#### Scenario: 装配点不一致是失败结果
- **WHEN** 被重放的日志里某条 `context/assembled` 与其前缀的重算结果不一致
- **THEN** replay 往 stderr 写一行 `REPLAY_MISMATCH: <detail>`（含该记录的 `seq`）并以退出码 1 结束；被重放的日志既不被改写、也不被追加

#### Scenario: replay 不重新调用模型
- **WHEN** 对一个用 mock fixture 跑出的 session 执行 replay
- **THEN** 过程中没有任何 Provider 调用发生，且工作区里没有任何文件被创建或修改（replay 也不执行工具）

#### Scenario: 没有装配点的日志不是重放不一致
- **WHEN** 被重放的日志里没有任何 `context/assembled`（第一次装配之前就溢出或取消收尾）
- **THEN** replay 打印逐回合序列与一行「没有装配点」的说明、不打印最后一次装配的上下文，并以退出码 0 结束
