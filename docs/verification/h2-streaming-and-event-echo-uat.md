# H2 流式与事件回显 — UAT 场次与观察表

**状态**：等人跑（ADR-0025：这张表没填完，H2 不得归档、不得合入 `main`；tty / 浏览器场次 agent 不得代跑）。

**怎么算「办一件真事」**：不是跑判据，是用 `minihns host` 开一个会话，在浏览器里看着字一个一个出来；中途断开 SSE，再带 `snapshot=1` 接回来；最后用 `replay` 对一次。五场按顺序跑。

## 这次交付了什么

- **没有正式产品 UI**。H2 交付的是 `GET /sessions/{id}/events` 的 SSE 协议与宿主流式；UAT 用一个**最小 HTML 客户端**：[h2-uat.html](h2-uat.html)。它是验收工具，不是壳。
- **有事件回显**：HTML 下方的 `durable 事件回显` 逐行显示 `session/start`、`model/request`、`model/response`、`tool/call`、`tool/result`、`turn/end`、`segment/end` 等 durable 帧。
- **有流式正文**：`model/delta` 是 ephemeral 帧，显示在上方 `▍` 区域；它不落日志，重连不补。
- **有工具**：S3 让模型调 `read`；工具调用参数**不逐字流**，在最终 `model/response.tool_calls` 与 `tool/call` 帧里一次给出。H2 没有 reasoning token、工具参数逐字流、WebSocket。

## 跑之前（PowerShell，在仓库根）

```powershell
$env:MINIHNS_HOST_TOKEN = "h2-uat-" + ("x" * 32)
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')

New-Item -ItemType Directory -Force .tmp\h2-uat\ws | Out-Null
Set-Content .tmp\h2-uat\ws\note.md "alpha`nbeta" -Encoding UTF8

uv run minihns host --http --port 19410 `
  --workspace .tmp\h2-uat\ws `
  --session-dir .tmp\h2-uat\sessions `
  --provider deepseek
```

保持这个终端开着。另开一个终端打开客户端：

```powershell
Start-Process (Resolve-Path docs\verification\h2-uat.html)
```

在页面填：

- `Base URL`：`http://127.0.0.1:19410`
- `Host token`：上面 `MINIHNS_HOST_TOKEN` 的值（`h2-uat-...`）

点 **创建会话**；完成后才能发送。

## S1 首帧延迟

1. 在输入框发：`用大约 300 字介绍你自己，分点说。`
2. 看 `durable 事件回显` 里的 `[first delta] ... ms after send`，看上方 `▍` 是否先出现半句。

**预期**：`[first delta]` 小于 1000 ms；`▍` 在最终 `model/response` 到达前就出现；delta 帧不带 `id`。

## S2 delta 拼接等于最终 content

1. 等助手最终消息出现在 `messages` 区域。
2. 看事件回显最后一条 `model/response`，确认它的 `content` 与刚才 `▍` 累积的文字一致。
3. 在终端跑（把 `<id>` 换成页面上的 session id）：

```powershell
Select-String -Path .tmp\h2-uat\sessions\<id>.jsonl -Pattern 'model/delta'
```

**预期**：拼接结果等于最终 `content`；上面命令**没有输出**（日志里没有 `model/delta`）。

## S3 工具调用流式拼装

1. 发：`必须调用 read 工具读取 note.md，然后用一句话告诉我文件里的内容。`
2. 看事件回显里的 `tool/call` 与 `tool/result`，以及最终 `model/response.payload.tool_calls`。

**预期**：`tool_calls` 有一条 `read`，参数是 `{"file_path":"note.md"}`；`tool/call` 与 `tool/result` 各一条；工具参数没有逐字 delta 帧。

## S4 断线、snapshot 重连、不重复

1. 发：`用大约 300 字介绍你自己，分点说。`
2. 看到 `▍` 开始出字后，点 **断开 SSE**。
3. 等一两秒，点 **snapshot 重连**。
4. 等最终 `model/response`。

**预期**：重连第一帧是 `snapshot`；`last_seq` 是 durable 高水位；重连前的 delta 不补；最终回复只出现一次（以 durable `model/response` 为准）。

## S5 replay 与不流式逐点相等

这一场用 mock fixture，避免真实模型每次措辞不同。

1. 另开一个终端，准备 fixture：

```powershell
$fixture = ".tmp\h2-uat\turns.json"
@'
[{"content":"你好","deltas":["你","好"],"finish_reason":"stop"}]
'@ | Set-Content $fixture -Encoding UTF8
```

2. 用 mock 起第二个 host（端口 19411）：

```powershell
$env:MINIHNS_HOST_TOKEN = "h2-uat-" + ("y" * 32)
uv run minihns host --http --port 19411 `
  --workspace .tmp\h2-uat\ws `
  --session-dir .tmp\h2-uat\sessions-mock `
  --provider mock --fixture $fixture
```

3. 打开第二个 HTML 标签页，Base URL 填 `http://127.0.0.1:19411`，token 填上面的 `h2-uat-yyy...`；创建会话、**必须发送一条「任务」**，否则日志只有 `session/start`，replay 会报 `no_context_assembled`。记下 session id（host 流式那一份）。
4. 同一个 fixture 跑 CLI 非流式（另开终端）：

```powershell
uv run minihns run -p "任务" --provider mock --fixture $fixture `
  --workspace .tmp\h2-uat\ws `
  --session-dir .tmp\h2-uat\sessions-cli --yes
```

5. 对两份日志跑 replay：

```powershell
uv run minihns replay <host-session-id> --session-dir .tmp\h2-uat\sessions-mock
uv run minihns replay <cli-session-id> --session-dir .tmp\h2-uat\sessions-cli
```

> **别把两个 session-dir 串了**：`minihns run` stdout 打出的 id 只在 `sessions-cli`；第二个 host 页面上的 id 只在 `sessions-mock`。拿 CLI id 去 `sessions-mock` 找，就会得到 `SESSION_NOT_FOUND`（这是 2026-10-28 人跑时实际踩到的坑）。

**预期**：两次 replay 都退出码 0、没有 `REPLAY_MISMATCH`；两份 `model/response.content` 都是 `你好`。`session/start.entry` 会不同（`host` / `run`），这是入口事实，不是流式差异；逐点相等的自动判据是 `test_replay_is_equal_with_and_without_streaming`。

## 观察表

| 场次 | 动作 | 预期 | 实际观察（命令 / 日志 / 截图） | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | 长回复首帧 | <1 s / 无 id | | | |
| S2 | delta 拼接 | 等于最终 content | | | |
| S3 | 工具调用 | tool_calls 完整 | | | |
| S4 | 断线 + snapshot | 不补 delta / 最终只一次 | | | |
| S5 | replay 对比 | 退出码 0 / 逐条相等 | | | |

**至少一条「用起来别扭」**（没有就写「这一版意外地顺」）：_

**结论**：通过 / 不通过（不通过要写清哪一场、哪条预期没成立、日志 session id）：_
