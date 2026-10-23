# M5 / M6 / M7 的 UAT 验收手册（人跑，2026-10-23）

**这一份是第五道门禁的执行手册**（ADR-0025）。UAT 不是跑判据：是**你坐在终端前，拿 `minihns` 在一份真实工作区里办一件你真想办的事**，然后按下面的场次把「屏幕上到底发生了什么」填回来。

- **谁跑**：人。agent 不得代跑 tty 场次（它跑不了 Ctrl-C，也读不到提示符）。agent 能跑的那一半（真实端点跑判据）已经在 `m5-context-budget-compaction-reacceptance.md` / `m6-chat-repl-reacceptance.md` / `m7-serve-http-sse-reacceptance.md` 里。
- **通过信号**：每一场的观察表填完、每场有一句「符合 / 不符合 / 别扭在哪」。**任何一场没填 = M5 / M6 / M7 的 UAT 那一半没过 = 这三个里程碑不算验收完成**（ADR-0025）。
- **填在哪**：本文件每场末尾那张表的「观察」列，直接改这个文件。别扭的地方写清楚，不要只写「正常」。

## 这一份现在的状态（2026-10-23 第一轮跑完）

人跑了一遍，把屏幕上看到的东西在对话里报了六条。下面每张表里的「看到」列按三种来源写清楚：

- **人**：你在终端里看到的原话（我照你的转述填，没写清的地方标「未报」）。
- **核**：我读代码读出来的事实（带文件与行号）。
- **复现**：我在 `.tmp/uat-repro/` 里用 mock fixture 复现出来的东西（不需要密钥，可重跑）。

**这一轮 UAT 没有过**：六条观察都填进来了，但**退出码那一列全是空的**（U1 / U4 / U5 / U6 的 `$LASTEXITCODE` 都没报），U2 与 U5 的 `replay` 对照也没报。这两样是这几场的判据本体，下一轮补。

**手册自己也有错**：U2 与 U3 给的命令在当前 HEAD 与 `main` 上会被启动地板直接拒（见「手册自身的错」）。你这一轮实际跑的不是那两条命令——你报的 token 数（70485 / 54481）对得上默认窗口 128000 / 8192（触发线 54272），对不上 60000 / 200 或 40000 / 100。

---

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

> **窗口那一栏今天能用的最小值**：`--window` 必须比 `--reserve + 65536` 大，否则在 session 开始之前就是退出码 2。这一轮 U2 / U3 写的 60000/200 与 40000/100 都过不了这道地板（实测各是退出码 2）。**今天能跑的近似替代是 `--window 70000 --reserve 100`**（触发线 4364、保留尾部 11200，复现里压缩真的发生）。地板本身是 change `fix-small-window-compaction-dead-zone` 要改的东西。

---

## U1 · M6 的底座：REPL 在真实工作区里办一件真事

```powershell
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 128000 --reserve 8192 --max-turns 12 --sandbox workspace-write --yes
```

进去之后打一句你真想问的话（例：「这份目录里哪个文件定义了 X？把它的前 20 行读给我」），再打第二句接着往下办（例：「把那一行的注释改成中文」）。办完按 **Ctrl-C 一次**（在提示符上）。

| 要观察的 | 你看到的 |
|---|---|
| 提示符出现、你打字它接住 | **人**：提示符出现，但它自己带一个回车——你打的那一行落在**空行**上。 **核**：`cli/main.py:646` 是 `print(_CHAT_PROMPT)`，`_CHAT_PROMPT = "> "`（`main.py:539`）——打的是「`> ` + 换行」，输入自然从下一行开始。 |
| 模型的回复逐段出现在 stdout | **人**：能回答（你问「刚才问了什么」它答得出）。 **核**：`_print_new_replies`（`main.py:561`）把不带 `purpose` 的 `model/response` 原文打回 stdout。 |
| 工具调用与结果在屏幕上看得见（不是只有日志里有） | **不符合规格，也符合你的感受**：规格明写工具结果 MUST NOT 上 stdout（`chat-repl` 「chat 的 stdout 只打印模型回复正文」）。屏幕上看得见的是**空行**：每个只带工具调用的回合 `content` 是空串，`print("")` 就是一行空白。 **复现**：`.tmp/uat-repro/out2.txt` 里三个工具回合之后是第 2、3、4 行三条空行。 |
| 第二句话接着第一句话的上下文（它记得刚才读了哪个文件） | **人**：接着得上（被中断的那次工具调用的返回结果它也能引用）。 **核**：与规格一致——取消只塌当前回合，已落日志的事实照旧折进表层。 |
| 提示符上 Ctrl-C 一次就干净退出（没有半条回复、没有 traceback） | **人**：纯提示符上 Ctrl-C **偶尔**出 traceback。 **未定位**：`_chat_sigint_handler`（`main.py:549`）在「没有段在跑」时 `raise KeyboardInterrupt`；`except KeyboardInterrupt` 只包住那个 while 循环（`main.py:644-686`），**`end_session` 在 try 之外**（`main.py:690`），落在缝隙里的取消就没人接。Windows 上四条 SIGINT 子进程判据被 skip，这一条目前没有判据。 |
| 退出码 | **未报**（`$LASTEXITCODE` 没填）。 **核**：规格要求 chat 会话收尾（EOF 或提示符上取消）退出码是 0（`cli` 「退出码只取自固定表」）。CLI 从不打印退出码。 |

