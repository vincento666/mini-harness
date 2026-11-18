---
status: proposed
---

# 轮次计数写成字段，准入点取首条 `turn/start`

DSH 的 `roundsStarted` 是 `GoalView` 的派生值——数的是「进入模型历史的 goal 来源消息」（`docs/subsystems/goal.md:119`）。mini 把它写成快照字段，并规定计数发生在该段**首条 `turn/start` 落盘之后**（`src/mini_harness/loop/turn_loop.py:1190`）；`replay` 用一条交叉校验兜住「字段与消息数不一致」（`goals.goal_round_defect`）。`2026-11-18` 落定，待人裁。

Considered options：照 DSH 派生、不落字段——否，mini 的日志是真源，但每次读轮号都要重扫全日志，且快照不是自足的（`get_goal` 要回一份完整快照）；在写消息时计数（复核 B4 的原稿）——否，provider 在 `turn/start` 之前失败会白烧一轮，等于让抖动吃掉额度；在首条 `context/assembled` 之后计数——更贴 DSH 的「进入模型历史」，但四事件顺序要改成 `turn/start → context/assembled → goal/updated`，契约行为 1 的三条判据全要跟着动，本轮先不做。

Consequences：快照多一个必须自洽的字段，正确性由 `replay` 的「每条快照的 `rounds_started` 等于此前轮次条数」保证（4.4 已落）；`turn/start` 与 `context/assembled` 之间（注入契约、注入技能目录、读日志、折叠、必要时压缩）失败会扣掉一轮，而 DSH 不会——窗口不大但真实，要消掉就把计数再往后挪一格（即上面第三个选项）；`rounds_started` 与 `rounds` 消息数是同一事实的两份写法，改任何一边都会让 `replay` 判红，这是刻意的 redundancy，不是遗漏。
