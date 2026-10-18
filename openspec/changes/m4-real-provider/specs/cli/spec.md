# Spec Delta

## ADDED Requirements

### Requirement: provider 选择与密钥
系统 SHALL 只接受 `--provider mock` 与 `--provider openai`，其它取值 SHALL 以退出码 2 结束、stderr 含 `UNKNOWN_PROVIDER`，且 MUST NOT 创建 session 日志。`--provider openai` 时：若 `DEEPSEEK_API_KEY` 未设且 `--base-url` 指向的 host 不是 loopback（`127.0.0.1`、`localhost`、`::1`），系统 SHALL 以退出码 2 结束、stderr 含 `MISSING_API_KEY` 与所查的环境变量名，且 MUST NOT 创建 session 日志。loopback 的 base-url MUST NOT 要求密钥。`--provider mock` 的路径 MUST NOT 发起任何网络请求。

#### Scenario: 未知 provider
- **WHEN** 执行 `minihns run -p "x" --provider claude`
- **THEN** 退出码为 2，stderr 含 `UNKNOWN_PROVIDER`，且没有 session 日志

#### Scenario: 默认 base-url 缺密钥
- **WHEN** `DEEPSEEK_API_KEY` 未设，执行 `minihns run -p "x" --provider openai --model m`
- **THEN** 退出码为 2，stderr 含 `MISSING_API_KEY` 与 `DEEPSEEK_API_KEY`，且没有 session 日志

#### Scenario: loopback 端点不需要密钥
- **WHEN** `DEEPSEEK_API_KEY` 未设，执行 `minihns run -p "x" --provider openai --base-url http://127.0.0.1:8088/v1 --model m`
- **THEN** 请求被发出（不因缺密钥被拒），退出码不因此为 2

## MODIFIED Requirements

### Requirement: minihns run 一次性完成一个 session
系统 SHALL 提供 `minihns run -p "任务"`：一次调用跑完一个 session 并返回退出码；参数为 `-p/--prompt`（必填、非空）、`--workspace`（默认当前目录）、`--session-dir`、`--provider`（默认 `mock`）、`--fixture`、`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、`--max-turns`、`--append-system-prompt`、`--events jsonl`、`--sandbox`（默认 `workspace-write`）、`--yes`（开关）。`--provider mock` 时 `--fixture` MUST 同时给出；`--provider openai` 时 `--fixture` MUST NOT 被使用。成功时 stdout SHALL 打印 session id。

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
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的有效参数：`workspace`（绝对路径）、`provider`、`max_turns`、`append_system_prompt`、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（本次注册并送给模型的工具名列表），以及用户 prompt 原文；`provider` 为 `openai` 时还 SHALL 记录 `base_url` 与 `model`。payload MUST NOT 记录 API key 或任何 Authorization 内容。payload MUST NOT 重复携带 `schema_version`——版本事实只存在于每条记录的信封字段。

#### Scenario: payload 与命令行一致
- **WHEN** 执行 `minihns run -p "x" --max-turns 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `max_turns` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`

#### Scenario: 工具名列表进 payload
- **WHEN** 执行一次 run
- **THEN** `session/start` 的 payload 里 `tools` 含 `read`、`write`、`edit`、`glob`、`grep` 五个名字

#### Scenario: 版本事实只在信封里
- **WHEN** 读取任一 session 日志的 `session/start` 记录
- **THEN** 该记录的信封 `schema_version` 为 1，且 payload 里没有 `schema_version` 键

#### Scenario: openai 的端点与模型进 payload
- **WHEN** 执行 `minihns run -p "x" --provider openai --base-url http://127.0.0.1:8088/v1 --model qwen3.8-27b`
- **THEN** `session/start` 的 payload 里 `provider` 为 `openai`、`base_url` 为所给地址、`model` 为 `qwen3.8-27b`，且 payload 里没有任何密钥字段
