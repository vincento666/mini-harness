# `fix-chat-screen-feedback` 的 UAT 验收手册（人跑）

**第五道门禁的执行手册**（ADR-0025）。这一份不是跑判据：是你坐在终端前拿 `minihns chat` 办一件真事，然后把「屏幕上到底发生了什么」填回来。**这张表没填完，本 change 不得归档、不得合入 `main`。**

三场都是**重跑** `docs/verification/m5-m6-m7-uat.md` 里的 U1 / U3 / U4，看这一轮报回来的六条是否消失、新加的那几行够不够用。准备（选真实工作区 `$WS`、注入两个密钥变量、选模型层 `$EP`）照那份手册的「准备」一节。

> **窗口那一栏**：`--window` 必须比 `--reserve + 65536` 大，否则在 session 开始之前就是退出码 2。下面用的是今天跑得通的 `--window 70000 --reserve 100`。
> **退出码怎么读**：别在 Ctrl-C 之后读 `$LASTEXITCODE`（Ctrl-C 中断的是 PowerShell 的前台管道）。用 `cmd /c "uv run minihns … & echo %ERRORLEVEL%"`，或跑完不取消的那一次再读。

---

## V1 · 提示符与空行：屏幕上还有隔行的空白吗

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-c\sessions @EP --window 128000 --reserve 8192 --max-turns 12 --sandbox workspace-write --yes
```

进去之后办一件你真想办的事，要它**多调几次工具**（读一个文件、再列目录、再读第二个文件），最后问一句总结。

| 要观察的 | 你看到的 |
|---|---|
| 提示符与你打的那一行在同一行上（不再落在空行里） | |
| 工具回合之间不再产生空行；新提示符紧跟在上一条回复之后 | |
| 屏幕上看得见工具调用与结果吗（这一条规格说 MUST NOT——你实际想要的是什么，写下来） | |
| 启动时 stderr 上那一行 session id：长什么样、有没有用 | |
| 拿那一行的 id 跑 `uv run minihns replay <id> --session-dir .tmp\uat-c\sessions`：找得到吗、退出码 | |
| 退出码（不取消、直接 EOF 或输入完） | |

**真事是什么**：写下来（一句话）。

---

## V2 · 溢出那一行：还重复吗、有没有把话说清楚

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-c\sessions @EP --window 70000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读一份**大文件**（真实工作区里最大的那份文本；没有就 `--workspace` 指到 `S:\Develop\mini-harness\.tmp\reacc\ws`），读两三回，每回都接着问一句。

| 要观察的 | 你看到的 |
|---|---|
| `[段] CONTEXT_WINDOW_EXCEEDED` 那一行里，这个词出现几次 | |
| 那一行有没有带上当时的预算读数与触发线（或「无可遮蔽的内容」那句） | |
| 连续两次溢出之后，有没有多出一行说明「这份会话降不下去、退出并新开一个会话」 | |
| 那句说明出现了几次 | |
| 看到那句说明之后你会怎么做（退出？接着问？） | |
| 会话有没有自己结束、退出码 | |

---

## V3 · 取消的两半：段中 Ctrl-C 与提示符上 Ctrl-C

不带 `--yes`，让工具调用要问人：

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-c\sessions @EP --window 128000 --reserve 8192 --max-turns 8 --sandbox workspace-write
```

1. 打一句要它跑工具的话，批准之后**在它正在跑的时候按一次 Ctrl-C**。
2. 再打第二句话，看会话还在不在、它记不记得被中断那次调用的结果。
3. 在提示符上按一次 Ctrl-C 退出。
4. 重跑一次，**刚启动、还没输入任何东西时**按一次 Ctrl-C。

| 要观察的 | 你看到的 |
|---|---|
| 段中 Ctrl-C 之后：stderr 上有没有 `[段] ABORTED` 那一行 | |
| 那一行之后屏幕上还有没有多余的空行 | |
| 会话继续、第二句能接着问、它答得出被中断那次调用的结果 | |
| 提示符上 Ctrl-C：有没有 traceback | |
| 刚启动就 Ctrl-C：有没有 traceback、日志里有没有 `session/end` | |
| 两次 Ctrl-C 的退出码（用上面那条 `cmd /c` 的读法） | |
| 中途取消的 `serve`：`uv run minihns serve --http -p "…" … --port 8321` 中途 Ctrl-C，stderr 那一行长什么样（还带悬空冒号吗） | |

---

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「这个 change 的 UAT 跑完了」。我会按填回来的东西判本 change 的 UAT 那一半；不符合的项照 ADR-0025 立成新的修复 change。
