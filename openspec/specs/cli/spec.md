# cli Specification

## Purpose

定义 M1 的命令行外部行为：`minihns run` 与 `minihns replay` 接受什么参数、产出什么可观察输出、失败时返回哪个退出码。

## Requirements

### Requirement: minihns run 一次性完成一个 session
`minihns run` SHALL 一次调用跑完一个 session；参数：`-p/--prompt`（必填、非空）、`--config`、`--workspace`（默认当前目录）、`--session-dir`、`--provider`（默认 `mock`）、`--fixture`、`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、`--api-key-env`（默认 `DEEPSEEK_API_KEY`）、`--max-turns`、`--window`（默认 128000）、`--reserve`（默认 8192）、`--append-system-prompt`、`--events jsonl`、`--sandbox`（默认 `workspace-write`）、`--yes`。`--provider mock` 时 `--fixture` MUST 同时给出，`openai` 时 MUST NOT 被使用。成功时 stdout 打印 session id。

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

#### Scenario: 配置文件里的设置生效于一次 run
- **WHEN** 工作区根有一份写满设置的 `mini.config.toml`，用 mock fixture 执行 `minihns run -p "任务" --provider mock --fixture <f> --yes`
- **THEN** 退出码为 0，且 `session/start` 的 payload 取自配置文件里的值而不是内置默认

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

### Requirement: --events jsonl 输出与日志逐行相同的事件流
系统 SHALL 在 `--events jsonl` 时把与日志文件内容逐行相同的事件 JSON 写到 stdout，使 CLI 输出本身可被重放；此时 stdout MUST NOT 额外打印 session id 行或其它非事件行（session id 由每条事件记录的 `session_id` 携带）。

#### Scenario: stdout 与日志逐行相等
- **WHEN** 一次成功的 run 带 `--events jsonl`
- **THEN** stdout 的行数与日志行数相同，且逐行解析后的对象相等

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

### Requirement: 未知 session id 是参数错误
当 `minihns replay` 的 session id 在 session 目录里没有对应日志文件时，系统 SHALL 以退出码 2 结束并在 stderr 输出 `SESSION_NOT_FOUND` 与所查找的路径。

#### Scenario: session id 不存在
- **WHEN** 执行 `minihns replay does-not-exist`
- **THEN** 退出码为 2，stderr 含 `SESSION_NOT_FOUND`

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

### Requirement: provider 选择与密钥是装配的必需项
系统 SHALL 接受 `mock`、`openai`、`deepseek` 三个 provider 取值，其它取值 SHALL 以退出码 2 结束、stderr 含 `UNKNOWN_PROVIDER`，且 MUST NOT 创建 session 日志。密钥 SHALL 只从 `api_key_env` 指定的环境变量读取；该项未显式给出时默认变量名随预设而变（`openai` 是 `MINIHNS_API_KEY`、`deepseek` 是 `DEEPSEEK_API_KEY`），未设或为空时 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。密钥 MUST NOT 出现在命令行参数、stdout、stderr、session 日志或 `session/start` 的 payload 里。

#### Scenario: 未知 provider
- **WHEN** 执行 `minihns run -p "x" --provider claude`
- **THEN** 退出码为 2，stderr 含 `UNKNOWN_PROVIDER`，且没有 session 日志

#### Scenario: 密钥变量未设是参数错误
- **WHEN** `--api-key-env` 指向的环境变量未设，执行 `--provider openai` 的 run
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与该变量名，没有 session 日志，也没有发出请求

#### Scenario: 密钥只进请求头
- **WHEN** `--api-key-env` 指向的变量已设，一次 openai run 跑完
- **THEN** 请求带上了该密钥，而 stdout、stderr 与该 session 的日志里都不含它

#### Scenario: deepseek 预设走自己的默认变量
- **WHEN** `MINIHNS_API_KEY` 未设、`DEEPSEEK_API_KEY` 已设，执行 `minihns run -p "x" --provider deepseek`
- **THEN** 装配成功，`session/start` 的 payload 里 `provider` 为 `deepseek`，且请求打到 `https://api.deepseek.com`

