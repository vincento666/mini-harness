# 加一个 openrouter 端点预设

## Why

2026-11-24 人裁：功能验证、真实端点验收与调优统一走 OpenRouter 的 `qwen/qwen3.8-27b`（`docs/reference/verification-endpoint.md`）。现在每次都要手打三项——`--base-url https://openrouter.ai/api/v1`、`--model qwen/qwen3.8-27b`、`--api-key-env OPENROUTER_API_KEY`——漏一项就在开跑前失败：`--model` 缺失会 `INVALID_ARGUMENT`，`--api-key-env` 缺失则会去读 `MINIHNS_API_KEY`。

provider 名在本项目里就是**端点预设**（ADR-0027），预设表已内置 `openai` 与 `deepseek` 两套，缺的正是 OpenRouter 这一套。

## What Changes

- `PROVIDER_PRESETS` 增加 `openrouter`：`base_url https://openrouter.ai/api/v1`、`model qwen/qwen3.8-27b`、`api_key_env OPENROUTER_API_KEY`。`PROVIDER_NAMES` 同步。
- `--provider` 接受第四个取值；`minihns run --provider openrouter` 即可跑，不必再给三项覆盖。预设仍只填**没被给**的那几项（`--model` 显式给了就用你的）。
- 仓库根放一份 `mini.config.toml`（`.gitignore` 已忽略），写 `provider = "openrouter"` 一行，让「在这个仓库里不传任何 provider/model 相关 flag」也走 qwen——配置文件只在 workspace 是仓库根时生效，这是 `discover_config` 的既有规则，不改。

## Non-goals

- **不改默认 provider**：不传 `--provider`、配置文件也没写时，仍按既有规则——`MINIHNS_API_KEY` 在场即 `openai`，否则 `mock`。默认值改动会影响所有入口与全部黑盒用例的默认路径，那是另一件事。
- 不做多模型路由、fallback 或重试策略（`AGENTS.md` 的「始终不做」）。
- 不把密钥写进任何文件；预设只记变量名。

## Impact

- 代码：`src/mini_harness/loop/settings.py`（预设表与词表）、`src/mini_harness/cli/main.py`（`--provider` 的 help 文案）。
- 规格：`cli`（接受的 provider 取值与密钥变量）、`config-layering`（预设表）。
- 测试：`tests/test_config_presets.py` 的预设表判据对每个名字都跑，新增名字自动受检；补一条「`--provider openrouter` 三项都由预设补齐」。
- 文档：`docs/reference/verification-endpoint.md` §2 现在说「openrouter 没有自己的预设名」，需要改口。
