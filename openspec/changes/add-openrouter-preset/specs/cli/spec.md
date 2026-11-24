# Spec Delta: cli

## MODIFIED Requirements

### Requirement: provider 选择与密钥是装配的必需项

系统 SHALL 接受 `mock`、`openai`、`deepseek`、`openrouter` 四个 provider 取值，其它取值 SHALL 以退出码 2 结束、stderr 含 `UNKNOWN_PROVIDER`，且 MUST NOT 创建 session 日志。密钥 SHALL 只从 `api_key_env` 指定的环境变量读取；该项未显式给出时默认变量名随预设而变（`openai` 是 `MINIHNS_API_KEY`、`deepseek` 是 `DEEPSEEK_API_KEY`、`openrouter` 是 `OPENROUTER_API_KEY`），未设或为空时 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。密钥 MUST NOT 出现在命令行参数、stdout、stderr、session 日志或 `session/start` 的 payload 里。

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

#### Scenario: openrouter 只要一个 flag
- **WHEN** `OPENROUTER_API_KEY` 已设，执行 `minihns run -p "x" --provider openrouter`，不给 `--base-url`、`--model`、`--api-key-env`
- **THEN** 装配成功，`session/start` 的 payload 里 `provider` 为 `openrouter`、`model` 为 `qwen/qwen3.8-27b`、`base_url` 为 `https://openrouter.ai/api/v1`，请求打到 OpenRouter

#### Scenario: openrouter 的默认模型可被覆盖
- **WHEN** `--provider openrouter --model 别的模型`
- **THEN** 生效的 `model` 是显式给的那个；`base_url` 与 `api_key_env` 仍由预设补齐
