# 提案：把「写满一轮」从失败改成轮边界

## 为什么

2026-11-25 的 UAT（会话 `3a88a3fb…`）暴露了一条让目标轮次完全失效的路径：

- 模型在**人类轮**里 8 步内写完三篇并合稿，第 8 步撞 `max_steps=8`；
- `turn/end.stop_reason = MAX_STEPS`，而 `MAX_STEPS` 在 `NO_CONTINUE_REASONS` 里，驱动直接按失败收尾、不续轮；
- 于是 `rounds_started = 0`，`max_rounds = 4` 一次没花，目标悬在 `active`，人看到的是「怎么都不进第二轮」。

根因不是模型「不肯分轮」，而是**把「轮内步数上限」当成了「失败收尾」**。旧名 `MAX_TURNS` 里的 `turn` 指的是今天的**步**（旧词把它读作「回合」），它一直是「一次输入内最多几步」；改名后词义才和事实对上——之前被误读成「轮数上限」，用完就停的裁决正是这个误读的产物。旧理由（对齐 DSH 的 max-tokens 停止）也不再成立：max-tokens 是模型输出长度上限，不是一轮里的工具步数。

第二个缺口是模型根本不知道「轮」的存在：`fold.py` 的内置系统提示只有一句「你是 mini-harness 的 agent…」，没有轮/步、人类轮与目标轮的说明。模型只能从 `create_goal` 的一句工具描述里猜。于是它选最省事的策略：一轮干完。

## 要改什么

- **L3（硬约束，治本）**：把 `MAX_STEPS` 移出 `NO_CONTINUE_REASONS`。撞步数上限 = 本轮收尾，驱动按既有条件判续轮（`phase == active`、已武装、`rounds_started < max_rounds`、无未决问题、未触发停滞）。`turn/end.stop_reason` 仍是 `MAX_STEPS`，词表与日志事实都不变。
- **L0（配套，让模型知道为什么）**：内置系统提示之后注入一段**不可覆盖**的 `tool:goal` 政策——轮/步是什么、写满不是失败、人输入开的轮不推进目标轮次、创建目标后想分轮就收尾、真正完成才调 `complete`。落点是 `session/start.goal_policy = "v1"`：折叠从日志里的版本号取对应文本，`--append-system-prompt` 只能追加在它之后、覆盖不了；旧日志没有这个字段，replay 不受影响。

## 不做什么

- **不做 L1（工具描述加条件句）与 L2（`create_goal` 后硬停后续工具）**：DSH 没有这两层约束，按对齐纪律不做。
- **不做 L4（轮内工作量预算）**：另开 `goal-round-budget` 记账，触发条件是「L3 之后仍出现一轮里写太多、轮次粒度不够用」。
- **不改 `SYSTEM_PROMPT` 常量本身**：那会让所有历史日志的 `context/assembled` 重算不一致（L-097 金样本的坑）。政策段走 `append_system_prompt`，旧日志里是空串，replay 不变。
- **不改 `turn/end` 词表、`max_steps` 默认值、`max_rounds` 默认值**。
- **不改 `create_goal` 的人类轮约束**：建目标仍只允许人类开口的轮。

## Impact

- 行为：有目标的会话里，撞 `MAX_STEPS` 不再停死；驱动会开下一轮，直到完成、额度用尽、停滞或其他失败收尾。
- 成本：目标轮的步数上限从 `max_steps` 变成 `max_steps × max_rounds`（默认 8×32=256），另加人类首轮的 8 步，共 264 步；部署可配。无目标的会话**驱动行为**不变，但系统提示多一段政策（模型可见输入变了，见 design D3 的代价）。
- 测试：`test_goal_rounds.py` 的驱动判定用例（把 `MAX_STEPS` 从「不续跑」集合里拿出来，补续跑正向用例）；新增「`session/start.goal_policy == "v1"` + 首条 `context/assembled` 含政策段」「显式 `--append-system-prompt` 后政策段仍在」「无 `goal_policy` 的合成 v2 日志 replay 不变」三条判据；`append_system_prompt` 的默认值**不动**，`test_cli_config.py:78` 与 `test_context_fold.py` 的等值断言都不受影响。
- 文档：`docs/reference/goal-rounds.md` 的驱动表、`docs/CURRENT.md`。
- 规格：`goal` 的「轮次驱动与上限」、`context-projection` 的「系统提示……只能追加」。
