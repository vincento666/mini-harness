# 变异测试：add-openrouter-preset

**日期**：2026-11-25。
**基线**：`tests/test_config_presets.py` 12 passed；加 `tests/test_cli_provider.py` 共 34 passed。
**方法**：逐条改坏实现 → 跑相关测试 → 记录哪些变红 → 用 Edit 反向改回 → 确认回到基线（`git diff --stat src/` 为空）。

## 变异

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | 预设模型写错 | `settings.py` 里 openrouter 的 model 由 `qwen/qwen3.8-27b` 改成 `qwen/qwen3.8-flash` | **杀死 1 条**：`test_the_openrouter_preset_carries_the_verification_model` |
| M2 | 词表少一个名字 | `PROVIDER_NAMES` 去掉 `"openrouter"` | **杀死 1 条**：`test_every_provider_name_has_a_preset_with_the_two_required_slots`（断言 `PROVIDER_NAMES` 与预设表键集合相等，左多一项 `openrouter`） |
| M3 | 预设覆盖显式值 | `layering.py` 的 `values[name] = fallback if from_layer is None else from_layer` 改成 `fallback if fallback is not None else from_layer` | **杀死 2 条**：`test_a_given_model_beats_the_openrouter_default`、`test_the_preset_never_overrides_a_flag_that_was_given` |

## 还原

三条都用 Edit 反向改回；`git diff --stat src/` 为空，相关两文件 `34 passed`，确认回到基线。

## 覆盖缺口

- **仓库根的 `mini.config.toml` 本身**没有判据：它是被 `.gitignore` 忽略的本机文件，写与不写不影响代码。行为由 `test_a_config_file_provider_gets_its_own_preset`（配置文件给 provider）覆盖，真实端点场次 1 用的是实际仓库根文件。
- **默认 provider 规则**未做变异：M2 只改词表不影响 `_provider_of` 的既有分支；该行为由 `test_the_key_present_makes_openai_the_builtin_default` 等三条判据守着，且本 change 明写不改默认值。
