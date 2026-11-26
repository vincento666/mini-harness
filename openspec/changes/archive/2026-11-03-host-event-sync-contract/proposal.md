# Proposal

## Why

Web 壳通过 Host 恢复 UI 时，现在的协议有三个空白：

- `snapshot=1` 返回的 `messages` 是 `fold` 出来的**模型上下文**，不是完整 UI 事件基线；客户端若把它当 transcript，会丢 tool/approval/error 行；
- `from` / `Last-Event-ID` 的边界没有写死（`from=0` 会跳过 seq 0；无游标才是全量）；
- SSE 断流时客户端分不清“物理断线可重连”与“业务/持久化错误应停止”。

这一片只补 **Host 同步契约**，不改内核事件形状、不做 UI、不加日志下载接口。

## What Changes

- **初次同步**：`snapshot` 明确定义为“消息级基线”，不是完整 UI 真相；完整 UI 首次加载 MUST 用 `/events` 从 seq 0 读 durable 事件，自己建 projection。
- **游标**：明确无游标 = 从 seq 0；`?from=N` / `Last-Event-ID` = 只发 `seq > N`；只有 durable 帧有 `id`；客户端按 seq 去重。
- **字段稳定**：`model/response.blocks`、`interrupted`、`model/attempt`、`error/*` 原样出现在 durable SSE 帧；snapshot 的 `messages` 明确是模型上下文，不是 UI transcript。
- **终止语义**：新增 ephemeral `stream/end` 帧（无 id、不落日志），只在 Host 主动终止（业务/持久化错误、会话结束）时发；物理断线不发 `stream/end`，客户端据此决定重连。
- **明确不做**：原始 JSONL 下载、UI 分页、active assistant baseline、compact stream、surface replacement。

## Capabilities

### New Capabilities

- `host-stream-sync`：初次同步、游标、snapshot 语义、durable 字段、`stream/end` 与重连判定。

### Modified Capabilities

无。现有 `host-api` / `event-stream` 的帧形状不变；本 change 是在其上补同步契约。

## Impact

- 代码：`cli/host.py`（snapshot 语义、`stream/end`）、`docs/reference/host-streaming.md`、tests。
- 测试：seam ⑥（host SSE blackbox），不新增内核 seam。
- 规格：新 capability `host-stream-sync`。
- 验收：首次全量、`from`/snapshot 边界、业务终止 vs 物理断线、UI 字段透出。
