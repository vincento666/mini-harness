# host-stream-hardening — UAT 场次手册

**状态**：**待人跑**。机器那一半已完成（1.1/1.2 实现、2.1/2.2 追认判据、3.1 真端点、3.3 变异，见同目录 `*-real-endpoint.md` 与 `*-mutation.md`）。这一半是**远端壳视角的手感**：用真 HTTP 客户端/浏览器直连 Host 的 SSE，看主动终止与正常收尾分不分得清。

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
  -d '{"workspace": "'"$PWD"'/tmp/uat-hardening"}'
curl -sN -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:19700/sessions/<session-id>/events"
```

## 场次表

| # | 怎么跑 | 看什么 | 通过判据 | 状态 |
|---|---|---|---|---|
| 1 | 订阅事件流后 POST 一条消息（如 `用两句话说明潮汐是怎么形成的`），读到 `turn/end` | 正常收尾的帧序 | 帧序与本地 `serve` 同形（durable 带 `id` 递增、思考/正文两条 ephemeral 流分离）；流**自然结束前**没有 `stream/end`（会话没被删、日志没坏） | **待人跑** |
| 2 | 接场 1，重连事件流，然后 `DELETE /sessions/<id>` | Host 主动终止 | 删除后事件流**先收到一帧 `stream/end`（`reason: session_ended`、无 `id`）再断开**，不是直接断 | **待人跑** |
| 3 | 重建会话、订阅，然后手动往 `sessions/<id>.jsonl` 追加一行 `{这不是 JSON` | 日志读不动的主动终止 | 事件流**先收到 `stream/end`（`reason: error, code: LOG_UNREADABLE`）再断开**；提示：坏行会让该会话下一次装配失败，这属既有「坏行终止会话」语义，只看流上的帧 | **待人跑** |

## 观察记录

- （待人跑后填写：每场帧序列粘贴、判据逐条勾）
