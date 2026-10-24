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
| 提示符与你打的那一行在同一行上（不再落在空行里） | （本场未跑。V2 那一跑里能看到同一件事：`> 读一下S:\Develop\mini-harness\.tmp\reacc\ws里的mid12.md`——输入紧跟提示符在同一行） |
| 工具回合之间不再产生空行；新提示符紧跟在上一条回复之后 | （未报） |
| 屏幕上看得见工具调用与结果吗（这一条规格说 MUST NOT——你实际想要的是什么，写下来） | （未报。V3 那一跑里工具调用与结果只进日志、屏幕上没有——你实际想要的是什么，写下来） |
| 启动时 stderr 上那一行 session id：长什么样、有没有用 | （本场未跑。V2 那一跑里是 `会话 6ca42674bbbc412d8610935ef331f795`） |
| 拿那一行的 id 跑 `uv run minihns replay <id> --session-dir .tmp\uat-c\sessions`：找得到吗、退出码 | （本场未跑。V3 那一跑的 id `b861ceee88ad48be904ac3c9233d5e47` 找得到：`verified seq=4/13/22/31/40/51: OK`、六条 `turn t1…t6`、`final_context` 一条，没有 `REPLAY_MISMATCH`） |
| 退出码（不取消、直接 EOF 或输入完） | （未报） |

**真事是什么**：写下来（一句话）。

---

## V2 · 溢出那一行：还重复吗、有没有把话说清楚

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat-c\sessions @EP --window 70000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读一份**大文件**（真实工作区里最大的那份文本；没有就 `--workspace` 指到 `S:\Develop\mini-harness\.tmp\reacc\ws`），读两三回，每回都接着问一句。

| 要观察的 | 你看到的 |
|---|---|
| `[段] CONTEXT_WINDOW_EXCEEDED` 那一行里，这个词出现几次 | 一次。原话：`[段] CONTEXT_WINDOW_EXCEEDED：无可遮蔽的内容，预算读数 7038 已超过触发线 4364`（2026-10-24，会话 `6ca42674bbbc412d8610935ef331f795`，`--window 70000 --reserve 100 --max-turns 20`，比手册里的 `--max-turns 6` 宽） |
| 那一行有没有带上当时的预算读数与触发线（或「无可遮蔽的内容」那句） | 有，三样都在同一行里：`无可遮蔽的内容` + 读数 7038 + 触发线 4364。触发线与真实端点验收那一跑的 4364 是同一个数（同一组 `--window` / `--reserve`） |
| 连续两次溢出之后，有没有多出一行说明「这份会话降不下去、退出并新开一个会话」 | 有。第二次溢出那一行之后紧跟 `[降不下去] 连续两段溢出：这份会话已经降不下去，退出并新开一个会话是可选动作。` |
| 那句说明出现了几次 | 一次（第三段又溢出一次也没有再说第二遍） |
| 看到那句说明之后你会怎么做（退出？接着问？） | （未报——那一跑你接着按了 EOF 退出，做法要你自己写一句） |
| 会话有没有自己结束、退出码 | 没有自己结束：那句说明之后提示符 `> ` 回来了。退出码未读（PowerShell 不打印它，Ctrl-C 之后 `$LASTEXITCODE` 也不可靠——用 `cmd /c "… & echo %ERRORLEVEL%"`） |

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
| 段中 Ctrl-C 之后：stderr 上有没有 `[段] ABORTED` 那一行 | （未报。日志那一半有：会话 `b861ceee88ad48be904ac3c9233d5e47` 的 `turn t5: ABORTED`。屏幕上那一行你有没有看见，要你自己写一句） |
| 那一行之后屏幕上还有没有多余的空行 | （未报） |
| 会话继续、第二句能接着问、它答得出被中断那次调用的结果 | 是。你的原话：「取消工具执行后提问能记住之前最后一次工具执行的结果」。日志里的配对证据：被取消的那次 `read` 带着结果词进上下文（`取消在派发之前置位，这个调用没有开始：read`），`turn t5: ABORTED` 之后 `turn t6: MODEL_COMPLETED` |
| 提示符上 Ctrl-C：有没有 traceback | 无。你的原话：「刚执行工具时以及提示符上 Ctrl+C 没有 traceback」 |
| 刚启动就 Ctrl-C：有没有 traceback、日志里有没有 `session/end` | （未报——手册第 4 步那一跑还没跑） |
| 两次 Ctrl-C 的退出码（用上面那条 `cmd /c` 的读法） | 屏幕上没有显示退出码，直接回到 PowerShell 提示符。这是 PowerShell 的行为：它不打印子进程的退出码，Ctrl-C 之后 `$LASTEXITCODE` 读到的也不是 CLI 的。要读码用 `cmd /c "uv run minihns chat … & echo %ERRORLEVEL%"` |
| 中途取消的 `serve`：`uv run minihns serve --http -p "…" … --port 8321` 中途 Ctrl-C，stderr 那一行长什么样（还带悬空冒号吗） | （未跑） |

---

## 2026-10-24 这一轮：还缺的格子

V2 与 V3 的观察已照原话转录进上面的表（V2 会话 `6ca42674bbbc412d8610935ef331f795`、V3 会话 `b861ceee88ad48be904ac3c9233d5e47`）。**这张表还没填完**，缺的是：V1 整场、V2 的「看到那句说明之后你会怎么做」、V3 的「段中 Ctrl-C 之后 stderr 上那一行你看见了吗」「那一行之后有没有多余空行」「刚启动就 Ctrl-C 那一跑」「两次 Ctrl-C 的退出码（`cmd /c` 读法）」「中途取消的 `serve`」。

## 2026-10-24 这一轮 UAT 看见的两条新事实（不在本 change 的六条里）

1. **模型对运行平台无知**。屏幕上出现的那段「我先查看工作区里有哪些文件 / 命令 `ls` 似乎不可用 / 这是一台 Windows shell（cmd）环境」不是 harness 的思考流——mini-harness 没有把 reasoning 与回复分开的通道，provider 一条消息里 `content` 与 `tool_calls` 同时回来，屏幕上打的就是它自己写的 `content`（1.2 的规则：非空就打）。它之所以要试错才发现平台：系统提示只有两句加一份工具名清单（`events/fold.py` 的 `SYSTEM_PROMPT`），**没有任何 OS / shell 事实**，而 `bash` 在 Windows 上走 `cmd.exe /c`（`tools/bash_tools.py`），`ls` / `wc` 必然失败。要不要立一个新 change 把平台事实放进装配（或给 `bash` 一个平台说明），**要人裁决**。
2. **`cmd.exe` 的输出碎成 U+FFFD**。你贴回来的 `tool` 内容里 `'ls' 不是内部或外部命令` 是一串乱码：`bash` 把命令输出按 `utf-8, errors="replace"` 解码（`tools/bash_tools.py`），而 `cmd.exe` 在本机用 GBK。这一条早已记在 `docs/adr/0002-deferred-refactors.md` 第 30 条（「解码选型要人裁决」），本轮是**第一次让人亲眼看见它**。

两条都不改本 change 的代码与判据；要不要立新的修复 change（以及第 30 条的解码选型）等 UAT 那张表填完一起裁。

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「这个 change 的 UAT 跑完了」。我会按填回来的东西判本 change 的 UAT 那一半；不符合的项照 ADR-0025 立成新的修复 change。
