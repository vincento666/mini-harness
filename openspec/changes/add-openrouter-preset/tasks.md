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
- [ ] 3.2 UAT（人跑）：手册已立 `docs/verification/add-openrouter-preset-uat.md`（仓库根无 flag 一场、覆盖模型一场）；结果列待填，填完才能归档
- [x] 3.3 变异测试一轮：把预设里的 `model` 改成 `deepseek-chat`，`test_the_openrouter_preset_carries_the_verification_model` 当场红；还原后 12 条全绿
- [ ] 3.4 Learning Gate：有可复用信号就进 `docs/lessons.md` 收件箱，没有就写 `NO-PROMOTION`
