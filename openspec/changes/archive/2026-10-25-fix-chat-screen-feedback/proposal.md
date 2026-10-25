## Why

M5 / M6 / M7 的 UAT 第一轮（2026-10-23，人跑，观察记录在 `docs/verification/m5-m6-m7-uat.md`）报回来的六条里，有五条是同一族：**屏幕上说了什么、怎么说**。

- 提示符自己带一个回车，用户输入落在空行上（`cli/main.py:646` 是 `print(_CHAT_PROMPT)`）。
- 只带工具调用的回合 `content` 是空串，`print("")` 就是一条空行：工具回合越多空行越多，新提示符被推到很远下面（实测三个工具回合 → stdout 上三条空行）。
- 段收尾那一行是 `[段] CONTEXT_WINDOW_EXCEEDED：CONTEXT_WINDOW_EXCEEDED`——同一个词打两遍，而唯一有用的那句（`无可遮蔽的内容，预算读数 54481 已超过触发线 …`，`turn_loop.py:850` 算出来了、也写进 `error/context` 了）被丢掉。
- 段被人取消之后屏幕上什么都没有（规格明令禁止那一行：`chat-repl` 「段不以正常回复收尾时 stderr 看得见一行」）。人自己按了 Ctrl-C，然后屏幕上没有任何回应。
- 一次性入口中途取消时那一行是 `ABORTED:`——悬空冒号，后面是空的（`_report_failure` 打 `f"{code}: {detail}"`，取消路径的 detail 是空）。
- chat 不给人 session id，于是「跑完之后用 replay 对照」这类判据在 chat 里根本没法执行。
- 纯提示符上 Ctrl-C 偶尔留下 traceback（`end_session` 在 `except KeyboardInterrupt` 的范围之外）。

这些都不在 mock 那一半的观察面上：seam ⑥ 的判据看退出码、看日志、看 stdout 里有没有某串字符，**不看排版**。四道门禁全绿 + 真实端点跑过判据，这六条一条都没照出来。这是 ADR-0024 与 ADR-0025 那两条硬判据的第一批真实猎物。

## What Changes

- **提示符不再自带换行**：打印在不带换行的同一行上，输入紧跟在提示符之后。
- **空回复不产生输出**：`content` 为空或全空白的 `model/response` MUST NOT 在 stdout 上留下空行。
- **段收尾那一行改形状**：段以 `ABORTED` 收尾时**要**打印这一行（从被禁止的那一半里移出来）；当停止理由与失败码是同一个词时 MUST NOT 把同一个词打两遍，改为打印该失败结果的 `detail`（没有 detail 时只有那个词）。
- **溢出之后屏幕上说清楚**：段以 `CONTEXT_WINDOW_EXCEEDED` 收尾时那一行含造成它的 `detail`（当时的预算读数与触发线，或「无可遮蔽的内容」那句）；同一会话里连续两个段以同一理由收尾时，额外打印一行说明「这份会话的表层已经降不下去，退出并新开一个会话是可选动作」，每个会话最多一次。会话照旧继续接受输入（裁决：继续，但说清楚）。
- **chat 在 stderr 给出 session id**：会话开始时一行，不进 stdout、不进事件日志。
- **非零退出那一行不许悬空冒号**：一次性入口以非 0 退出时 stderr 那一行含失败码；有 `detail` 时含它，没有时 MUST NOT 打印冒号或空说明。
- **提示符上取消不得留下 traceback**：写 `session/end`、退出码 0、没有未捕获异常——这条现在是实现缝隙，没有判据。

## Out of scope

- **预算读数本身**：遮蔽之后仍留在尾部的那条 `usage.input_tokens` 回报继续充当当前表层的读数，于是「降至」后面的数比前面的大、溢出之后每问必溢出。那是另一族，在 `fix-post-compaction-budget-reading`。本 change 只负责把这件事**说清楚**，不负责让它不发生。
- **精细的 token 预算管理**（提前看当前表层是否即将立刻满、提前预警并提前压缩，照 DSH 的做法再决策）：记账，不在本 change，也不在下一个。
- 工具调用与结果上不上 stdout：规格明写 MUST NOT，本轮不动这条（人报的「工具调用看得见」实际看到的是空行，不是工具结果）。

## Impact

- **主规格**：`chat-repl`（MODIFIED 3、ADDED 2）、`cli`（ADDED 1）。
- **代码**：`src/mini_harness/cli/main.py` 一处集中——提示符的打印方式、`_print_new_replies`、`_print_segment_note`、`_print_shadow_feedback` 不动、`_report_failure`、`_serve_session` 与 `_chat_session` 的 try 范围。`src/mini_harness/loop/` 不动。
- **测试**：seam ⑥（真实子进程，判据看 stdout / stderr 的**排版**与内容）与 seam ①（取消收尾时的 stdout / stderr）。取消类判据在 Windows 上要用 `CREATE_NEW_PROCESS_GROUP` + `CTRL_C_EVENT` 发真 Ctrl-C——现在那四条被 skip，本 change 要有一条不 skip 的。
- **与既有 change 的关系**：`fix-small-window-compaction-dead-zone` 只动 `context-budget` 与 `turn-loop`；`add-key-driven-default-provider` 只动 `cli` 与 `config-layering` 里 provider 与 `--help` 那两条。本 change 动 `chat-repl` 全部、`cli` 一条新 requirement——与两者都不落在同一个 requirement 上。
- **编号预留**：ADR-0028 归本 change（把「取消的段要打印那一行」写进规格是一条真实取舍：正常收尾不打扰与取消要有回应之间的取舍）。`fix-post-compaction-budget-reading` 预留 ADR-0029。
