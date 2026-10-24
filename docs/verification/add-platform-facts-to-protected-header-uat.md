# UAT 手册：`add-platform-facts-to-protected-header`

**这是 propose 阶段立的骨架**（ADR-0025）。场次由人跑，观察表由人填；**那张表没填完这个 change 不得归档、不得合入 `main`**。tty 场次 agent 不得代跑——agent 只能核对日志与 `context/assembled` 那一半。

跑之前先取密钥（本机实测可用的那条）：

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
```

## U1 拿它办一件真事（Windows 工作区）

```powershell
uv run minihns chat --workspace <一个真实工作区> --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --max-turns 8
```

进去打：`看看这个目录里有什么，然后读其中一个文件的前二十行`。

| 要观察的 | 你看到的 |
|---|---|
| 屏幕上还有没有那段试错正文（「`ls` 似乎不可用」「这是一台 Windows shell（cmd）环境」） | |
| 它第一次调 `bash` 用的什么命令 | |
| 它有没有在第一次失败之后就换到 `dir` / `Get-ChildItem` 这类形态 | |
| 这一场烧了几个回合（对比 2026-10-24 那一场的回合数） | |
| 启动时 stderr 上那一行 session id | |

**真事是什么**：写下来（一句话）。

## U2 乱码仍然会发生——看它怎么对待

同一场里打：`用 bash 跑 dir，然后把输出里你看不懂的地方告诉我`。

| 要观察的 | 你看到的 |
|---|---|
| 输出里有没有 U+FFFD（替换字符） | |
| 它有没有把乱码当成「工具坏了」去重试 | |
| 它有没有引用那句说明（命令输出按 UTF-8 解码）来解释 | |
| 它最后有没有把能读出来的部分读给你 | |

## U3 旧日志照旧可重放

拿一条**这条事实存在之前**的 session id（例如 `b861ceee88ad48be904ac3c9233d5e47`）跑：

```powershell
uv run minihns replay b861ceee88ad48be904ac3c9233d5e47 --session-dir .tmp\uat-c\sessions
```

| 要观察的 | 你看到的 |
|---|---|
| 每个装配点是不是 `verified … OK` | |
| 有没有 `REPLAY_MISMATCH` | |
| 退出码 | |

## U4 追加文本仍然排在最后

```powershell
uv run minihns run -p "说一句话" --append-system-prompt "回答只用中文" --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY
```

然后从那份日志的第一条 `context/assembled` 里读头部（agent 可以代读这一半）。

| 要观察的 | 你看到的 |
|---|---|
| 头部第一条是不是内置系统提示 | |
| 运行环境块在工具块之后、追加文本之前吗 | |
| 追加文本还在头部最后吗 | |
| 回答是不是只用中文 | |

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「这个 change 的 UAT 跑完了」。我会按填回来的东西判 UAT 那一半；不符合的项照 ADR-0025 立成新的修复 change。
