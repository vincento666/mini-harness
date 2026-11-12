# Spec Delta

## REMOVED Requirements

### Requirement: 清单注入，正文按需加载

**Reason**: 目录改为持久的 user 消息，由每个 turn 的指纹决定是否替换；「启动时写进受保护头部」不再是事实。

**Migration**: 由下面新增的「目录消息与按需加载」取代；`session/start.payload.skills` 保留为装配期快照（审计与命令面用），但不再驱动头部。

## ADDED Requirements

### Requirement: 目录消息与按需加载

模型目录 SHALL 是一条 `user/message`，payload 含 `source: "skill-catalog"` 与 `incomplete: bool`；内容 SHALL 只含**模型可调**技能的 `name` 与截断到 500 字符的 `description`，MUST NOT 含正文、路径或来源。

在第一个 turn 的 `context/assembled` 之前，若存在模型可调技能或发现不完整，系统 SHALL 注入初始目录；之后每个 turn 之前 SHALL 重新观察（全局四根 + 子会话的 preset 层）并计算指纹（模型可调 `(name, description)` 列表 + `complete`）。指纹变化 SHALL 追加一条完整替换；指纹不变 MUST NOT 重复注入。

发现不完整 SHALL 发布「确认条目 + 警告」并标 `incomplete: true`，下一次观察 SHALL 重试；恢复完整 SHALL 追加无警告的替换。曾发过目录、现在模型可调条目为空且完整 SHALL 追加一条空目录消息，明确让模型不要使用旧名字；从未发过且为空 MUST NOT 注入。

受保护头部 MUST NOT 再含技能目录。`session/start.payload.skills` MAY 保留装配期快照（审计与命令面），但模型目录 MUST NOT 从它折叠。压缩若把目录消息的 seq 折进 `compaction/summary.shadowed_range`，下一次装配 SHALL 重新注入。

#### Scenario: 首个 turn 注入目录

- **WHEN** 会话有模型可调技能，开第一个 turn
- **THEN** `context/assembled` 之前有一条 `user/message`，`source` 是 `skill-catalog`，内容含 `<available_skills>`

#### Scenario: 指纹不变不重复

- **WHEN** 连续两个 turn 之间技能没有变化
- **THEN** 第二个 turn 之前没有新的目录消息

#### Scenario: 会话中途加技能

- **WHEN** 第一个 turn 之后在根里新增一个技能，跑第二个 turn
- **THEN** 第二个 turn 之前追加一条含新条目的替换目录

#### Scenario: 不完整与恢复

- **WHEN** 一次观察里某个根 `iterdir` 失败
- **THEN** 目录带警告与 `incomplete: true`；下一次观察恢复后追加无警告的替换

#### Scenario: 清空退休旧名字

- **WHEN** 之前发过目录，现在所有技能都被删除
- **THEN** 追加一条空目录消息，明确不要使用旧名字

#### Scenario: 头部不再有技能

- **WHEN** 任意会话启动
- **THEN** 受保护头部里没有「可用技能」块；目录只在 `user/message` 里
