## Context

六条观察全部落在同一个文件里：`src/mini_harness/cli/main.py` 的 chat 与 serve 的打印段。内核（`loop/`、`context/`）不需要动——它已经把该说的都写进日志了，是入口没把它说给人听。

mock 那一半照不出这一族的原因要说清楚：seam ⑥ 的判据断言的是「stdout / stderr 里**有没有**某串字符」与退出码，没有一条断言「这一行长什么样、第几行」。空行、重复词、悬空冒号都是「有字符」的满足方式。

## Decisions

### D1 提示符不再自带换行：`sys.stdout.write(_CHAT_PROMPT)` + `flush()`
不再 `print`。**取舍**：管道用法下 stdout 可能以不带换行的 `> ` 结尾（最后一行不完整）。接受——chat 的 stdout 是给人看的屏幕，`> ` 之后本来就该等人打字；`minihns chat` 的输出被逐行喂给别的程序不是这条路径的用途（要一次性输出用 `run`）。判据把这条写死：管道喂一行、段以 `MODEL_COMPLETED` 收尾时，stdout 恰为 `> <正文>\n> `。

### D2 空回复不产生输出：判据是 `content.strip()` 非空
只带工具调用的回合 `content` 是空串，现在 `print("")` 留下一条空行。**取舍**：模型真给出一条全空白的回复时屏幕上什么都不出现。接受——那条 `model/response` 仍在日志里，`replay` 看得见；屏幕上「没有输出」与「输出了一条空白」对人没有区别。

### D3 段收尾那一行的组装规则：reason，然后不同的 code，然后 detail
`[段] <reason>`；`code` 与 `reason` 不同时追加 `：<code>`，相同时不追加；`detail` 非空时追加。于是：

- `[段] PROVIDER_ERROR：PROVIDER_HTTP_STATUS <httpx 那句>`（既有的 scenario 照旧成立）
- `[段] CONTEXT_WINDOW_EXCEEDED：无可遮蔽的内容，预算读数 54481 已超过触发线 54272`（人报的那条重复词消失，唯一有用的那句话回来了）
- `[段] MAX_TURNS`（没有失败结果）
- `[段] ABORTED`（取消没有失败结果）

**为什么不截断 detail**：最简实现，且 detail 短的时候截断是白加的。**代价**：provider 的 detail 可能是一整句英文，那一行会变长。

### D4 取消的段要打印那一行：改的是规格，不是实现
`chat-repl` 现在明令「段以 `ABORTED` 收尾时 MUST NOT 打印这一行」，实现照它做（`main.py:581` 的 `_SEGMENT_NOTE_SUPPRESSED`）。本 change 把 `ABORTED` 从这一半移到打印那一半。**取舍**：「正常收尾不打扰」与「你按了 Ctrl-C 屏幕上要有回应」之间的取舍；`MODEL_COMPLETED` 留在不打扰那一半。这条要 ADR-0028 落字（难回退：规格的反面集合被改过一次就会被再改回去；无上下文会困惑：名字「段不以正常回复收尾」与正文曾经互相矛盾；真实取舍：打扰与回应）。

### D5 session id 走 stderr，不改 stdout 投影规则
**为什么不放 stdout**：`chat-repl` 的 stdout 规则是「只有模型回复正文与提示符」，把 id 塞进去会让那条判据变形，也会让「逐行读 stdout 拿回复」这条路混进一行不是回复的东西。**为什么放 stderr 成立**：stderr 已经是段收尾与遮蔽反馈那两行的去处，人已经在读它；`serve` 已经在 stdout 打 id（一次性入口，stdout 归 id），chat 不是。代价：把 stderr 丢掉（`2>$null`）的人拿不到 id——那一行同时是「这次会话的日志在哪」的入口，值得留在屏幕上。

### D6 非 0 退出那一行：detail 为空时只打失败码，不带冒号
`_report_failure` 现在无条件打 `f"{code}: {detail}"`。**取舍**：取消收尾那一行只剩 `ABORTED`。日志里 `error/abort` 写着「取消被置位」（`turn_loop.py:944`），但 `SegmentOutcome.detail` 不带它（`turn_loop.py:961-966` 只带 `denial_detail`）。把它搬进 outcome 要改 `turn_loop` 的失败结果形状——那是另一族（内核的失败结果里该带什么），不在本 change。**待裁决**：要那一行也带上「取消被置位」就说一声，判据加一条、`turn_loop` 动一处。

### D7 traceback 的修法：把会话收尾纳入 `except KeyboardInterrupt` 的覆盖范围
现在 handler 装在 `_prepare_or_fail` 之后（`main.py:639`），`except KeyboardInterrupt` 只包住那个 while 循环（`main.py:644-686`），`end_session` 在 try 之外（`main.py:690`）——取消落进缝隙里就没人接。**改法**：收尾段（含 `end_session` 与它的打印）移进同一个 try 的覆盖范围，handler 的判定不变（有段在跑置位、没有段在跑走 `KeyboardInterrupt`）。判据：seam ⑥ 发真 Ctrl-C 在提示符上 → 退出码 0、stderr 里没有 `Traceback`。

### D8 取消类判据在 Windows 上不再 skip
`CREATE_NEW_PROCESS_GROUP` + `os.kill(pid, signal.CTRL_C_EVENT)` 发真 Ctrl-C，同步点是「先等 stdout 上出现 `> ` 再发信号」。**取舍**：这类判据对时序敏感、可能 flaky。接受并写死同步点，因为现在四条 SIGINT 子进程判据全被 skip，取消这条只有人在 U4 里判——ADR-0025 之后这条不该只靠人。

## Risks & Trade-offs

- **与 change A 的交界**：A 把溢出判据改成压力预算、并可能改「无可遮蔽的内容」那句 detail 的措辞（已知三处措辞差异）。本 change 的判据只断言「那一行含非空 detail、reason 这个词不重复」，**不断言 detail 的原文**，所以不与 A 撞。
- **与 change B 的交界**：B 的 `cli` delta 动 provider 与 `--help` 那两条 requirement，本 change 的 `cli` delta 是一条新的——不同 requirement，合并时不冲突。
- **`[段]` 行变长**：detail 长的 provider 失败那一行可能占两行屏幕。不截断。
- **连续溢出的「说明」需要 chat 记住上一个段的收尾理由**：一个局部变量（上一个段的 `stop_reason`），不新增状态机、不进日志。

## Open questions

- 取消那一行要不要带「取消被置位」（D6 的待裁决）。
- 那句「降不下去」的说明要不要同时给出建议命令（例如提示 `minihns chat` 新开一个会话）——规格只承诺「说明这件事」，措辞留给实现，UAT 那一半由人判它够不够。
