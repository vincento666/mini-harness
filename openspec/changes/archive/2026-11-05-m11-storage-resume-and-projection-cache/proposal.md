# Proposal

## Why

M10 前，session 日志只能从头读；进程重启/硬杀后没有 resume，Host 也列不出已结束会话。折叠每次都重算整份日志，遮蔽范围重叠也没有固定规则。M11 把这些补成可恢复的存储/投影层。

## What Changes

- **`EventLog.open` 读最后 `seq`**：续写不重号；已有日志可继续 append。
- **`--resume` / resume API**：把已有 session 重新装配，硬杀留下的半条收尾补成闭合；`replay` 仍逐点相等。
- **`schema_version` 相邻迁移**：只支持 N→N+1，跳版拒绝；迁移写回前校验。
- **session index**：Host 重启后 `GET /sessions` 能列出已结束会话（不靠进程内表）。
- **fold 缓存**：日志领先时缓存跟随；缓存只做加速，不成为第二真源。
- **投影三态**：`in_context` / `shadowed` / `log_only`；压缩遮蔽范围可重叠，后写覆盖先写。
- **硬杀后的读方修复**：读到半条/缺闭合时按日志事实补 `session/end` 或明确报告，不改写已写事实。

## Capabilities

### New Capabilities

- `session-resume`：打开/续写/迁移/索引/硬杀修复。
- `projection-cache`：fold 缓存与三态投影。

### Modified Capabilities

- `event-log`：`open` 读最后 seq、schema 迁移边界。
- `host-api`：重启后的 session index。

## Impact

- 代码：`events/writer.py`、`events/reader.py`、`events/fold.py`、`session/assembly.py`、`cli/main.py`、`cli/host.py`、`session/host.py`。
- 测试：seam ④（日志/折叠）、seam ⑥（CLI/host 黑盒）。
- 非目标：fork（ADR-0035）、跨进程共享缓存、跨 schema 跳版迁移。
