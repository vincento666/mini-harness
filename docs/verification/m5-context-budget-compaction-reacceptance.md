# M5 `m5-context-budget-compaction` 真实端点重新验收（2026-10-23）

按 ADR-0024 重跑：mock 那一半是 2026-10-21 的门禁（403 条测试时是 385 条，本轮 408 条），这一份是**真实那一半**。端点是本机 Strata `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`（`n_ctx` 196608），密钥走用户作用域 `MINIHNS_STRATA_KEY` 逐条命令注入，不落盘不打印。工作区 `.tmp/reacc/ws`：`big.md` 247,988 字符 / 2,000 行，`huge.md` 409,248 字符 / 3,300 行。

## 判据逐条

| 判据（`docs/roadmap.md` 的 M5 行） | 结果 | 实测 |
| --- | --- | --- |
| 小 W 下触发压缩 | **通过** | session `4bd8dd0aea424c77b1a37e3be9a2a105`（`--window 80000 --reserve 100`，69 条记录）：`compaction/summary` 在 seq 42，`shadowed_range` 1 至 37，`tokens_before` 33227 → `tokens_after` 111，摘要是真实端点回的 254 个字符；之后 seq 44 / 53 / 62 三次 `model/request` 都成功 |
| 原文事件仍在日志里 | **通过** | 同一 session：遮蔽之后日志里仍有 63,254 字符的 `tool/result` 原文；`replay` 的 `final_context` 里头部之后是那条真实摘要，再后面是保留尾部的原文 `tool` 消息 |
| 压缩仍不够时以退出码 4 结束且日志里有对应 `error/*` | **通过（但只以「无可遮蔽」这一种形状出现，见下）** | session `70fa85600d484109b2f266506ee24c42`（`--window 70000 --reserve 100`）：`error/context` seq 24（`code: CONTEXT_WINDOW_EXCEEDED`）、`turn/end` seq 25 同一停止理由、`session/end` `turns: 4`、**退出码 4**、stderr `无可遮蔽的内容，预算读数 5933 已超过触发线 4364`。session `8de532bbf9d045d58ca3cf56cd55c7ad`（`--window 100000 --reserve 100`，一次 `read` 得到 424,641 字符 ≈ 106,161 估算 token）：`error/context` seq 10、**退出码 4**、stderr 读数超过触发线 34364 |
| `Usage` 进预算 | **通过** | 每条 `model/response` 的 payload 带 `usage`（`turn_id` / `content` / `tool_calls` / `usage` / `finish_reason`） |

## 这一跑查出来的东西（要回灌成判据的那类）

**三次溢出全部走「无可遮蔽」，没有一次是「压缩发生了、仍然不够」。** 机制在 `src/mini_harness/context/budget.py` 的 `shadowed_range`：保留尾部从最后一条候选起算，`_round_end` 把切点推到整组工具往返之后，当那一组本身就超保留线时落点越过最后一条候选，函数返回 `None`（`budget.py` 第 200 至 211 行）。算术上也一样：一次压缩成功后的表层不超过「头部 + 摘要 + 保留线」，保留线是 `0.16 W`、预算是 `W - reserve`；前者要超过后者需要 `reserve > 0.84 W`，而那时 `trigger_line = max(0, W - reserve - 65536) = 0`，压缩根本不会开始。**结论：M5 的「压缩仍不够」这条判据在当前预算形状下只能以「无可遮蔽」实现**，而「无可遮蔽」正是小窗口死区（`trigger_line < retain_line`）的落点。已作为该 change 的第一条证据，不在此处改实现。

## 待人跑的那一半

无。M5 的完成判据里没有需要终端的动作。
