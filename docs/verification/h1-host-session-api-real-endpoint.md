# H1 真实端点验收（`h1-host-session-api`，2026-10-27）

**端点**：DeepSeek 官方 `https://api.deepseek.com`，`provider=deepseek`、模型用预设 `deepseek-chat`。密钥只从环境变量 `DEEPSEEK_API_KEY` 注入子进程；本文不记录它的值。
**脚本**：`.tmp/h1_real.py`（一次性验收脚本，不进仓库）。它起真实 `minihns host --http` 子进程，用 HTTP 依次做：建会话 → 读+写（审批一次）→ 长任务中途取消 → `?snapshot=1` 重连。

## 跑法

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')
.venv\Scripts\python.exe .tmp\h1_real.py
```

宿主参数：`--http --port <free> --workspace <tmp>/workspace --session-dir <tmp>/sessions --provider deepseek`；token 由脚本随机生成，只走 `MINIHNS_HOST_TOKEN`。

## 观察

```text
SESSION a19bdf592f81438e9bc1f52e131a95e5
health={'protocol': 1, 'sessions': 0}
create=201
message1=202 {'segment_id': 's1', 'cursor': 0, 'queued': False}
approval(call_00_K7kRTZfwEuOKbaw3Dqrm7727)=200
approval(call_00_K7kRTZfwEuOKbaw3Dqrm7727)=404
approved=True
first_segment_idle=True
notes_after_write='TODO\nbeta\n'
message2=202 {'segment_id': 's2', 'cursor': 24, 'queued': False}
cancel=202 {'cancelled': True}
snapshot=last_seq=39 messages=12
EXIT 0
STDERR host 监听 http://127.0.0.1:5773
TYPES [... 'segment/end', 'segment/start', 'user/message', ..., 'tool/call', 'tool/result',
       'tool/call', 'tool/result', 'tool/call', 'tool/result', 'error/abort', 'turn/end',
       'segment/end', 'session/end']
```

完整记录类型序列（按日志顺序）：

```text
session/start, segment/start, user/message, turn/start, context/assembled, model/request,
model/response, tool/call, tool/result, turn/end, turn/start, context/assembled,
model/request, model/response, tool/call, approval/request, approval/response, tool/result,
turn/end, turn/start, context/assembled, model/request, model/response, turn/end,
segment/end, segment/start, user/message, turn/start, context/assembled, model/request,
model/response, tool/call, tool/result, tool/call, tool/result, tool/call, tool/result,
error/abort, turn/end, segment/end, session/end
```

日志在 `<tmp>/sessions/a19bdf592f81438e9bc1f52e131a95e5.jsonl`；脚本只打印路径，不保留在仓库。

## 逐条对照 H1 完成判据

| 判据 | 结果 |
|---|---|
| `minihns host --http` 起来 | `GET /health` 200，`{protocol: 1, sessions: 0}` |
| `POST /sessions` 写 `entry=host` | 201；日志第一条 `session/start`，`entry` 是 `host`、`prompt` 是空串 |
| 第一句开段 | 202，`queued=false`，段以 `MODEL_COMPLETED` 结束并回到 `idle` |
| 批准一次写 | 真实模型先 `read notes.md`、再 `write`；`approval/request` 后 `approval/response=APPROVED`，`tool/result=OK`，文件从 `alpha\nbeta\n` 变成 `TODO\nbeta\n` |
| 取消一次 | 第二句起 `s2`，模型连续三次 `bash` 后 `cancel` 202；`error/abort`、`turn/end(ABORTED)`、`segment/end(ABORTED)`，随后 `session/end` |
| `?snapshot=1` 重连 | 第一帧 `snapshot`，`last_seq=39`，折叠出 12 条 `messages` |
| 退出 | 收掉进程时退出码 0，日志以 `session/end` 收尾 |

**结论：通过。** 真实端点跑通了「读 → 写（审批）→ 取消 → snapshot 重连」这条链；没有出现 401/403/429/500，也没有在日志里找到密钥（脚本没打印密钥；日志里只有 `api_key_env` 的名字）。

## 别扭的地方

- 脚本的审批轮询没有去重，同一 `tool_call_id` 第二次 POST 得到 404（第一次已解决）——这是脚本的重复提交，不是宿主缺陷；`404` 对「已失效的审批」是 spec 要求的结果。
- 真实模型的工具选择比 fixture 慢且不固定：这次它先读再写，正好覆盖审批；但模型的输出正文没有断言，验收看的是记录形状与文件内容。
