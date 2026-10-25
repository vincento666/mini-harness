# M5 / M6 / M7 的 UAT 验收手册（人跑，2026-10-23）

**这一份是第五道门禁的执行手册**（ADR-0025）。UAT 不是跑判据：是**你坐在终端前，拿 `minihns` 在一份真实工作区里办一件你真想办的事**，然后按下面的场次把「屏幕上到底发生了什么」填回来。

- **谁跑**：人。agent 不得代跑 tty 场次（它跑不了 Ctrl-C，也读不到提示符）。agent 能跑的那一半（真实端点跑判据）已经在 `m5-context-budget-compaction-reacceptance.md` / `m6-chat-repl-reacceptance.md` / `m7-serve-http-sse-reacceptance.md` 里。
- **通过信号**：每一场的观察表填完、每场有一句「符合 / 不符合 / 别扭在哪」。**任何一场没填 = M5 / M6 / M7 的 UAT 那一半没过 = 这三个里程碑不算验收完成**（ADR-0025）。
- **填在哪**：本文件每场末尾那张表的「观察」列，直接改这个文件。别扭的地方写清楚，不要只写「正常」。

## 准备（一次）

在 PowerShell 里，先选一个**你真的在乎的工作区**（不是 `S:\Develop\mini-harness\.tmp\`，那是脚手架）。下面用 `$WS` 代表它。

```powershell
cd S:\Develop\mini-harness
$WS = "S:\Develop\agent_harness\re\verified"        # 换成你自己的真实工作区
$env:MINIHNS_STRATA_KEY   = [Environment]::GetEnvironmentVariable("MINIHNS_STRATA_KEY","User")
$env:DEEPSEEK_API_KEY     = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
```

模型层两套（任选一套，两套都跑更好）：

```powershell
# A：本机 Strata（已在跑，别关它）
$EP = @("--provider","openai","--base-url","http://127.0.0.1:8300/v1","--model","qwen3.8-flash-next-iq3_xxs","--api-key-env","MINIHNS_STRATA_KEY")
# B：DeepSeek 真端点
$EP = @("--provider","openai","--base-url","https://api.deepseek.com","--model","deepseek-chat","--api-key-env","DEEPSEEK_API_KEY")
```

> 提示：`--sandbox workspace-write --yes` 会自动批准工具调用；**U4 与 U6 不要带 `--yes`**，那两场要的就是「问人」这件事发生。

---

## U1 · M6 的底座：REPL 在真实工作区里办一件真事

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 128000 --reserve 8192 --max-turns 12 --sandbox workspace-write --yes
```

进去之后打一句你真想问的话（例：「这份目录里哪个文件定义了 X？把它的前 20 行读给我」），再打第二句接着往下办（例：「把那一行的注释改成中文」）。办完按 **Ctrl-C 一次**（在提示符上）。

| 要观察的 | 你看到的 |
|---|---|
| 提示符出现、你打字它接住 | |
| 模型的回复逐段出现在 stdout | |
| 工具调用与结果在屏幕上看得见（不是只有日志里有） | |
| 第二句话接着第一句话的上下文（它记得刚才读了哪个文件） | |
| 提示符上 Ctrl-C 一次就干净退出（没有半条回复、没有 traceback） | |
| 退出码 | `$LASTEXITCODE` = |

**真事是什么**：写下来（一句话）。这一场记的是「用起来是什么样」。

---

## U2 · M5 的压缩在屏幕上看得见（`[遮蔽]` 那一行）

