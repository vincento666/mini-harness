# 任务：goal-ux-one-line

- [x] 1.1 `fold.py` 新增 `GOAL_POLICY_VERSIONS["v3"]`（v1/v2 原文不动），`GOAL_POLICY_VERSION = "v3"`
- [x] 1.2 `tools/goal.py` 的 `create_goal` 描述改条件句（何时建、建完只计划并结束本轮、内容从目标轮 1 开始）
- [x] 1.3 判据：政策 v3 含「一句话」「建目标的那一轮只做计划」「每个目标轮只推进一块」「纯问答」等句子；`GOAL_POLICY_VERSION` 命中表；旧版本仍按原文重算
- [x] 1.4 真端点验收：3 场**一句话提示词**（不加流程说明），看自动建目标、分轮推进、轮边界停下、完成才 complete；记录会话 id 与读数
- [x] 1.5 门禁：`uv run pytest` 全绿、`ruff`、`mypy --strict`、`openspec validate --all --strict`
- [x] 1.6 文档：`docs/CURRENT.md` 政策版本与开放缺口同步；UAT/验收记录写进 `docs/verification/goal-ux-one-line-real-endpoint.md`
