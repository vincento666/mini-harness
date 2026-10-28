# H2 真实端点验收（deepseek）

**日期**：2026-10-28。**端点**：deepseek（真实 `DEEPSEEK_API_KEY`，不落日志）。**入口**：`minihns host --http` + `GET /events` SSE。

## 跑法

- 工作区 `.tmp/h2-real/workspace`，脚本 `.tmp/h2-real/run.py`；会话由 HTTP 创建，SSE 连接后 `POST /messages`。
- 计时从 SSE 连接建立/发消息前开始，到第一个 `model/delta`；包含 HTTP 与轮询开销。
- 工具场：`.tmp/h2-real/run_tool.py`，提示强制 `read note.md`，读到 `segment/end`。

## S1/S2：首帧与拼接

修复前的两条样本（记录在案，说明当时的 bug）：

```text
first_delta_s 1.219 / 1.078
delta_count 81 / 84
concat_equals_final true
contains_delta_in_log false
```

`1.0 s` 目标未达成。原因不是端点首 token，而是 `_events` 只在遇到 `model/response` 时才排空 delta 队列，整段文字被缓冲到结束。修复后：

```text
first_delta_s 0.734 / 0.406
delta_count 9 / 10
concat_equals_final true
contains_delta_in_log false
```

- 首帧 **0.406–0.734 s**，满足 <1 s（单次真实端点；不是统计保证）。
- 所有 delta 拼接等于最终 `model/response.content`。
- 日志里没有 `model/delta`。
- 修复提交 `f4b60a2`：没有 response 时也把已到的增量送出去。

## S3：真实工具调用

```json
{"delta_count": 14, "responses": 2, "tool_calls": 1,
 "tool_names": ["read"], "tool_args": [{"file_path": "note.md"}]}
```

- 第一个 `model/response` 有 1 条 `read` 调用，参数是 `{"file_path": "note.md"}`。
- 工具执行后第二个 response 给出最终回答；两轮之间没有工具参数逐字帧。
- session `52543daa6ce14f3eace0781a203e1031`。

## S4：断线重连

真实端点跑了一次（`.tmp/h2-real/run_reconnect.py`，session `8623ef82bd0b46c7ba3e12f4b7976d2c`）：

```json
{"saw_delta": true, "status": "idle", "snapshot_last_seq": 8,
 "status_last_seq": 8, "snapshot_messages": 3,
 "model_responses": 1, "contains_delta_in_log": false}
```

- 看到第一个 delta 后主动断开 SSE；段继续跑到 `idle`。
- 带 `?snapshot=1` 重连，`last_seq` 与 `GET /sessions/{id}` 的 `last_seq` 都是 8。
- 最终 `model/response` 只有 1 条；日志没有 delta；snapshot 的 `messages` 是折叠后的 3 条。
- 丢掉的 delta 不补（重连后没有收到旧 delta）。

## 结论

S1/S2/S3/S4 真实端点通过。首帧在修复后为 0.406–0.734 s（单次样本），拼接相等，工具调用拼装正确，断线重连不补 delta、最终 response 唯一。
