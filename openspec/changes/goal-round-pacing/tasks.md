# 任务：goal-round-pacing

## 1 实现

- [ ] 1.1 先写红判据：`next_round(goal=active, armed=True, stop_reason="MAX_STEPS")` 返回 `continue`；`goal=None` 或 `paused` 返回 `stop`（`tests/test_goal_rounds.py`）
- [ ] 1.2 `loop/goal_driver.py`：把 `MAX_STEPS` 从 `NO_CONTINUE_REASONS` 删除；其余四项保留；同步集合上方的注释（删掉「两个是撞到自己的上限」的旧说法，只剩 `CONTEXT_WINDOW_EXCEEDED`）
- [ ] 1.3 `loop/settings.py`：`DEFAULT_APPEND_SYSTEM_PROMPT` 改为 `tool:goal` 政策段；**同时**把 `SessionSettings.append_system_prompt` 的字段默认改成同一个常量（两处默认必须一致）
- [ ] 1.4 `cli/main.py`：`--append-system-prompt` 的 help 从「默认是空串」改为「默认是内置的 goal 政策段；显式给出会覆盖它」
- [ ] 1.5 政策段与 `render_goal_round` 的口径对齐：不出现「写满即失败」的相反说法；政策段里的续跑条件写成条件句（active + 已武装 + 有额度 + 无未决问题），不承诺无条件续跑
- [ ] 1.6 检查 `settle_turn` 的失败分支：`MAX_STEPS` 不再走 `close_failed_round`，武装位保持；无目标时仍停

## 2 判据

- [ ] 2.1 单测：驱动四类失败仍 `stop`，`MAX_STEPS` 为 `continue`（参数化）
- [ ] 2.2 单测（经 `settle_turn`，不是纯函数）：`ABORTED` → `phase == "paused"` 且 `armed == false`；其余三类 → `phase` 不变且 `armed == false`；`MAX_STEPS` → `armed` 保持
- [ ] 2.3 黑盒：人类轮 `max_steps=2` 写满、目标 active → 出现 goal 来源消息与第二条 `turn/start`，`rounds_started == 1`
- [ ] 2.4 黑盒：目标轮写满且 `rounds_started < max_rounds` → 开下一轮；两条 `turn/end.stop_reason` 都是 `MAX_STEPS`
- [ ] 2.5 黑盒：无目标时写满 → 不开新轮，行为与基线一致
- [ ] 2.6 端到端：不经 flag/config 开一个会话 → `session/start.append_system_prompt` 非空且含「轮」「目标」；首条 `context/assembled` 的 `messages[0].content` 以 `SYSTEM_PROMPT` 开头、含政策段
- [ ] 2.7 单测：显式 `--append-system-prompt "额外规则"` → 头部只有「额外规则」，不含默认政策（不出现两段来源）
- [ ] 2.8 合成一份 v2 日志（`append_system_prompt=""`、至少一条 `context/assembled`，照 `test_cli_replay.py:123` 的写法）→ `replay` 退 0、无 `REPLAY_MISMATCH`；v1 日志已不可读，不要拿 `sessions/` 里的旧文件当样本

## 3 收尾

- [ ] 3.1 全量门禁：ruff `format --diff` / `check`、`mypy --strict`、pytest 全量、`openspec validate --all --strict`
- [ ] 3.2 真实端点验收：OpenRouter `qwen/qwen3.8-27b`（`--proxy http://127.0.0.1:7897`）跑一次「人类轮写满 → 目标轮接上」，记录 `rounds_started` 与 `turn/end`（`docs/verification/goal-round-pacing-real-endpoint.md`）
- [ ] 3.3 UAT 验收：人跑；场次手册 `docs/verification/goal-round-pacing-uat.md`（关键场次是长任务手感，按 ADR-0025 不得由 agent 代跑）
- [ ] 3.4 变异测试一轮：记录 `docs/verification/goal-round-pacing-mutation.md`，存活变异补测试
- [ ] 3.5 DSH 对齐账本：写 `docs/verification/goal-round-pacing-dsh-review.md`——L3 记 `simplified`（`MAX_STEPS` 是 mini 的步数上限，DSH 的 `max-tokens` 是模型输出长度，二者无等价物，并纠正 m13 复核里「与 DSH max-tokens 同向」的旧记账）；L0 记 `simplified`（DSH 是 `tool:goal` 自带政策段，mini 是全局可覆盖的 append，作用域与覆盖代价写清）；请人裁 m13 的 deferred 触发条件是否算命中
- [ ] 3.6 两轴 code review 与对照门禁（子代理，归档前）
- [ ] 3.7 Learning Gate：可复用教训写进 `docs/lessons.md` 收件箱，没有就写 `NO-PROMOTION`
- [ ] 3.8 文档：`docs/reference/goal-rounds.md` 的驱动表删掉 `MAX_STEPS` 不续行；`docs/CURRENT.md` 活动 change 与门禁读数更新
- [ ] 3.9 改名收尾：把 `goal` 加进 `align-turn-step-naming` 的 4.1 清单（当前清单不含它）；本 delta 已用新词重写「轮次驱动与上限」，其余 Requirement 由 4.1 统一
- [ ] 3.10 待办登记：L4（轮内工作量预算）写进 `docs/CURRENT.md` 开放缺口，change 名 `goal-round-budget`，触发条件「L3 之后仍出现一轮里工作量过大、轮次粒度不够」
