---
status: accepted
---

# 段的边界对两种入口都写；人话住哪儿由 `entry` 说

M6 加 `minihns chat`：一次 chat 恰有一份 session 日志、一个 `session_id`，`session/start` 在第一条输入之前写出、`session/end` 只在会话收尾时写出。事件词表加三个值（`user/message`、`segment/start`、`segment/end`），`session/start` 加一个 `entry` 字段（`run` | `chat`）。段的边界**两种入口都写**：内核只有一种循环，`run` 也是一个段——「段」因此是日志里的事实，不是 REPL 的私有概念，判据也只用一套。代价是已钉死事件序列的六处既有判据里四处要改（design 的测试策略表里写明），那是已计代价，不是回归。**这个数字实测偏低（2026-10-21 收尾轮更正）**：`git diff main...HEAD` 里新增的 `segment/start` / `segment/end` 断言共 47 行，分布在 **8 个测试文件**——`test_turn_loop.py` 16、`test_context_fold.py` 10、`test_turn_compaction.py` 7、`test_event_vocabulary.py` 6、`test_cli_run.py` 4、`test_turn_cancel.py` 2、`test_approval_gate.py` 1、`test_cli_replay.py` 1；涉及的测试函数约 21 个。design 的表列的六处里 `test_event_log_append.py` 一行没改，另有四个文件不在那张表上。Shotgun Surgery 的账记进 ADR-0002。

不对称留在人话这一处：`run` 的人话住在 `session/start.payload.prompt`，`chat` 的人话住在 `user/message`，`chat` 的 `prompt` 是空串。读一份日志要先看 `entry` 才知道去哪儿找人话。

Considered options：段边界只 chat 写（否：内核就要有两条路、判据也要双份，而「内核不知道 REPL」这条就守不住）；`run` 的 prompt 也写成一条 `user/message`（否：`session/start` 已经记着这次运行的全部入参，改它要连动 M1 至 M5 钉死的序列）；给「人结束了会话」加一个新的 `stop_reason`（否：`StopReason` 是回合终止结果的名字，EOF 与提示符上的 Ctrl-C 不是回合的终止结果）。

Consequences：会话收尾复用 `MODEL_COMPLETED`——`session/end.payload.stop_reason` 因此分不清「模型自己收尾」与「人收尾」，要分清得先给词表加一个在回合层没有对应物的值。`max_turns` 是**段内**上限，会话级没有上限：DSH 的 turn / step 两层都没有轮次上限，它唯一的轮次上限是委派工具的 `maxRounds`（默认 256），归 seam ⑦ 与 M15，不与 `max_turns` 混名。
