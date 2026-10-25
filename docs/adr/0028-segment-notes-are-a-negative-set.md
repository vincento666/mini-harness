---
status: accepted
---

# 段收尾那一行用反面集合：只有 `MODEL_COMPLETED` 不打扰

`chat-repl` 的规格原先从正面写这条：「段以 `ABORTED` 收尾时 MUST NOT 打印这一行」，实现照它做（`_SEGMENT_NOTE_SUPPRESSED` 里躺着 `MODEL_COMPLETED` 与 `ABORTED` 两个名字）。`fix-chat-screen-feedback` 把它反过来写：规格只留一条「正常收尾不打扰」的场景，其余收尾理由（`ABORTED`、`MAX_TURNS`、`FENCE_DENIED`、`CONTEXT_WINDOW_EXCEEDED`、provider 那一族）一律给人一行，实现里反面集合只剩 `MODEL_COMPLETED`。**取舍**是「正常收尾不打扰」与「你按了 Ctrl-C 屏幕上要有回应」之间的取舍，而反面集合让**新增的收尾理由默认是看得见的**——`loop/` 以后多一种收尾理由，屏幕上默认就有那一行，要让它安静得显式地把它写进集合。

## Considered options

- **正面清单（要打印的理由列出来）**：被否。这个形状下新增的收尾理由默认没有那一行，而「屏幕上看不见发生过的收尾」正是本 change 要修的病。
- **把「打不打」搬进 `loop/`**：被否。屏幕上打不打是 CLI 的判断；回合循环不该知道有人在看着（不变量 A：日志是唯一真源，屏幕是它的投影）。
- **保持原规格、只把 `ABORTED` 从集合里删掉**：被否。规格正文与常量名字互相矛盾（旧场景名「段不以正常回复收尾」与正文说的不是同一件事），下次接手会照着矛盾的那一半改。

## Consequences

- 反面集合被改过一次就有被改回去的风险：以后有人觉得「取消那一行太吵」，第一反应是把 `ABORTED` 塞回集合。要改先改规格的场景，再改集合，两处一起；这份 ADR 记录的是「为什么是反面」而不只是「为什么是 `ABORTED`」。
- 屏幕上的那一行不是新事实：它由 `segment/end` 与 `error/*` 已有的字段组装（design D3），不进日志、不进 stdout。以后新增收尾理由时**不需要**为它新增事件类型。
