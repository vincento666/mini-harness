# M11 storage/resume UAT

**状态**：等人跑。

## 场次

### S1 · 重启后列表

结束一个 Host 会话，重启 Host；`GET /sessions` 仍列出该会话，状态 `ended`。

### S2 · resume 续写

用同一 session id resume，追加一条消息；`replay` 历史逐点相等，新段也一致。

### S3 · 硬杀修复

段中途硬杀 Host；重新打开日志，看到缺口被明确处理，旧记录未改写。

### S4 · 迁移

用旧 schema_version 的 fixture 启动；相邻版本可迁移，跳版被拒绝且日志未改。

### S5 · 缓存

连续对话/压缩后，UI/上下文使用缓存但 messages 与无缓存一致。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | Host 重启 | 仍列 ended | `test_host_lists_ended_sessions_after_restart`：重启后 `GET /sessions` 有该 session，status=ended | 通过（agent） | 无 |
| S2 | resume 续写 | replay 相等 | 真实 reasoner session `c30432c8...`：`chat --resume` 续写，`replay` seq 4/13 都 OK；`test_chat_resume_appends_to_the_same_log` | 通过（agent） | 无 |
| S3 | 硬杀 | 缺口明确、旧行不改 | `test_resume_closes_hard_kill_gap_without_rewriting`：构造未闭合日志，resume 补 `session/end`，旧字节前缀不变 | 通过（构造日志，非真实 OS kill） | 未真正 kill -9；只验证了缺口形状 |
| S4 | 迁移 | 相邻过、跳版拒 | `test_adjacent_schema_migration` / `test_schema_skip_is_rejected_without_writing` | 通过（agent） | 无 |
| S5 | 缓存 | messages 一致 | `test_fold_cache_follows_new_log_seq` / `test_fold_cache_corruption_falls_back` / 碰撞测试 | 通过（agent） | 无 |

**至少一条「用起来别扭」**：S3 没有真的硬杀进程，只构造了硬杀留下的日志形状；真实 kill 时机仍值得在后续 shell/运维场景补。

**结论**：S1/S2/S4/S5 通过；S3 构造形状通过，真实硬杀留作后续。API/CLI 部分由 agent 代跑。
