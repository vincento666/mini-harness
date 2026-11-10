# Proposal

## Why

模型现在只在受保护头部看到「可用工具」，看不到「团队有哪些技能」。把技能正文全塞进头部会撑爆预算；让壳自己读文件又绕开内核、`replay` 也对不上。M14 做 DSH 的**渐进式披露**：启动只注入技能清单，正文按需用 `skill` 工具加载（结果落日志），并给 CLI 与 host 同一份命令面。

同时补上 `subagent-preset` 留的那一半：`[subagent.presets.<id>].persona` 进子会话的受保护头部，preset 才和 DSH 的 `agentPreset`（persona + toolFilter）同形。

## What Changes

- **技能发现（4 级根）**：`<workspace>/.minihns/skills/`（100）、`<workspace>/.agents/skills/`（200）、`$MINIHNS_HOME/skills/`（500，默认 `~/.mini-harness/skills/`）、内置 `src/mini_harness/skills/`（600）。同名技能高优先级（数字小）胜出；发现结果按 `(rank, path)` 排序。
- **清单注入**：`session/start.payload.skills` 只放 `{name, description, rank, path}`；受保护头部只放紧凑清单（名字 + 一句描述），超预算截断并留 marker；正文不进头部。
- **`skill` 工具**：`{name}` → 正文（上限 32 KiB，超了截断并提示用 `read`）；未知技能是 `TOOL_ARGS_INVALID`；正文作为 `tool/result` 落日志，`replay` 因此不依赖磁盘上的当前文件。
- **同一份命令面**：CLI `chat` 的 `/skills`、`/skill <name>`、`/help`；host 的 `GET /commands` 与 `POST /sessions/{id}/commands`。命令调用落 `command/invoked {name, arguments, ok}`；`/skill` 的正文另外写成一条 `user/message` 并开启一个段（`/skills` 不开启段）。
- **preset 的 persona**：`[subagent.presets.<id>].persona`（可选字符串）进子 `session/start.payload.preset_persona` 与受保护头部；preset 与 DSH 的 `agentPreset` 同形。

## Capabilities

### New Capabilities

- `skills`：四级发现、清单注入、`skill` 按需加载、同一份命令面与 `command/invoked`。

### Modified Capabilities

- `chat-repl`：`/skills`、`/skill`、`/help`。
- `host-api`：`GET /commands` 与 `POST /sessions/{id}/commands`。
- `event-log`：事件词表加 `command/invoked`。
- `subagent-delegation`：preset 的 `persona`。
- `config-layering`：`[subagent.presets.<id>].persona`。

## Impact

- 代码：新增 `skills/`（发现与读取）、`tools/skill.py`、`config`（persona 校验与编译）、`events/fold.py`（技能清单与 persona 头部）、`events/vocabulary.py`（`command/invoked`）、`cli/main.py`（chat 命令）、`cli/host.py` 与 `session/host.py`（命令路由与队列）。
- 测试：seam ②（`skill` 工具与 preset persona）、seam ④（技能清单与 persona 头部）、seam ⑥（CLI/host 命令面）、seam ⑦（子会话 persona）。
- 非目标：300/400 两级根、`run --skill`、外部连接器（MCP / hooks allowlist）、技能热重载、壳自己读技能文件。
