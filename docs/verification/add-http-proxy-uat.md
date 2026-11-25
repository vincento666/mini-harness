# add-http-proxy UAT 场次手册

**立骨架**：2026-11-25（按 ADR-0025，这张表没填完不得归档、不得合入 `main`）。

**跑法**：2026-11-25 **agent 代跑**（沿用用户对同类核验的授权；非交互 `run`，不需要 tty）。这是有意偏离，如实记录，不把代跑当人跑。

**为什么要人跑**：代理是环境相关的东西——「本机必须挂 7897 才能出网」是这台机器的现实，只有人知道换一台机器该不该配、错误信息够不够看懂。

**环境**：本机 macOS，代理 `http://127.0.0.1:7897`，真实端点 OpenRouter。

**已知环境事实**：直连 OpenRouter 的推理请求返回 400 `Request path cannot be relayed`（`docs/reference/verification-endpoint.md` §5 的分诊表），所以场次 1 必须带 `--proxy` 才有意义。

## 准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
mkdir -p .tmp/uat/proxy2/sessions
```

## 场次 1：经代理跑通真实端点

```bash
uv run minihns run -p "只回答一个词：ok" --provider openrouter \
  --proxy http://127.0.0.1:7897 --max-steps 2 --yes \
  --session-dir .tmp/uat/proxy2/sessions
```

- 期望：退出码 0；`session/end` 是 `{MODEL_COMPLETED, steps: 1}`；`session/start` 的键集合里**没有** `proxy`。
- 观察：不给 `--proxy` 时同一命令会撞 400（那是环境事实，不是本 change 的判据）。
- 结果：**通过**。会话 `27a99bb0a6b047d88f0907773248016a`；`provider=openrouter`、`model=qwen/qwen3.8-27b`、`base_url=https://openrouter.ai/api/v1`；payload 无 `proxy` 键；`session/end = {MODEL_COMPLETED, steps: 1}`。

## 场次 2：坏代理值当场拒绝

```bash
uv run minihns run -p "只回答 ok" --provider openrouter \
  --proxy socks5://127.0.0.1:1080 --session-dir .tmp/uat/proxy3
```

- 期望：退出码 2；stderr 说只支持 http/https、不建日志、不发请求。
- 结果：**通过**。退出码 2，stderr 是 `INVALID_ARGUMENT: --proxy 'socks5://127.0.0.1:1080' 必须以 http:// 或 https:// 开头（不支持 socks）`；会话目录里 0 个文件。

## 场次 3（对照，不必重复跑）：不给代理时直连

- 现象：`ProviderFailure` / `PROVIDER_HTTP_STATUS` 400 `Request path cannot be relayed`，退出码 1。
- 这条已在 `docs/reference/verification-endpoint.md` §5 与被拒诊断里记过，是促成本 change 的动机证据；UAT 不重复跑，避免无谓请求。

## 待确认

- 场次 1、2 均由 agent 代跑（2026-11-25）。归档时一并确认接受该偏离。
