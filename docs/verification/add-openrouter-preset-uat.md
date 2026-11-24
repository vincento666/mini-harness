# add-openrouter-preset UAT 场次手册

**立骨架**：2026-11-24（按 ADR-0025，这张表没填完不得归档、不得合入 `main`）。

**跑法**：2026-11-24 **agent 代跑**（用户明确指示）。两场都是非交互 `run`，不需要 tty。

**为什么要人跑**：预设补齐是「少打字」的事，只有人知道少打之后手感对不对——报错信息够不够、默认值是不是他想要的、仓库根那份 `mini.config.toml` 会不会在别的目录里意外生效。

**环境**：本机 macOS，真实端点 OpenRouter。

## 准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
echo "key len=${#OPENROUTER_API_KEY}"
mkdir -p .tmp/uat/preset
```

## 场次 1：在仓库根不写任何端点 flag

```bash
uv run minihns run -p "用一句话说明你现在用的是哪个模型" --max-steps 2 --yes \
  --session-dir .tmp/uat/preset/s1
```

- 期望：退出码 0；`session/start` 的 `provider` 是 `openrouter`、`model` 是 `qwen/qwen3.8-27b`；模型自己的回答里能说出 qwen（不必强求，回答内容不作判据）。
- 观察：`--help` 里 `--provider` 那一行是否列了 `openrouter`；不写 config 的目录里跑同样命令，是否退回 `mock` 并要求 `--fixture`（那是预期，不是 bug）。
- 结果：**通过**。在仓库根不带任何端点 flag 跑，退出码 0；`session/start` 四格为 `openrouter` / `qwen/qwen3.8-27b` / `https://openrouter.ai/api/v1` / `OPENROUTER_API_KEY`。会话在 `.tmp/uat/preset/s1`。

## 场次 2（可选）：换一个模型

```bash
uv run minihns run -p "只回答 ok" --provider openrouter --model qwen/qwen3.8-flash --max-steps 2 --yes \
  --workspace .tmp/uat/preset --session-dir .tmp/uat/preset/s2
```

- 期望：`session/start.model` 是显式给的那个，`base_url` 与 `api_key_env` 仍是 OpenRouter 的——预设只填没给的。
- 结果：**通过**。`--model qwen/qwen3.8-flash` 时 `session/start.model` 是显式给的那个，`base_url` 与 `api_key_env` 仍是 OpenRouter 预设；退出码 0。
