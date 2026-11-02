# Host event sync UAT

**状态**：等人跑。

**怎么算办一件真事**：用真实 Host 打开一个有多回合/工具的会话，观察首次全量、snapshot、断线重连、业务终止四种路径；确认远端壳不需要读日志文件也能对齐 durable 投影。

## 跑之前

- 真实 reasoner 或 mock fixture；Host `--http` + token。
- 记录 session id、SSE 原始帧、日志路径。

## H1 · 首次全量

不带 cursor / snapshot 连接 `/events`。

**预期**：从 seq 0 起收到完整 durable；delta 无 id；tool/error/attempt 记录都在。

## H2 · snapshot 语义

`?snapshot=1` 连接。

**预期**：首帧 snapshot 带 `last_seq` 与 `messages`；后续从 last_seq 之后开始；`messages` 只含模型上下文，不是 UI 全量。

## H3 · 游标重连

断开后带 `?from=<last_seq>` 或 `Last-Event-ID` 重连。

**预期**：只补 `seq > last_seq`；不重发旧 durable；delta 不补。

## H4 · 业务终止

制造日志读失败（或会话结束/删除），观察 Host 主动终止。

**预期**：收到 `stream/end`（reason/code），无 id、日志里没有该帧；客户端收到后不自动重连。

## H5 · 物理断线

直接断开 TCP。

**预期**：没有 `stream/end`；客户端可按 last_seq 重连。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| H1 | 首次全量 | seq 0 起 | | | |
| H2 | snapshot | 消息基线 + last_seq | | | |
| H3 | 游标重连 | 只补 >N | | | |
| H4 | 业务终止 | stream/end | | | |
| H5 | 物理断线 | 无 end | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过（写清 session id、帧证据）：_
