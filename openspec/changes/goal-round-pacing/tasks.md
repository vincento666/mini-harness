# 任务：goal-round-pacing

## 1 实现

- [ ] 1.1 先写红判据：`next_round(goal=active, armed=True, stop_reason="MAX_STEPS")` 返回 `continue`；`goal=None` 或 `paused` 返回 `stop`（`tests/test_goal_rounds.py`）
- [ ] 1.2 `loop/goal_driver.py`：把 `MAX_STEPS` 从 `NO_CONTINUE_REASONS` 删除；其余四项保留
- [ ] 1.3 `loop/settings.py`：`DEFAULT_APPEND_SYSTEM_PROMPT` 改为 `tool:goal` 政策段（轮/步、写满不是失败、人类轮与目标轮、创建后想分轮就收尾、完成才 `complete`；用「若你有 `create_goal` 工具」的条件句）
- [ ] 1.4 政策段与 `render_goal_round` 的口径对齐：不出现「写满即失败」的相反说法；必要时补一句引用
- [ ] 1.5 检查 `settle_turn` 的失败分支：`MAX_STEPS` 不再走 `close_failed_round`，武装位保持；无目标时仍停

## 2 判据

- [ ] 2.1 单测：驱动四类失败仍 `stop`，`MAX_STEPS` 为 `continue`（参数化）
- [ ] 2.2 单测：`ABORTED` 仍把 `active` 目标置 `paused` 并解除武装；其余三类只解除武装
- [ ] 2.3 黑盒：人类轮 `max_steps=2` 写满、目标 active → 出现 goal 来源消息与第二条 `turn/start`，`rounds_started == 1`
- [ ] 2.4 黑盒：目标轮写满且 `rounds_started < max_rounds` → 开下一轮；两条 `turn/end.stop_reason` 都是 `MAX_STEPS`
- [ ] 2.5 黑盒：无目标时写满 → 不开新轮，行为与基线一致
- [ ] 2.6 单测：默认 `append_system_prompt` 含政策关键词；`SYSTEM_PROMPT` 常量原文不含政策句
- [ ] 2.7 单测：显式 `--append-system-prompt` 覆盖默认，不出现两段来源
- [ ] 2.8 金样本：`append_system_prompt` 为空串的旧日志 `replay` 退 0、无 `REPLAY_MISMATCH`

## 3 收尾

- [ ] 3.1 全量门禁：ruff `format --diff` / `check`、`mypy --strict`、pytest 全量、`openspec validate --all --strict`
- [ ] 3.2 真实端点验收：OpenRouter `qwen/qwen3.8-27b`（`--proxy http://127.0.0.1:7897`）跑一次「人类轮写满 → 目标轮接上」，记录 `rounds_started` 与 `turn/end`（`docs/verification/goal-round-pacing-real-endpoint.md`）
- [ ] 3.3 UAT 验收：人跑；场次手册 `docs/verification/goal-round-pacing-uat.md`（关键场次是长任务手感，按 ADR-0025 不得由 agent 代跑）
- [ ] 3.4 变异测试一轮：记录 `docs/verification/goal-round-pacing-mutation.md`，存活变异补测试
- [ ] 3.5 两轴 code review 与对照门禁（子代理，归档前）
- [ ] 3.6 Learning Gate：可复用教训写进 `docs/lessons.md` 收件箱，没有就写 `NO-PROMOTION`
- [ ] 3.7 文档：`docs/reference/goal-rounds.md` 的驱动表删掉 `MAX_STEPS` 不续行；`docs/reference/h2-streaming-and-reasoning.md` 若提到停止理由也同步；`docs/CURRENT.md` 活动 change 与门禁读数更新
- [ ] 3.8 待办登记：L4（轮内工作量预算）写进 `docs/CURRENT.md` 开放缺口，change 名 `goal-round-budget`，触发条件「L3 之后仍出现一轮里工作量过大、轮次粒度不够」
