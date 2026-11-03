# Spec Delta

## ADDED Requirements

### Requirement: 打开已有日志时续写 seq

`EventLog.open` SHALL 读日志最后一条 `seq`，下一次 append 从 `last+1` 开始；MUST NOT 重号或从 0 重写。空日志从 0 开始。

#### Scenario: 重启后追加不重号

- **WHEN** 一份日志最后 seq 是 7，进程重新打开后 append 一条
- **THEN** 新记录 seq 是 8，原 0–7 一条不改

### Requirement: `--resume` 重新装配已有 session

`minihns chat --resume <id>` / Host 的 resume 路径 SHALL 从已有日志装配 `SessionEnv`，后续段继续写同一份日志；MUST NOT 新建 session。若日志缺少闭合（硬杀），resume SHALL 按日志事实补 `session/end` 或明确报告缺口，MUST NOT 改写既有记录。

#### Scenario: resume 后 replay 仍相等

- **WHEN** 对一个已完成 session resume 并追加一段，再跑 `replay`
- **THEN** 所有历史装配点逐点相等，新段也一致

#### Scenario: 硬杀缺口被明确处理

- **WHEN** 日志最后有 `segment/start`/`turn/start` 但没有对应闭合
- **THEN** resume 补一条可解释的 `session/end` 或报告缺口，既有记录不变

### Requirement: schema_version 只做相邻迁移

只支持 `N → N+1`；跳版或未知版本 SHALL 以参数/内部错误拒绝，MUST NOT 猜测迁移。迁移 SHALL 先校验后写回。

#### Scenario: 相邻版本迁移

- **WHEN** 日志 schema_version 是 1，当前是 2
- **THEN** 迁移到 2 并可读

#### Scenario: 跳版拒绝

- **WHEN** 日志 schema_version 是 1，当前是 3
- **THEN** 拒绝，不写日志

### Requirement: Host 重启后能列出历史 session

Host SHALL 从 session 目录/session index 重建列表，`GET /sessions` 能列出已结束会话；MUST NOT 只依赖进程内 `HostState.sessions`。

#### Scenario: 重启后仍列出 ended

- **WHEN** 一个 session 已结束，Host 重启
- **THEN** `GET /sessions` 仍能列出它，状态为 ended
