# projection-cache Specification

## Purpose
定义 fold 缓存的边界、投影三态（in_context / shadowed / log_only）与重叠遮蔽合并。

## Requirements

### Requirement: fold 缓存只做加速

fold 缓存 SHALL 以日志 `seq` 为水位；日志领先时缓存跟随，不得返回旧结果。缓存 MISS/损坏时 SHALL 回退重算，MUST NOT 产生与无缓存不同的 messages。

#### Scenario: 新事件使缓存失效

- **WHEN** 缓存停在 seq 10，日志已到 12
- **THEN** fold 重算到 12，返回与无缓存相同的结果

#### Scenario: 缓存损坏回退

- **WHEN** 缓存内容不可读
- **THEN** 重算，不抛错、不返回旧 messages

### Requirement: 投影三态

`fold`/投影 SHALL 能把每个 source 标成 `in_context`、`shadowed`、`log_only`：

- `in_context`：进入模型上下文；
- `shadowed`：被压缩遮蔽，留在日志但不进上下文；
- `log_only`：只做证据（attempt、header 等），从不进模型历史。

#### Scenario: 遮蔽后不进上下文

- **WHEN** 一条 user 消息被 `compaction/summary` 遮蔽
- **THEN** 它的状态是 shadowed，messages 里不再有它，日志里仍在

#### Scenario: attempt 是 log_only

- **WHEN** fold 遇到 `model/attempt`
- **THEN** 它不进 messages，状态是 log_only

### Requirement: 遮蔽范围可重叠，后写覆盖先写

多个 `shadowed_range` 重叠时 SHALL 按日志顺序合并；后写的遮蔽覆盖先写，不能重复计数或漏遮蔽。

#### Scenario: 重叠区间

- **WHEN** 第一次遮蔽 1–5，第二次遮蔽 3–8
- **THEN** 1–8 都被遮蔽，边界只算一次

