# Design

## Context

三条防御性条款来自 `host-event-sync-contract` 旧分支的 `host-stream-sync` 规格（人裁 2026-11-26：废弃分支、捡回条款）。当前线 `host.py` 的 snapshot 实现已满足条款一与条款三（`_snapshot_frame` 的 `messages` 取自 `fold(records)`；路由表无日志路径接口），只有条款二缺实现：`_events` 读日志失败分支直接 `return response`，客户端看到的是连接关闭，无法区分正常收尾与主动终止。

## Decisions

**D1 只补 `stream/end` 实现，其余两条纯规格追认。** snapshot 与日志禁令的实现现状已满足，不为「追认」写代码。

**D2 `stream/end` 是 ephemeral 帧，形状照旧分支定案**：`{reason: "error" | "session_ended", code: string}`，无 `id`、不落日志、不参与游标——与 `model/delta` 同类（ephemeral）。`host.py` 的读日志失败分支与 `serve.py` 的 `LogReadFailure` 分支各发一帧再关流；会话删除路径在流还开着时也发 `session_ended`。

**D3 旧分支的其余实现不迁移。** 旧分支的 snapshot/游标实现与当前线重复且是旧词表（turn_id），只搬三条款文本与 stream/end 语义，代码以当前线为准重写。

## Risks

- 客户端不认识 `stream/end`：SSE 未知事件按忽略处理，向后兼容。
- `serve.py`（单会话版）与 `host.py`（多会话版）两条流实现都要改，漏一处就会行为不一致——测试两端都写。
