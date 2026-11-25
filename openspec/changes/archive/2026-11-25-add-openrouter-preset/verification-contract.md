# 验证契约

**日期**：2026-11-25（补记：本 change 的 apply 期没有落契约文件，归档前按已完成的实现与判据回写，不新增行为）。

## 目标

加一个 `openrouter` 端点预设：`base_url https://openrouter.ai/api/v1`、`model qwen/qwen3.8-27b`、`api_key_env OPENROUTER_API_KEY`。于是功能验证不必每次手打三项，也不会因为漏一项在开跑前失败。

## 可观察行为

1. **预设补齐三项**：`--provider openrouter` 且不给 `--model` / `--base-url` / `--api-key-env` 时，三项都来自预设。
2. **只填没给的**：显式给的那一项 MUST 胜出，预设 MUST NOT 覆盖它（flag 与配置文件两个来源都一样）。
3. **词表与预设表同集合**：`PROVIDER_NAMES` 与 `PROVIDER_PRESETS` 的键集合相等，每个名字都有 `base_url` 与 `api_key_env` 两个必需槽（`mock` 允许全空）。
4. **仓库根走 openrouter**：仓库根的 `mini.config.toml` 写 `provider = "openrouter"`，在仓库根不传任何端点 flag 也走 qwen。
5. **默认 provider 规则不变**：不传 `--provider`、配置也没写时，仍是「`MINIHNS_API_KEY` 在场即 `openai`，否则 `mock`」。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | `test_the_openrouter_preset_carries_the_verification_model`（`tests/test_config_presets.py`）；真实端点场次 2 的四格读数 |
| 2 | `test_a_given_model_beats_the_openrouter_default`、`test_the_preset_never_overrides_a_flag_that_was_given`、`test_the_preset_never_overrides_a_model_the_config_file_gave` |
| 3 | `test_every_provider_name_has_a_preset_with_the_two_required_slots` |
| 4 | `test_a_config_file_provider_gets_its_own_preset`；真实端点场次 1（仓库根、无 flag，四格是 openrouter / qwen / openrouter.ai / `OPENROUTER_API_KEY`） |
| 5 | `test_the_key_present_makes_openai_the_builtin_default`、`test_no_key_means_the_builtin_default_is_still_mock`、`test_a_given_provider_is_not_overridden_by_the_key` |

真实端点两场（`docs/verification/add-openrouter-preset-real-endpoint.md`，2026-11-24）：仓库根无 flag 与只给 `--provider openrouter` 两种形状的四格完全相同。UAT 两场（`docs/verification/add-openrouter-preset-uat.md`，agent 代跑）另验了「显式换模型」时预设不覆盖。

## 坏法清单（变异种子，2026-11-25 实跑）

1. **预设模型写错**：`qwen/qwen3.8-27b` 改成 `qwen/qwen3.8-flash` → 行为 1 红（`test_the_openrouter_preset_carries_the_verification_model`）。
2. **词表少一个名字**：`PROVIDER_NAMES` 去掉 `openrouter` → 行为 3 红（键集合不等）。
3. **预设覆盖显式值**：`values[name] = fallback if from_layer is None else from_layer` 改成优先 `fallback` → 行为 2 红（两条判据）。

## 不验什么

- **不改默认 provider**：默认值仍是 `MINIHNS_API_KEY` 决定 `openai` / `mock`。改动它会影响所有入口与黑盒默认路径，属另一件事。
- **不做多模型路由、fallback 或重试策略**（`AGENTS.md` 的「始终不做」）。
- **不在仓库里存密钥**：预设只记变量名，值仍在环境变量。
