# Proposal

## Why

M14 落成了 `/skill <name>`，但 DSH 把 user-invocable 技能直接作为命令暴露（`/<name>`）。少这一条，用户得记住「先 /skill 再名字」这层中转，壳之间的命令面也不齐。

## What Changes

- **直接技能命令**：每个发现的技能以其名字作为一条命令。chat 的 `/<name>` 与 `/skill <name>` 等价；host 的 `POST /sessions/{id}/commands {name:"<name>"}` 等价。内置命令同名时内置胜出。
- **命令清单**：`GET /commands` 列内置命令；带 `?session_id=<id>` 时追加该会话发现到的技能命令；chat 的 `/help` 列内置命令 + 当前会话的技能命令。
- **补两条端到端判据**：渐进式披露的实际效果（第一轮上下文没有正文、调完 `skill` 后正文才作为工具结果进来）；技能执行结果（模型按正文约束回答）——用 fixture 在 seam ⑥ 里判，不依赖真实端点。

## Capabilities

### Modified Capabilities

- `skills`：命令面加「每个技能一条命令」。
- `chat-repl`：`/<name>` 与 `/skill <name>` 等价，`/help` 列技能命令。

## Impact

- 代码：`commands.py`（技能命令的解析与目录）、`cli/main.py`（`/help` 与直接命令）、`cli/host.py`（`GET /commands?session_id=`、`POST` 直接技能名）。
- 测试：seam ②（解析）、seam ⑥（chat 与 host 的直接调用、披露效果、执行结果）。