**真事是什么**：**未报**。

**这一场的判定**：**不符合**。提示符独占一行 + 工具回合的空行是屏幕反馈的缺陷；提示符上 Ctrl-C 的 traceback 是没有判据的缺口；退出码没读到。

---

## U2 · M5 的压缩在屏幕上看得见（`[遮蔽]` 那一行）

把窗口压小，让压缩真的发生：

```powershell
# 这一条在当前 HEAD 上跑不起来（退出码 2，见「手册自身的错」）。今天能用的替代：
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 70000 --reserve 100 --max-turns 10 --sandbox workspace-write --yes
```

进去之后让它读一份**大文件**（真实工作区里最大的那份文本；没有就 `--workspace` 指到 `S:\Develop\mini-harness\.tmp\reacc\ws`，那里有 `big.md` 247,988 字符与 `huge.md` 409,248 字符），读两三回，每回都接着问一句。

| 要观察的 | 你看到的 |
|---|---|
| stderr 上出现 `[遮蔽] 折掉 seq <起> 至 <止>：tokens <前> 降至 <后>` | **人**：读到一份大文件之后出现 `[段] MAX_TURNS` 与 `[遮蔽] 折掉 seq 1 至 91：tokens 70485 降至 71030`。 **不符合**：「降至」后面那个数**比前面那个大**。 |
| 同一条压缩记录**只报一次**（不重复刷） | **人**：没报重复。 **核**：`_print_shadow_feedback` 按 `through` 游标只报新记录（`main.py:598-620`）。 |
| 报完之后对话继续，模型还能引用被遮蔽之前的结论 | **人**：能回答之前的读取结果。 |
| 那一行**不在 stdout**（它不该混进模型的输出里） | **核**：那一行走 stderr（`main.py:618`）。 **复现**：`.tmp/uat-repro/err2.txt` 有、`out2.txt` 没有。 |
| 退出后跑 `uv run minihns replay <session id> --session-dir .tmp\uat\sessions`：输出里**没有**「遮蔽」二字、退出码 0 | **未报**——而且**跑不了**：见下一行，你拿不到 session id。 |

**「降至」那个数为什么会变大**（这是这一轮最硬的一条事实）：

- **核**：`tokens_after = budget_reading(幸存记录, fold(幸存).messages) + 摘要的估算`（`loop/turn_loop.py:678-682`）。而 `budget_reading` 取的是 `max(估算, 未遮蔽的 `model/response` 里最大的 `input_tokens` 回报)`（`context/budget.py:77-97`）。
- 保留尾部**总是留着最后那几条**（`budget.py:190-198`），而最新那条 `model/response` 回报的 `input_tokens` 正是把这次请求顶到越线的那个数。遮蔽砍得动估算，砍不动这个回报。于是 `tokens_after` = 同一个读数 + 摘要 → **只增不减**。你报的两组数差值 545 与 208，就是那次摘要的大小。
- **复现**（不需要密钥）：`.tmp/uat-repro/err2.txt` 里 `tokens 60000 降至 60002`——fixture 的第 4 条写着 `usage.input_tokens = 60000`，遮蔽之后那条留在尾部。
- **为什么 mock 那一半从来没抓到**：mock 桩的 `usage` 默认全 0（`provider/contract.py:25`），校准那一路永远是 0，读数只剩估算，遮蔽当然砍得动。**这是 ADR-0024「mock 全绿不算完成」的一条实锤证据。**

**这一场的判定**：**不符合**。遮蔽那一行本身在、只报一次、不在 stdout——都对；但那一行报的数说的是反话，而且 chat 不给 session id 导致 replay 那一半没法判。

