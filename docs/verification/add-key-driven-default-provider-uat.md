# `add-key-driven-default-provider` 的 UAT 手册（人跑）

第五道门禁（ADR-0025）。三场。**这张表没填完，本 change 不得归档、不得合入 `main`。**

准备（一次）：

```powershell
cd S:\Develop\mini-harness
$WS = "S:\Develop\mini-harness\.tmp\reacc\ws"
```

## U1 · 裸跑现在说什么（这一场是修复本身）

修复前：裸跑 `minihns chat` 退出码 2、stdout 空、stderr 是 `--provider mock 需要 --fixture 指向 JSON 数组`——一个配好密钥的人看不出该做什么。

先把密钥设成你本机端点的那把（**只设当前进程**）：

```powershell
$env:MINIHNS_API_KEY = [Environment]::GetEnvironmentVariable("MINIHNS_STRATA_KEY","User")
uv run minihns chat --workspace $WS --session-dir .tmp\uat3\sessions --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs --sandbox workspace-write --yes
```

注意：**没给 `--provider`、没给 `--api-key-env`**。

| 要观察的 | 你看到的 |
|---|---|
| 它是不是直接就能对话（默认落到了 openai 预设） | **是**（2026-10-26 代跑，端点换 `https://api.deepseek.com/v1` + `deepseek-chat`）：没给 `--provider`、没给 `--api-key-env`，`MINIHNS_API_KEY` 已设 → `session/start` 里 `provider=openai`、`base_url=https://api.deepseek.com/v1`、`model=deepseek-chat`、`api_key_env=MINIHNS_API_KEY`，对话跑完、退出码 0（会话 `6cb36294be644382a763f46307ccdf36`） |
| 它有没有报 `INVALID_ARGUMENT`，报的是哪一项 | 连 `--model` 都不给的裸跑报 **`--model`**：`--provider openai 需要 --model：openai 预设不给 model 默认`（退出码 2、无日志）——这是 ADR-0027 写明的设计（openai 预设不给 model 默认），不是缺口 |
| `minihns replay` 看 `session/start` 里 `provider` 那一格写的是什么 | 成功那一跑写 **`openai`**（上面那行逐字）；失败的两跑在 session 开始之前就退出，没有日志可看 |
| 把 `$env:MINIHNS_API_KEY` 清掉再裸跑一次，这次说什么 | 回落到 **mock**：`INVALID_ARGUMENT: --provider mock 需要 --fixture 指向 JSON 数组`（退出码 2） |

## U2 · `--provider deepseek` 能对话，且连的是 deepseek

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
uv run minihns chat --workspace $WS --session-dir .tmp\uat3\sessions --provider deepseek --sandbox workspace-write --yes
```

| 要观察的 | 你看到的 |
|---|---|
| 它不再报 `UNKNOWN_PROVIDER` | 是，`--provider deepseek` 直接跑通（退出码 0） |
| 它连的是 `https://api.deepseek.com`（不是本机 8300） | 是：`session/start` 里 `provider=deepseek`、`base_url=https://api.deepseek.com`、`model=deepseek-chat`、`api_key_env=DEEPSEEK_API_KEY` |
| 对话正常跑完 / 失败时 `detail` 里说的是哪台机器 | 正常跑完，回答是「一句话：你好，需要我做什么？」；没有失败分支可看 |
| 换成 `--provider claude` 时还是不是 `UNKNOWN_PROVIDER` | 是：`UNKNOWN_PROVIDER: --provider 只接受 mock / openai / deepseek，收到 claude`，退出码 2、无日志 |

## U3 · `--help` 看得见默认

```powershell
uv run minihns chat --help
```

| 要观察的 | 你看到的 |
|---|---|
| `--provider` 那一行有没有把 `mock` / `openai` / `deepseek` 与「看 `MINIHNS_API_KEY` 是否在场」写清楚 | 是，逐字：「端点预设名 mock / openai / deepseek。没给时这一层看环境变量 MINIHNS_API_KEY：已设且非空就是 openai，否则是 mock」 |
| `--api-key-env` 那一行有没有写「默认变量名随预设而变」 | 是：「没给时随 provider：openai 读 MINIHNS_API_KEY，deepseek 读 DEEPSEEK_API_KEY」 |
| 你只看 `--help` 能不能自己拼出一条能对话的命令 | 能：三个预设 + 三个「没给时随 provider」的默认（`base-url` / `model` / `api-key-env`）连起来就够；唯一要留神的是 openai 预设不给 `model` 默认，`--help` 也明写了「缺它当场失败」 |

## 2026-10-26 这一轮：DeepSeek 端点代跑（人授权同前）

三场都用 `https://api.deepseek.com` 替代手册里的本机 studio（8300 没在监听），其余按手册。**三场的实质结论**：

1. **U1 的核心修复成立**：只设 `MINIHNS_API_KEY`、不给 `--provider` / `--api-key-env`，默认落到 openai 预设，而且 `session/start` 把 `api_key_env` 记成 `MINIHNS_API_KEY`——「密钥决定默认 provider」这条端到端可见。
2. **U2 的预设成立**：`--provider deepseek` 一眼把 base_url、model、密钥变量名都定下来；`claude` 仍是 `UNKNOWN_PROVIDER` 且不产生日志。
3. **一处值得留意的措辞**：只给密钥、不给 `--model` 的裸跑报的是 `--provider openai 需要 --model`。对「刚配好密钥的人」来说，这比修复前那句 `--provider mock 需要 --fixture` 更贴近他要做的事，但**仍然要他自己再想一个模型名**——ADR-0027 明写 openai 预设不给 model 默认（不给模型猜），所以这是设计，不是缺口；`--help` 里那句「openai 预设不给默认，缺它当场失败」把它讲清了。

## 填完之后

在对话里说一句「这个 change 的 UAT 跑完了」，我按填回来的东西判第三半，并把不符合的项立成修复 change。
