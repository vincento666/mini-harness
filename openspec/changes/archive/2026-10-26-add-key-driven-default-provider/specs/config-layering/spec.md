# config-layering Delta

## ADDED Requirements

### Requirement: provider 预设表填的是没被给的那几项
系统 SHALL 内置一张按 provider 名索引的端点预设表：`openai` = `base_url https://api.openai.com/v1`、`api_key_env MINIHNS_API_KEY`、`model` **无默认**；`deepseek` = `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`；`mock` 没有端点三项。预设 SHALL 只填 CLI 与配置文件都没给的那几项，MUST NOT 覆盖已给出的那一项。表里 MUST NOT 出现任何密钥的值，只有变量名。

#### Scenario: 预设不覆盖命令行给过的那一项
- **WHEN** 执行 `--provider openai --base-url http://127.0.0.1:8300/v1 --model q --api-key-env TEST_KEY_ENV`
- **THEN** 生效的端点三项就是给进去的这三项，预设一项都没用上

#### Scenario: 配置文件写 provider 时预设同样生效
- **WHEN** 配置文件写 `provider = "deepseek"`，未写 `base_url`、`model`、`api_key_env`
- **THEN** 端点三项取 `deepseek` 预设，`session/start` 的 payload 里 `base_url` 为 `https://api.deepseek.com`

#### Scenario: openai 预设不落到 deepseek 的默认
- **WHEN** `--provider openai` 且未给 `--base-url`
- **THEN** 生效的 `base_url` 是 `https://api.openai.com/v1`，不是 `https://api.deepseek.com`

#### Scenario: mock 预设没有端点三项
- **WHEN** 生效 provider 为 `mock`
- **THEN** `session/start` 的 payload 里没有 `base_url`、`model`、`api_key_env` 三格，与既有形状一致

## MODIFIED Requirements

### Requirement: 取值优先级是内置默认、配置文件、CLI flag
系统 SHALL 按「内置默认 < 配置文件 < CLI flag」派生每一项设置：配置文件里的值覆盖内置默认，命令行显式给出的值覆盖配置文件。判断「命令行显式给出」以该开关是否出现为准，MUST NOT 用「值恰好等于默认」来判断。`provider` 的内置默认由环境决定：CLI 与配置文件都没给 `provider` 时，`MINIHNS_API_KEY` 已设且非空则默认 `openai`，否则默认 `mock`。

#### Scenario: 配置文件覆盖内置默认
- **WHEN** 配置文件写 `max_turns = 3`，命令行未给 `--max-turns`
- **THEN** 本次运行的 `max_turns` 为 3

#### Scenario: 命令行覆盖配置文件
- **WHEN** 配置文件写 `max_turns = 3`，命令行给 `--max-turns 5`
- **THEN** 本次运行的 `max_turns` 为 5

#### Scenario: 与默认同值的命令行开关仍是显式值
- **WHEN** 配置文件写 `max_turns = 8`，命令行给 `--max-turns 8`（内置默认也是 8）
- **THEN** 本次运行的 `max_turns` 为 8，且它取自命令行这一层

#### Scenario: 有密钥时裸跑的默认 provider 是 openai
- **WHEN** `MINIHNS_API_KEY` 已设且非空，配置文件与命令行都没给 `provider`
- **THEN** 生效 provider 为 `openai`，且 `api_key_env` 默认为 `MINIHNS_API_KEY`

#### Scenario: 没有密钥时裸跑的默认 provider 仍是 mock
- **WHEN** `MINIHNS_API_KEY` 未设，配置文件与命令行都没给 `provider`
- **THEN** 生效 provider 为 `mock`，未给 `--fixture` 时以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与 `--fixture`

### Requirement: 端点必需项缺失当场失败
生效 provider 为 `openai` 或 `deepseek` 时，端点三项先由预设表补齐没被给的那几项（见「provider 预设表填的是没被给的那几项」）。补齐后仍缺 `model` 时系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT` 并指出 `--model`。`api_key_env` 指向的环境变量 SHALL 已设且非空；否则系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT` 并指出该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。这一条对取自配置文件与取自命令行的设置同样成立。

#### Scenario: 密钥变量未设
- **WHEN** `--provider openai` 且 `--api-key-env` 指向的变量未设
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与该变量名，且没有创建 session 日志

#### Scenario: 密钥变量设为空串
- **WHEN** `--provider openai` 且该变量被设为空字符串
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 配置文件指定的 provider 同样判
- **WHEN** 配置文件写 `provider = "openai"`，命令行未给 `--provider`，且 `api_key_env` 指向的变量未设
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: openai 预设缺 model 当场失败
- **WHEN** `--provider openai --api-key-env MINIHNS_API_KEY`（该变量已设）且未给 `--model`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `--model`，没有创建 session 日志，也没有发出请求
