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
| 它是不是直接就能对话（默认落到了 openai 预设） | |
| 它有没有报 `INVALID_ARGUMENT`，报的是哪一项 | |
| `minihns replay` 看 `session/start` 里 `provider` 那一格写的是什么 | |
| 把 `$env:MINIHNS_API_KEY` 清掉再裸跑一次，这次说什么 | |

## U2 · `--provider deepseek` 能对话，且连的是 deepseek

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
uv run minihns chat --workspace $WS --session-dir .tmp\uat3\sessions --provider deepseek --sandbox workspace-write --yes
```

| 要观察的 | 你看到的 |
|---|---|
| 它不再报 `UNKNOWN_PROVIDER` | |
| 它连的是 `https://api.deepseek.com`（不是本机 8300） | |
| 对话正常跑完 / 失败时 `detail` 里说的是哪台机器 | |
| 换成 `--provider claude` 时还是不是 `UNKNOWN_PROVIDER` | |

## U3 · `--help` 看得见默认

```powershell
uv run minihns chat --help
```

| 要观察的 | 你看到的 |
|---|---|
| `--provider` 那一行有没有把 `mock` / `openai` / `deepseek` 与「看 `MINIHNS_API_KEY` 是否在场」写清楚 | |
| `--api-key-env` 那一行有没有写「默认变量名随预设而变」 | |
| 你只看 `--help` 能不能自己拼出一条能对话的命令 | |

## 填完之后

在对话里说一句「这个 change 的 UAT 跑完了」，我按填回来的东西判第三半，并把不符合的项立成修复 change。