把窗口压小，让压缩真的发生：

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 60000 --reserve 200 --max-turns 10 --sandbox workspace-write --yes
```

进去之后让它读一份**大文件**（真实工作区里最大的那份文本；没有就 `--workspace` 指到 `S:\Develop\mini-harness\.tmp\reacc\ws`，那里有 `big.md` 247,988 字符与 `huge.md` 409,248 字符），读两三回，每回都接着问一句。

| 要观察的 | 你看到的 |
|---|---|
| stderr 上出现 `[遮蔽] 折掉 seq <起> 至 <止>：tokens <前> 降至 <后>` | |
| 同一条压缩记录**只报一次**（不重复刷） | |
| 报完之后对话继续，模型还能引用被遮蔽之前的结论 | |
| 那一行**不在 stdout**（它不该混进模型的输出里） | |
| 退出后跑 `uv run minihns replay <session id> --session-dir .tmp\uat\sessions`：输出里**没有**「遮蔽」二字、退出码 0 | |

session id 在 chat 启动时打在 stdout 上（第一行那串十六进制）。

---

## U3 · M5 的溢出：退出码 4 且屏幕上有一行

窗口再压小到压缩救不了：

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 40000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读那份大文件。

| 要观察的 | 你看到的 |
|---|---|
| stderr 上有一行 `[段] CONTEXT_WINDOW_EXCEEDED` | |
| 还有一行 `CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 <n> 已超过触发线 <m>` | |
| 会话**不崩**：提示符还在，你可以接着问一句别的 | |
| 退出后 `$LASTEXITCODE` = **4** | |
| 日志里有一条 `error/context`（`uv run minihns replay <id> --session-dir .tmp\uat\sessions` 里看得见） | |

---

## U4 · M6 的取消：Ctrl-C 取消一个回合，会话继续（等人这一半）

不带 `--yes`，让工具调用要问人，这样一个回合会跑得久一点：

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 128000 --reserve 8192 --max-turns 8 --sandbox workspace-write
```

1. 打一句要它跑工具的话（例：「用 bash 列一下这个目录」）。
2. 批准提示出现时回答 `y`，**在它正在跑的时候按一次 Ctrl-C**。
3. 再打第二句话，看会话还在不在。
4. 最后在提示符上按一次 Ctrl-C 退出。

| 要观察的 | 你看到的 |
|---|---|
| 第一次 Ctrl-C 之后：屏幕上有没有 `[段] ABORTED` 那一行 | |
| 会话继续（提示符回来，第二句能接着问） | |
| 日志里那一段以 `ABORTED` 收尾、会话没结束 | |
| 提示符上 Ctrl-C：干净退出、退出码 | `$LASTEXITCODE` = |
| 批准提示长什么样（问人的那一问在屏幕上是什么措辞） | |

这一场是 M6 完成判据里「取消一个回合后会话继续」那一半，Windows 上四条 SIGINT 子进程判据被 skip，只有你能判它。

---

## U5 · M7 的事件流与断线续读 + Ctrl-C

**终端 A**：

```powershell
uv run minihns serve --http -p "读一下 <真实工作区里的一份大文件>，然后三句话告诉我里面有什么" --workspace $WS --session-dir .tmp\uat\sessions @EP --window 150000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes --host 127.0.0.1 --port 8321
```

**终端 B**（另开一个 PowerShell）：

```powershell
cd S:\Develop\mini-harness
curl.exe -N -s http://127.0.0.1:8321/events          # 从头读，看到几条后按 Ctrl-C 断开
curl.exe -N -s -H "Last-Event-ID: 6" http://127.0.0.1:8321/events   # 带游标重连
curl.exe -N -s "http://127.0.0.1:8321/events?from=2"                 # from 覆盖 Last-Event-ID
```

| 要观察的 | 你看到的 |
|---|---|
| 每帧三行：`id:` / `event:` / `data:`，`id` 就是日志里的 `seq` | |
| `data` 那一串 JSON 与日志整行内容一致（可以 `uv run minihns replay <id> --session-dir .tmp\uat\sessions` 对照） | |
| 断开后带 `Last-Event-ID: 6` 重连，从 `seq 7` 开始，不漏不重 | |
| `?from=2` 时从 `seq 3` 开始（`from` 覆盖 header） | |
| 会话跑完进程自己退出，退出码 | `$LASTEXITCODE` = |
| **Ctrl-C 那一半**：重跑一次，在会话中途在终端 A 按 Ctrl-C → 日志最后一条不是半条记录、`replay` 不报 `REPLAY_MISMATCH` | |

---

## U6 · 裸跑的默认档位（给下一个 change 留基线）

什么档位都不给：

```powershell
uv run minihns chat --workspace $WS
uv run minihns run -p "读一下当前目录里最大的文件" --workspace $WS
uv run minihns chat --help
```

| 要观察的 | 你看到的 |
|---|---|
| 裸跑 `chat` 的退出码 | `$LASTEXITCODE` = |
| stdout 有没有东西 | |
| stderr 那一行原文 | |
| `--help` 里 `--provider` 那行有没有写默认值 | |
| 你期望它怎么做（一句话） | |

这一场是给「密钥驱动的默认 provider」那个 change 的 UAT 基线，先记下现状。

---

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「UAT 跑完了」，我会按填回来的东西判 M5 / M6 / M7 的 UAT 那一半，并把不符合的项立成修复 change。