### Requirement: 配置层失败都在 session 开始之前
配置文件非法、`--config` 指向的路径不存在、工具白名单里的未知名、以及 openai 路径缺失密钥时，系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT`，且 MUST NOT 创建 session 日志、MUST NOT 追加任何事件。这一类失败与既有的参数错误同形，是「每个非零退出都有 `error/*`」的例外之一。

#### Scenario: 配置层失败没有日志
- **WHEN** 上述任一配置层失败发生
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT`，且 session 目录里没有任何新文件

### Requirement: 非零退出在 stderr 说清楚
一次性入口（`minihns run` 与 `minihns serve --http`）以非 0 退出时，系统 SHALL 往 stderr 打印一行，含造成这次退出的失败码。当该失败结果带非空 `detail` 时那一行 SHALL 含那句 `detail`；当 `detail` 为空时那一行 MUST NOT 以冒号结尾、MUST NOT 带空说明（只有失败码本身）。这一行 MUST NOT 写进事件日志，也 MUST NOT 出现在 stdout。`minihns chat` 的段级收尾不适用这一条（会话收尾退出码是 0，见 `chat-repl`）。

#### Scenario: 取消收尾的 serve 那一行不是悬空冒号
- **WHEN** `minihns serve --http` 的会话进行中收到取消信号，进程以退出码 5 结束
- **THEN** stderr 里有一行含 `ABORTED`，该行不以冒号结尾，日志以 `error/abort` 收尾

#### Scenario: 有 detail 时带上那句说明
- **WHEN** `minihns run` 以 `stop_reason: CONTEXT_WINDOW_EXCEEDED` 结束、造成它的失败结果带着「无可遮蔽的内容，预算读数 <n> 已超过触发线 <m>」
- **THEN** stderr 那一行含 `CONTEXT_WINDOW_EXCEEDED` 与那句非空 `detail`，退出码为 4

#### Scenario: 那一行不是日志的投影
- **WHEN** 一次性入口以非 0 退出
- **THEN** stdout 上没有那一行，该会话的日志里也没有为打印它而存在的记录

### Requirement: 运行平台事实记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的平台事实 `platform`：`os`（运行所在操作系统的名字）与 `shell`（`bash` 工具实际用来执行命令的 shell 形态）。`run`、`chat`、`serve` 三个入口 SHALL 都记录。`platform` MUST NOT 是命令行开关或配置文件里的键，也 MUST NOT 记录密钥、环境变量值或用户名。

#### Scenario: run 记下 os 与 shell
- **WHEN** 执行 `minihns run -p "x" --workspace <dir>`
- **THEN** `session/start` 的 payload 里 `platform` 含非空的 `os` 与 `shell`，且 `shell` 与这份日志里 `bash` 实际执行命令用的形态一致

#### Scenario: chat 与 serve 同样记录
- **WHEN** 分别跑一次 `chat`（EOF 退出）与一次 `serve`
- **THEN** 两份日志的 `session/start` payload 里都有 `platform`，且两处的 `os` 与 `shell` 相同

#### Scenario: 平台事实不来自可配置性
- **WHEN** 不给任何命令行开关、也不给配置文件
- **THEN** `session/start` 的 payload 里 `platform` 仍非空，且 `os` 与 `shell` 都有值

### Requirement: --help 写出设置类 flag 的默认值
`minihns run --help`、`minihns chat --help` 与 `minihns serve --help` SHALL 在设置类 flag 的说明里写出该项当前的默认，且 MUST NOT 写出任何密钥的值。`--provider` 那一行 SHALL 写明生效规则而不是一个固定词：未给 `--provider` 时按 `MINIHNS_API_KEY` 是否已设且非空选 `openai` 或 `mock`。`--api-key-env` 那一行 SHALL 写明默认变量名随预设而变。

#### Scenario: --provider 那行写着生效规则
- **WHEN** 执行 `minihns chat --help`
- **THEN** 输出里 `--provider` 的说明同时含 `mock`、`openai`、`deepseek` 与 `MINIHNS_API_KEY` 这四个词

#### Scenario: 默认值说明里没有密钥值
- **WHEN** `MINIHNS_API_KEY` 已设且执行任一 `--help`
- **THEN** 输出里不含该变量的值，只含变量名

#### Scenario: 数值与档位那几行写着内置默认
- **WHEN** 执行 `minihns run --help`
- **THEN** `max-turns`、`window`、`reserve`、`sandbox` 四行的说明里各写出该项的内置默认，且写出的值就是内置默认本身，不是 help 里另抄的一份数字