---

## U3 · M5 的溢出：屏幕上有一行，会话不崩

窗口再压小到压缩救不了：

```powershell
# 这一条在当前 HEAD 上跑不起来（退出码 2）。今天能用的替代：
uv run minihns chat --workspace $WS --session-dir .tmp\uat\sessions @EP --window 70000 --reserve 100 --max-turns 6 --sandbox workspace-write --yes
```

让它读那份大文件。

| 要观察的 | 你看到的 |
|---|---|
| stderr 上有一行 `[段] CONTEXT_WINDOW_EXCEEDED` | **人**：`[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED`——同一个词打了两遍。 **核**：`_print_segment_note` 打 `f"{stop_reason}：{failure_code}"`（`main.py:592-595`），溢出时两者是同一个词（`turn_loop.py:521-523`）。 |
| 还有一行 `CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 <n> 已超过触发线 <m>` | **不符合**：这一行在 chat 里不存在。 **核**：那句 detail 确实被算出来了（`turn_loop.py:850`：`无可遮蔽的内容，预算读数 {reading} 已超过触发线 {line}`）也写进了 `error/context`（`turn_loop.py:513`），但 chat 的 `[段]` 那一行只打 reason 与 code，**detail 被丢掉**；`CODE: detail` 那个形状只在一次性入口（`_report_failure`，`main.py:217`）出现。**手册这一行是我写错的。** |
| 会话**不崩**：提示符还在，你可以接着问一句别的 | **一半符合**：提示符还在。**但接着问什么都立刻溢出**——你报的原文是每输入一句都得一条 `[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED`（「之前问了什么」「读了哪个文件？」各一条）。 **机制**：与 U2 同一条——读数被尾部那条 `input_tokens` 回报钉住，遮蔽砍不动它，于是每一段的每一次装配都越线。**会话活着但救不回来，屏幕上没有任何一句话告诉你这一点。** |
| 退出后 `$LASTEXITCODE` = **4** | **手册写错**：chat 里溢出是**段级收尾**，进程不退出；会话收尾的退出码是 0。4 只成立于 `run` / `serve`（`cli` 「退出码只取自固定表」）。 **未报**：你这一轮没读到退出码。 |
| 日志里有一条 `error/context` | **未报**。 **核**：`turn_loop.py:513` 写这条记录，payload 里带着那句 detail。 |

**这一场的判定**：**不符合**。溢出那一行在、会话不崩——都对；但那一行把同一个词打两遍、把唯一有用的那句话（读数与触发线）丢了，而且溢出之后会话进入不可恢复状态却没有给人任何指示。

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
| 第一次 Ctrl-C 之后：屏幕上有没有 `[段] ABORTED` 那一行 | **人**：没有。 **这是规格故意的**：`chat-repl` 「段不以正常回复收尾时 stderr 看得见一行」明写「段以 `MODEL_COMPLETED` 或 `ABORTED` 收尾时 MUST NOT 打印这一行」，代码照它做（`main.py:581` 的 `_SEGMENT_NOTE_SUPPRESSED`）。**手册这一行是我写错的**——它要人去找规格禁止的东西。要不要改这条规格，是人的裁决，不是缺陷。 |
| 会话继续（提示符回来，第二句能接着问） | **人**：会中断当前那次工具调用、会话继续、第二句能接着问，而且它答得出被中断那次调用返回了什么（结果已落日志、能被模型访问）。 **符合**。 |
| 日志里那一段以 `ABORTED` 收尾、会话没结束 | **人**：结果已落日志（你问它答得出）。 **核**：`error/abort` + `turn/end(ABORTED)` + `segment/end(ABORTED)`，不写 `session/end`。 |
| 提示符上 Ctrl-C：干净退出、退出码 | **人**：偶尔 traceback（见 U1 那一行）。 **未报**：`$LASTEXITCODE`。 |
| 批准提示长什么样（问人的那一问在屏幕上是什么措辞） | **人**（从 U3 的转述里）：`输入 y 或 n：`。 |

