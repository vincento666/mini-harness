# 任务

## 1. 实现

- [x] 1.1 `loop/settings.py`：`PROVIDER_PRESETS` 加 `openrouter`（三项齐全），`PROVIDER_NAMES` 同步
- [x] 1.2 `cli/main.py`：`--provider` 的 help 从「mock / openai / deepseek」改成含 `openrouter`
- [x] 1.3 判据：`tests/test_config_presets.py` 补一条——`layer_settings` 在 `provider="openrouter"` 且三项都没给时，`base_url` / `model` / `api_key_env` 全由预设补齐；显式给了 `model` 时不被预设覆盖

## 2. 本地默认

- [x] 2.1 仓库根写 `mini.config.toml`（`provider = "openrouter"`，已被 `.gitignore` 忽略）；`.tmp` 之外不留第二份
- [x] 2.2 验证：在仓库根不带任何 provider/model flag 跑一次 `run`，`session/start` 的 `model` 是 `qwen/qwen3.8-27b`

## 3. 收尾（ADR-0024 / ADR-0025 的四项）

- [x] 3.1 真实端点验收：两场都过（仓库根无 flag、另开工作区只给 `--provider openrouter`），`session/start` 四格齐全；记录在 `docs/verification/add-openrouter-preset-real-endpoint.md`
- [x] 3.2 UAT：**2026-11-24 agent 代跑（用户明确指示）**，两场全过——仓库根无端点 flag 时四格为 openrouter/qwen/qwen3.8-27b/…；`--model qwen/qwen3.8-flash` 时只有 model 被覆盖。记录在 `docs/verification/add-openrouter-preset-uat.md`
- [x] 3.3 变异测试一轮：把预设里的 `model` 改成 `deepseek-chat`，`test_the_openrouter_preset_carries_the_verification_model` 当场红；还原后 12 条全绿
- [x] 3.4 Learning Gate：**`NO-PROMOTION`**（2026-11-25）。扫本轮证据：变异 M3 杀死的两条判据分别是「flag 给的值」与「配置文件给的值」——这是 L-098「同一语义的两条实现路径要各有一条判据」的又一次实例，不是新信号；其余证据（预设表写错、词表漏名）都被既有判据直接抓住，没有返工过的规格。收件箱不新增条目。
