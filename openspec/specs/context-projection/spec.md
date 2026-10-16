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
系统 SHALL 把受保护头部（内置系统提示 + 工具描述）放在折叠结果最前，其后按事件发生顺序保留对话体：`session/start` 的 payload 里的用户 prompt 是对话体的第一条 `user` 消息，随后是 assistant 消息与工具结果消息。M1 MUST NOT 做摘要、遮蔽或剪枝。

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
系统 SHALL 使用内置常量作为受保护头部；`--append-system-prompt` SHALL 把文本追加到头部之后，MUST NOT 提供替换内置头部的入口。

#### Scenario: 追加文本生效且常量仍在最前
- **WHEN** 运行时传入 `--append-system-prompt "额外规则"`
- **THEN** 折叠头部第一条仍是内置常量，且追加文本出现在头部内

### Requirement: M1 不施加窗口预算与截断
系统 SHALL 在 M1 把全部对话事件折入上下文而不截断、不遮蔽；窗口预算与 `CONTEXT_WINDOW_EXCEEDED` 由后续里程碑引入，M1 MUST NOT 产生该结果。

#### Scenario: 长对话不截断
- **WHEN** 一次 mock run 产生 50 条对话事件
- **THEN** 折叠结果包含全部 50 条对应的消息，且日志里没有 `CONTEXT_WINDOW_EXCEEDED`