**这一场的判定**：**符合**（取消只塌当前段、会话继续、日志形状对）。**别扭两处**：中断之后屏幕上是一堆空行把新提示符推远（U1 那条空行缺陷在这里最刺眼）；`[段] ABORTED` 没有——那是规格的选择，要不要改由你裁决。

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
| 每帧三行：`id:` / `event:` / `data:`，`id` 就是日志里的 `seq` | **人**：三条命令都有效返回带 seq id 的结果。 **符合**。 |
| `data` 那一串 JSON 与日志整行内容一致 | **未报**（没做 replay 对照）。 |
| 断开后带 `Last-Event-ID: 6` 重连，从 `seq 7` 开始，不漏不重 | **人**：三条命令都有效返回。 **未报**：有没有真的从 `seq 7` 起。 |
| `?from=2` 时从 `seq 3` 开始（`from` 覆盖 header） | **人**：同上。 **未报**：起始 seq。 |
| 会话跑完进程自己退出，退出码 | **人**：「主进程自己退出打印退出码：`7ab810d0b9354dba878d549bce721920`」——**那串十六进制是 session id，不是退出码**（stdout 归 session id，`main.py:530`）。 **未报**：`$LASTEXITCODE`。 |
| **Ctrl-C 那一半**：重跑一次，在会话中途在终端 A 按 Ctrl-C → 日志最后一条不是半条记录、`replay` 不报 `REPLAY_MISMATCH` | **人**：屏幕上出现 `serve 监听 http://127.0.0.1:8321` / `3280c27e913c496599a6c5d364fc541a` / `ABORTED:`。 **不符合**：`ABORTED:` 后面是空的。 **核**：`_report_failure` 打 `f"{code}: {detail}"`（`main.py:217-219`），取消路径的 `SegmentOutcome.detail` 是空（`turn_loop.py:961-966` 只带 `denial_detail`，取消时它是 None）——可日志里那条 `error/abort` 写着 `detail: "取消被置位"`（`turn_loop.py:944`），**它没被带出来**。 **未报**：replay 对照。 |

**这一场的判定**：**事件流那一半符合**（三帧、带 seq、都返回）。**Ctrl-C 那一半不符合**：那一行是 `ABORTED:` 加一个悬空冒号，等于什么也没说；replay 那一半没判。

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
| 裸跑 `chat` 的退出码 | **未报**。 **核**：这一条是退出码 2（参数错误）。 |
| stdout 有没有东西 | **人**：没有。 |
| stderr 那一行原文 | **人**：`INVALID_ARGUMENT: --provider mock 需要 --fixture 指向 JSON 数组`（三条命令里前两条都是这一行）。 |
| `--help` 里 `--provider` 那行有没有写默认值 | **人**：没写（你贴的是 usage 那一行，被截断）。 |
| 你期望它怎么做（一句话） | 已在别处裁决：`MINIHNS_API_KEY` 在场就走 `openai`，`--provider deepseek` 走 `DEEPSEEK_API_KEY`。 |

**这一场的判定**：**基线照到了，而且已经被修掉了**——`add-key-driven-default-provider` 就是冲这一条去的：默认 provider 由 `MINIHNS_API_KEY` 在场决定，`--help` 写出每个设置类 flag 的内置默认值。**但这一场在 change B 的分支上重跑仍然会是同一个错**：这台机器没有 `MINIHNS_API_KEY`，密钥不在场 → 默认还是 mock → 还是那一条 `INVALID_ARGUMENT`。要看到新行为，先设那个变量（或给 `--provider deepseek` 配 `DEEPSEEK_API_KEY`）。

---

## 手册自身的错（我写的，跑之前就该改）

1. **U2 与 U3 的命令在当前 HEAD 与 `main` 上直接跑不起来**：`--window 60000 --reserve 200` 与 `--window 40000 --reserve 100` 都在 session 开始之前被拒，实测各是退出码 2、`INVALID_ARGUMENT: --window … 减去 --reserve … 与余量 65536 之后没有剩余压力预算`（`cli/main.py:337`）。这两场要等 `fix-small-window-compaction-dead-zone` 合进来才照原样跑得通；今天能用的替代是 `--window 70000 --reserve 100`。
2. **U2 说「session id 在 chat 启动时打在 stdout 上」**：规格没有这条要求（`chat-repl` 明写 stdout 上只有模型回复正文与提示符），代码也不打（只有 `run` 与 `serve` 打，`main.py:456` / `main.py:530`）。这不是你记错，是我凭空写了一条不存在的行为。
3. **U4 问「有没有 `[段] ABORTED` 那一行」**：规格明写 ABORTED 收尾 MUST NOT 打这一行。我把一条被禁止的行为写成了判据。
4. **U3 问「退出后 `$LASTEXITCODE` = 4」**：chat 里溢出是段级收尾、进程不退出，会话收尾退出码是 0。4 只在 `run` / `serve`。
5. **U3 期望的第二行 `CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 …`**：那个 `CODE: detail` 形状只在一次性入口出现；chat 只有 `[段]` 那一行。

