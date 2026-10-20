# Spec Delta

## MODIFIED Requirements

### Requirement: 折叠产出形状为受保护头部加保留尾部
系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`session/start` 的 payload 里的用户 prompt 是对话体的第一条 `user` 消息，随后是 assistant 消息与工具结果消息。被 `compaction/summary` 遮蔽的记录不进入对话体（见「遮蔽范围由 compaction/summary 记录定义」）。

#### Scenario: 用户 prompt 是对话体第一条
- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

#### Scenario: 头部不被对话内容顶替
- **WHEN** fixture 的模型回复文本与内置系统提示完全相同
- **THEN** 折叠结果的第一条消息仍是内置系统提示

#### Scenario: 工具结果按顺序进入对话体
- **WHEN** 某回合产生一次 `tool/call` 与对应 `tool/result`
- **THEN** 折叠结果按发生顺序包含该 assistant 工具请求消息与对应工具结果消息

## ADDED Requirements

### Requirement: 遮蔽范围由 compaction/summary 记录定义
折叠遇到一条 `compaction/summary` 时，系统 SHALL 把它 payload 里 `shadowed_range` 的 `start` 与 `end`（含两端）覆盖的那些记录视为不产出任何消息。受保护头部与 `session/start` 派生的那条 `user` 消息 MUST NOT 被遮蔽。该规则 MUST 是确定性的，且 MUST 只依赖该装配点之前的日志前缀。

#### Scenario: 被遮蔽的记录不产出消息
- **WHEN** 一份日志里有一条遮蔽了某段对话体的 `compaction/summary`
- **THEN** 折叠结果里不含那段记录对应的任何消息，而该段之后未被遮蔽的消息照常出现

#### Scenario: 被遮蔽的调用不派生闭合
- **WHEN** 被遮蔽的那段里有一条 `tool/call` 与配对的 `tool/result`
- **THEN** 折叠结果里既没有该调用的消息，也没有为它派生的 `TOOL_OUTCOME_UNKNOWN` 消息

#### Scenario: 遮蔽不拆散一对调用与结果
- **WHEN** 一次压缩完成
- **THEN** 折叠结果里没有任何一条 `role` 为 `tool` 的派生闭合消息是由该遮蔽范围造成的

#### Scenario: 压缩过的日志可被逐点重放
- **WHEN** 对一次发生过压缩的 run 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 都与其前缀的重算结果逐字段相等

### Requirement: 摘要作为头部之后的 system 消息进入表层
系统 SHALL 把每条 `compaction/summary` 的 `summary` 文本作为一条 `role` 为 `system` 的消息进入折叠结果，位置在受保护头部之后、保留尾部的第一条消息之前；多条摘要 SHALL 按各自记录的 `seq` 顺序排列。该消息 MUST NOT 被写进日志。

#### Scenario: 一次压缩后头部之后是摘要
- **WHEN** 一份日志里有一条 `compaction/summary`
- **THEN** 折叠结果的第二条消息 `role` 为 `system`、`content` 为该记录的 `summary` 原文

#### Scenario: 两次压缩的摘要按 seq 排列
- **WHEN** 一份日志里有两条 `compaction/summary`
- **THEN** 折叠结果里两条 `system` 摘要消息相邻且顺序与两条记录的 `seq` 一致

### Requirement: 带压缩用途标记的模型回复不产出消息
`model/response` 的 payload 里 `purpose` 为 `compaction` 时，系统 SHALL 不把该记录折成 assistant 消息：它是压缩的记账，不是对话。没有该标记的 `model/response` 照常产出消息。

#### Scenario: 摘要的回复不在表层里出现两次
- **WHEN** 一次压缩的摘要文本来自一条 `purpose` 为 `compaction` 的 `model/response`
- **THEN** 折叠结果里该文本只作为 `system` 摘要消息出现一次，没有任何 assistant 消息携带它

#### Scenario: 没有标记的回复照常进入表层
- **WHEN** 一次 run 既有普通回合回复又有压缩回复
- **THEN** 只有带 `purpose: compaction` 的那条不产出 assistant 消息

## REMOVED Requirements

### Requirement: M1 不施加窗口预算与截断
**Reason**: 这条是 M1 的阶段性限定（「窗口预算与 `CONTEXT_WINDOW_EXCEEDED` 由后续里程碑引入」）。M5 兑现不变量 D，主规格里留着它会让「系统 MUST NOT 产生 `CONTEXT_WINDOW_EXCEEDED`」与 `context-budget` 的要求直接矛盾。
**Migration**: 预算、触发线与溢出结果改由 `context-budget` 的「窗口预算由 window 与 reserve 两个参数决定」「触发线由固定公式给出」「压缩救不了时是 CONTEXT_WINDOW_EXCEEDED 结果」约束；折叠侧不再有「不截断」这条。
