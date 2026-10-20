---
status: superseded by ADR-0011
---

# Ctrl-C 取消整个 session；「继续回合」只属于超时

决策 15 写「Ctrl-C 与超时都写 `tool/cancelled` 事件并**继续回合**（不中断）」，而 M1/M2 落地的 turn-loop 规格与决策 29 的退出码表钉的是「取消 → `error/abort` + `turn/end: ABORTED` + 退出码 5」。M3 把派发段变成可被打断的地方，这条冲突不能再拖，因此裁决：**Ctrl-C 取消整个 session**——正在执行的那个调用写 `tool/cancelled`（配对它的 `tool/call`），随后 `error/abort` + `turn/end(ABORTED)`，退出码 5；「继续回合」只属于超时。理由：`minihns run` 是一次性 headless，按了 Ctrl-C 没有提示符可回，「打断当前工具、继续回合」在这种形状下的实际含义是「用户按了停止，进程接着往下干活」。

Considered options：两次 Ctrl-C（第一次取消当前工具、第二次终止 session）——否，一次性 run 里「第二次」没有语义位置，那是把交互式 REPL 的习惯搬进 headless CLI；Ctrl-C 不写 `tool/cancelled`——否，会留下没有配对结果的 `tool/call`，撞 fences 主规格「每个 `tool/call` 仍有配对 `tool/result`」。

代价与边界：决策 15 被**部分**推翻——「Ctrl-C 写 `tool/cancelled`」保留，「并继续回合」作废。`docs/handoff-2026-10-15.md` 是冻结的决策输入、不编辑它，本份 ADR 是权威更正处。M6 的 REPL 里「打断但不退出会话」是另一件事，届时另裁。
