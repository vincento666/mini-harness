# Verification Contract

每个任务一条判据，先红后绿。

- **1.1**：黑盒把日志文件改成读不动（如换成目录），连 SSE，客户端在断开前收到 `data` 解析为 `{"reason": "error", "code": "LOG_UNREADABLE"}` 的 `event: stream/end` 帧；帧无 `id:` 行；`read_events(日志)` 无 `stream/end` 记录。两端（`host.py` 多会话、`serve.py` 单会话）各跑一次。
- **1.2**：开一条 SSE 后删除会话，客户端收到 `{"reason": "session_ended"}` 的 `stream/end` 帧再断开；日志无该记录。
- **2.1**：会话含 tool 调用历史时，`?snapshot=1` 首帧的 `messages` 数组只含角色为 user/assistant 的上下文消息，不含 tool/approval/error 记录。
- **2.2**：`GET /log?path=<任意路径>` 返回 404，Host 文件系统不可读。
- **3.1**：真实端点跑一场，逐帧核对 durable 帧与日志相等；重放序列不含 `stream/end`。
- **3.3**：至少一条变异（如删掉 `stream/end` 发送分支）被 1.1 杀死。
