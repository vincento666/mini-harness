## MODIFIED Requirements

### Requirement: 折叠产出形状为受保护头部加保留尾部
系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`role` 为 `user` 的消息有两个来源——一次性 `run` 的 `session/start` payload 里的 prompt（对话体第一条），以及 REPL 的 `user/message` 记录（按 `seq` 顺序进对话体）。随后是 assistant 消息与工具结果消息。`user/message` 与其它正文记录一样可进遮蔽范围。`segment/start` 与 `segment/end` 与 `turn/*` 一样是记账记录，MUST NOT 产出上下文里的消息，遮蔽它们对折叠结果没有效果。被 `compaction/summary` 遮蔽的记录不进入对话体（见「遮蔽范围由 compaction/summary 记录定义」）。

#### Scenario: 用户 prompt 是对话体第一条
- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

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

### Requirement: 每次模型调用前记录 context/assembled
系统 SHALL 在每次给人跑的回合调用 Provider 之前写入一条 `context/assembled` 记录，payload 含本次进入模型的完整消息序列与头部指纹（内容哈希）。带 `purpose: compaction` 的摘要调用 MUST NOT 写这条记录：它的上下文是该回合装配点的表层再加一条固定的摘要指令。请求级压缩之后的那次重试 SHALL 在它之前再写一条 `context/assembled`，内容是遮蔽之后重新折叠的那份表层。照 DSH：一次 provider 尝试一条记录（`assistant/attempt`，`dsh-agent-loop/lib/index.js:1101-1134`），上下文记录只在表层变化之后补一条（`request/header` 只在头部变化时写，同文件 :1214-1225）。

#### Scenario: 每回合恰有一条
- **WHEN** 一次 run 跑了 N 个回合，且没有回合走到请求级重试
- **THEN** 日志里恰有 N 条 `context/assembled`，且每条都紧接在其对应的 `model/request` 之前

#### Scenario: 请求级重试之前还有一条
- **WHEN** 某回合的模型调用得到 `PROVIDER_CONTEXT_OVERFLOW`，请求级压缩之后重试成功
- **THEN** 该回合有两条 `context/assembled`，第二条紧接在重试那条 `model/request` 之前，它的消息序列含那条摘要、第一条不含

#### Scenario: 摘要调用不写装配记录
- **WHEN** 某回合完成了一次请求级压缩
- **THEN** 那条带 `purpose: compaction` 的 `model/request` 之前没有 `context/assembled`
