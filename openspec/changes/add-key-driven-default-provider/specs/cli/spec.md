# cli Delta

## ADDED Requirements

### Requirement: --help 写出设置类 flag 的默认值
`minihns run --help`、`minihns chat --help` 与 `minihns serve --help` SHALL 在设置类 flag 的说明里写出该项当前的默认，且 MUST NOT 写出任何密钥的值。`--provider` 那一行 SHALL 写明生效规则而不是一个固定词：未给 `--provider` 时按 `MINIHNS_API_KEY` 是否已设且非空选 `openai` 或 `mock`。`--api-key-env` 那一行 SHALL 写明默认变量名随预设而变。

#### Scenario: --provider 那行写着生效规则
- **WHEN** 执行 `minihns chat --help`
- **THEN** 输出里 `--provider` 的说明同时含 `mock`、`openai`、`deepseek` 与 `MINIHNS_API_KEY` 这四个词

#### Scenario: 默认值说明里没有密钥值
- **WHEN** `MINIHNS_API_KEY` 已设且执行任一 `--help`
- **THEN** 输出里不含该变量的值，只含变量名

## MODIFIED Requirements

### Requirement: provider 选择与密钥是装配的必需项
系统 SHALL 接受 `mock`、`openai`、`deepseek` 三个 provider 取值，其它取值 SHALL 以退出码 2 结束、stderr 含 `UNKNOWN_PROVIDER`，且 MUST NOT 创建 session 日志。`openai` 与 `deepseek` 都由 openai 兼容适配器执行，两者的差别只在预设的端点三项默认（见 `config-layering` 的「provider 预设表填的是没被给的那几项」）。密钥 SHALL 只从 `api_key_env` 指定的环境变量读取，该项未显式给出时的默认变量名随预设而变：`openai` 预设是 `MINIHNS_API_KEY`、`deepseek` 预设是 `DEEPSEEK_API_KEY`；该变量未设或为空时系统 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。密钥 MUST NOT 出现在命令行参数、stdout、stderr、session 日志或 `session/start` 的 payload 里。

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
