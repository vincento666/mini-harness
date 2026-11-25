# UAT：goal-round-pacing

**状态**：已完成（2026-11-25）。
**归属**：**人已授权 agent 代跑**（2026-11-25 指令）。按 ADR-0025 这是有意偏离：关键场次本应由人坐在终端跑；本文件如实记偏离，不把代跑当人跑。

## 场次

| # | 命令 | 观察什么 | 通过判据 | 结果 |
|---|---|---|---|---|
| 1 | `run -p "写三章，每章一轮…" --max-steps 2/3` | 人类轮建目标后，写满或收尾是否自动进目标轮 | 出现 goal 来源 `user/message` 与第二条 `turn/start`，`rounds_started == 1` | **通过**：场次 3、5 均出现（会话 `aabfd8c3…`、`2fcf7997…`） |
| 2 | 同上，让目标轮写到撞步数上限 | 撞 `MAX_STEPS` 后是否自动开下一轮 | 第二条 `turn/end.stop_reason == MAX_STEPS`，随后有第三条 `turn/start`；`rounds_started` 递增 | **通过**：场次 3、5；场次 2（`--max-steps 1`）4 轮全部 `MAX_STEPS` 仍连续推进 |
| 3 | `run -p "列目录…不要创建目标" --max-steps 1` | 无目标时写满是否照旧停 | 只有一条 `turn/end`（`MAX_STEPS`），无 goal 事件、无第二条 `turn/start` | **通过**：会话 `eadcfdb4…` |
| 4 | 目标轮进行中 Ctrl-C | 取消是否仍停、不自动续 | `ABORTED` 收尾；目标 `paused`；不再出现新 `turn/start` | **未在真实端点跑**：由单测 `test_a_cancelled_round_pauses_the_goal_and_disarms_it` 覆盖；m13 UAT 场次 2 已在真控制终端验过同一路径 |
| 5 | 任一真实会话的 `session/start` 与首条 `context/assembled` | 政策段是否在会话开头且不可覆盖 | `goal_policy == "v1"`；头部含「写满步数上限」；显式 append 后政策仍在 | **通过**：会话 `2fcf7997…`、`eadcfdb4…` 均为 `goal_policy=v1`，头部含政策段；append 覆盖场景由单测覆盖 |

## 观察记录

- 终端：非交互（`run` 一次性入口，stdout 只有 session id；正文与轮次读日志）
- 端点：OpenRouter `qwen/qwen3.8-27b`，经 `--proxy http://127.0.0.1:7897`
- 时间：2026-11-25 12:55–13:10
- 场次 1/2：见 `docs/verification/goal-round-pacing-real-endpoint.md` 场次 1–3
- 场次 3：`eadcfdb4…`，`turns=[("s1","MAX_STEPS",1)]`，`goal events=[]`
- 场次 5：`2fcf7997…`，`goal_policy=v1`，头部 `policy_in_header=True`

## 已知偏离

- **代跑**：场次 1、2、3、5 由 agent 在真实端点上执行；场次 4 未跑真实端点，由单测与 m13 的真终端 UAT 覆盖。这是 ADR-0025 的有意偏离，归档时需人确认接受。
