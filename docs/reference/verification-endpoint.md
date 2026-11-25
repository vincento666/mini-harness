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

2026-11-24 起这台机器同时做了自动载入，两处都是「文件存在才 source」：

| 文件 | 覆盖谁 | 备注 |
|---|---|---|
| `~/.zshrc` | 交互式终端 | 只在交互 shell 读 |
| `~/.zshenv` | 所有 zsh 进程（登录、非登录、脚本） | 非交互场景靠它 |

**仍然会读不到的一种情况**：用 `zsh -f`（不读任何 rc）起的进程。WorkBuddy 的 Bash 工具就是这种形态——实测 `vendor zsh -c` 能拿到 73 字符，`vendor zsh -fc` 是 0。所以 agent 跑命令时照旧在命令里 source 一次，或者把长命令包在 `zsh -c '...'` 里。

写成 600 权限的独立文件而不是直接 `export` 的原因：改 key 只动一个文件、不会进 shell 历史，也不会被 `git status` 看见；跑之前 `echo ${#OPENROUTER_API_KEY}` 就能确认（长度非 0 即可，别把值打到终端）。

## 4. 裸 curl 冒烟（不经 harness，先确认端点通）

```bash
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"qwen/qwen3.8-27b","stream":true,"messages":[{"role":"user","content":"Hello"}]}'
```

401 且 message 里写着 `No API key in the Authorization header` 就是变量没进这个进程，不是模型名或端点的问题。

## 5. 报错分诊：先分「端点侧」与「代码侧」

两条裸 curl 就能分，别看代码：

```bash
curl -sS -o /dev/null -w "key=%{http_code}\n" https://openrouter.ai/api/v1/key \
  -H "Authorization: Bearer $OPENROUTER_API_KEY"
curl -sS -w "\nchat=%{http_code}\n" https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"qwen/qwen3.8-27b","messages":[{"role":"user","content":"hi"}],"max_tokens":8}'
```

| 读数 | 结论 | 下一步 |
|---|---|---|
| `key=200` + `chat=200` | 端点通 | 再跑 harness；仍失败才是代码侧 |
| `key=200` + `chat=4xx/5xx` | **端点/账户侧**，与 mini 无关 | 换 key、看控制台、向 OpenRouter 报（附 `x-openrouter-release`） |
| `key=401` | 变量没进这个进程 | `set -a && . ~/.config/minihns/openrouter.env && set +a` |

**2026-11-25 实例（400 `Request path cannot be relayed`）**：`key=200`（余额 $2.89 / $3、非 free tier、无 `expires_at`），而推理请求一律 400。逐项排除过：4 个模型、`openrouter/auto`、指定 provider（Darkbloom）、`/chat/completions` 与 `/responses` 与 `/messages` 三条路径、换 UA/`HTTP-Referer`、`--http1.1`、`--noproxy '*'` 直连——全是同一句 400。同时 `GET /api/v1/models` 与 `/models/<id>/endpoints` 都是 200（模型在列、6 个端点 `status=0`）。响应头 `x-openrouter-error-origin: client` 是网关自己判的，不是上游透传。结论：**只拒推理类 POST，读取类 GET 正常**，属端点侧；前一晚同一条 curl 还是 200。

harness 侧看到这事的形状是固定的，**不要**据此改轮次逻辑：

```text
error/model {code: PROVIDER_HTTP_STATUS, detail: "HTTP 400：Request path cannot be relayed"}
step/end    {stop_reason: PROVIDER_ERROR}
turn/end    {stop_reason: PROVIDER_ERROR, tool_calls: 0}
```

`tool_calls=0` 且第一次 `model/request` 之后就报错，说明模型一次都没叫通——目标根本没建起来，`[轮] 收尾 PROVIDER_ERROR` 只是入口照常收尾。

## 6. 不做什么

- **不把密钥写进仓库**：不出现在 `.env`、不出现在 `mini.config.toml`、不写进日志。
- **不把这条端点加进 CI**：ADR-0024 明写真实那一半不进 CI，理由是密钥与抖动。
- **不因为换端点就改判据**：判据钉的是值与形状（`stop_reason`、事件名、`turns` 计数），不是某个模型的措辞。
