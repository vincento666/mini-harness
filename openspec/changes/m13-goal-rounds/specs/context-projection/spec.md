# Spec Delta: context-projection

## MODIFIED Requirements

### Requirement: 折叠产出形状为受保护头部加保留尾部

系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 运行环境块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`role` 为 `user` 的消息有**三个**来源——一次性 `run` 的 `session/start` payload 里的 prompt（对话体第一条）、REPL 的 `user/message` 记录，以及 goal 轮次注入的 `user/message`（`source.kind == "goal"`，与 REPL 同形，按 `seq` 顺序进对话体）。随后是 assistant 消息与工具结果消息。`user/message` 与其它正文记录一样可进遮蔽范围。`segment/start` 与 `segment/end` 与 `turn/*` 一样是记账记录，MUST NOT 产出上下文里的消息，遮蔽它们对折叠结果没有效果。`goal/updated` MUST NOT 产出上下文里的消息——模型看到的目标事实来自 goal 轮次正文与工具调用历史。被 `compaction/summary` 遮蔽的记录不进入对话体（见「遮蔽范围由 compaction/summary 记录定义」）。

#### Scenario: 用户 prompt 是对话体第一条

- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

#### Scenario: goal 轮次正文进对话体

- **WHEN** 日志里有一条 `source.kind == "goal"` 的 `user/message`，正文为 `<goal_round>…</goal_round>`
- **THEN** 折叠结果里出现同内容的 `role: user` 消息，位置在 `seq` 顺序处，且 `goal/updated` 不产生任何消息

#### Scenario: 头部不被对话内容顶替

- **WHEN** fixture 的模型回复文本与内置系统提示完全相同
- **THEN** 折叠结果的第一条消息仍是内置系统提示

#### Scenario: 工具结果按顺序进入对话体

- **WHEN** 某回合产生一次 `tool/call` 与对应 `tool/result`
- **THEN** 折叠结果按发生顺序包含该 assistant 工具请求消息与对应工具结果消息

#### Scenario: REPL 的输入按 seq 顺序进对话体

- **WHEN** 一份日志里有两条 `user/message`，中间夹着一组工具往返
- **THEN** 折叠结果里两条 `role` 为 `user` 的消息与那组往返按 `seq` 顺序出现，且头部之后第一条仍是第一条输入

#### Scenario: 被遮蔽的输入不进对话体

- **WHEN** 一条 `user/message` 落在某条 `compaction/summary` 的 `shadowed_range` 内
- **THEN** 折叠结果里没有它对应的 `user` 消息，该摘要的 `system` 消息在表层里
