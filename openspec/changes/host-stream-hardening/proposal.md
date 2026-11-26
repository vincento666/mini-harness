# Proposal

## Why

对照 `host-event-sync-contract` 旧分支（2026-11-26 人裁：废弃分支、捡回防御性条款）发现，当前线 host-api 的机制主干已被替代实现覆盖（snapshot、游标、逐行镜像、observer 推送），但三条**防御性/语义条款**在当前线规格与实现里完全缺失（grep 零命中）：远端壳恢复 UI 时，Host 主动断流的语义、snapshot 的误用边界、原始日志的暴露面都没有被规格钉住。

## What Changes

- **ADDED**「snapshot 是消息基线，不是完整 UI」：实现已满足（`_snapshot_frame` 的 `messages` 就是 `fold` 出的模型上下文），纯规格追认，把「需要完整 UI 必须从 seq 0 读 durable 帧」的边界写死。
- **ADDED**「Host 主动终止发 stream/end」：**唯一实现缺口**——当前 `host.py` / `serve.py` 读日志失败时直接断流不发帧，客户端无法区分「正常结束」与「Host 主动终止」。补 ephemeral `stream/end` 帧（`{reason, code}`，无 `id`、不落日志、不参与游标）。
- **ADDED**「不提供原始日志下载」：路由表无此接口，纯规格追认，防御性禁令（远端 UI 只走 snapshot + durable SSE）。

**非目标**：`model/attempt` 的 log-only 语义不捡——当前线日志里没有 `model/attempt` 事件类型（grep 零命中），该条款无对应实体，留到 attempt 机制进当前线时再议。

## Capabilities

### Modified Capabilities

- `host-api`：事件流的主动终止语义、snapshot 的边界、日志的暴露面。

## Impact

- 代码：`cli/host.py`、`cli/serve.py`（读日志失败分支发 `stream/end` 再关流）。
- 测试：seam ⑥（黑盒：Host 终止时客户端先收到 `stream/end` 帧再断开；`stream/end` 无 `id`、不进日志）。
- 风险：小——新增一种 ephemeral 帧类型，客户端旧版会把它当未知事件忽略。
