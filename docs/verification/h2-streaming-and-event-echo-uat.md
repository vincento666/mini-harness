# H2 流式与事件回显 — UAT 场次与观察表

**状态**：等人跑（ADR-0025：这张表没填完，H2 不得归档、不得合入 `main`；tty / 浏览器场次 agent 不得代跑）。

**怎么算「办一件真事」**：不是跑判据，是用 `minihns host` 开一个会话，让真实模型写一段长回复，看着字一个一个出来；中途断开 SSE，再带 `snapshot=1` 接回来；最后用 `replay` 对一次。五场按顺序跑。

## 跑之前

- `MINIHNS_HOST_TOKEN` 设成 ≥32 字符随机串；真实端点用 `DEEPSEEK_API_KEY`。
- 工作区临时目录；起服务：`minihns host --http --port 19410 --workspace <tmp> --provider deepseek`。
- 客户端用 `curl -N`、httpx 或最小 HTML + `fetch`；SSE 用 `curl -N` 看。
- 五场之间不重启服务（U5 除外）。

## S1 首帧延迟

1. 建会话，发一句会让模型写长回复的话（例如「用 300 字介绍你自己」）。
2. `curl -N` 接事件流，记下从 POST 到第一个 `model/delta` 的时间。

**预期**：真实端点首帧在 1 s 内；`model/delta` 不带 `id`，`data` 含 `turn_id` / `index` / `text`。

## S2 delta 拼接等于最终 content

1. 把同一次调用的所有 `model/delta.text` 按 `index` 拼接。
2. 等 durable `model/response` 到达。

**预期**：拼接结果等于 `model/response.content`；日志里没有 `model/delta`。

## S3 工具调用流式拼装

1. 让它调用一个工具（例如读一个文件），工具调用本身可能不流式。
2. 观察 `model/response` 的 `tool_calls` 是否完整。

**预期**：`tool_calls` 按 `index` 拼装成完整调用；`tool/call` 与 `tool/result` 各一条；没有工具参数的逐字 delta 帧。

## S4 断线、snapshot 重连、不重复

1. 长回复生成到一半时杀掉 SSE 客户端。
2. 带 `?snapshot=1` 重连。
3. 等最终 `model/response`。

**预期**：第一帧是 `snapshot`；`last_seq` 是 durable 高水位；丢掉的 delta 不补；最终回复只出现一次（以 durable `model/response` 为准）。

## S5 replay 与不流式逐点相等

1. 同一 fixture / 同一真实端点提示，分别跑一次带流式与不带流式的会话。
2. 对两份日志各跑 `minihns replay <id>`。

**预期**：两次 replay 退出码 0；`model/response`、`tool/*`、`turn/*` 序列逐点相等；`model/delta` 不在日志里。

## 观察表

| 场次 | 动作 | 预期 | 实际观察（命令 / 日志 / 截图） | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | 长回复首帧 | <1 s / 无 id | | | |
| S2 | delta 拼接 | 等于最终 content | | | |
| S3 | 工具调用 | tool_calls 完整 | | | |
| S4 | 断线 + snapshot | 不补 delta / 最终只一次 | | | |
| S5 | replay 对比 | 退出码 0 / 逐点相等 | | | |

**至少一条「用起来别扭」**（没有就写「这一版意外地顺」）：_

**结论**：通过 / 不通过（不通过要写清哪一场、哪条预期没成立、日志 session id）：_
