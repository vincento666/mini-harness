# 真实端点验收：goal-round-pacing

**日期**：2026-11-25
**端点**：OpenRouter `qwen/qwen3.8-27b`（`--proxy http://127.0.0.1:7897`，出口地区限制见 `verification-endpoint.md` §5）
**判据**：`MAX_STEPS` 不再阻止续轮；目标轮能连续推进；任务能完成并落 `complete`；额度用尽仍落 `round-limit`。

## 场次

| # | 会话 | 任务 | 参数 | 轮次（turn/end 序列） | 目标终态 | 产物 | 结论 |
|---|---|---|---|---|---|---|---|
| 1 | `89715f6f…` | 三章小说，每章一轮 | `--max-steps 4` | `MODEL_COMPLETED` / `MODEL_COMPLETED` / `MAX_STEPS` | `complete`（3 轮） | ch1–ch3 + 合稿 | 通过：模型按章分轮，最后一轮声明完成 |
| 2 | `755771b1…` | 压力：每轮只允许一步 | `--max-steps 1` | `MAX_STEPS` × 4 | `blocked(round-limit)`（3 轮额度） | 三章草稿 | 通过：每轮都撞上限，轮次照常 1→2→3，额度兜底生效 |
| 3 | `aabfd8c3…` | 修复 `calc.py` 让测试通过 | `--max-steps 2` | `MAX_STEPS` × 4 | `complete`（3 轮） | `calc.py` 改为 `a + b`；`pytest` 1 passed | 通过：定位 / 修改 / 验证各占一轮，任务真的完成 |
| 4 | `2661d0f2…` | 三节报告（初版提示） | `--max-steps 2` | `MODEL_COMPLETED` × 2 + `MAX_STEPS` × 3 | `blocked(round-limit)`（4 轮后） | 三节 + 合稿 15911 B | 产物完成、声明缺失：模型没调 `complete`，属「完成声明在模型」的结构性正常 |
| 5 | `2fcf7997…` | 三节报告（要求完成声明） | `--max-steps 3` | `MODEL_COMPLETED` × 3 + `MAX_STEPS` × 2 | `complete`（4 轮） | 三节 + 合稿 3335 B | 通过：第 4 轮 `MAX_STEPS` 后接第 5 轮，`update_goal complete` 落盘 |
| 6 | `eadcfdb4…` | 无目标：列目录（不要建目标） | `--max-steps 1` | `MAX_STEPS` × 1 | 无目标事件 | — | 通过：无目标时写满即停，没有第二条 `turn/start` |
| 7 | `beb79902…` | 三节报告（**政策 `v2`** 复核场） | `--max-steps 3` | `MODEL_COMPLETED` × 3 + `MAX_STEPS` × 2 + `MODEL_COMPLETED` | `complete`（5 轮） | 三节 + 合稿 10923 B | 通过：`v2` 文本下自然收尾与写满续轮交替出现，第 6 轮 `update_goal complete` |

> 另有 `429592e3…`（无目标、`--max-steps 2`）模型两步 `MODEL_COMPLETED`，没撞上限，只作为「无目标正常收尾」的对照，不计入判据。

## 关键观察

- **`MAX_STEPS` 已恢复为轮边界**：场次 2、3、4、5、7 都出现「本轮 `MAX_STEPS` → 下一轮 `turn/start`」，`rounds_started` 逐轮递增；场次 2 在 3 轮额度用尽后照旧 `round-limit`。
- **不再一轮干完**：场次 3、5、7 的人类轮都只做该轮的事（建目标 + 第一步），后续轮次各做一段；模型能在政策段与目标轮正文的共同约束下分轮。
- **完成声明仍在模型**：场次 4 产物齐全但没调 `complete`，最终 `blocked`；场次 5、7 明确要求后落 `complete`。这与 `goal-rounds.md` 的「最终闸门在 harness，完成声明在模型」一致，不是驱动缺陷。
- **无目标仍停**：场次 6 只有一条 `turn/end MAX_STEPS`，没有 goal 事件、没有第二条轮。
- **政策段落盘与版本**：场次 1–6 的 `session/start.goal_policy == "v1"`；场次 7 是 `"v2"`（政策补停滞条件与条件句后的复核场）。两者首条 `context/assembled` 头部都含「写满步数上限」，`v1` 的日志仍按 `v1` 原文重算，replay 不受升版本影响。

## 结论

**通过**。`MAX_STEPS` 语义恢复（写满一轮 = 轮边界，不解除武装、不停止续跑），目标轮在真实模型上能连续推进并完成任务；额度用尽、完成声明、无目标三条收尾都按规格落账。场次 7 是政策升 `v2`（补停滞条件与条件句）之后的复核场，结论与 `v1` 的 1–6 场一致。
