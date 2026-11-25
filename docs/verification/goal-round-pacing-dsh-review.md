# DSH 对齐复核：goal-round-pacing

**日期**：2026-11-25。位置按流程（§0.4 第一道）：apply 之前之后各一次；本文记结论与记账。

**结论**：L3 与 L0 都记 `simplified`，**不是 aligned**。两条都不假装对齐。

## L3：`MAX_STEPS` 移出不续跑集合

| 项 | DSH（一手/本地记录） | mini | 结论 |
|---|---|---|---|
| 停止词 | `max-tokens` 是**模型输出长度**上限，触发即本轮停止（`dsh-reference/DSH运行时架构剖析.html` 的停止词表） | `MAX_STEPS` 是**一轮内工具步数**上限 | 无等价物 |
| 轮次驱动 | 目标轮在 turn 结束后判定；停止理由里没有「步数用尽」这一项 | 原先把 `MAX_TURNS` 加进不续跑集合，理由是「与 DSH max-tokens 同向」；改名后该理由不成立 | **纠正**：m13 复核第 42 行的记账在单位变化后失效；本 change 记 `simplified`（mini-specific） |

处置：不声称对齐 DSH；在 `goal` 规格里明写 `MAX_STEPS` 是轮边界，并在 `docs/lessons.md` L-103 记「改名要连单位与消费方一起改」。

## L0：goal 政策段

| 项 | DSH | mini | 结论 |
|---|---|---|---|
| 位置 | `tool:goal` 政策段随工具包提供（m13 复核记为 `deferred`，本地一手树不在 checkout，条文无法就地核验） | `session/start.goal_policy = "v1"`，`fold` 按版本注入受保护头部 | `simplified` |
| 作用域 | 按工具包；没有 goal 工具的会话不注入 | **所有**新会话都注入（含 `run`、子代理） | mini 更宽 |
| 可覆盖性 | 政策段属于工具包定义 | 不可被 `--append-system-prompt` 覆盖；没有配置键或 flag 能关掉 | 对齐「不可覆盖」这一层 |
| 版本化 | 无版本号（政策随代码走） | 文本按 `v1` 冻结；改文案必须升版本，否则旧日志 replay 会红 | mini 特有 |

处置：记 `simplified`；理由（全局注入、无工具包开关）写进 design D3 与 `context-projection` delta。

## m13 的 deferred 触发条件

m13 复核把政策段记为 `deferred`，触发条件是「真实使用里出现模型反复试错才知门槛的记录」。本 change 的触发证据是会话 `3a88a3fb…`：模型不知道轮/步、在一个人类轮里 8 步干完三章、`rounds_started = 0`、`max_rounds` 从未上场。这属于「模型不知道 goal 规则边界」的同族证据，但**不是**「反复试错才知门槛」那条原句。

**请人裁**：是否算命中 deferred 的触发条件。本文不自行把它记成「已命中」。
