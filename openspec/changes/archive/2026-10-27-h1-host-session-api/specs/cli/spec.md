# Spec Delta

## MODIFIED Requirements

### Requirement: run 参数记录进 session/start

系统 SHALL 在 `session/start` 的 payload 里记录本次运行的**有效参数**（层叠之后的结果）：`entry`（`run`、`chat`、`serve` 或 `host`，记录会话由哪个入口开始）、`workspace`（绝对路径）、`provider`、`max_turns`、`window`、`reserve`、`append_system_prompt`、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（装配筛出来并送给模型的工具名列表），以及用户 prompt 原文——`entry` 为 `chat` 或 `host` 时 prompt MUST 是空串，人话住在 `user/message` 里。`provider` 为 `openai` 时还 SHALL 记录 `base_url`、`model` 与 `api_key_env`（**环境变量的名字**，不是它的值）。payload MUST NOT 记录密钥的值或任何 Authorization 内容。payload MUST NOT 重复携带 `schema_version`。

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

#### Scenario: host 的入口与空 prompt
- **WHEN** 通过 `POST /sessions` 创建一个会话
- **THEN** `session/start` 的 payload 里 `entry` 为 `host`、`prompt` 为空串，其余设置字段与请求体/层叠后的有效值一致
