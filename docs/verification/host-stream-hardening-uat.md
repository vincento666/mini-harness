# host-stream-hardening — UAT 场次手册

**状态**：**已过**（2026-11-27 人跑）。机器那一半已完成（1.1/1.2 实现、2.1/2.2 追认判据、3.1 真端点、3.3 变异，见同目录 `*-real-endpoint.md` 与 `*-mutation.md`）。这一半是**远端壳视角的手感**：用真 HTTP 客户端/浏览器直连 Host 的 SSE，看主动终止与正常收尾分不分得清。

## 跑之前的准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
export MINIHNS_HOST_TOKEN="uat-token-0123456789abcdef0123456789"
uv run minihns host --http --port 19700 \
  --provider openrouter --model qwen/qwen3.8-27b \
  --workspace .tmp/uat-hardening --session-dir .tmp/uat-hardening/sessions \
  --sandbox read-only --yes
```

另开一个终端当「远端壳」：

```bash
TOKEN="uat-token-0123456789abcdef0123456789"
# 建会话并订阅事件流（保持这个连接开着）
curl -sN -H "Authorization: Bearer $TOKEN" \
  -X POST http://127.0.0.1:19700/sessions -H "Content-Type: application/json" \
  -d '{"workspace": "'"$PWD"'/.tmp/uat-hardening"}'
curl -sN -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:19700/sessions/<session-id>/events"
# 往会话发一条消息（让流里有真帧）：
curl -s -H "Authorization: Bearer $TOKEN" \
  -X POST http://127.0.0.1:19700/sessions/<session-id>/messages \
  -H "Content-Type: application/json" -d '{"content": "用两句话说明潮汐是怎么形成的"}'
```

## 场次表

> **订阅时序（2026-11-27 人跑校正）**：ephemeral 帧（`reasoning/delta` / `model/delta`）**只发给连接期间发生的事件**，backlog 重放只有 durable 帧——连接必须先于发消息，否则看不到两条 ephemeral 流。

| # | 怎么跑 | 看什么 | 通过判据 | 状态 |
|---|---|---|---|---|
| 1 | **先**在终端 A 挂起 `curl -sN …/events`，**再**在终端 B POST 一条消息（如 `用两句话说明潮汐是怎么形成的`），读到 `turn/end` | 正常收尾的帧序 | 帧序与本地 `serve` 同形（durable 带 `id` 递增、思考/正文两条 ephemeral 流分离且 reasoning 全在正文 delta 之前）；流**自然结束前**没有 `stream/end`（会话没被删、日志没坏） | **已过**（会话 `5f59d714…` + 重跑 `287a0f30…`；重跑场 ephemeral 段由人目测确认，durable 段经日志核对） |
| 2 | 接场 1，`DELETE /sessions/<id>` | Host 主动终止 | 删除后事件流先收到 durable `session/end`，**再收到一帧 `stream/end`（`reason: session_ended`、无 `id`）然后断开**，不是直接断 | **已过**（`5f59d714…`：id 9 `session/end` + `stream/end session_ended`） |
| 3a | 新会话、订阅，POST 一条消息让轮跑起来，然后手动往该会话日志追加一行 `{这不是 JSON` | 坏行让会话下一次装配失败（既有语义） | 事件流收到 `stream/end`（`reason: session_ended`）后断开——坏行杀死的是**会话**，不是传输层；live 循环不重读日志，所以这里**不该**出现 `LOG_UNREADABLE` | **已过**（`b0156793…`：日志确认 1 行坏行、durable 止于 `step/start`、流以 `session_ended` 收尾） |
| 3b | 接 3a，**重连**同一会话的事件流 | Host 自己读 backlog 撞上坏行 | 立刻收到 `stream/end`（`reason: error, code: LOG_UNREADABLE`）再断开，不是 404 也不是空流 | **已过** |

## 观察记录（2026-11-27，人跑）

- **场 1**（`287a0f3092e4405c98313928c0d636a5`，重跑）：durable 段 id 0–8 帧序正常、`blocks=["reasoning","text"]`、usage `212/121`、无坏行；ephemeral 段（`reasoning/delta`/`model/delta` 分离）人目测确认，且同代码 curl 复现（会话 `eb40eb5b…`）实测 13 帧 reasoning + 59 帧 delta、reasoning 全在正文之前。第一跑 `5f59d714…` 因连接时序（订阅晚于轮结束）没看到 ephemeral，按此把「先订阅后发消息」写进手册。
- **场 2**（`5f59d714…`）：`id: 9 session/end`（durable）后紧跟 `stream/end {"reason":"session_ended"}`（无 `id`）再断开。
- **场 3a**（`b0156793…`）：坏行进真日志（host 的 `--session-dir` 启动即定死，与 create-session 的 `workspace` 无关），durable 止于 `step/start`（装配塌了，既有语义），流以 `session_ended` 收尾。原手册预期 `LOG_UNREADABLE` 系写错：host 事件循环 live 阶段不重读日志。
- **场 3b**（`b0156793…` 重连）：立刻收到 `stream/end {"reason":"error","code":"LOG_UNREADABLE"}` 再断开，不是 404 也不是空流。
- 手册连带修订：订阅时序注记、场 3 拆 3a/3b。
