# M6 `m6-chat-repl` 真实端点重新验收（2026-10-23）

按 ADR-0024 重跑：mock 那一半是门禁四道（本轮 408 条通过 / 5 条跳过），这一份是**真实那一半**。端点与密钥同 `m5-context-budget-compaction-reacceptance.md`。

## 判据逐条

| 判据（`docs/roadmap.md` 的 M6 行 + 本轮新落地的 chat 规格） | 结果 | 实测 |
| --- | --- | --- |
| REPL 续跑同一会话内核 | **通过** | session `1123346cda5b43efa26a2ad5dcb1befb`（90 条记录，`--window 80000 --reserve 100 --max-turns 8`）：2 个 `segment/start`，段 1 `segment/end` = `MAX_TURNS`（8 个 `turn/end`），段 2 `segment/end` = `MODEL_COMPLETED`；段 2 的第二条 user 消息与它的 `read` 往返出现在 `replay` 的 `final_context` 里，头部之后紧跟着**两条真实端点回的摘要**（system 消息），段 2 的回答直接引用了段 1 被遮蔽后剩下的结论（`big.md` 共 247,990 字节、2,000 行、`value = 7 × N`）并答出 step 1000 = 7000 |
| 压缩与遮蔽在屏幕上看得见（本轮新规格） | **通过** | 同一次 chat 的 stderr：`[遮蔽] 折掉 seq 1 至 8：tokens 33046 降至 120` 与 `[遮蔽] 折掉 seq 14 至 20：tokens 33173 降至 197`，各一次；日志里两次 `compaction/summary` |
| 段不以正常回复收尾时 stderr 看得见一行（本轮新规格，反面集合） | **通过** | 同一次 chat 的 stderr 有 `[段] MAX_TURNS`；`MODEL_COMPLETED` 收尾的段 2 不打扰 |
| 围栏拒绝收尾的段在屏幕上有一行 | **通过** | session `9609937eb2554e34a59e22e753838613`（不带 `--yes`）：stderr 只有 `[段] FENCE_DENIED：APPROVAL_UNAVAILABLE` 一行；日志 2 段，段 1 `FENCE_DENIED`、`error/*` 的 code 是 `APPROVAL_UNAVAILABLE`，**会话继续**到第二条输入并 `MODEL_COMPLETED`，退出码 0 |
| 遮蔽反馈不是日志的投影 | **通过** | `minihns replay 1123346cda5b43efa26a2ad5dcb1befb` 退出码 0、无 `REPLAY_MISMATCH`；replay 的 stdout 里没有「遮蔽」二字，日志整份也没有 |
| 取消一个回合后会话继续 | **待人** | 需要终端前的 Ctrl-C；Windows 上四条 SIGINT 子进程判据仍是 skip（要 Linux runner） |

## 这一跑查出来的东西

真实端点下 chat 的**回合消耗比 mock 桩大得多**：段 1 用完 8 个回合才收尾，模型在 `cmd` 不可用的命令上绕圈（`ls` / `pwd` / `wc` 各失败一次，再改用 `node -e` 与 `python -c`）。mock 桩的 chat 测试里 `--max-turns` 从不是约束，真实端点下它是。这不是缺陷，但它意味着 chat 的 mock 判据对「一段能走完多少事」没有覆盖。

## 待人跑的那一半

Ctrl-C 取消一个回合后会话继续；以及 tty 下的提示符与逐段输出观感。
