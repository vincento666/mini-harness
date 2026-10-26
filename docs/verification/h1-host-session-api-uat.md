# H1 宿主会话 API — UAT 场次与观察表

**状态**：等人跑（ADR-0025：这张表没填完，H1 不得归档、不得合入 `main`；tty / 浏览器场次 agent 不得代跑）。

**怎么算「办一件真事」**：不是跑判据，是用宿主 API 真的完成一次「开一个会话 → 让它改一个文件 → 看着它跑完 → 中途取消一次 → 断开再连上」。下面五场按顺序跑；每场把观察写进表里，最后写「别扭在哪」。

## 跑之前

- `MINIHNS_HOST_TOKEN` 设成一个 ≥32 字符的随机串（不要贴进聊天记录）。
- 真实端点：`DEEPSEEK_API_KEY` 或 `MINIHNS_API_KEY`；工作区用一个临时目录，里面放一个可改的 `notes.md`。
- 起服务：`minihns host --http --port 19410 --workspace <tmp> --provider deepseek`（或 `openai` + `--model`）。
- 客户端用 `curl`、`httpx` 或一个最小 HTML + `fetch` 都行；SSE 那一条用 `curl -N` 看。
- 五场之间**不重启服务**（U5 的最后一场除外），这样能看见「服务比会话活得久」。

## U1 开一个会话，发两句话

1. `POST /sessions` 建会话；记下 `session_id`。
2. `POST /sessions/{id}/messages` 发「读 notes.md，告诉我里面有什么」。
3. 第一段还没完时再发第二句「把 notes.md 的第一行改成 TODO」。
4. 同时 `GET /sessions/{id}/events` 看流。

**预期**：第一句 202；第二句 202 且 `queued: true`；两段按顺序跑；流里能看见 `user/message`、`model/response`、`tool/call`、`tool/result`；第二段触发审批（见 U2）。

## U2 批准一次写、拒绝一次写

1. 在 U1 的第二段弹审批时，`POST /sessions/{id}/approvals/{tool_call_id}`，`decision: "approve"`。
2. 再让它改另一个文件，这次 `decision: "deny"`。

**预期**：批准的那次 `tool/result` 是 `OK`、文件真的变了；拒绝的那次是 `DENIED_BY_APPROVAL`、段以 `FENCE_DENIED` 收尾、会话还在；日志里 `approval/request` 与 `approval/response` 成对。

## U3 段进行中取消，然后继续

1. 发一句会跑一阵的活（例如「读三个文件并总结」）。
2. 段进行中 `POST /sessions/{id}/cancel`。
3. 等它回到 `idle`，再发一句「刚才做到哪了？」。

**预期**：取消只结束当前段（`ABORTED`），会话不结束；下一句正常开新段；事件流上能看到 `error/abort` 与新的 `segment/start`。

## U4 断开、重连、snapshot

1. 在 U3 的段跑到一半时把 SSE 客户端直接杀掉（不是 cancel）。
2. 带 `?snapshot=1` 重新连。
3. 如果壳是浏览器，用一个最小 HTML + `fetch` 流跑同一场（会触发 `OPTIONS` 预检与 `Authorization` 头）。

**预期**：第一帧是 `snapshot`，带当前 `last_seq` 与折叠后的消息；之后只送新帧；会话没有因为客户端断开而改变；最终 `model/response` 与不流式时一致；浏览器 `fetch` 能过预检。

## U5 安全与边界

1. 不带 token 请求 `GET /sessions`。
2. 带正确 token 请求 `GET /sessions/../secret/events`。
3. 再开一个会话，确认 `GET /sessions` 列出两个。
4. 段进行中 `DELETE /sessions/{id}`。
5. 重启服务（这一场可以重启），确认旧会话不在列表里（H1 不承诺跨进程列表，M11 再补）。

**预期**：401 / 400 / 200 / 409；错误信封是 JSON，detail 里没有 token；重启后旧会话不在列表里不是 bug，是 H1 的边界。

## 观察表

| 场次 | 动作 | 预期 | 实际观察（命令 / 日志 / 截图） | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| U1 | 建会话 + 两句话 | 202 / 排队 / 两段顺序 | | | |
| U2 | 批准一次 / 拒绝一次 | OK / FENCE_DENIED / 会话继续 | | | |
| U3 | 段中取消再继续 | ABORTED / 新段正常 | | | |
| U4 | 断线 + snapshot 重连 | snapshot 后只送新帧 | | | |
| U5 | 无 token / 穿越 / 第二会话 / DELETE / 重启 | 401 / 400 / 200 / 409 / 列表空 | | | |

**至少一条「用起来别扭」**（没有就写「这一版意外地顺」）：_

**结论**：通过 / 不通过（不通过要写清哪一场、哪条预期没成立、日志 session id）：_
