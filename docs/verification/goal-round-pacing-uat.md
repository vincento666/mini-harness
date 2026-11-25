# UAT：goal-round-pacing

**状态**：骨架（propose 时立；apply 后补「实际结果」列）。
**归属**：长任务手感属于关键场次，按 ADR-0025 由人跑；agent 只准备场次与观察表，除非人再次明确授权代跑并在本文件标注偏离。

## 场次

| # | 命令 | 观察什么 | 通过判据 | 结果 |
|---|---|---|---|---|
| 1 | `minihns chat --max-steps 8`，用「只建目标、不动手」的提示词 | 人类轮建目标后结束，是否自动出现 `[轮] 1/4` 并开始第 1 目标轮 | 人类轮 `MODEL_COMPLETED` 或 `MAX_STEPS` 收尾后，日志出现 goal 来源 `user/message` 与 `rounds_started == 1` | 待跑 |
| 2 | 同上，但让模型在目标轮里写到撞 8 步 | 目标轮写满后是否自动开 `[轮] 2/4`，而不是回提示符 | 第二条 `turn/end.stop_reason` 仍是 `MAX_STEPS`，但随后有第三条 `turn/start`；`rounds_started == 2` | 待跑 |
| 3 | `minihns chat --max-steps 4`，不提目标，让它做一件长任务 | 没有目标时写满是否照旧停、回提示符 | 只有一条 `turn/end`（`MAX_STEPS`），没有 `[轮]` 行，提示符回来 | 待跑 |
| 4 | 场次 2 进行中按 Ctrl-C | 取消是否仍停（不自动续） | `[轮] 收尾 ABORTED`；日志 `turn/end ABORTED`、目标 `phase == "paused"`；不再出现新 `turn/start` | 待跑 |
| 5 | 场次 1 的会话 `minihns replay <id>` / 看 `session/start` | 政策段是否在会话开头、旧日志是否不受影响 | 新会话 `append_system_prompt` 非空且含「轮」「目标」；旧日志 replay 退 0 | 待跑 |

## 观察记录

- 终端：iTerm2 / Terminal.app（写清哪个）
- 端点：OpenRouter `qwen/qwen3.8-27b`（经 `--proxy http://127.0.0.1:7897`）
- 时间：
- 场次 1 实际：
- 场次 2 实际：
- 场次 3 实际：
- 场次 4 实际：
- 场次 5 实际：

## 已知偏离

- 暂无。
