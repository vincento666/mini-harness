## MODIFIED Requirements

### Requirement: run 参数记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的**有效参数**（层叠之后的结果）：`entry`（`run`、`chat` 或 `serve`，记录会话由哪个入口开始）、`workspace`（绝对路径）、`provider`、`max_turns`、`window`、`reserve`、`append_system_prompt`、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（装配筛出来并送给模型的工具名列表），以及用户 prompt 原文——`entry` 为 `chat` 时 prompt MUST 是空串，人话住在 `user/message` 里。`provider` 为 `openai` 时还 SHALL 记录 `base_url`、`model` 与 `api_key_env`（**环境变量的名字**，不是它的值）。payload MUST NOT 记录密钥的值或任何 Authorization 内容。payload MUST NOT 重复携带 `schema_version`。

#### Scenario: payload 与命令行一致
- **WHEN** 执行 `minihns run -p "x" --max-turns 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `entry` 为 `run`、`max_turns` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`

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

#### Scenario: 同一命令行在两份配置下 payload 不同
- **WHEN** 同一份命令行分别在「工作区根写着 `max_turns = 2` 与 `tools = ["read"]`」和「没有配置文件」两种情况下执行
- **THEN** 两份日志的 `session/start` payload 里 `max_turns` 分别为 2 与 8、`tools` 分别只含 `read` 与含全部六个内置工具名

### Requirement: 退出码只取自固定表
系统 SHALL 只用固定退出码：0 成功、1 模型或内部错误、2 参数错误、3 围栏拒绝或审批被拒、4 上下文预算溢出、5 用户取消。除参数错误（发生在 session 开始之前）、日志不可写、以及 replay 不一致这三种情况外，每个非零退出 SHALL 有对应的 `error/*` 事件。3 与 4 都是可达码：`stop_reason: FENCE_DENIED` 映射到 3，`stop_reason: CONTEXT_WINDOW_EXCEEDED` 映射到 4。一次性入口（`minihns run` 与 `minihns serve --http`）里会话收尾就是这次进程的退出码；`minihns chat` 里段级收尾（`ABORTED`、`FENCE_DENIED`、`MAX_TURNS`、`CONTEXT_WINDOW_EXCEEDED`、`PROVIDER_ERROR`）MUST NOT 结束进程，会话收尾（EOF 或提示符上取消）的退出码 SHALL 是 0。

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

#### Scenario: chat 的正常收尾是 0
- **WHEN** 一次 `minihns chat` 以 EOF 结束，且其中某个段以 `FENCE_DENIED` 收尾
- **THEN** 进程退出码为 0，日志里 `error/fence` 在盘上而 `session/end` 的 `stop_reason` 是 `MODEL_COMPLETED`
