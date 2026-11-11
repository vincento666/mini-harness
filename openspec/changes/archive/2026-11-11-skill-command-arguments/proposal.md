# Proposal

## Why

`/<技能名>` 现在只打印正文，`/<技能名> 指令` 会报「用法」错误。用户真正要的是「用这个技能来做这件事」——命令 + 一句自然语言，技能正文与指令一起进上下文、开一个段。这也和 Claude Code / DSH 的 user-invocable 技能用法一致。

## What Changes

- **技能命令 + 指令**：`/<技能名> <指令>` 把技能正文（XML 三段）与指令拼成一条 `user/message`，开一个段；命令本身照落 `command/run` + `command/done`。不带指令的 `/<技能名>` 仍是「打印正文、不开段」。
- **host 同义**：`POST /sessions/{id}/commands {name:"<技能名>", arguments:"<指令>"}` 写同样的命令事件、投递同样的消息（空闲直接起段、忙时排队），返回 202 与 `{queued, segment_id, cursor}`。
- **抽一个渲染函数**：`skill_content(skill, instruction="")` 供 `skill` 工具与命令展开共用，避免两处 XML 漂移。

## Capabilities

### Modified Capabilities

- `skills`：技能命令 + 指令展开成消息（命令面从「不开段」变成「无指令不开段、有指令展开」）。
- `chat-repl`：`/<技能名> <指令>` 开段，消息含正文与指令。

## Impact

- 代码：`skills.py`（`skill_content`）、`tools/skill.py`（复用）、`commands.py`（`direct_skill`）、`cli/main.py`（命令返回展开文本）、`session/host.py`（`expand_skill_command`）、`cli/host.py`（202 分支）。
- 测试：seam ②（渲染）、seam ⑥（chat 展开、host 202 与排队）。
