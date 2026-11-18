---
status: accepted
---

# 轮次计数写成字段，准入点取首条 `context/assembled`

DSH 的 `roundsStarted` 是 `GoalView` 的派生值——数的是「进入模型历史的 goal 来源消息」（`docs/subsystems/goal.md:119`）。mini 把它写成快照字段，并规定计数发生在该段**首条 `context/assembled` 落盘之后**（`src/mini_harness/loop/turn_loop.py` 的装配段），也就是这一轮真的装进上下文之后；`replay` 用一条交叉校验兜住「字段与消息数不一致」（`goals.goal_round_defect`）。`2026-11-18` 定字段与近似点，`2026-11-19` 人裁把准入点再往后挪一格到 `context/assembled`。

Considered options：照 DSH 派生、不落字段——否，mini 的日志是真源，但每次读轮号都要重扫全日志，快照不自足（`get_goal` 要回一份完整快照）；在写消息时计数（复核 B4 的原稿）——否，provider 在 `turn/start` 之前失败会白烧一轮，等于让抖动吃掉额度；在首条 `turn/start` 之后计数（2026-11-18 的版本）——否，`turn/start` 与 `context/assembled` 之间还有注入、折叠与装配内压缩，那段失败仍会白烧一轮，而 DSH 在「进历史」之前不计数。

Consequences：四事件顺序变成 `segment/start → goal 消息 → turn/start → context/assembled → goal/updated`，`goal/updated` 不再是「紧跟消息」的第二条；快照多一个必须自洽的字段，正确性由 `replay` 的「每条快照的 `rounds_started` 等于此前轮次条数」保证（4.4）；`rounds_started` 与 goal 消息条数是同一事实的两份写法，改任何一边都会让 `replay` 判红——这是刻意的 redundancy，不是遗漏；额度仍可能被「装配成功但 `model/request` 立刻失败」消耗掉一轮，这与 DSH 一致（消息已进历史）。
