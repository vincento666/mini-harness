# 任务：goal-round-pacing

## 1 实现

- [x] 1.1 先写红判据：`next_round(goal=active, armed=True, stop_reason="MAX_STEPS")` 返回 `continue`；`goal=None` 或 `paused` 返回 `stop`（`tests/test_goal_rounds.py`）
- [x] 1.2 `loop/goal_driver.py`：把 `MAX_STEPS` 从 `NO_CONTINUE_REASONS` 删除；其余四项保留；同步集合上方的注释（只剩 `CONTEXT_WINDOW_EXCEEDED` 是「撞上限」）
- [x] 1.3 `events/fold.py`：定义 `GOAL_POLICY_VERSIONS = {"v1": "<文本>"}` 与 `GOAL_POLICY_VERSION = "v1"`；`_start_facts` 读 `session/start.goal_policy`；`protected_header` 在 `SYSTEM_PROMPT` 与人格/工具/环境块之后、`append_system_prompt` 之前插入对应版本文本
- [x] 1.4 `loop/turn_loop.py` 的 `start_session`：payload 写 `"goal_policy": GOAL_POLICY_VERSION`；不来自配置、没有 flag
- [x] 1.5 政策文本与 `render_goal_round` 的口径对齐：续跑条件写成条件句（active + 已武装 + 有额度 + 无未决问题），不承诺无条件续跑；不出现「写满即失败」
- [x] 1.6 检查 `settle_turn` 的失败分支：`MAX_STEPS` 不再走 `close_failed_round`，武装位保持；无目标时仍停

## 2 判据

- [x] 2.1 单测：驱动四类失败仍 `stop`，`MAX_STEPS` 为 `continue`（参数化）
- [x] 2.2 单测（经 `settle_turn`）：`ABORTED` → `phase == "paused"` 且 `armed == false`；其余三类 → `phase` 不变且 `armed == false`；`MAX_STEPS` → `armed` 保持
- [x] 2.3 黑盒：人类轮 `max_steps=2` 写满、目标 active → 出现 goal 来源消息与第二条 `turn/start`，`rounds_started == 1`
- [x] 2.4 黑盒：目标轮写满且 `rounds_started < max_rounds` → 开下一轮；两条 `turn/end.stop_reason` 都是 `MAX_STEPS`
- [x] 2.5 黑盒：无目标时写满 → 不开新轮，行为与基线一致
- [x] 2.6 端到端：新会话 `session/start.goal_policy == "v1"`；首条 `context/assembled.messages[0].content` 以 `SYSTEM_PROMPT` 开头、含政策段（「写满」「目标轮」）
- [x] 2.7 单测：显式 `--append-system-prompt "额外规则"` → 头部顺序为 `SYSTEM_PROMPT` → 政策段 → `额外规则`，政策段仍在
- [x] 2.8 合成 v2 日志（`session/start` 不带 `goal_policy`、含 `context/assembled`）→ `replay` 退 0、无 `REPLAY_MISMATCH`、头部无政策段
- [x] 2.9 单测：`GOAL_POLICY_VERSIONS` 的 `v1` 文本改了但版本没升 → 同一份合成日志重算与记录不一致
- [x] 2.10 政策升 `v2`：文本补停滞闸门、完成声明改成条件句；`v1` 原文保留在表里给旧日志重算（两轴 review F3/F7）
- [x] 2.11 黑盒：配置写 `goal_policy = "off"` → `INVALID_ARGUMENT`；`--goal-policy off` → `unrecognized arguments`（F5）
- [x] 2.12 黑盒：极小窗口下首步装配前超线 → `CONTEXT_WINDOW_EXCEEDED`、本轮无 `context/assembled`、`rounds_started` 仍为 0（F2）
- [x] 2.13 `GOAL_POLICY_VERSION` 必须命中 `GOAL_POLICY_VERSIONS`；`render_goal_round` 不写死「连续两轮」（F3/F4）

## 3 收尾

- [x] 3.1 全量门禁：ruff `format --diff` / `check`、`mypy --strict`、pytest 全量、`openspec validate --all --strict`
- [x] 3.2 真实端点验收：OpenRouter `qwen/qwen3.8-27b`（`--proxy http://127.0.0.1:7897`）5 场 + 无目标 1 场，记录在 `docs/verification/goal-round-pacing-real-endpoint.md`
- [x] 3.3 UAT 验收：**人已授权代跑**（2026-11-25），偏离记在 `docs/verification/goal-round-pacing-uat.md`
- [x] 3.4 变异测试一轮：记录 `docs/verification/goal-round-pacing-mutation.md`（3 条全杀）
- [x] 3.5 DSH 对齐账本：`docs/verification/goal-round-pacing-dsh-review.md`（L3/L0 均 `simplified`；与 m13 那条 `deferred` 的关系已写成「相关但不同族」的**分析**，并列出两条可选记法——**仍待人裁**，本 change 不自行关闭那条 `deferred`）
- [x] 3.6 两轴 code review 与对照门禁（子代理，归档前）：`docs/verification/goal-round-pacing-code-review.md`
- [x] 3.7 Learning Gate：L-103「改名要连单位与消费方一起改」进 `docs/lessons.md` 收件箱
- [x] 3.8 文档：`docs/reference/goal-rounds.md` 驱动表删掉 `MAX_STEPS` 不续行、加「轮边界」一行；`docs/CURRENT.md` 更新
- [x] 3.9 改名收尾：`goal` 已在 `align-turn-step-naming` 的 4.1 清单里；本 delta 已用新词重写「轮次驱动与上限」
- [x] 3.10 待办登记：L4 写进 `docs/CURRENT.md` 开放缺口（`goal-round-budget`）
- [x] 3.11 两轴 review 的 7 条 finding 全部处置（F1–F7），处置表在 `goal-round-pacing-code-review.md`
