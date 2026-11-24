# 功能验证与调优用哪个端点

**定位**：ADR-0024 说的「真实那一半」到底接哪家端点。这份文只回答一件事——跑验收、跑调优、量真实形状时用哪个模型、密钥从哪来、命令长什么样。规格在 ADR-0024 / ADR-0027，验收场次在各 change 的 `docs/verification/*.md`。

**一句话**：2026-11-24 起统一用 OpenRouter 的 `qwen/qwen3.8-27b`，密钥读环境变量 `OPENROUTER_API_KEY`；`deepseek` 预设留在代码里，但不再当验收端点。

---

## 1. 端点与模型

| 项 | 值 |
|---|---|
| Base URL | `https://openrouter.ai/api/v1` |
| 模型 | `qwen/qwen3.8-27b` |
| 密钥变量 | `OPENROUTER_API_KEY` |
| 协议 | OpenAI 兼容（`POST /chat/completions`，SSE 流式） |

模型元数据（2026-11-24 查 `GET https://openrouter.ai/api/v1/models`）：上下文 1,024,000、最大输出 131,072、`supported_parameters` 含 `tools` / `tool_choice` / `stream`；价格 $0.035/M 输入、$1.5/M 输出。**支持工具调用**，所以工具循环、围栏、审批这些判据都能在这上面跑，不需要退化成纯问答。

## 2. 在 mini-harness 里怎么调

provider 名是**端点预设**（ADR-0027）。2026-11-24 起有 `openrouter` 预设，三项默认都在表里，所以一个 flag 就够：

```bash
uv run minihns run -p "读 README.md 第一段并总结一句" \
  --provider openrouter \
  --max-steps 3 --yes \
  --workspace .tmp/verify/<change> \
  --session-dir .tmp/verify/<change>/sessions
```

预设只填**没被给**的那几项：显式写 `--model` 就用你的，`base_url` 与 `api_key_env` 仍是 OpenRouter 的。

**在仓库根跑、连 provider 都不想写**：仓库根有一份 `mini.config.toml`（被 `.gitignore` 忽略），内容只有 `provider = "openrouter"` 一行。它的生效范围等于 `discover_config` 的规则——只在 workspace 是仓库根时读到；`--workspace .tmp/xxx` 这类调用读不到，那种场合仍要写 `--provider openrouter`。

改造前的写法（`--provider openai` + 三个覆盖参数）现在仍能跑，但三缺一就失败：`openai` 预设默认读 `MINIHNS_API_KEY`、base URL 是 `api.openai.com`、且**不给默认模型**。留作兜底，不再当默认路径。

## 3. 密钥从哪来

`minihns` 只从**进程环境**读，不读 `.env`、不读配置文件。所以跑之前那个变量必须已经在 shell 里。

本机做法（2026-11-24 起）：key 放在 `~/.config/minihns/openrouter.env`，目录 700、文件 600，仓库外，不进版本控制。用之前 source 一次：

```bash
set -a && . ~/.config/minihns/openrouter.env && set +a
```

写成文件而不是写进 `~/.zshrc` 的理由：这台机器的 shell 启动文件不导出它，`launchctl` 里也没有，所以「你以为设了」和「子进程真的继承了」会分叉；文件源一次是显式的，跑之前 `echo ${#OPENROUTER_API_KEY}` 就能确认（长度非 0 即可，别把值打到终端）。

## 4. 裸 curl 冒烟（不经 harness，先确认端点通）

```bash
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"qwen/qwen3.8-27b","stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

401 且 message 里写着 `No API key in the Authorization header` 就是变量没进这个进程，不是模型名或端点的问题。

## 5. 不做什么

- **不把密钥写进仓库**：不出现在 `.env`、不出现在 `mini.config.toml`、不写进日志。
- **不把这条端点加进 CI**：ADR-0024 明写真实那一半不进 CI，理由是密钥与抖动。
- **不因为换端点就改判据**：判据钉的是值与形状（`stop_reason`、事件名、`turns` 计数），不是某个模型的措辞。
