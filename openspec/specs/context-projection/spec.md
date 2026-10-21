# context-projection Specification

## Purpose

定义如何从只追加的事件日志折叠出「当前算数的上下文」：受保护头部加保留尾部，冷启动全量重放，且折叠结果可被 replay 逐字段复现。

## Requirements

### Requirement: 当前上下文只由折叠派生
系统 SHALL 通过折叠事件日志得到每次模型调用的消息序列；MUST NOT 维护独立于日志的对话状态，也 MUST NOT 依赖缓存或检查点。冷启动时 SHALL 全量重放日志重建上下文。

#### Scenario: 冷启动逐点重建出同一上下文
- **WHEN** 进程结束后只给折叠器该 session 的日志文件
- **THEN** 对日志里每一条 `context/assembled`，用它之前的日志前缀折叠得到的消息序列与该记录的 payload 逐字段一致

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

### Requirement: 每次模型调用前记录 context/assembled
系统 SHALL 在每次调用 Provider 之前写入一条 `context/assembled` 记录，payload 含本次进入模型的完整消息序列与头部指纹（内容哈希）。

#### Scenario: 每回合恰有一条
- **WHEN** 一次 run 跑了 N 个回合
- **THEN** 日志里恰有 N 条 `context/assembled`，且每条都紧接在其对应的 `model/request` 之前

### Requirement: 折叠是确定性纯函数
系统 SHALL 保证对同一日志文件折叠两次得到逐字段相同的结果；折叠 MUST NOT 依赖墙钟时间、随机数或进程内残留状态。

#### Scenario: 同一日志折叠两次结果相同
- **WHEN** 对同一日志文件连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

### Requirement: 折叠一致性由前缀重算定义
系统 SHALL 把「折叠结果与日志一致」定义为逐点性质：对日志任一前缀折叠，结果 MUST NOT 依赖该点之后的事件，也 MUST NOT 依赖进程内残留状态；`minihns replay` 按这条性质逐点校验，任一点不一致即为失败结果。

#### Scenario: 前缀折叠不受后续事件影响
- **WHEN** 对同一日志的两个前缀（前者是后者的严格前缀）分别折叠
- **THEN** 较短前缀的折叠结果与在完整日志上同一位置重算的结果相同

### Requirement: 系统提示与工具描述是内置常量且只能追加
系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；`--append-system-prompt` SHALL 把文本追加到头部之后，MUST NOT 提供替换内置系统提示的入口。工具描述块的内容由日志派生（见「头部的工具块由日志前缀派生」），MUST NOT 成为可由调用方替换的头部。

#### Scenario: 追加文本生效且常量仍在最前
- **WHEN** 运行时传入 `--append-system-prompt "额外规则"`
- **THEN** 折叠头部第一条仍是内置常量，且追加文本出现在头部内

### Requirement: 头部的工具块由日志前缀派生
系统 SHALL 让受保护头部里的工具块内容取自该装配点当时的工具名列表，且该列表 MUST 从该装配点之前的日志前缀派生（取自 `session/start` 的 payload），MUST NOT 取自进程内注册表或该点之后的事件。

#### Scenario: 注册了工具的日志可被逐点重放
- **WHEN** 对一次注册了五个文件工具的 run 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 的头部都含这五个工具名，且重算结果与该记录逐字段相等

#### Scenario: 头部不依赖装配点之后的事件
- **WHEN** 某条 `context/assembled` 之后的事件被改动或删除
- **THEN** 该点的头部工具块不变

### Requirement: 未配对的工具调用由折叠派生闭合
当折叠遇到一条没有配对 `tool/result` 的 `tool/call` 时，系统 SHALL 在折叠结果里为该调用派生一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息，使每个 assistant 工具请求消息都有配平的工具结果消息。该派生 MUST NOT 写入日志、MUST NOT 新造事件类型、MUST NOT 触发对该调用的自动重试，且 MUST 是确定性的。

#### Scenario: 半截日志折叠补出闭合
- **WHEN** 一份日志以「有 `tool/call` 没 `tool/result`」结尾
- **THEN** 折叠结果里该 `tool_call_id` 有一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的消息，且该日志文件的字节数与内容都不变

#### Scenario: 闭合不被重放成事件
- **WHEN** 对同一份半截日志连续执行两次 `minihns replay`
- **THEN** 日志里没有任何新记录，也没有任何类型为 `TOOL_OUTCOME_UNKNOWN` 的事件

#### Scenario: 完整日志不派生闭合
- **WHEN** 对一次正常收尾的 run 的日志折叠
- **THEN** 折叠结果里没有任何 `TOOL_OUTCOME_UNKNOWN` 消息

#### Scenario: 派生闭合是确定性的
- **WHEN** 对同一份半截日志连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

#### Scenario: 闭合不改变已有消息的顺序
- **WHEN** 一份日志里未配对的调用之前已有若干条对话消息
- **THEN** 派生出的工具结果消息出现在该调用的 assistant 请求消息之后、该点之后的既有消息之前

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
系统 SHALL 把每条 `compaction/summary` 的 `summary` 文本作为一条 `role` 为 `system` 的消息进入折叠结果，位置在受保护头部与 `session/start` 派生的那条 `user` 消息之后、保留尾部的第一条消息之前；多条摘要 SHALL 按各自记录的 `seq` 顺序排列。该消息 MUST NOT 被写进日志。

#### Scenario: 一次压缩后用户 prompt 之后是摘要
- **WHEN** 一份日志里有一条 `compaction/summary`
- **THEN** 折叠结果里 `session/start` 派生的那条 `user` 消息之后那条消息 `role` 为 `system`、`content` 为该记录的 `summary` 原文

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