---

## 不符合项清单（立修复 change 的输入）

| 编号 | 现象 | 分类 | 证据 |
|---|---|---|---|
| F1 | 提示符独占一行，输入落在空行 | 实现（屏幕反馈） | `main.py:646` |
| F2 | 只带工具调用的回合在 stdout 上打一条空行，工具回合越多空行越多，新提示符被推远 | 实现（屏幕反馈） | `main.py:576`；复现 `out2.txt` 第 2-4 行 |
| F3 | `[段] X：X` 同一个词打两遍，且把 outcome 里已有的 detail 丢掉 | 实现（屏幕反馈） | `main.py:592-595`、`turn_loop.py:521-523`、`turn_loop.py:850` |
| F4 | `[遮蔽] … tokens <前> 降至 <后>` 的「后」可以大于「前」 | 实现（预算读数） | 你报的 70485→71030、54481→54689；复现 60000→60002；机制 `budget.py:77-97` + `turn_loop.py:678-682` |
| F5 | 溢出之后会话不可恢复：每问一句都立刻溢出，屏幕上没有任何指示 | 实现 + 规格缺口 | 你报的连续三条；机制同 F4 |
| F6 | chat 不给人 session id，`replay` 无从下手 | 规格缺口 | `chat-repl` 的 stdout 要求；`main.py` 只有 run/serve 打 |
| F7 | 非 0 退出那一行 detail 是空：`ABORTED:` 悬空冒号 | 实现 | `main.py:217`、`turn_loop.py:961-966` vs `turn_loop.py:944` |
| F8 | 纯提示符 Ctrl-C 偶尔 traceback | 实现（未定位，无判据） | `main.py:644-690` 的 try 范围 |
| F9 | 段以 `ABORTED` 收尾时屏幕上什么都没有 | 规格如此，要不要改是裁决 | `chat-repl` L84、`main.py:581` |
| F10 | 裸跑默认档位仍是 mock 并报 `INVALID_ARGUMENT` | 已被 change B 修掉（本机没有 `MINIHNS_API_KEY` 所以照旧） | `loop/settings.py`、`config/layering.py:89` |
| S1 | 「各种状态下 Ctrl+C 都不会出现退出码」 | shell 现象 | Ctrl-C 在 PowerShell 里中断前台管道，`$LASTEXITCODE` 不保证更新；CLI 也从不打印退出码。要读退出码换 `cmd /c "… & echo %ERRORLEVEL%"` |
| S2 | 「主进程自己退出打印退出码：7ab810d0…」 | 读错了 | 那串是 session id（stdout 归 session id） |

## 复现证据（无密钥，可重跑）

```powershell
cd S:\Develop\mini-harness
cmd /c "uv run python -m mini_harness.cli.main chat --workspace .tmp\uat-repro --session-dir .tmp\uat-repro\sessions2 --provider mock --fixture .tmp\uat-repro\fixture2.json --yes < .tmp\uat-repro\in.txt > .tmp\uat-repro\out2.txt 2> .tmp\uat-repro\err2.txt"
```

- `err2.txt`：`[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED` 与 `[遮蔽] 折掉 seq 1 至 15：tokens 60000 降至 60002`（F3 + F4，且两行的先后次序与你贴的原文一致）。
- `out2.txt`：`> ` 独占一行、三条空行、然后才是回复（F1 + F2）。
- 同一份 fixture 加 `--window 70000 --reserve 100`：`[遮蔽] 折掉 seq 1 至 8：tokens 15045 降至 24`——mock 桩把 `usage` 报成 0 时遮蔽砍得动，砍不动的是真实端点回报的那个数（F4 的边界）。

## 跑完之后

把每一场的观察填进本文件，然后在对话里说一句「UAT 跑完了」，我会按填回来的东西判 M5 / M6 / M7 的 UAT 那一半，并把不符合的项立成修复 change。

**下一轮还缺的观察**：U1 / U4 / U5 / U6 的 `$LASTEXITCODE`（用 `cmd /c "… & echo %ERRORLEVEL%"` 读，别在 Ctrl-C 之后读）；U2 / U5 的 `replay` 对照；U1 的「真事是什么」一句话；U5 的 `Last-Event-ID: 6` 与 `?from=2` 各自从哪个 seq 起。
