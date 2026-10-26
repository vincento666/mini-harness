---
status: proposed
---

# 流式逐字帧是宿主的 ephemeral 帧，不落日志；最终 response 才是 durable 真相

H2 让 provider 走 `stream: true`，但逐字增量只出现在宿主流上（`event: model/delta`，不带 `id`/`seq`、不进 JSONL）；一次模型调用仍只在日志里落一条 `model/request` 与一条完整的 `model/response`，`replay` 与预算只看后者。重试只允许发生在**首 delta 之前**：已经吐过字的流再重试会在屏幕上留下两遍开头；断线重连只从 durable `seq` 续读，已经丢掉的 delta 不补，客户端以最终 `model/response` 为准。

Considered options：把每个 delta 落成日志记录——否，一次回复能把日志撑大两个数量级，`replay`、折叠、预算都要为它加一条读方规则，而它不是「发生了什么」的事实；用 WebSocket 单独承载 delta——否，为 ephemeral 再养一条传输，SSE 已经够；把 delta 缓冲到结束再一次性发——否，那就不是流式。

Consequences：ADR-0006 的「非流式」收窄成「默认非流式、H2 起可选流式」；`Provider.generate` 的接口要多一个 delta sink（或等价的回调），mock 也要能发 delta 才能进 CI；UI 重连时可能先看到一段不完整的文字，最终以 `model/response` 校正；E1 要量首 token 延迟与 delta 间隔；日志里永远找不到逐字帧，这是有意的。
