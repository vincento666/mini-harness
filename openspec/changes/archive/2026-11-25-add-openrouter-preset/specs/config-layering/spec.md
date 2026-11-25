# Spec Delta: config-layering

## MODIFIED Requirements

### Requirement: provider 预设表填的是没被给的那几项

系统 SHALL 内置一张按 provider 名索引的端点预设表：`openai` = `base_url https://api.openai.com/v1`、`api_key_env MINIHNS_API_KEY`、`model` **无默认**；`deepseek` = `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`；`openrouter` = `https://openrouter.ai/api/v1` / `qwen/qwen3.8-27b` / `OPENROUTER_API_KEY`；`mock` 没有端点三项。预设 SHALL 只填 CLI 与配置文件都没给的那几项，MUST NOT 覆盖已给出的那一项。表里 MUST NOT 出现任何密钥的值，只有变量名。

#### Scenario: 预设不覆盖命令行给过的那一项
- **WHEN** 执行 `--provider openai --base-url http://127.0.0.1:8300/v1 --model q --api-key-env TEST_KEY_ENV`
- **THEN** 生效的端点三项就是给进去的这三项，预设一项都没用上

#### Scenario: 配置文件写 provider 时预设同样生效
- **WHEN** 配置文件写 `provider = "deepseek"`，未写 `base_url`、`model`、`api_key_env`
- **THEN** 端点三项取 `deepseek` 预设，`session/start` 的 payload 里 `base_url` 为 `https://api.deepseek.com`

#### Scenario: openai 预设不落到 deepseek 的默认
- **WHEN** `--provider openai` 且未给 `--base-url`
- **THEN** 生效的 `base_url` 是 `https://api.openai.com/v1`，不是 `https://api.deepseek.com`

#### Scenario: 配置文件只写一行 provider 就够
- **WHEN** 配置文件只写 `provider = "openrouter"`，三项端点都没写
- **THEN** 生效的 `base_url`、`model`、`api_key_env` 全取 `openrouter` 预设（`https://openrouter.ai/api/v1` / `qwen/qwen3.8-27b` / `OPENROUTER_API_KEY`）

#### Scenario: mock 预设没有端点三项
- **WHEN** 生效 provider 为 `mock`
- **THEN** `session/start` 的 payload 里没有 `base_url`、`model`、`api_key_env` 三格，与既有形状一致
