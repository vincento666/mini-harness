# Spec Delta

## ADDED Requirements

### Requirement: 头部的工具块由日志前缀派生
系统 SHALL 让受保护头部里的工具块内容取自该装配点当时的工具名列表，且该列表 MUST 从该装配点之前的日志前缀派生（取自 `session/start` 的 payload），MUST NOT 取自进程内注册表或该点之后的事件。

#### Scenario: 注册了工具的日志可被逐点重放
- **WHEN** 对一次注册了五个文件工具的 run 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 的头部都含这五个工具名，且重算结果与该记录逐字段相等

#### Scenario: 头部不依赖装配点之后的事件
- **WHEN** 某条 `context/assembled` 之后的事件被改动或删除
- **THEN** 该点的头部工具块不变

## MODIFIED Requirements

### Requirement: 折叠产出形状为受保护头部加保留尾部
系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`session/start` 的 payload 里的用户 prompt 是对话体的第一条 `user` 消息，随后是 assistant 消息与工具结果消息。M2 MUST NOT 做摘要、遮蔽或剪枝。

#### Scenario: 用户 prompt 是对话体第一条
- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

#### Scenario: 头部不被对话内容顶替
- **WHEN** fixture 的模型回复文本与内置系统提示完全相同
- **THEN** 折叠结果的第一条消息仍是内置系统提示

#### Scenario: 工具结果按顺序进入对话体
- **WHEN** 某回合产生一次 `tool/call` 与对应 `tool/result`
- **THEN** 折叠结果按发生顺序包含该 assistant 工具请求消息与对应工具结果消息

### Requirement: 系统提示与工具描述是内置常量且只能追加
系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；`--append-system-prompt` SHALL 把文本追加到头部之后，MUST NOT 提供替换内置系统提示的入口。工具描述块的内容由日志派生（见「头部的工具块由日志前缀派生」），MUST NOT 成为可由调用方替换的头部。

#### Scenario: 追加文本生效且常量仍在最前
- **WHEN** 运行时传入 `--append-system-prompt "额外规则"`
- **THEN** 折叠头部第一条仍是内置常量，且追加文本出现在头部内
