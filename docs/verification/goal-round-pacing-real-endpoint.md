# 真实端点验收：goal-round-pacing

**日期**：2026-11-25
**端点**：OpenRouter `qwen/qwen3.8-27b`（`--proxy http://127.0.0.1:7897`，出口地区限制见 `verification-endpoint.md` §5）
**判据**：`MAX_STEPS` 不再阻止续轮；目标轮能连续推进；任务能完成并落 `complete`；额度用尽仍落 `round-limit`。

## 场次

| # | 任务 | 参数 | 轮次（turn/end 序列） | 目标终态 | 产物 | 结论 |
|---|---|---|---|---|---|---|
| 1 | 三章小说，每章一轮 | `--max-steps 4` | `MODEL_COMPLETED` / `MODEL_COMPLETED` / `MAX_STEPS` | `complete`（3 轮） | ch1–ch3 + 合稿 | 通过：模型按章分轮，最后一轮声明完成 |
| 2 | 压力：每轮只允许一步 | `--max-steps 1` | `MAX_STEPS` × 4 | `blocked(round-limit)`（3 轮额度） | 三章草稿 | 通过：每轮都撞上限，轮次照常 1→2→3，额度兜底生效 |
| 3 | 修复 `calc.py` 让测试通过 | `--max-steps 2` | `MAX_STEPS` × 4 | `complete`（3 轮） | `calc.py` 改为 `a + b`；`pytest` 1 passed | 通过：定位 / 修改 / 验证各占一轮，任务真的完成 |
| 4 | 三节报告（初版提示） | `--max-steps 2` | `MODEL_COMPLETED` × 2 + `MAX_STEPS` × 3 | `blocked(round-limit)`（4 轮后） | 三节 + 合稿 15911 B | 产物完成、声明缺失：模型没调 `complete`，属「完成声明在模型」的结构性正常 |
| 5 | 三节报告（要求完成声明） | `--max-steps 3` | `MODEL_COMPLETED` × 3 + `MAX_STEPS` × 2 | `complete`（4 轮） | 三节 + 合稿 3335 B | 通过：第 4 轮 `MAX_STEPS` 后接第 5 轮，`update_goal complete` 落盘 |

## 关键观察

- **`MAX_STEPS` 已恢复为轮边界**：场次 2、3、4、5 都出现「本轮 `MAX_STEPS` → 下一轮 `turn/start`」，`rounds_started` 逐轮递增；场次 2 在 3 轮额度用尽后照旧 `round-limit`。
- **不再一轮干完**：场次 3、5 的人类轮都只做该轮的事（建目标 + 第一步），后续轮次各做一段；模型能在政策段与目标轮正文的共同约束下分轮。
- **完成声明仍在模型**：场次 4 产物齐全但没调 `complete`，最终 `blocked`；场次 5 明确要求后落 `complete`。这与 `goal-rounds.md` 的「最终闸门在 harness，完成声明在模型」一致，不是驱动缺陷。
- **成本**：5 场均为真实调用；场次 2 的 `--max-steps 1` 是最强的语义探针，用最小 token 复现了续轮与额度兜底。

## 结论

**通过**。`MAX_STEPS` 语义恢复（写满一轮 = 轮边界，不解除武装、不停止续跑），目标轮在真实模型上能连续推进并完成任务；额度用尽与完成声明两条收尾都按规格落账。
